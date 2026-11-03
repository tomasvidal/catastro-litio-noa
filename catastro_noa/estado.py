"""
Estado de cada fuente: cuando se intento descargar por ultima vez y cuando salio bien.

  data/estado_fuentes.csv   una fila por provincia. Lo escribe cada corrida (salvo --offline) y
                            lo versiona el robot, asi que tambien sirve de prueba de que el robot
                            sigue corriendo aunque el catastro no cambie. La app lo lee para
                            mostrar de que fecha son los datos y avisar si una fuente falla.

Columnas:
  provincia, ultimo_intento, ultima_descarga_ok (fechas AAAA-MM-DD), resultado ("ok" / "error"),
  registros (de la ultima descarga buena), registros_intento (de la ultima descarga, aunque se
  haya descartado), fuente (de donde salio) y detalle (motivo del error).

  data/historial/descargas.csv   registro de todas las corridas: una fila por dia y provincia
                                 (fecha, provincia, resultado, registros, fuente, detalle). Si una
                                 corrida se repite el mismo dia, queda la ultima. Un dia sin filas
                                 es un dia en que el robot no llego a correr.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import pandas as pd

from . import ESTADO_FUENTES, REGISTRO_DESCARGAS

RUTA = ESTADO_FUENTES
RUTA_REGISTRO = REGISTRO_DESCARGAS
COLUMNAS = ["provincia", "ultimo_intento", "ultima_descarga_ok", "resultado", "registros", "registros_intento",
            "fuente", "detalle"]
COLUMNAS_REGISTRO = ["fecha", "provincia", "resultado", "registros", "fuente", "detalle"]


def leer(ruta: Path | None = None) -> pd.DataFrame:
    ruta = ruta or RUTA
    if not ruta.exists():
        return pd.DataFrame(columns=COLUMNAS)
    return pd.read_csv(ruta, dtype=str, keep_default_na=False).reindex(columns=COLUMNAS, fill_value="")


def registrar(estado: pd.DataFrame, provincia: str, fecha: dt.date, ok: bool, registros: int | None = None,
              fuente: str = "", detalle: str = "") -> pd.DataFrame:
    """`registros`: cuantos trajo la descarga (aunque se descarte); vacio si no se pudo leer."""
    # Si fallo, se conservan la fecha, los registros y la fuente de la ultima descarga buena.
    previa = estado[estado["provincia"] == provincia]
    fila = previa.iloc[0].to_dict() if len(previa) else dict.fromkeys(COLUMNAS, "")
    fila.update(provincia=provincia, ultimo_intento=f"{fecha:%Y-%m-%d}",
                resultado="ok" if ok else "error", detalle=" ".join(detalle.split())[:300],
                registros_intento="" if registros is None else str(registros))
    if ok:
        fila.update(ultima_descarga_ok=f"{fecha:%Y-%m-%d}", registros=str(registros), fuente=fuente)
    resto = estado[estado["provincia"] != provincia]
    return pd.concat([resto, pd.DataFrame([fila])], ignore_index=True)[COLUMNAS].sort_values("provincia")


def registros_intento(estado: pd.DataFrame, provincia: str) -> int | None:
    fila = estado.loc[estado["provincia"] == provincia, "registros_intento"]
    return int(fila.iat[0]) if len(fila) and fila.iat[0].isdigit() else None


def escribir(estado: pd.DataFrame, ruta: Path | None = None) -> str:
    ruta = ruta or RUTA
    ruta.parent.mkdir(parents=True, exist_ok=True)
    estado.to_csv(ruta, index=False, encoding="utf-8", lineterminator="\n")
    return str(ruta)


def anotar(estado: pd.DataFrame, fecha: dt.date, provincias: list[str], ruta: Path | None = None) -> str:
    """Suma al registro de descargas el resultado de hoy de cada provincia intentada."""
    ruta = ruta or RUTA_REGISTRO
    previo = (pd.read_csv(ruta, dtype=str, keep_default_na=False) if ruta.exists()
              else pd.DataFrame(columns=COLUMNAS_REGISTRO))
    hoy = estado[estado["provincia"].isin(provincias)]
    nuevas = pd.DataFrame({
        "fecha": f"{fecha:%Y-%m-%d}", "provincia": hoy["provincia"], "resultado": hoy["resultado"],
        # registros de esta descarga, aunque se haya descartado
        "registros": hoy["registros_intento"],
        "fuente": hoy["fuente"].where(hoy["resultado"] == "ok", ""), "detalle": hoy["detalle"]})
    registro = (pd.concat([previo, nuevas], ignore_index=True)
                .drop_duplicates(["fecha", "provincia"], keep="last")
                .sort_values(["fecha", "provincia"])[COLUMNAS_REGISTRO])
    ruta.parent.mkdir(parents=True, exist_ok=True)
    registro.to_csv(ruta, index=False, encoding="utf-8", lineterminator="\n")
    return str(ruta)
