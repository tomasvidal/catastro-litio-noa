import pytest

from catastro_noa.minerales import ClasificadorMinerales

C = ClasificadorMinerales()


@pytest.mark.parametrize("texto, minerales, grupos", [
    # Jujuy: nombres en mayuscula, separados por coma / 'Y' / guion
    ("DISEMINADO DE COBRE, ORO, PLATA Y SALES ALCALINAS",
     ["Cobre", "Oro", "Plata", "Sales alcalinas"], ["Metalíferos", "Litio y potasio"]),
    ("ORO-DISEMINADO", ["Oro"], ["Metalíferos"]),
    ("SAL DE COSECHA, LITIO Y OTRAS SALES ALCALINAS",
     ["Sal", "Litio", "Sales alcalinas"], ["Litio y potasio", "Depósitos evaporíticos"]),
    ("DISEMINADO DE BORATO, LITIO, SALES ALCALINAS \nY ALCALINO TERROSAS",
     ["Boratos", "Litio", "Sales alcalinas", "Alcalinotérreos"], ["Litio y potasio", "Depósitos evaporíticos"]),
    ("SULFATO DE SODIO, BORATO Y LITIO", ["Sulfato de sodio", "Boratos", "Litio"],
     ["Litio y potasio", "Depósitos evaporíticos"]),
    ("BORATO - LITIO Y POTACIO", ["Boratos", "Litio", "Potasio"], ["Litio y potasio", "Depósitos evaporíticos"]),
    ("PLOMO ARGENTIFERO", ["Plomo", "Plata"], ["Metalíferos"]),
    # Salta: simbolos quimicos + nombres separados por coma
    ("BORATOS,K,Li", ["Boratos", "Potasio", "Litio"], ["Litio y potasio", "Depósitos evaporíticos"]),
    ("Cu,TTRR,U,V", ["Cobre", "Tierras raras", "Uranio", "Vanadio"], ["Metalíferos", "Tierras raras"]),
    ("Au ALUVIONAL", ["Oro"], ["Metalíferos"]),
    ("ÁRIDOS", ["Áridos"], ["Canteras, rocas de aplicación y otros minerales"]),
    ("Sb", ["Antimonio"], ["Metalíferos"]),
    # Catamarca: nombres en minuscula con 'y'
    ("Litio, Potasio y Cloruros", ["Litio", "Potasio", "Cloruros"], ["Litio y potasio"]),
    ("Oro, Cobre y Molib", ["Oro", "Cobre", "Molibdeno"], ["Metalíferos"]),
    ("Carbón Mineral", ["Carbón mineral"], ["Canteras, rocas de aplicación y otros minerales"]),
    ("Tantalio, Niobio y Estroncio", ["Tantalio", "Niobio"], ["Metalíferos"]),
])
def test_clasifica(texto, minerales, grupos):
    r = C.clasificar(texto)
    assert r.minerales == minerales
    assert r.grupos == grupos


def test_la_y_conjuncion_no_es_itrio():
    r = C.clasificar("ORO Y PLATA")
    assert "Itrio" not in r.minerales
    assert r.sin_clasificar is None


def test_cloruro_de_sodio_es_sal_y_no_cloruros():
    assert C.clasificar("CLORURO DE SODIO").minerales == ["Sal"]


def test_diseminado_solo_cuenta_si_no_hay_otro_mineral():
    assert C.clasificar("DISEMINADO POLIMETALICO").minerales == ["Metales sin especificar"]
    assert C.clasificar("DISEMINADO").minerales == ["Diseminado"]
    assert "Diseminado" not in C.clasificar("BORATO Y DISEMINADO DE LITIO").minerales


@pytest.mark.parametrize("texto, categoria", [
    ("1 Y 2", "1 y 2"), ("1 y2", "1 y 2"), ("1", "1"), ("2", "2"), ("12.0", "1 y 2"), ("1.0", "1"),
    ("DISEMINADOS DE 1RA. Y 2DA. CATEGORIA", "1 y 2"),
    ("COBRE?PLATA-COBALTO y\nMOLIBDENO (1º CATEGORIA)", "1"),
    ("TIERRAS RARAS 2DA CAT - DISEMINADO DE POTASIO, COBRE Y ORO 1RA CAT", "1 y 2"),
    ("LITIO", None),
])
def test_categoria(texto, categoria):
    assert C.clasificar(texto).categoria == categoria


def test_solo_categoria_no_tiene_minerales():
    r = C.clasificar("1 Y 2")
    assert r.minerales == [] and r.sin_clasificar is None


def test_lo_desconocido_queda_para_revisar():
    r = C.clasificar("PIEDRA FILOSOFAL")
    assert r.sin_clasificar == "FILOSOFAL"


def test_cretacico_es_cantera():
    r = C.clasificar("CRETACICO (OBSERVADO)")
    assert r.minerales == ["Cretácico"] and r.sin_clasificar is None
    assert r.grupos == ["Canteras, rocas de aplicación y otros minerales"]


@pytest.mark.parametrize("texto", [
    "CAMPAMENTO",
    "CAMPAMENTO P/GRUPO MINERO OSIRIS N° 104-I-1990",
    "COLAS Y RELAVES",
    "PLANTA DE BENEFICIO",
    "INSTAL.CAMP, CANCHA MINA Y ACOPIO P/MINA JOSE OCTAVIO N° 805-A-2007",
])
def test_instalaciones_no_son_minerales_ni_quedan_para_revisar(texto):
    r = C.clasificar(texto)
    assert r.minerales == [] and r.sin_clasificar is None


def test_instalacion_con_minerales_conserva_los_minerales():
    r = C.clasificar("DESMONTES Y RELAVES DE PLOMO, ZINC Y PLATA")
    assert r.minerales == ["Plomo", "Zinc", "Plata"] and r.sin_clasificar is None


def test_subproductos_figuran_pero_no_definen_el_grupo():
    r = C.clasificar("BORATOS,Cs,K,Li,Na,Rb")
    assert "Cesio" in r.minerales and "Rubidio" in r.minerales and r.sin_clasificar is None
    assert r.grupos == ["Litio y potasio", "Depósitos evaporíticos"]
    assert C.clasificar("Cs").grupos == []


def test_sales_alcalinas_terreas_con_error_de_tipeo():
    r = C.clasificar("BORATO, LITIO Y SALES ALCALINAS TERREAS")
    assert r.minerales == ["Boratos", "Litio", "Alcalinotérreos"]


@pytest.mark.parametrize("vacio", [None, "", "-", "   ", float("nan")])
def test_vacios(vacio):
    r = C.clasificar(vacio)
    assert r.minerales == [] and r.categoria is None and r.sin_clasificar is None
