import datetime as dt

import geopandas as gpd
import pandas as pd
from shapely.geometry import Polygon, box

from catastro_noa import snapshot
from catastro_noa.snapshot import hash_geometria, preparar

CUADRADO = box(-66.50, -23.50, -66.49, -23.49)


def _base(*filas):
    """filas: (provincia, expediente, nombre, geometria)"""
    df = pd.DataFrame({
        "provincia": [f[0] for f in filas], "id_fuente": [str(i) for i in range(len(filas))],
        "expediente": [f[1] for f in filas], "nombre": [f[2] for f in filas],
        "fuente": "archivo crudo x", "fecha_descarga": dt.date(2026, 11, 2),
        "fecha_actualizacion_fuente": dt.date(2026, 11, 2),
    })
    return gpd.GeoDataFrame(df, geometry=[f[3] for f in filas], crs="EPSG:4326")


def test_hash_ignora_ruido_de_punto_flotante():
    ruido = Polygon([(x + 1e-9, y - 1e-9) for x, y in CUADRADO.exterior.coords])
    assert hash_geometria(ruido) == hash_geometria(CUADRADO)


def test_hash_ignora_vertice_inicial_y_sentido():
    coords = list(CUADRADO.exterior.coords)[:-1]
    girado = Polygon(coords[2:] + coords[:2])
    invertido = Polygon(coords[::-1])
    assert hash_geometria(girado) == hash_geometria(invertido) == hash_geometria(CUADRADO)


def test_hash_cambia_si_cambia_la_forma():
    assert hash_geometria(box(-66.50, -23.50, -66.49, -23.4899)) != hash_geometria(CUADRADO)


def test_hash_sin_geometria():
    assert hash_geometria(None) is None


def test_preparar_saca_columnas_volatiles_y_ordena():
    base = _base(("salta", "2", "B", CUADRADO), ("jujuy", "9", "A", CUADRADO), ("salta", "1", "C", CUADRADO))
    tabla, geoms = preparar(base)
    for c in ("fuente", "fecha_descarga", "fecha_actualizacion_fuente", "id_fuente", "geometry"):
        assert c not in tabla
    assert list(tabla["expediente"]) == ["9", "1", "2"]
    assert len(geoms) == 1  # los tres comparten poligono: se guarda una vez


def test_preparar_es_estable_ante_el_orden_de_entrada():
    a = _base(("salta", "1", "A", CUADRADO), ("jujuy", "2", "B", box(0, 0, 1, 1)))
    b = a.iloc[::-1].reset_index(drop=True)
    ta, ga = preparar(a)
    tb, gb = preparar(b)
    assert ta.equals(tb)
    assert list(ga["geom_hash"]) == list(gb["geom_hash"])


def test_geometrias_solo_se_reescribe_si_cambia(tmp_path, monkeypatch):
    monkeypatch.setattr(snapshot, "DATA_SNAPSHOT", tmp_path)
    base = _base(("jujuy", "1", "A", CUADRADO))
    snapshot.escribir_snapshot(*preparar(base))
    ruta = tmp_path / "geometrias.parquet"
    antes = ruta.stat().st_mtime_ns

    snapshot.escribir_snapshot(*preparar(base.assign(nombre="A2")))  # cambia un atributo, no el poligono
    assert ruta.stat().st_mtime_ns == antes

    snapshot.escribir_snapshot(*preparar(_base(("jujuy", "1", "A", box(0, 0, 1, 1)))))
    assert ruta.stat().st_mtime_ns != antes


def test_csv_con_fin_de_linea_unix(tmp_path, monkeypatch):
    monkeypatch.setattr(snapshot, "DATA_SNAPSHOT", tmp_path)
    snapshot.escribir_snapshot(*preparar(_base(("jujuy", "1", "A", CUADRADO))))
    assert b"\r" not in (tmp_path / "catastro_noa.csv").read_bytes()
