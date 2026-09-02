"""
Fase 1 - verificar que se pueden obtener los catastros mineros de las 3 provincias.

Uso:
    uv run python scripts/explorar_fuentes.py [--n 50]

Que hace:
  - Jujuy    : descarga directa del SHP del Juzgado Administrativo de Minas.
  - Salta    : WFS del GeoServer de geoportal.salta.gob.ar (capa "Catastro Minero").
  - Catamarca: WFS del GeoServer de nodoide.catamarca.gob.ar (capa idecat:MINAS_*),
               que esta detras de Cloudflare -> se usa cloudscraper.

Para cada provincia imprime el total de registros y las primeras filas, y guarda
una muestra en data/samples/<provincia>.csv (sin geometria, sin datos de contacto).
"""

from __future__ import annotations

import argparse
import io
import re
import unicodedata
import zipfile
from pathlib import Path

import cloudscraper
import geopandas as gpd
import httpx
import pandas as pd

SAMPLES_DIR = Path(__file__).resolve().parents[1] / "data" / "samples"
RAW_DIR = Path(__file__).resolve().parents[1] / "data" / "raw"

# Columnas comunes de la muestra (solo para verificar; NO es el modelo final).
COLS = ["provincia", "expediente", "nombre", "titular", "mineral", "tipo",
        "estado", "departamento", "superficie_ha", "fuente"]

FUENTES = {
    "jujuy": "mineriajujuy.gob.ar/site/jam_catastro.php (descarga SHP)",
    "salta": "geoportal.salta.gob.ar/geoserver/wfs :: geonode:poligonos_adaf55f39328ff45c8c60e94eb13a7a0",
    "catamarca": "nodoide.catamarca.gob.ar/geoserver/wfs :: idecat:MINAS_19022026",
}


def _num(x) -> float | None:
    """'11,5395 ha' -> 11.5395 ; 4978.6 -> 4978.6 ; None -> None"""
    if x is None or (isinstance(x, float) and pd.isna(x)):
        return None
    s = re.sub(r"[^\d,.\-]", "", str(x)).replace(".", "").replace(",", ".") if "," in str(x) else \
        re.sub(r"[^\d.\-]", "", str(x))
    try:
        return round(float(s), 4) if s not in ("", "-", ".") else None
    except ValueError:
        return None


# --------------------------------------------------------------------------- Jujuy
def get_jujuy(n: int) -> tuple[int, pd.DataFrame]:
    c = httpx.Client(verify=False, timeout=120, follow_redirects=True,
                     headers={"User-Agent": "Mozilla/5.0"})
    landing = "https://www.mineriajujuy.gob.ar/site/jam_catastro.php"
    href = re.search(r"download_catastrominero\.php\?d=[0-9a-f]+&t=shp", c.get(landing).text)
    if not href:
        raise RuntimeError("no se encontro el link de descarga del SHP en la landing de Jujuy")
    url = "https://www.mineriajujuy.gob.ar/site/" + href.group(0)
    blob = c.get(url).content
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    (RAW_DIR / "jujuy_catastro_minero.zip").write_bytes(blob)

    zf = zipfile.ZipFile(io.BytesIO(blob))
    shp = next(x for x in zf.namelist() if x.upper().endswith("CATASTRO_MINERO.SHP"))
    gdf = gpd.read_file(f"zip://{RAW_DIR / 'jujuy_catastro_minero.zip'}!{shp}")

    total = len(gdf)
    d = gdf.drop(columns="geometry").head(n).copy()
    out = pd.DataFrame({
        "provincia": "jujuy",
        "expediente": d["expediente"],
        "nombre": d["nombre"],
        "titular": d["titular_ac"],          # razon social del titular (dato publico)
        "mineral": d["tipo_miner"],
        "tipo": d["rg_tipo"],
        "estado": d["estado"],
        "departamento": d["depto"],
        "superficie_ha": d["superficie"].map(_num),
        "fuente": "shp",
    })
    return total, out[COLS]


