import datetime as dt

from catastro_noa import estado
from catastro_noa.fuentes import capa_por_titulo


def test_un_error_conserva_la_ultima_descarga_buena(tmp_path):
    e = estado.leer(tmp_path / "no_existe.csv")
    e = estado.registrar(e, "salta", dt.date(2026, 11, 2), ok=True, registros=3924, fuente="WFS x")
    e = estado.registrar(e, "salta", dt.date(2026, 11, 3), ok=False, detalle="HTTPError:\n 503")
    fila = e.set_index("provincia").loc["salta"]
    assert fila["ultimo_intento"] == "2026-11-03" and fila["ultima_descarga_ok"] == "2026-11-02"
    assert fila["registros"] == "3924" and fila["fuente"] == "WFS x"
    assert fila["resultado"] == "error" and fila["detalle"] == "HTTPError: 503"

    estado.escribir(e, tmp_path / "e.csv")
    assert estado.leer(tmp_path / "e.csv").to_dict("records") == e.to_dict("records")
    assert b"\r" not in (tmp_path / "e.csv").read_bytes()


def test_capa_por_titulo():
    xml = """<wfs:WFS_Capabilities><FeatureTypeList>
      <FeatureType><Name>geonode:servidumbres_l</Name><Title>Catastro Minero: Servidumbres</Title></FeatureType>
      <FeatureType><Name>geonode:poligonos_nuevo</Name><Title> Catastro minero </Title></FeatureType>
    </FeatureTypeList></wfs:WFS_Capabilities>"""
    assert capa_por_titulo(xml, "Catastro Minero") == "geonode:poligonos_nuevo"
    assert capa_por_titulo(xml, "Otra capa") is None
