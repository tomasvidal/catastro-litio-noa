import pandas as pd

from catastro_noa.claves import asignar_claves, clave_base


def _t(*filas):
    """filas: (provincia, expediente, nombre, geom_hash)"""
    return pd.DataFrame(filas, columns=["provincia", "expediente", "nombre", "geom_hash"])


def test_clave_base_normaliza():
    assert clave_base("jujuy", "2917-M-2022", "Masa 46") == "jujuy:2917 M 2022:MASA 46"
    assert clave_base("salta", "143-1/18", None) == "salta:143 1 18:"


def test_sin_historial_usa_la_clave_base():
    t = asignar_claves(_t(("jujuy", "1-A", "UNO", "h1"), ("salta", "2", None, "h2")))
    assert list(t["clave"]) == ["jujuy:1 A:UNO", "salta:2:"]
    assert t.columns[0] == "clave"


def test_expediente_repetido_se_desempata_por_poligono():
    t = asignar_claves(_t(("salta", "9", None, "h1"), ("salta", "9", None, "h2")))
    assert list(t["clave"]) == ["salta:9:#h1", "salta:9:#h2"]


def test_poligonos_identicos_en_un_grupo_no_repiten_clave():
    t = asignar_claves(_t(("salta", "9", None, "h1"), ("salta", "9", None, "h1")))
    assert t["clave"].is_unique


def test_la_clave_sobrevive_al_cambio_de_forma():
    antes = asignar_claves(_t(("jujuy", "1", "UNO", "h1")))
    despues = asignar_claves(_t(("jujuy", "1", "UNO", "h2")), antes)
    assert despues["clave"].iloc[0] == antes["clave"].iloc[0]


def test_grupo_repetido_conserva_claves_de_los_que_no_cambian():
    antes = asignar_claves(_t(("salta", "9", None, "h1"), ("salta", "9", None, "h2")))
    despues = asignar_claves(_t(("salta", "9", None, "h2"), ("salta", "9", None, "h3")), antes)
    por_hash = dict(zip(despues["geom_hash"], despues["clave"]))
    assert por_hash["h2"] == "salta:9:#h2"  # no cambio
    assert por_hash["h3"] == "salta:9:#h1"  # era el h1: le cambio la forma


def test_grupo_con_varios_cambios_a_la_vez_da_altas_nuevas():
    antes = asignar_claves(_t(("salta", "9", None, "h1"), ("salta", "9", None, "h2")))
    despues = asignar_claves(_t(("salta", "9", None, "h3"), ("salta", "9", None, "h4")), antes)
    assert not set(despues["clave"]) & set(antes["clave"])


def test_cambio_de_expediente_con_el_mismo_poligono_conserva_la_clave():
    antes = asignar_claves(_t(("salta", "143-1412/18", None, "h1"), ("salta", "5", "OTRO", "h9")))
    despues = asignar_claves(_t(("salta", "143-1412/2018", None, "h1"), ("salta", "5", "OTRO", "h9")), antes)
    assert despues["clave"].iloc[0] == antes["clave"].iloc[0]


def test_poligono_compartido_no_se_usa_para_reconocer_renombres():
    antes = asignar_claves(_t(("salta", "1", "A", "h1"), ("salta", "2", "B", "h1")))
    despues = asignar_claves(_t(("salta", "3", "C", "h1"), ("salta", "4", "D", "h1")), antes)
    assert not set(despues["clave"]) & set(antes["clave"])


def test_otra_provincia_no_se_mezcla():
    antes = asignar_claves(_t(("jujuy", "1", "UNO", "h1")))
    despues = asignar_claves(_t(("salta", "1", "UNO", "h1")), antes)
    assert despues["clave"].iloc[0] == "salta:1:UNO"


def test_mismo_poligono_pero_otro_expediente_nombre_y_titular_es_otro_derecho():
    antes = asignar_claves(_t(("jujuy", "2029-V-2014", "CHINCHILLA VI", "h1")).assign(titular_clave="PIRQUITAS SA"))
    despues = asignar_claves(
        _t(("jujuy", "3685-J-2026", "AREA DE RESERVA", "h1")).assign(titular_clave="JEMSE"), antes)
    assert despues["clave"].iloc[0] != antes["clave"].iloc[0]


def test_mismo_poligono_y_mismo_titular_con_otro_nombre_conserva_la_clave():
    antes = asignar_claves(_t(("jujuy", "1-A", "VIEJO", "h1")).assign(titular_clave="ACME SA"))
    despues = asignar_claves(_t(("jujuy", "9-B", "NUEVO", "h1")).assign(titular_clave="ACME SA"), antes)
    assert despues["clave"].iloc[0] == antes["clave"].iloc[0]
