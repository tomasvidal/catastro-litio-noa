"""
Chequea que diccionarios/minerales.csv respete las planillas del equipo de
investigacion (docs/insumos/Denominaciones_provinciales_minerales.xlsx):
todo termino de la planilla esta en el diccionario y en el mismo grupo.
Si el equipo actualiza la planilla, este test marca que hay que sumar terminos.
"""

import openpyxl
import pandas as pd
import pytest

from catastro_noa import DICCIONARIOS, RAIZ
from catastro_noa.minerales import GRUPOS
from catastro_noa.texto import clave

PLANILLA = RAIZ / "docs" / "insumos" / "Denominaciones_provinciales_minerales.xlsx"
SOLAPAS = {  # solapa de la planilla -> grupo del diccionario
    "Metalíferos": "Metalíferos",
    "Litio y potasio": "Litio y potasio",
    "Depósitos evaporíticos": "Depósitos evaporíticos",
    "Tierras raras": "Tierras raras",
    "Canteras, rocas de aplicación y": "Canteras, rocas de aplicación y otros minerales",
}
# Diferencias conocidas con la planilla, pendientes de validar (ver docs/metodologia.md).
EXCEPCIONES = {("Canteras, rocas de aplicación y otros minerales", "BERILIO")}

D = pd.read_csv(DICCIONARIOS / "minerales.csv", dtype=str, keep_default_na=False)


def _terminos_planilla():
    wb = openpyxl.load_workbook(PLANILLA, read_only=True)
    for solapa, grupo in SOLAPAS.items():
        for fila in wb[solapa].iter_rows(values_only=True):
            v = fila[0] if fila else None
            if v is None or clave(v) == clave(solapa):  # la primera fila repite el titulo
                continue
            yield grupo, str(v).strip()


@pytest.mark.skipif(not PLANILLA.exists(), reason="falta la planilla del equipo")
def test_planilla_cubierta():
    por_termino = {}
    for r in D.itertuples(index=False):
        k = r.termino if r.tipo == "simbolo" else clave(r.termino)
        por_termino[k] = r.grupo
    faltan, otro_grupo = [], []
    for grupo, termino in _terminos_planilla():
        k = termino if termino in por_termino else clave(termino)
        if k not in por_termino:
            faltan.append(termino)
        elif por_termino[k] != grupo and (grupo, k) not in EXCEPCIONES:
            otro_grupo.append((termino, grupo, por_termino[k]))
    assert not faltan, f"terminos de la planilla que no estan en el diccionario: {faltan}"
    assert not otro_grupo, f"terminos en otro grupo que en la planilla: {otro_grupo}"


def test_diccionario_bien_formado():
    assert set(D["tipo"]) <= {"nombre", "simbolo", "modificador"}
    assert set(D.loc[D["tipo"] != "modificador", "grupo"]) <= set(GRUPOS)
    assert set(D["origen"]) <= {"investigadores", "propuesta"}
    assert not D.duplicated(["termino", "tipo"]).any()
    # un mismo mineral canonico no puede quedar en dos grupos
    assert (D[D["mineral"] != ""].groupby("mineral")["grupo"].nunique() == 1).all()


def test_etapas_y_estados_bien_formados():
    e = pd.read_csv(DICCIONARIOS / "etapas.csv", dtype=str, keep_default_na=False)
    assert set(e["etapa_proyecto"]) <= {"Exploración", "Explotación", "Canteras y otros"}
    s = pd.read_csv(DICCIONARIOS / "estados.csv", dtype=str, keep_default_na=False)
    assert set(s["estado"]) <= {"Vigente", "En trámite", "Vacante", "Anulado", "Con recurso", "Otro"}
