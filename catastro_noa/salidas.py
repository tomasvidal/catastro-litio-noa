"""
Archivos que produce el pipeline, en data/processed/:

  catastro_noa.parquet            base unificada con geometria (GeoParquet, EPSG:4326)
  catastro_noa.csv                misma base sin geometria (para mirar diffs en git)
  revision_estandarizacion.xlsx   planilla para que el equipo revise la homologacion
"""

from __future__ import annotations

import geopandas as gpd
import pandas as pd
from openpyxl.styles import Font, PatternFill

from . import DATA_PROCESSED

_LEEME = [
    ("BASE", "Un registro por derecho minero, sin geometrías. En esta hoja y en MINERALES y ETAPAS, el color del "
             "encabezado indica si la columna es un dato tal como lo publica la provincia, si se construyó al "
             "homologar o si es información de control o un conteo."),
    ("MINERALES", "Cada texto de mineral distinto, cómo se clasificó y cuántos registros lo usan. "
                  "Arriba los que tienen algo sin clasificar: son los que conviene revisar."),
    ("ETAPAS", "Cada combinación provincia / trámite / estado y a qué etapa y estado homologado se asignó."),
    ("RESUMEN", "Conteos por etapa del proyecto, estado, categoría y grupo de minerales: "
                "una tabla por provincia, una al lado de la otra."),
]

# Colores de los encabezados de BASE, MINERALES y ETAPAS: qué viene de la fuente y qué se construyó.
_ORIGINALES = ["id_fuente", "expediente", "nombre", "titular", "tramite_original", "estado_original",
               "mineral_original", "departamento", "superficie_ha_fuente", "fecha_inicio",
               "fecha_actualizacion_fuente"]
_HOMOLOGADAS = ["titular_clave", "titulares_claves", "n_titulares","etapa_administrativa", "etapa_proyecto", "estado", "minerales",
                "grupos_minerales", "categoria_codigo", "tiene_litio", "mineral_sin_clasificar",
                "superficie_ha_calculada", "anio_expediente"]
_COLOR_ORIGINAL, _COLOR_HOMOLOGADA, _COLOR_CONTROL = "2F75B5", "548235", "A6A6A6"
_LEYENDA = [
    (_COLOR_ORIGINAL, "Azul", "Dato tal como lo publica la provincia (solo se limpiaron espacios y saltos de línea)."),
    (_COLOR_HOMOLOGADA, "Verde", "Columna construida al homologar: es la que queda en la base y la que conviene verificar "
                                 "contra su columna azul."),
    (_COLOR_CONTROL, "Gris", "Información de control o conteo: provincia, fecha de descarga, cantidad de registros y la marca de revisar."),
]


def _pintar_encabezados(ws) -> None:
    """Colorea el encabezado de cada columna según su origen."""
    for c in ws[1]:
        color = (_COLOR_ORIGINAL if c.value in _ORIGINALES
                 else _COLOR_HOMOLOGADA if c.value in _HOMOLOGADAS else _COLOR_CONTROL)
        c.fill = PatternFill("solid", fgColor=color)
        c.font = Font(bold=True, color="FFFFFF")


def _escribir_leyenda(ws, fila: int) -> None:
    ws.cell(row=fila, column=1, value="Colores de los encabezados").font = Font(bold=True)
    for i, (color, nombre, texto) in enumerate(_LEYENDA, start=1):
        a = ws.cell(row=fila + i, column=1, value=nombre)
        a.fill = PatternFill("solid", fgColor=color)
        a.font = Font(bold=True, color="FFFFFF")
        ws.cell(row=fila + i, column=2, value=texto)


def _tabla_minerales(base: pd.DataFrame) -> pd.DataFrame:
    cols = ["provincia", "mineral_original", "minerales", "grupos_minerales",
            "categoria_codigo", "mineral_sin_clasificar"]
    t = (base[cols].fillna("").groupby(cols).size().rename("registros").reset_index())
    t["revisar"] = t["mineral_sin_clasificar"].ne("")
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


def _escribir_resumen(xw: pd.ExcelWriter, resumen: pd.DataFrame) -> None:
    """Una tabla por provincia, una al lado de la otra, en la misma hoja."""
    col = 0
    for prov, t in resumen.groupby("provincia", sort=True):
        t = t.drop(columns="provincia")
        t.to_excel(xw, sheet_name="RESUMEN", index=False, startrow=1, startcol=col)
        xw.sheets["RESUMEN"].cell(row=1, column=col + 1, value=prov).font = Font(bold=True)
        col += len(t.columns) + 1


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
        pd.DataFrame(_LEEME, columns=["hoja", "descripción"]).to_excel(xw, sheet_name="LEER", index=False)
        tabla.drop(columns="fuente").to_excel(xw, sheet_name="BASE", index=False)
        _tabla_minerales(tabla).to_excel(xw, sheet_name="MINERALES", index=False)
        _tabla_etapas(tabla).to_excel(xw, sheet_name="ETAPAS", index=False)
        _escribir_resumen(xw, _tabla_resumen(tabla))
        for hoja in xw.sheets.values():
            _autoajustar(hoja)
        xw.sheets["RESUMEN"].freeze_panes = "A3"
        for hoja in ("BASE", "MINERALES", "ETAPAS"):
            _pintar_encabezados(xw.sheets[hoja])
        _escribir_leyenda(xw.sheets["LEER"], len(_LEEME) + 3)
        xw.sheets["LEER"].column_dimensions["B"].width = 132  # descripciones en una sola línea
        xw.sheets["MINERALES"].column_dimensions["H"].width = 12
    return {k: str(v) for k, v in rutas.items()}
