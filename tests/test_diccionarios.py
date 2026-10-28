"""
Chequea que diccionarios/minerales.csv respete la planilla de minerales del equipo
de investigacion: todo termino de la planilla esta en el diccionario y en el mismo
grupo. Los terminos de la planilla estan copiados en tests/datos/planilla_minerales.csv
(una fila por termino, con el grupo = la solapa donde estaba). Si el equipo actualiza
la planilla, se actualiza ese CSV y este test marca que hay que sumar terminos.
"""

import pandas as pd

from catastro_noa import DICCIONARIOS, RAIZ
from catastro_noa.minerales import GRUPOS
from catastro_noa.texto import clave

PLANILLA = RAIZ / "tests" / "datos" / "planilla_minerales.csv"
# Diferencias conocidas con la planilla, pendientes de validar (ver docs/metodologia.md).
EXCEPCIONES = {("Canteras, rocas de aplicación y otros minerales", "BERILIO")}

D = pd.read_csv(DICCIONARIOS / "minerales.csv", dtype=str, keep_default_na=False)
P = pd.read_csv(PLANILLA, dtype=str, keep_default_na=False)


def test_planilla_cubierta():
    por_termino = {}
    for r in D.itertuples(index=False):
        k = r.termino if r.tipo == "simbolo" else clave(r.termino)
        por_termino[k] = r.grupo
    faltan, otro_grupo = [], []
    for grupo, termino in P.itertuples(index=False):
        k = termino if termino in por_termino else clave(termino)
        if k not in por_termino:
            faltan.append(termino)
        elif por_termino[k] != grupo and (grupo, k) not in EXCEPCIONES:
            otro_grupo.append((termino, grupo, por_termino[k]))
    assert not faltan, f"terminos de la planilla que no estan en el diccionario: {faltan}"
    assert not otro_grupo, f"terminos en otro grupo que en la planilla: {otro_grupo}"


def test_planilla_bien_formada():
    assert len(P) > 100
    assert set(P["grupo"]) <= set(GRUPOS)
    assert (P["termino"] != "").all()


def test_diccionario_bien_formado():
    assert set(D["tipo"]) <= {"nombre", "simbolo", "modificador", "no_mineral"}
    assert set(D.loc[~D["tipo"].isin(["modificador", "no_mineral"]), "grupo"]) <= set(GRUPOS)
    assert set(D["origen"]) <= {"investigadores", "propuesta"}
    assert not D.duplicated(["termino", "tipo"]).any()
    # un mismo mineral canonico no puede quedar en dos grupos
    assert (D[D["mineral"] != ""].groupby("mineral")["grupo"].nunique() == 1).all()


def test_etapas_y_estados_bien_formados():
    e = pd.read_csv(DICCIONARIOS / "etapas.csv", dtype=str, keep_default_na=False)
    assert set(e["etapa_proyecto"]) <= {"Exploración", "Explotación", "Canteras y otros"}
    s = pd.read_csv(DICCIONARIOS / "estados.csv", dtype=str, keep_default_na=False)
    assert set(s["estado"]) <= {"Vigente", "En trámite", "Vacante", "Anulado", "Con recurso", "Otro"}