# ----------------------------------------------------------------- Salta / Catamarca (WFS)
def _wfs_hits(session, base: str, typename: str) -> int:
    r = session.get(base, params={"service": "WFS", "version": "2.0.0", "request": "GetFeature",
                                  "typeNames": typename, "resultType": "hits"}, timeout=90)
    m = re.search(r'numberMatched="(\d+)"', r.text)
    return int(m.group(1)) if m else -1


def _wfs_sample(session, base: str, typename: str, n: int) -> gpd.GeoDataFrame:
    r = session.get(base, params={"service": "WFS", "version": "2.0.0", "request": "GetFeature",
                                  "typeNames": typename, "count": str(n),
                                  "outputFormat": "application/json", "srsName": "EPSG:4326"},
                    timeout=120)
    r.raise_for_status()
    return gpd.read_file(io.BytesIO(r.content))


def get_salta(n: int) -> tuple[int, pd.DataFrame]:
    base = "https://geoportal.salta.gob.ar/geoserver/wfs"
    tn = "geonode:poligonos_adaf55f39328ff45c8c60e94eb13a7a0"
    s = httpx.Client(verify=False, follow_redirects=True, headers={"User-Agent": "Mozilla/5.0"})
    total = _wfs_hits(s, base, tn)
    g = _wfs_sample(s, base, tn, n).drop(columns="geometry")
    out = pd.DataFrame({
        "provincia": "salta",
        "expediente": g["expediente"],
        "nombre": g["nombre"],
        "titular": g["concesionario"],
        "mineral": g["mineral"],
        "tipo": g["tipo"],
        "estado": g["estado"],
        "departamento": g["departamento"],
        "superficie_ha": g["area"].map(_num),
        "fuente": "wfs",
    })
    return total, out[COLS]


def get_catamarca(n: int) -> tuple[int, pd.DataFrame]:
    base = "https://nodoide.catamarca.gob.ar/geoserver/wfs"
    tn = "idecat:MINAS_19022026"
    s = cloudscraper.create_scraper(browser={"browser": "chrome", "platform": "windows", "desktop": True})
    total = _wfs_hits(s, base, tn)
    g = _wfs_sample(s, base, tn, n).drop(columns="geometry")
    out = pd.DataFrame({
        "provincia": "catamarca",
        "expediente": g.get("exptedgtl", g.get("expediente")),
        "nombre": g.get("mina"),
        "titular": g.get("concsrio"),
        "mineral": g.get("mineral"),
        "tipo": None,
        "estado": g.get("estado"),
        "departamento": g.get("dpto"),
        "superficie_ha": None,     # esta capa no publica superficie
        "fuente": "wfs",
    })
    return total, out[COLS]


# --------------------------------------------------------------------------- main
def _clean(df: pd.DataFrame) -> pd.DataFrame:
    def norm(v):
        return unicodedata.normalize("NFC", v).strip() if isinstance(v, str) else v
    for col in df.columns:
        if col != "superficie_ha":
            df[col] = df[col].map(norm)
    return df


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=50, help="filas por provincia en la muestra")
    n = ap.parse_args().n

    SAMPLES_DIR.mkdir(parents=True, exist_ok=True)
    getters = {"jujuy": get_jujuy, "salta": get_salta, "catamarca": get_catamarca}

    print(f"\nMuestra de {n} filas por provincia\n" + "=" * 60)
    for prov, fn in getters.items():
        try:
            total, df = fn(n)
        except Exception as e:  # noqa: BLE001
            print(f"\n### {prov.upper()}  -> ERROR: {e!r}")
            continue
        df = _clean(df)
        path = SAMPLES_DIR / f"{prov}.csv"
        df.to_csv(path, index=False, encoding="utf-8")
        print(f"\n### {prov.upper()}   registros totales en la fuente: {total}")
        print(f"    fuente: {FUENTES[prov]}")
        print(f"    muestra -> {path.relative_to(path.parents[2])}  ({len(df)} filas)")
        with pd.option_context("display.max_columns", None, "display.width", 200,
                               "display.max_colwidth", 26):
            print(df[["expediente", "nombre", "titular", "mineral", "estado",
                      "departamento", "superficie_ha"]].head(8).to_string(index=False))

    print("\n" + "=" * 60)
    print("OK: se obtuvieron datos de las 3 provincias. CSV en data/samples/")


if __name__ == "__main__":
    main()
