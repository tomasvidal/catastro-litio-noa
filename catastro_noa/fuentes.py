"""
Descarga de los catastros completos (con geometria) de cada provincia.

Cada descarga se guarda tal cual en data/raw/<provincia>/<provincia>_<AAAAMMDD>.<ext>
(ignorado por git). Si una fuente no responde, se usa el ultimo archivo crudo
disponible, para que una caida de un geoportal no frene al resto del pipeline.
Tambien se puede dejar a mano un archivo en esa carpeta (ej. una descarga manual).

  - Jujuy    : shapefile de mineriajujuy.gob.ar (link con token, se saca de la landing).
  - Salta    : WFS de geoportal.salta.gob.ar. La capa se busca por su titulo ("Catastro
               Minero") en el GetCapabilities, porque el nombre es un codigo que cambia si la
               vuelven a publicar; si no se encuentra, se prueba con el ultimo nombre conocido.
  - Catamarca: WFS de nodoide.catamarca.gob.ar. El nombre de la capa lleva la fecha
               de actualizacion (idecat:MINAS_<DDMMAAAA>) y cambia sin aviso, asi que
               se busca la mas reciente en el GetCapabilities. Si no hay capa (o el
               WFS rechaza el pedido), se usa el export estatico del visor de mineria
               (mismos campos, sin estado ni superficie).
"""

from __future__ import annotations

import datetime as dt
import io
import json
import re
import zipfile
from dataclasses import dataclass
from pathlib import Path

import geopandas as gpd
import httpx

from . import DATA_RAW

UA = {"User-Agent": "Mozilla/5.0 (catastro-litio-noa; UNSAM)"}

JUJUY_LANDING = "https://www.mineriajujuy.gob.ar/site/jam_catastro.php"
SALTA_WFS = "https://geoportal.salta.gob.ar/geoserver/wfs"
SALTA_TITULO = "Catastro Minero"
SALTA_CAPA = "geonode:poligonos_adaf55f39328ff45c8c60e94eb13a7a0"  # ultimo nombre conocido (10/2026)
CATAMARCA_WFS = "https://nodoide.catamarca.gob.ar/geoserver/wfs"
CATAMARCA_VISOR = "https://nodoide.catamarca.gob.ar/mineria_visor/data/MINAS_5.js"


@dataclass
class Crudo:
    provincia: str
    gdf: gpd.GeoDataFrame
    archivo: Path
    fuente: str          # descripcion corta del origen (url / capa)
    fecha: dt.date       # fecha de la descarga (o del archivo crudo reutilizado)
    reutilizado: bool    # True si no se pudo descargar y se uso un crudo anterior


def _wfs_params(capa: str) -> dict:
    return {"service": "WFS", "version": "2.0.0", "request": "GetFeature", "typeNames": capa,
            "outputFormat": "application/json", "srsName": "EPSG:4326"}


def _guardar(provincia: str, contenido: bytes, ext: str, hoy: dt.date) -> Path:
    carpeta = DATA_RAW / provincia
    carpeta.mkdir(parents=True, exist_ok=True)
    ruta = carpeta / f"{provincia}_{hoy:%Y%m%d}.{ext}"
    ruta.write_bytes(contenido)
    return ruta


# --------------------------------------------------------------------------- descargas
def _bajar_jujuy(hoy: dt.date) -> tuple[Path, str]:
    with httpx.Client(verify=False, timeout=180, follow_redirects=True, headers=UA) as c:
        m = re.search(r"download_catastrominero\.php\?d=[0-9a-f]+&(?:amp;)?t=shp", c.get(JUJUY_LANDING).text)
        if not m:
            raise RuntimeError("no se encontro el link de descarga del SHP en la landing de Jujuy")
        blob = c.get("https://www.mineriajujuy.gob.ar/site/" + m.group(0).replace("&amp;", "&")).content
    zipfile.ZipFile(io.BytesIO(blob))  # valida que sea un zip
    return _guardar("jujuy", blob, "zip", hoy), "mineriajujuy.gob.ar (SHP CATASTRO_MINERO)"


def capa_por_titulo(capabilities: str, titulo: str) -> str | None:
    """Nombre de la capa cuyo titulo es `titulo` (sin distinguir mayusculas), en un GetCapabilities."""
    for ft in re.findall(r"<(?:wfs:)?FeatureType\b.*?</(?:wfs:)?FeatureType>", capabilities, re.S):
        nombre = re.search(r"<(?:wfs:)?Name>([^<]+)</", ft)
        t = re.search(r"<(?:wfs:)?Title>([^<]*)</", ft)
        if nombre and t and t.group(1).strip().casefold() == titulo.casefold():
            return nombre.group(1).strip()
    return None


