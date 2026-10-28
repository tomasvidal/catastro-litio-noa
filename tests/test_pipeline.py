"""Corrida completa del pipeline (`python -m catastro_noa`) con fuentes simuladas y carpetas temporales."""

import datetime as dt
import sys
from pathlib import Path

import geopandas as gpd
import pandas as pd
import pytest
from shapely.geometry import box

from catastro_noa import __main__ as cli
from catastro_noa import auditoria, estado as estado_fuentes, snapshot
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
    monkeypatch.setattr(estado_fuentes, "RUTA", tmp_path / "estado_fuentes.csv")
    monkeypatch.setattr(sys, "argv", ["catastro_noa", "--estricto"])
    estado["tmp"] = tmp_path
    return estado


def _archivos(tmp):
    """Foto e historial (el estado de las fuentes cambia en cada corrida: tiene la fecha del intento)."""
    return {p.relative_to(tmp).as_posix(): p.read_bytes() for p in sorted(tmp.rglob("*"))
            if p.is_file() and p.name != "estado_fuentes.csv"}


def _estado(tmp):
    return pd.read_csv(tmp / "estado_fuentes.csv", dtype=str, keep_default_na=False).set_index("provincia")


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




def _filas_csv(tmp, provincia):
    lineas = (tmp / "snapshot" / "catastro_noa.csv").read_text(encoding="utf-8").splitlines()
    return [x for x in lineas[1:] if x.split(",")[1] == provincia]


def test_la_primera_corrida_registra_el_estado_de_cada_fuente(entorno):
    _dia1(entorno)
    cli.main()
    e = _estado(entorno["tmp"])
    assert list(e.index) == ["jujuy", "salta"]
    assert e["resultado"].eq("ok").all()
    assert e["ultima_descarga_ok"].eq("2026-11-02").all()
    assert e.loc["jujuy", "registros"] == "2"


def test_si_una_provincia_falla_las_demas_se_actualizan_y_ella_conserva_sus_datos(entorno, capsys):
    _dia1(entorno)
    cli.main()
    tmp = entorno["tmp"]
    salta_antes = _filas_csv(tmp, "salta")
    h_antes = pd.read_parquet(tmp / "historial" / "historial.parquet")

    entorno["fecha"] = dt.date(2026, 11, 9)
    entorno["jujuy"] = _jujuy((1, "1-A-2020", "UNO", "OTRA S.A.", "EN TRAMITE"), (2, "2-B-2021", "DOS", "BETA S.A.", "EN TRAMITE"))
    entorno["salta"] = None  # Salta no responde
    assert cli.main() == 1  # --estricto: termina en rojo, pero después de escribir
    assert "ERROR: salta" in capsys.readouterr().out

    nov = _novedades(tmp)
    assert list(nov["evento"]) == ["cambio_titular"] and set(nov["provincia"]) == {"jujuy"}  # sin bajas de Salta
    assert _filas_csv(tmp, "salta") == salta_antes  # Salta sigue publicada tal cual
    geoms = pd.read_parquet(tmp / "snapshot" / "geometrias.parquet")
    snap = pd.read_csv(tmp / "snapshot" / "catastro_noa.csv")
    assert set(snap["geom_hash"]) <= set(geoms["geom_hash"])
    h = pd.read_parquet(tmp / "historial" / "historial.parquet")
    assert h[h["provincia"] == "salta"].reset_index(drop=True).equals(h_antes[h_antes["provincia"] == "salta"].reset_index(drop=True))

    e = _estado(tmp)
    assert e.loc["jujuy", ["resultado", "ultima_descarga_ok"]].tolist() == ["ok", "2026-11-09"]
    assert e.loc["salta", "resultado"] == "error" and "no responde" in e.loc["salta", "detalle"]
    assert e.loc["salta", ["ultima_descarga_ok", "registros"]].tolist() == ["2026-11-02", "2"]

    # Salta vuelve igual que antes: no hay altas falsas ni cambios en sus archivos.
    entorno["fecha"] = dt.date(2026, 11, 10)
    entorno["jujuy"] = _jujuy((1, "1-A-2020", "UNO", "OTRA S.A.", "EN TRAMITE"), (2, "2-B-2021", "DOS", "BETA S.A.", "EN TRAMITE"))
    _dia1_salta = _salta((10, "3", "GAMMA S.A."), (11, "4", "DELTA S.A."))
    entorno["salta"] = _dia1_salta
    assert cli.main() == 0
    assert len(_novedades(tmp)) == 1
    assert _filas_csv(tmp, "salta") == salta_antes
    assert _estado(tmp).loc["salta", ["resultado", "ultima_descarga_ok"]].tolist() == ["ok", "2026-11-10"]


def test_si_fallan_todas_queda_registrado_y_no_se_toca_la_foto(entorno):
    _dia1(entorno)
    cli.main()
    antes = _archivos(entorno["tmp"])
    entorno["jujuy"] = entorno["salta"] = None
    assert cli.main() == 1
    assert _archivos(entorno["tmp"]) == antes
    assert _estado(entorno["tmp"])["resultado"].eq("error").all()


def test_descarga_con_muchos_menos_registros_se_descarta(entorno):
    entorno["jujuy"] = _jujuy(*[(i, f"{i}-A-2020", f"M{i}", "ACME S.A.", "EN TRAMITE") for i in range(1, 5)])
    entorno["salta"] = _salta((10, "3", "GAMMA S.A."), (11, "4", "DELTA S.A."))
    cli.main()
    jujuy_antes = _filas_csv(entorno["tmp"], "jujuy")

    entorno["fecha"] = dt.date(2026, 11, 9)
    entorno["jujuy"] = _jujuy((1, "1-A-2020", "M1", "ACME S.A.", "EN TRAMITE"))  # 1 de 4: respuesta cortada
    assert cli.main() == 1
    assert _novedades(entorno["tmp"]).empty  # no se registran 3 bajas falsas
    assert _filas_csv(entorno["tmp"], "jujuy") == jujuy_antes
    e = _estado(entorno["tmp"])
    assert e.loc["jujuy", "resultado"] == "error" and "sospechosa" in e.loc["jujuy", "detalle"]
    assert e.loc["salta", "resultado"] == "ok"

    # Al otro día trae lo mismo: es una baja real y se acepta.
    entorno["fecha"] = dt.date(2026, 11, 10)
    assert cli.main() == 0
    assert sorted(_novedades(entorno["tmp"])["evento"]) == ["baja"] * 3
    assert _estado(entorno["tmp"]).loc["jujuy", ["resultado", "registros"]].tolist() == ["ok", "1"]


def test_si_la_fuente_cambia_sus_columnas_no_frena_a_las_demas(entorno):
    _dia1(entorno)
    cli.main()
    entorno["fecha"] = dt.date(2026, 11, 9)
    entorno["salta"] = gpd.GeoDataFrame({"columna_nueva": ["x"]}, geometry=[_caja(30)], crs="EPSG:4326")
    assert cli.main() == 1
    e = _estado(entorno["tmp"])
    assert e.loc["salta", "resultado"] == "error" and e.loc["jujuy", "resultado"] == "ok"
    assert len(_filas_csv(entorno["tmp"], "salta")) == 2


def test_offline_no_registra_intentos(entorno, monkeypatch):
    _dia1(entorno)
    monkeypatch.setattr(sys, "argv", ["catastro_noa", "--offline"])
    assert cli.main() == 0
    assert not (entorno["tmp"] / "estado_fuentes.csv").exists()
