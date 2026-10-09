"""
Archivos que produce el pipeline, en data/processed/:

  catastro_noa.parquet            base unificada con geometria (GeoParquet, EPSG:4326)
  catastro_noa.csv                misma base sin geometria (para mirar diffs en git)
  revision_estandarizacion.xlsx   planilla para que el equipo revise la homologacion
"""

from __future__ import annotations

import geopandas as gpd
import pandas as pd

from . import DATA_PROCESSED

_LEEME = [
    ("Qué es", "Base unificada de los catastros mineros de Jujuy, Salta y Catamarca, "
               "estandarizada con los criterios acordados con el equipo."),
    ("BASE", "Un registro por derecho minero, sin geometría. Diccionario de columnas: "
             "docs/diccionario_de_datos.md en el repositorio."),
    ("MINERALES", "Cada texto de mineral distinto, cómo se clasificó y cuántos registros lo usan. "
                  "Arriba los que tienen algo sin clasificar: son los que conviene revisar."),
    ("ETAPAS", "Cada combinación provincia / trámite / estado y a qué etapa y estado homologado se asignó."),
    ("RESUMEN", "Conteos por provincia, etapa del proyecto y grupo de minerales."),
    ("Cómo corregir", "Las reglas están en la carpeta diccionarios/ del repositorio (minerales.csv, "
                      "etapas.csv, estados.csv). La columna 'origen' indica si la regla viene de las "
                      "planillas del equipo ('investigadores') o es una propuesta a validar ('propuesta')."),
]


def _tabla_minerales(base: pd.DataFrame) -> pd.DataFrame:
    cols = ["provincia", "mineral_original", "minerales", "grupos_minerales",
            "categoria_codigo", "mineral_sin_clasificar"]
    t = (base[cols].fillna("").groupby(cols).size().rename("registros").reset_index())
    t["revisar"] = t["mineral_sin_clasificar"].ne("") | (t["minerales"].eq("") & t["categoria_codigo"].eq("")
                                                          & t["mineral_original"].ne(""))
    return t.sort_values(["revisar", "registros"], ascending=[False, False])


def _tabla_etapas(base: pd.DataFrame) -> pd.DataFrame:
    cols = ["provincia", "tramite_original", "estado_original", "etapa_administrativa",
            "etapa_proyecto", "estado"]
    return (base[cols].fillna("").groupby(cols).size().rename("registros").reset_index()
            .sort_values(["provincia", "registros"], ascending=[True, False]))


def _tabla_resumen(base: pd.DataFrame) -> pd.DataFrame:
    partes = []
    total = base.groupby("provincia").size().rename("registros").reset_index()
    total.insert(1, "dimension", "total")
    total.insert(2, "valor", "")
    partes.append(total)
    for dim in ("etapa_proyecto", "estado", "categoria_codigo"):
        t = base.fillna({dim: "(sin dato)"}).groupby(["provincia", dim]).size().rename("registros").reset_index()
        partes.append(t.rename(columns={dim: "valor"}).assign(dimension=dim))
    g = base.assign(grupo=base["grupos_minerales"].str.split("; ")).explode("grupo")
    g = g.fillna({"grupo": "(sin grupo)"}).groupby(["provincia", "grupo"]).size().rename("registros").reset_index()
    partes.append(g.rename(columns={"grupo": "valor"}).assign(dimension="grupo_mineral"))
    litio = base.groupby("provincia")["tiene_litio"].sum().rename("registros").reset_index()
    partes.append(litio.assign(dimension="tiene_litio", valor="sí"))
    return pd.concat(partes)[["provincia", "dimension", "valor", "registros"]]


def _autoajustar(ws) -> None:
    ws.freeze_panes = "A2"
    for col in ws.columns:
        largo = max(len(str(c.value)) if c.value is not None else 0 for c in col)
        ws.column_dimensions[col[0].column_letter].width = min(largo + 2, 60)


def escribir(base: gpd.GeoDataFrame) -> dict[str, str]:
    DATA_PROCESSED.mkdir(parents=True, exist_ok=True)
    rutas = {
        "parquet": DATA_PROCESSED / "catastro_noa.parquet",
        "csv": DATA_PROCESSED / "catastro_noa.csv",
        "xlsx": DATA_PROCESSED / "revision_estandarizacion.xlsx",
    }
    base = base.sort_values(["provincia", "expediente", "nombre", "id_fuente"], na_position="last")
    base = base.reset_index(drop=True)
    base.to_parquet(rutas["parquet"], index=False)

    tabla = pd.DataFrame(base.drop(columns="geometry"))
    tabla.to_csv(rutas["csv"], index=False, encoding="utf-8")

    with pd.ExcelWriter(rutas["xlsx"], engine="openpyxl") as xw:
        pd.DataFrame(_LEEME, columns=["hoja", "descripción"]).to_excel(xw, sheet_name="LEEME", index=False)
        tabla.to_excel(xw, sheet_name="BASE", index=False)
        _tabla_minerales(tabla).to_excel(xw, sheet_name="MINERALES", index=False)
        _tabla_etapas(tabla).to_excel(xw, sheet_name="ETAPAS", index=False)
        _tabla_resumen(tabla).to_excel(xw, sheet_name="RESUMEN", index=False)
        for hoja in xw.sheets.values():
            _autoajustar(hoja)
    return {k: str(v) for k, v in rutas.items()}
