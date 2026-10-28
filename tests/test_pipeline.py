"""Corrida completa del pipeline (`python -m catastro_noa`) con fuentes simuladas y carpetas temporales."""

import datetime as dt
import sys
from pathlib import Path

import geopandas as gpd
import pandas as pd
import pytest
from shapely.geometry import box

from catastro_noa import __main__ as cli
from catastro_noa import auditoria, snapshot
from catastro_noa.fuentes import Crudo


def _caja(i):
    x = -66.5 + i * 0.05
    return box(x, -23.5, x + 0.01, -23.49)


def _jujuy(*filas):
    """filas: (id, expediente, nombre, titular, estado)"""
    regs = [{"id": i, "expediente": e, "nombre": n, "titular_ac": t, "rg_tipo": "SOLICITUD DE MINA",
             "estado": s, "tipo_miner": "LITIO", "depto": "SUSQUES", "superficie": 100.0} for i, e, n, t, s in filas]
    return gpd.GeoDataFrame(regs, geometry=[_caja(int(f[1][0])) for f in filas], crs="EPSG:4326")


def _salta(*filas):
    """filas: (fid, expediente, titular)"""
    regs = [{"fid": f"salta.{i}", "expediente": e, "nombre": None, "concesionario": t, "tipo": "Mina",
             "estado": "Vigente", "mineral": "Litio", "departamento": "LOS ANDES", "area": "100 ha"}
            for i, e, t in filas]
    return gpd.GeoDataFrame(regs, geometry=[_caja(int(f[1][0]) + 20) for f in filas], crs="EPSG:4326")


@pytest.fixture
def entorno(tmp_path, monkeypatch):
    """Redirige las salidas a tmp_path y deja controlar qué publica cada provincia."""
    estado = {"fecha": dt.date(2026, 11, 2), "jujuy": None, "salta": None}

    def obtener(prov, offline=False):
        if estado[prov] is None:
            raise RuntimeError(f"{prov} no responde")
        return Crudo(prov, estado[prov], Path("x"), "fuente simulada", estado["fecha"], reutilizado=False)

    monkeypatch.setattr(cli, "obtener", obtener)
    monkeypatch.setattr(cli, "escribir", lambda base: {})
    monkeypatch.setattr(snapshot, "DATA_SNAPSHOT", tmp_path / "snapshot")
    monkeypatch.setattr(auditoria, "DATA_HISTORIAL", tmp_path / "historial")
    monkeypatch.setattr(sys, "argv", ["catastro_noa", "--estricto"])
    estado["tmp"] = tmp_path
    return estado


def _archivos(tmp):
    return {p.relative_to(tmp).as_posix(): p.read_bytes() for p in sorted(tmp.rglob("*")) if p.is_file()}


def _novedades(tmp):
    ruta = tmp / "historial" / "novedades.csv"
    return pd.read_csv(ruta) if ruta.exists() else pd.DataFrame(columns=auditoria.NOVEDADES)


def _dia1(e):
    e["jujuy"] = _jujuy((1, "1-A-2020", "UNO", "ACME S.A.", "EN TRAMITE"), (2, "2-B-2021", "DOS", "BETA S.A.", "EN TRAMITE"))
    e["salta"] = _salta((10, "3", "GAMMA S.A."), (11, "4", "DELTA S.A."))


def test_primera_corrida_es_punto_de_partida(entorno):
    _dia1(entorno)
    assert cli.main() == 0
    tmp = entorno["tmp"]
    assert _novedades(tmp).empty
    assert len(pd.read_csv(tmp / "snapshot" / "catastro_noa.csv")) == 4
    assert auditoria.vigentes(pd.read_parquet(tmp / "historial" / "historial.parquet")).shape[0] == 4


def test_repetir_la_corrida_no_cambia_nada_aunque_cambien_ids_y_fechas(entorno):
    _dia1(entorno)
    cli.main()
    antes = _archivos(entorno["tmp"])

    entorno["fecha"] = dt.date(2026, 11, 3)  # otro día, y Salta regenera todos sus ids
    entorno["jujuy"] = _jujuy((1, "1-A-2020", "UNO", "ACME S.A.", "EN TRAMITE"), (2, "2-B-2021", "DOS", "BETA S.A.", "EN TRAMITE"))
    entorno["salta"] = _salta((90, "3", "GAMMA S.A."), (91, "4", "DELTA S.A."))
    assert cli.main() == 0
    assert _archivos(entorno["tmp"]) == antes


def test_detecta_cambio_baja_y_alta_y_no_las_repite(entorno):
    _dia1(entorno)
    cli.main()

    entorno["fecha"] = dt.date(2026, 11, 9)
    entorno["jujuy"] = _jujuy((1, "1-A-2020", "UNO", "OTRA S.A.", "EN TRAMITE"),
                              (2, "2-B-2021", "DOS", "BETA S.A.", "EN TRAMITE"),
                              (5, "5-C-2026", "CINCO", "ACME S.A.", "EN TRAMITE"))
    entorno["salta"] = _salta((10, "3", "GAMMA S.A."))
    assert cli.main() == 0
    nov = _novedades(entorno["tmp"])
    assert sorted(nov["evento"]) == ["alta", "baja", "cambio_titular"]
    assert set(nov["provincia"]) == {"jujuy", "salta"}
    assert nov["fecha"].eq("2026-11-09").all()

    despues = _archivos(entorno["tmp"])
    entorno["fecha"] = dt.date(2026, 11, 10)
    assert cli.main() == 0
    assert _archivos(entorno["tmp"]) == despues

    h = pd.read_parquet(entorno["tmp"] / "historial" / "historial.parquet")
    assert auditoria.vigentes(h).shape[0] == 4  # 3 de Jujuy + 1 de Salta
    assert h["clave"].duplicated().sum() == 1  # el derecho que cambió de titular tiene dos versiones


def test_si_una_provincia_falla_no_se_escribe_nada(entorno, capsys):
    _dia1(entorno)
    cli.main()
    antes = _archivos(entorno["tmp"])

    entorno["fecha"] = dt.date(2026, 11, 9)
    entorno["salta"] = None  # Salta no responde: sin respaldo no hay que darla de baja
    assert cli.main() == 1
    assert "ERROR" in capsys.readouterr().out
    assert _archivos(entorno["tmp"]) == antes
