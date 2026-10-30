"""
La app corre sin errores con los datos versionados y avisa cuando una fuente falla.

El workflow de actualizacion no corre este archivo: una falla de la app no tiene que frenar
la descarga de datos.
"""

import datetime as dt

import pytest
import streamlit as st
from streamlit.testing.v1 import AppTest

import catastro_noa
from catastro_noa import RAIZ

APP = str(RAIZ / "streamlit_app.py")
ENCABEZADO = "provincia,ultimo_intento,ultima_descarga_ok,resultado,registros,fuente,detalle\n"


@pytest.fixture
def estado(tmp_path, monkeypatch):
    ruta = tmp_path / "estado_fuentes.csv"
    monkeypatch.setattr(catastro_noa, "ESTADO_FUENTES", ruta)
    st.cache_data.clear()
    return ruta


def _correr():
    at = AppTest.from_file(APP, default_timeout=120).run()
    assert not at.exception, at.exception
    return at


def test_todas_las_vistas_funcionan(estado):
    at = _correr()  # sin archivo de estado: no muestra fechas ni avisos
    assert not at.warning
    for vista in (":material/table: Tabla", ":material/bar_chart: Por año", ":material/history: Novedades"):
        at.segmented_control[0].set_value(vista).run()
        assert not at.exception, at.exception
    assert len(at.dataframe) == 1


def test_por_anio_estimado(estado):
    at = _correr()
    at.segmented_control[0].set_value(":material/bar_chart: Por año").run()
    at.segmented_control[1].set_value("Expedientes abiertos (estimado)").run()
    assert not at.exception, at.exception


def test_avisa_si_una_fuente_fallo(estado):
    hoy = dt.date.today()
    estado.write_text(ENCABEZADO + f"jujuy,{hoy},{hoy},ok,1,x,\nsalta,{hoy},2026-10-25,error,1,x,timeout\n",
                      encoding="utf-8")
    at = _correr()
    assert "Salta: datos al **25/10/2026**" in at.caption[0].value
    assert [w.value for w in at.warning] == [
        f"No se pudieron descargar datos nuevos de Salta en el último intento ({hoy:%d/%m/%Y}). "
        "Se muestran los datos del 25/10/2026."]


def test_avisa_si_el_robot_dejo_de_correr(estado):
    viejo = dt.date.today() - dt.timedelta(days=30)
    estado.write_text(ENCABEZADO + f"jujuy,{viejo},{viejo},ok,1,x,\nsalta,{viejo},{viejo},ok,1,x,\n",
                      encoding="utf-8")
    at = _correr()
    assert len(at.warning) == 1 and "no corre desde" in at.warning[0].value
