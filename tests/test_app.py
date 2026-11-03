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
    for vista in (":material/manage_search: Buscar expediente", ":material/table: Tabla",
                  ":material/history: Novedades"):
        at.segmented_control[0].set_value(vista).run()
        assert not at.exception, at.exception
    assert len(at.dataframe) == 1


def test_novedades_muestran_el_expediente(estado):
    at = _correr()
    at.segmented_control[0].set_value(":material/history: Novedades").run()
    tabla = at.dataframe[0].value
    assert "expediente" in tabla.columns
    assert tabla["expediente"].ne("").all()  # tambien las bajas, que ya no estan en la foto


def test_tabla_descarga_csv_y_excel(estado):
    at = _correr()
    at.segmented_control[0].set_value(":material/table: Tabla").run()
    assert not at.exception, at.exception  # el Excel se arma al mostrar la vista
    assert len(at.get("download_button")) == 2


@pytest.mark.parametrize("texto, cambios", [
    ("2911-M-2022", True),   # MASA 40: paso de solicitud a mina concedida
    ("2911 m 2022", True),   # sin guiones ni mayusculas
    ("212-L-1996", True),    # CASA COLORADA: dada de baja, ya no esta en la foto
    ("no existe", False),
])
def test_buscar_expediente(estado, texto, cambios):
    at = _correr()
    at.segmented_control[0].set_value(":material/manage_search: Buscar expediente").run()
    at.text_input[0].input(texto).run()
    assert not at.exception, at.exception
    if cambios:
        assert len(at.dataframe) == 2  # ficha y cambios
    else:
        assert "No se encontró" in at.info[0].value


def test_mapa_vacio_si_no_hay_derechos(estado):
    at = _correr()
    at.sidebar.button_group[0].set_value([]).run()  # ninguna provincia elegida
    assert not at.exception, at.exception
    assert not at.info  # no reemplaza el mapa por un aviso


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
