"""
Planilla para clasificar a los titulares de derechos mineros (tipo de actor, origen
del capital y grupo economico). Una fila por titular, ordenada por superficie, con
columnas vacias para completar y listas desplegables con los valores permitidos.

Un derecho con varios titulares cuenta para cada uno (columna titulares_claves).

    uv run python scripts/armar_planilla_titulares.py
    -> data/processed/clasificacion_titulares_<fecha>.xlsx
"""

import sys
from datetime import date
from pathlib import Path

import pandas as pd
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from catastro_noa import DATA_PROCESSED, DATA_SNAPSHOT  # noqa: E402

TIPOS_ACTOR = ["Empresa privada", "Empresa estatal o provincial", "Persona física", "Cooperativa",
               "Otro", "Sin dato"]
ORIGENES = ["Argentina", "Australia", "Canadá", "China", "Corea del Sur", "Estados Unidos", "Francia",
            "Japón", "Reino Unido", "Suiza", "Mixto (varios países)", "Otro", "Sin dato"]
UMBRAL_PRIORIDAD = 0.8  # titulares que juntan el 80 % de la superficie (total o con litio)

_COLOR_DATO, _COLOR_COMPLETAR = "2F75B5", "BF8F00"
_A_COMPLETAR = {  # columna -> ancho
    "tipo_actor": 22, "origen_capital": 20, "grupo_economico": 28, "fuente": 40, "observaciones": 40,
}
_LEER = [
    ("Qué es", "Una fila por titular de derechos mineros de Jujuy y Salta, con datos de la base unificada. "
               "Las columnas con encabezado azul son datos de la base; las de encabezado ocre están vacías "
               "para completar."),
    ("Orden", "De mayor a menor superficie. La columna prioridad marca con 'Alta' a los titulares que, "
              "sumados, concentran el 80 % de la superficie total o el 80 % de la superficie con litio: "
              "con esos alcanza para un primer análisis."),
    ("Varios titulares", "Si un derecho tiene varios titulares, cuenta para cada uno de ellos."),
    ("titular", "Nombre normalizado (mayúsculas, sin acentos ni puntuación). Es la clave para cruzar "
                "esta planilla con la base: no modificarla."),
    ("nombre_en_la_fuente", "Cómo aparece escrito en el catastro provincial (la forma más frecuente). "
                            "Si comparte derechos con otros, puede aparecer junto a ellos."),
    ("tipo_actor", "Elegir de la lista: " + ", ".join(TIPOS_ACTOR) + "."),
    ("origen_capital", "País de origen del capital que controla al titular (casa matriz o accionista "
                       "principal). Elegir de la lista; si no está el país, 'Otro' y aclararlo en observaciones."),
    ("grupo_economico", "Grupo o casa matriz a la que pertenece, si corresponde (texto libre). Usar "
                        "siempre el mismo nombre para el mismo grupo, para poder agruparlos después."),
    ("fuente", "De dónde sale el dato (link a la web de la empresa, informe, registro, nota periodística)."),
    ("observaciones", "Cualquier aclaración: dudas, cambios de control recientes, etc."),
]