def _capa_salta(c: httpx.Client) -> str:
    try:
        r = c.get(SALTA_WFS, params={"service": "WFS", "version": "2.0.0", "request": "GetCapabilities"})
        r.raise_for_status()
        return capa_por_titulo(r.text, SALTA_TITULO) or SALTA_CAPA
    except httpx.HTTPError:
        return SALTA_CAPA


def _bajar_salta(hoy: dt.date) -> tuple[Path, str]:
    with httpx.Client(verify=False, timeout=300, follow_redirects=True, headers=UA) as c:
        capa = _capa_salta(c)
        r = c.get(SALTA_WFS, params=_wfs_params(capa))
        r.raise_for_status()
    json.loads(r.content)  # valida que sea JSON (GeoServer devuelve XML ante errores)
    return _guardar("salta", r.content, "geojson", hoy), f"geoportal.salta.gob.ar WFS {capa}"


def _capa_catamarca(c: httpx.Client) -> str | None:
    try:
        r = c.get(CATAMARCA_WFS, params={"service": "WFS", "version": "2.0.0",
                                         "request": "GetCapabilities"}, timeout=120)
        r.raise_for_status()
    except httpx.HTTPError:  # el WFS a veces rechaza pedidos automaticos: se usa el visor
        return None
    capas = set(re.findall(r"idecat:MINAS_(\d{8})", r.text))
    if not capas:
        return None
    ultima = max(capas, key=lambda f: dt.datetime.strptime(f, "%d%m%Y"))
    return f"idecat:MINAS_{ultima}"


def _bajar_catamarca(hoy: dt.date) -> tuple[Path, str]:
    with httpx.Client(timeout=300, follow_redirects=True, headers=UA) as c:
        capa = _capa_catamarca(c)
        if capa:
            r = c.get(CATAMARCA_WFS, params=_wfs_params(capa))
            r.raise_for_status()
            json.loads(r.content)
            return _guardar("catamarca", r.content, "geojson", hoy), f"nodoide.catamarca.gob.ar WFS {capa}"
        r = c.get(CATAMARCA_VISOR)
        r.raise_for_status()
    return _guardar("catamarca", r.content, "js", hoy), "nodoide.catamarca.gob.ar visor de mineria (qgis2web)"


_DESCARGAS = {"jujuy": _bajar_jujuy, "salta": _bajar_salta, "catamarca": _bajar_catamarca}


# --------------------------------------------------------------------------- lectura
def leer_crudo(ruta: Path) -> gpd.GeoDataFrame:
    """Lee un archivo crudo de cualquiera de los formatos que se guardan."""
    ext = ruta.suffix.lower()
    if ext == ".zip":
        with zipfile.ZipFile(ruta) as zf:
            shp = next(x for x in zf.namelist() if x.upper().endswith("CATASTRO_MINERO.SHP"))
        return gpd.read_file(f"zip://{ruta}!{shp}")
    if ext == ".js":  # export qgis2web: 'var json_MINAS_5 = {...};'
        txt = ruta.read_text(encoding="utf-8").split("=", 1)[1].strip().rstrip(";")
        return gpd.read_file(io.StringIO(txt)).set_crs("EPSG:4326", allow_override=True)
    return gpd.read_file(ruta)


def ultimo_crudo(provincia: str) -> Path | None:
    carpeta = DATA_RAW / provincia
    archivos = sorted(p for p in carpeta.glob(f"{provincia}_*.*") if p.suffix in (".zip", ".geojson", ".js", ".gpkg"))
    return archivos[-1] if archivos else None


def _fecha_de(ruta: Path) -> dt.date:
    m = re.search(r"_(\d{8})\.", ruta.name)
    return dt.datetime.strptime(m.group(1), "%Y%m%d").date() if m else \
        dt.date.fromtimestamp(ruta.stat().st_mtime)


def obtener(provincia: str, offline: bool = False) -> Crudo:
    """Descarga el catastro de una provincia; si falla, usa el ultimo crudo guardado."""
    hoy = dt.date.today()
    error: Exception | None = None
    if not offline:
        try:
            ruta, fuente = _DESCARGAS[provincia](hoy)
            return Crudo(provincia, leer_crudo(ruta), ruta, fuente, hoy, reutilizado=False)
        except Exception as e:  # noqa: BLE001 - cualquier falla de red/servidor
            error = e
    ruta = ultimo_crudo(provincia)
    if ruta is None:
        motivo = f"la descarga falló ({type(error).__name__}: {error})" if error else "modo offline"
        raise RuntimeError(f"{motivo} y no hay archivos crudos guardados")
    return Crudo(provincia, leer_crudo(ruta), ruta, f"archivo crudo {ruta.name}", _fecha_de(ruta),
                 reutilizado=True)
