import datetime as dt
from pathlib import Path

import geopandas as gpd
import pandas as pd
import pytest
from shapely.geometry import Polygon, box

from catastro_noa.estandarizar import COLUMNAS, estandarizar
from catastro_noa.fuentes import Crudo
from catastro_noa.minerales import ClasificadorMinerales
from catastro_noa.tramites import ClasificadorTramites

M, T = ClasificadorMinerales(), ClasificadorTramites()
HOY = dt.date(2026, 10, 9)
# ~0.01 grado en la Puna: alrededor de 100 ha
CUADRADO = box(-66.50, -23.50, -66.49, -23.49)


def _crudo(prov, registros, crs="EPSG:4326"):
    g = gpd.GeoDataFrame(registros, geometry=[CUADRADO] * len(registros), crs="EPSG:4326").to_crs(crs)
    return Crudo(prov, g, Path("x"), "test", HOY, reutilizado=False)


def test_catamarca_visor():
    crudo = _crudo("catamarca", [
        {"DPTO": "Antofagasta de la Sierra", "MINA": "La Mordaja", "EXPEDIENTE": None,
         "EXPTE DGTL": "EX-2024-00266542- -CAT-SGAM#AM", "CONCSRIO": "RODO HUASI S.A.",
         "MINERAL": "Litio, Potasio y Cloruros"},
    ])
    r = estandarizar(crudo, M, T).iloc[0]
    assert list(estandarizar(crudo, M, T).columns) == COLUMNAS
    assert r.expediente == "EX-2024-00266542- -CAT-SGAM#AM"
    assert r.departamento == "ANTOFAGASTA DE LA SIERRA"
    assert r.titular_clave == "RODO HUASI SA"
    assert r.tiene_litio and r.grupos_minerales == "Litio y potasio"
    assert r.etapa_proyecto is None and r.estado is None  # Catamarca no publica tramite ni estado
    assert 90 < r.superficie_ha_calculada < 120


def test_catamarca_wfs_campos_en_minuscula():
    crudo = _crudo("catamarca", [{"dpto": "BELEN", "mina": "JALOM 2", "exptedgtl": "EX-1",
                                  "concsrio": "Bortz, Sergio", "mineral": "Oro y Cobre"}])
    r = estandarizar(crudo, M, T).iloc[0]
    assert (r.expediente, r.nombre, r.minerales) == ("EX-1", "JALOM 2", "Oro; Cobre")


def test_jujuy_reproyecta_y_no_copia_contacto():
    crudo = _crudo("jujuy", [{"id": 1879, "expediente": "3671-S-2026", "nombre": "EL TORO II",
                              "titular_ac": "SUSQUES ENERGIA S.A.", "dom_corre": "alguien@mail.com",
                              "tipo_miner": "LITIO", "rg_tipo": "SOLICITUD DE MINA",
                              "estado": "EN TRAMITE", "depto": "SUSQUES", "superficie": 4978.6,
                              "revision": "2026-09-14"}], crs="EPSG:22183")
    df = estandarizar(crudo, M, T)
    r = df.iloc[0]
    assert df.crs.to_epsg() == 4326
    assert "dom_corre" not in df.columns
    assert not df.drop(columns="geometry").astype(str).apply(lambda c: c.str.contains("@")).any().any()
    assert (r.etapa_administrativa, r.etapa_proyecto, r.estado) == ("Solicitud de mina", "Exploración", "En trámite")
    assert r.id_fuente == "1879" and r.fecha_actualizacion_fuente == dt.date(2026, 9, 14)
    assert r.geometry.bounds == pytest.approx(CUADRADO.bounds, abs=1e-6)


def test_geometria_invalida_se_repara():
    moño = Polygon([(-66.5, -23.5), (-66.49, -23.49), (-66.49, -23.5), (-66.5, -23.49)])
    g = gpd.GeoDataFrame([{"fid": 1, "expediente": "1", "concesionario": "X", "tipo": "Mina",
                           "estado": "Vigente", "mineral": "Li", "area": "1,5 ha"}],
                         geometry=[moño], crs="EPSG:4326")
    r = estandarizar(Crudo("salta", g, Path("x"), "test", HOY, False), M, T).iloc[0]
    assert r.geometry.is_valid and r.geometry.geom_type in ("Polygon", "MultiPolygon")
    assert r.superficie_ha_fuente == 1.5


def test_si_la_fuente_cambia_de_formato_falla_en_vez_de_publicar_vacios():
    g = gpd.GeoDataFrame([{"fid": 1, "expte": "1", "mineral": "Li"}], geometry=[CUADRADO], crs="EPSG:4326")
    with pytest.raises(ValueError, match="concesionario"):
        estandarizar(Crudo("salta", g, Path("x"), "test", HOY, False), M, T)
    vacio = gpd.GeoDataFrame({"expediente": []}, geometry=[], crs="EPSG:4326")
    with pytest.raises(ValueError, match="0 registros"):
        estandarizar(Crudo("jujuy", vacio, Path("x"), "test", HOY, False), M, T)


def test_anio_expediente():
    jujuy = _crudo("jujuy", [{"expediente": "3428-T-2024", "nombre": "A", "titular_ac": "X", "rg_tipo": "CATEO",
                              "estado": "EN TRAMITE", "tipo_miner": "LITIO"},
                             {"expediente": "SIN AÑO", "nombre": "B", "titular_ac": "X", "rg_tipo": "CATEO",
                              "estado": "EN TRAMITE", "tipo_miner": "LITIO"}])
    anios = estandarizar(jujuy, M, T)["anio_expediente"]
    assert anios.iloc[0] == 2024 and pd.isna(anios.iloc[1])
    salta = _crudo("salta", [{"expediente": "21041", "concesionario": "X", "tipo": "Cateo", "estado": "Vigente",
                              "mineral": "Li", "fecha_inicio": "2023-05-02"},
                             {"expediente": "143-1412/2018", "concesionario": "X", "tipo": "Cateo",
                              "estado": "Vigente", "mineral": "Li", "fecha_inicio": None}])
    assert estandarizar(salta, M, T)["anio_expediente"].tolist() == [2023, 2018]


def test_servidumbre_no_deja_texto_para_revisar():
    crudo = _crudo("jujuy", [{"expediente": "2593-M-2019", "nombre": None, "titular_ac": "X",
                              "rg_tipo": "SERVIDUMBRE", "estado": "EN TRAMITE",
                              "tipo_miner": "P/CHINCHILLA Y CHINCHILLA I"}])
    r = estandarizar(crudo, M, T).iloc[0]
    assert r.etapa_administrativa == "Servidumbre"
    assert r.minerales is None and r.mineral_sin_clasificar is None