def tabla_titulares(base: pd.DataFrame) -> pd.DataFrame:
    b = base.assign(
        titular=base["titulares_claves"].str.split("|"),
        superficie_ha=pd.to_numeric(base["superficie_ha_calculada"], errors="coerce"),
        con_litio=base["tiene_litio"].eq("True"),
    ).explode("titular", ignore_index=True)
    b = b[b["titular"].fillna("") != ""]
    b["sup_litio"] = b["superficie_ha"].where(b["con_litio"], 0)
    g = b.groupby("titular")
    t = pd.DataFrame({
        "nombre_en_la_fuente": g["titular_original"].agg(lambda s: s.mode().iat[0]),
        "provincias": g["provincia"].agg(lambda s: ", ".join(sorted(s.str.title().unique()))),
        "derechos": g.size(),
        "derechos_con_litio": g["con_litio"].sum(),
        "superficie_ha": g["superficie_ha"].sum().round(0),
        "superficie_con_litio_ha": g["sup_litio"].sum().round(0),
    })
    etapas = pd.crosstab(b["titular"], b["etapa_proyecto"])
    for e in ("Exploración", "Explotación", "Canteras y otros"):
        t[f"derechos_{e.split()[0].lower()}"] = etapas.get(e, 0)
    t = t.sort_values("superficie_ha", ascending=False)

    def _top(col):
        acum = t[col].sort_values(ascending=False).cumsum() / t[col].sum()
        return set(acum[acum.shift(fill_value=0) < UMBRAL_PRIORIDAD].index)

    alta = _top("superficie_ha") | _top("superficie_con_litio_ha")
    t.insert(0, "prioridad", ["Alta" if i in alta else "" for i in t.index])
    for c in _A_COMPLETAR:
        t[c] = ""
    return t.reset_index()


def escribir(t: pd.DataFrame, destino) -> None:
    wb = Workbook()
    leer = wb.active
    leer.title = "LEER"
    leer.append(["Columna / tema", "Descripción"])
    for fila in _LEER:
        leer.append(list(fila))
    leer.column_dimensions["A"].width, leer.column_dimensions["B"].width = 22, 110
    for fila in leer.iter_rows(min_row=2):
        fila[1].alignment = Alignment(wrap_text=True, vertical="top")
    for c in leer[1]:
        c.font = Font(bold=True)

    ws = wb.create_sheet("TITULARES")
    ws.append(list(t.columns))
    for fila in t.itertuples(index=False):
        ws.append(list(fila))
    for c in ws[1]:
        color = _COLOR_COMPLETAR if c.value in _A_COMPLETAR else _COLOR_DATO
        c.fill = PatternFill("solid", fgColor=color)
        c.font = Font(bold=True, color="FFFFFF")
    anchos = {"prioridad": 10, "titular": 45, "nombre_en_la_fuente": 45, "provincias": 13, **_A_COMPLETAR}
    for i, col in enumerate(t.columns, start=1):
        ws.column_dimensions[get_column_letter(i)].width = anchos.get(col, 14)
    ws.freeze_panes = "C2"
    ws.auto_filter.ref = ws.dimensions

    listas = wb.create_sheet("LISTAS")
    listas.append(["tipo_actor", "origen_capital"])
    for i in range(max(len(TIPOS_ACTOR), len(ORIGENES))):
        listas.append([TIPOS_ACTOR[i] if i < len(TIPOS_ACTOR) else None,
                       ORIGENES[i] if i < len(ORIGENES) else None])
    ultima = len(t) + 1
    for col, letra_lista, n in (("tipo_actor", "A", len(TIPOS_ACTOR)), ("origen_capital", "B", len(ORIGENES))):
        dv = DataValidation(type="list", formula1=f"=LISTAS!${letra_lista}$2:${letra_lista}${n + 1}",
                            allow_blank=True)
        letra = get_column_letter(t.columns.get_loc(col) + 1)
        dv.add(f"{letra}2:{letra}{ultima}")
        ws.add_data_validation(dv)

    wb.save(destino)


def main() -> None:
    base = pd.read_csv(DATA_SNAPSHOT / "catastro_noa.csv", dtype=str, keep_default_na=False)
    base["titular_original"] = base["titular"]
    t = tabla_titulares(base)
    DATA_PROCESSED.mkdir(parents=True, exist_ok=True)
    destino = DATA_PROCESSED / f"clasificacion_titulares_{date.today():%Y-%m-%d}.xlsx"
    escribir(t, destino)
    print(f"{len(t)} titulares, {(t['prioridad'] == 'Alta').sum()} con prioridad alta -> {destino}")


if __name__ == "__main__":
    main()
