"""
Arma un Excel de relevamiento con una muestra de 100 filas por provincia y dos
hojas auxiliares (MINERALES, TITULAR) para el trabajo de homologacion de la
proxima etapa.

Uso:
    uv run python scripts/armar_relevamiento.py

Jujuy y Salta se piden igual que en explorar_fuentes.py (SHP directo / WFS).

Catamarca: la capa WFS "idecat:MINAS_<fecha>" que usaba explorar_fuentes.py
dejo de estar publicada (el nombre de la capa lleva la fecha de la ultima
actualizacion y el organismo la rota sin aviso, sin mantener un alias fijo).
Como alternativa se usa el export estatico (qgis2web) que publica el mismo
organismo para su visor de mineria en
https://nodoide.catamarca.gob.ar/mineria_visor/ , que trae los mismos campos
(DPTO, MINA, EXPEDIENTE, CONCSRIO, MINERAL). No publica estado ni superficie.
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

import cloudscraper
import pandas as pd

from explorar_fuentes import COLS, _clean, get_jujuy, get_salta

OUT = Path(__file__).resolve().parents[1] / "data" / "samples" / "catastro_relevamiento.xlsx"
CATAMARCA_VISOR = "https://nodoide.catamarca.gob.ar/mineria_visor/data/MINAS_5.js"


def get_catamarca_visor(n: int) -> tuple[int, pd.DataFrame]:
    s = cloudscraper.create_scraper(browser={"browser": "chrome", "platform": "windows", "desktop": True})
    r = s.get(CATAMARCA_VISOR, timeout=120)
    r.raise_for_status()
    txt = r.text.split("=", 1)[1].strip().rstrip(";")
    data = json.loads(txt)
    props = [f["properties"] for f in data["features"]]
    total = len(props)
    d = pd.DataFrame(props[:n])
    out = pd.DataFrame({
        "provincia": "catamarca",
        "expediente": d["EXPEDIENTE"].fillna(d.get("EXPTE DGTL")),
        "nombre": d["MINA"],
        "titular": d["CONCSRIO"],
        "mineral": d["MINERAL"],
        "tipo": None,
        "estado": None,
        "departamento": d["DPTO"],
        "superficie_ha": None,
        "fuente": "visor estatico qgis2web (WFS idecat:MINAS_* dado de baja)",
    })
    return total, out[COLS]


def _valores(series_list: list[pd.Series]) -> list[str]:
    vals: list[str] = []
    for s in series_list:
        vals.extend(v.strip() for v in s.dropna().astype(str) if v.strip() not in ("", "-"))
    return vals


def _autoajustar(ws) -> None:
    ws.freeze_panes = "A2"
    for col in ws.columns:
        largo = max(len(str(c.value)) if c.value is not None else 0 for c in col)
        ws.column_dimensions[col[0].column_letter].width = min(largo + 2, 60)


def main() -> None:
    n = 100
    jujuy_total, jujuy = get_jujuy(n)
    salta_total, salta = get_salta(n)
    cat_total, catamarca = get_catamarca_visor(n)

    for df in (jujuy, salta, catamarca):
        _clean(df)

    minerales = sorted(set(_valores([jujuy["mineral"], salta["mineral"], catamarca["mineral"]])))
    df_minerales = pd.DataFrame({"mineral": minerales, "grupo_normalizado": ""})

    conteo = Counter(_valores([jujuy["titular"], salta["titular"], catamarca["titular"]]))
    df_titular = pd.DataFrame(
        sorted(conteo.items(), key=lambda kv: (-kv[1], kv[0])),
        columns=["titular", "apariciones"],
    )

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(OUT, engine="openpyxl") as xw:
        jujuy.to_excel(xw, sheet_name="JUJUY", index=False)
        salta.to_excel(xw, sheet_name="SALTA", index=False)
        catamarca.to_excel(xw, sheet_name="CATAMARCA", index=False)
        df_minerales.to_excel(xw, sheet_name="MINERALES", index=False)
        df_titular.to_excel(xw, sheet_name="TITULAR", index=False)
        for hoja in xw.sheets.values():
            _autoajustar(hoja)

    print(f"Jujuy:     {jujuy_total} en la fuente -> {len(jujuy)} en la muestra")
    print(f"Salta:     {salta_total} en la fuente -> {len(salta)} en la muestra")
    print(f"Catamarca: {cat_total} en la fuente (visor estatico) -> {len(catamarca)} en la muestra")
    print(f"Minerales unicos (tal como figuran): {len(df_minerales)}")
    print(f"Titulares unicos: {len(df_titular)}")
    print(f"-> {OUT}")


if __name__ == "__main__":
    main()
