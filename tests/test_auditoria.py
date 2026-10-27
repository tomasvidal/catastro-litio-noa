import datetime as dt

import pandas as pd

from catastro_noa import auditoria
from catastro_noa.claves import asignar_claves

D1, D2, D3 = dt.date(2026, 10, 1), dt.date(2026, 10, 8), dt.date(2026, 10, 15)
BASE = dict(titular="ACME S.A.", titular_clave="ACME SA", tramite_original="CATEO", etapa_administrativa="Cateo",
            etapa_proyecto="Exploración", estado_original="VIGENTE", estado="Vigente",
            mineral_original="LITIO", minerales="Litio", superficie_ha_calculada=100.0, geom_hash="h1")


def _tabla(*filas):
    """filas: (provincia, expediente, nombre, {campos a pisar})"""
    return pd.DataFrame([{"provincia": p, "expediente": e, "nombre": n, **BASE, **extra} for p, e, n, extra in filas])


def _correr(*fotos):
    """fotos: [(fecha, tabla)]; devuelve (novedades de cada foto, historial final)."""
    historial, salidas = None, []
    for fecha, tabla in fotos:
        tabla = asignar_claves(tabla, auditoria.vigentes(historial))
        nov, historial = auditoria.aplicar(historial, tabla, fecha)
        salidas.append(nov)
    return salidas, historial


def test_primera_foto_es_punto_de_partida_sin_novedades():
    (nov,), h = _correr((D1, _tabla(("jujuy", "1", "UNO", {}))))
    assert nov.empty
    assert list(h["vigente_desde"]) == [pd.Timestamp(D1)] and h["vigente_hasta"].isna().all()


def test_foto_igual_no_genera_novedades_ni_versiones():
    f = _tabla(("jujuy", "1", "UNO", {}))
    (_, nov), h = _correr((D1, f), (D2, f))
    assert nov.empty and len(h) == 1


def test_cambio_de_titular_cierra_y_abre_version():
    a = _tabla(("jujuy", "1", "UNO", {}))
    b = _tabla(("jujuy", "1", "UNO", {"titular": "OTRA S.A.", "titular_clave": "OTRA SA"}))
    (_, nov), h = _correr((D1, a), (D2, b))
    assert list(nov["evento"]) == ["cambio_titular"]
    assert (nov.loc[0, "antes"], nov.loc[0, "despues"]) == ("ACME SA", "OTRA SA")
    assert len(h) == 2
    vieja, nueva = h.sort_values("vigente_desde").itertuples()
    assert vieja.vigente_hasta == pd.Timestamp(D2) and pd.isna(nueva.vigente_hasta)
    assert (vieja.titular_clave, nueva.titular_clave) == ("ACME SA", "OTRA SA")


def test_cambio_de_etapa_informa_las_dos_etapas():
    a = _tabla(("jujuy", "1", "UNO", {}))
    b = _tabla(("jujuy", "1", "UNO", {"tramite_original": "MINA", "etapa_administrativa": "Mina concedida",
                                       "etapa_proyecto": "Explotación"}))
    (_, nov), _ = _correr((D1, a), (D2, b))
    assert set(nov["campo"]) == {"etapa_administrativa", "etapa_proyecto"}
    assert set(nov["evento"]) == {"cambio_etapa"}


def test_alta_y_baja():
    a = _tabla(("jujuy", "1", "UNO", {}), ("jujuy", "2", "DOS", {}))
    b = _tabla(("jujuy", "1", "UNO", {}), ("jujuy", "3", "TRES", {"geom_hash": "h3"}))
    (_, nov), h = _correr((D1, a), (D2, b))
    assert dict(zip(nov["evento"], nov["nombre"])) == {"alta": "TRES", "baja": "DOS"}
    cerrada = h[h["nombre"] == "DOS"].iloc[0]
    assert cerrada["vigente_hasta"] == pd.Timestamp(D2)
    assert h["vigente_hasta"].isna().sum() == 2  # UNO y TRES


def test_cambio_de_forma_y_de_superficie():
    a = _tabla(("jujuy", "1", "UNO", {}))
    b = _tabla(("jujuy", "1", "UNO", {"geom_hash": "h2", "superficie_ha_calculada": 150.0}))
    (_, nov), _ = _correr((D1, a), (D2, b))
    assert set(nov["evento"]) == {"cambio_geometria", "cambio_superficie"}


def test_ruido_de_superficie_no_es_novedad():
    a = _tabla(("jujuy", "1", "UNO", {}))
    b = _tabla(("jujuy", "1", "UNO", {"superficie_ha_calculada": 100.004}))
    (_, nov), _ = _correr((D1, a), (D2, b))
    assert nov.empty


def test_cambio_de_diccionario_no_es_novedad_pero_actualiza_la_version_vigente():
    a = _tabla(("jujuy", "1", "UNO", {}))
    b = _tabla(("jujuy", "1", "UNO", {"minerales": "Litio; Boratos"}))  # mismo mineral_original
    (_, nov), h = _correr((D1, a), (D2, b))
    assert nov.empty and len(h) == 1
    assert h.loc[0, "minerales"] == "Litio; Boratos"


def test_cambio_de_texto_que_no_cambia_el_valor_homologado_no_es_novedad():
    a = _tabla(("jujuy", "1", "UNO", {}))
    b = _tabla(("jujuy", "1", "UNO", {"titular": "ACME SA"}))  # titular_clave igual
    (_, nov), _ = _correr((D1, a), (D2, b))
    assert nov.empty


def test_cambio_de_expediente_con_mismo_poligono():
    a = _tabla(("salta", "143-1/18", None, {}))
    b = _tabla(("salta", "143-1/2018", None, {}))
    (_, nov), h = _correr((D1, a), (D2, b))
    assert list(nov["evento"]) == ["cambio_expediente"]
    vig = auditoria.vigentes(h)
    assert len(vig) == 1 and vig["clave"].is_unique


def test_provincia_nueva_entra_sin_altas_y_la_ausente_no_se_da_de_baja():
    solo_jujuy = _tabla(("jujuy", "1", "UNO", {}))
    ambas = _tabla(("jujuy", "1", "UNO", {}), ("salta", "9", "NUEVA", {"geom_hash": "h9"}))
    solo_salta = _tabla(("salta", "9", "NUEVA", {"geom_hash": "h9"}))
    (_, n2, n3), h = _correr((D1, solo_jujuy), (D2, ambas), (D3, solo_salta))
    assert n2.empty and n3.empty
    assert h["vigente_hasta"].isna().all() and len(h) == 2


def test_escribir_agrega_novedades_y_no_reescribe_historial_igual(tmp_path):
    a = _tabla(("jujuy", "1", "UNO", {}))
    b = _tabla(("jujuy", "1", "UNO", {"titular": "OTRA S.A.", "titular_clave": "OTRA SA"}))
    (_, nov), h = _correr((D1, a), (D2, b))
    auditoria.escribir(h, nov, tmp_path)
    parquet = tmp_path / "historial.parquet"
    antes = parquet.stat().st_mtime_ns
    auditoria.escribir(h, nov.iloc[0:0], tmp_path)
    assert parquet.stat().st_mtime_ns == antes
    assert len(pd.read_csv(tmp_path / "novedades.csv")) == 1
    assert b"\r" not in (tmp_path / "novedades.csv").read_bytes()
