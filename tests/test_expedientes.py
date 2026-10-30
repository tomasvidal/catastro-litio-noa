import pandas as pd
import pytest

from catastro_noa.expedientes import COLUMNAS, expedientes_por_anio, numero_expediente


@pytest.mark.parametrize("provincia, expediente, numero", [
    ("jujuy", "3428-T-2024", 3428),
    ("jujuy", "1380-CH-2010", 1380),
    ("jujuy", "2911 - M - 2022", 2911),
    ("jujuy", "AREA 12", None),
    ("salta", "18746", 18746),
    ("salta", "143-1412/2018", None),  # no es el correlativo del catastro
    ("salta", None, None),
    ("catamarca", "123", None),  # sin serie conocida
])
def test_numero_expediente(provincia, expediente, numero):
    assert numero_expediente(provincia, expediente) == numero


def _base(filas):
    return pd.DataFrame(filas, columns=["provincia", "expediente", "anio_expediente"])


def test_estima_con_la_diferencia_entre_ultimos_numeros():
    t = expedientes_por_anio(_base([
        ("jujuy", "3040-A-2022", 2022), ("jujuy", "3041-B-2022", 2022),
        ("jujuy", "3100-A-2023", 2023), ("jujuy", "3285-C-2023", 2023),
        ("jujuy", "3300-A-2024", 2024),
    ]))
    assert list(t.columns) == COLUMNAS
    assert t["publicados"].tolist() == [2, 2, 1]
    assert t["ultimo_numero"].tolist() == [3041, 3285, 3300]
    # el primer año no tiene contra que comparar
    assert pd.isna(t["abiertos_estimados"].iloc[0])
    assert t["abiertos_estimados"].iloc[1:].tolist() == [244, 15]


def test_fuera_de_la_serie_solo_cuenta_publicados():
    t = expedientes_por_anio(_base([
        ("salta", "24000", 2019), ("salta", "24277", 2019),
        ("salta", "24372", 2020), ("salta", "745460", 2020),  # 2020 mezcla dos numeradores
        ("salta", "143-1412/2018", 2018),
    ])).set_index("anio")
    assert t.loc[2020, "publicados"] == 2
    assert pd.isna(t.loc[2020, "ultimo_numero"]) and pd.isna(t.loc[2020, "abiertos_estimados"])
    assert t.loc[2018, "publicados"] == 1 and pd.isna(t.loc[2018, "ultimo_numero"])
    assert pd.isna(t.loc[2019, "abiertos_estimados"])  # 2018 no tiene numero correlativo


def test_falta_un_anio_o_salto_hacia_atras():
    t = expedientes_por_anio(_base([
        ("jujuy", "100-A-2003", 2003), ("jujuy", "300-A-2005", 2005),  # falta 2004
        ("jujuy", "250-A-2006", 2006),  # numero menor al del año anterior
        ("jujuy", "X", None),
    ])).set_index("anio")
    assert t["abiertos_estimados"].isna().all()
    assert t["publicados"].sum() == 3  # el que no tiene año no se cuenta
