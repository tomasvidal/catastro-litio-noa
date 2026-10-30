"""
Expedientes por año: los que se publican hoy y una estimacion de los que se abrieron.

La base solo trae los derechos que la provincia publica hoy, asi que contar filas por año
subestima los años viejos (los caducados o archivados ya no estan). Donde el numero de
expediente es un correlativo propio del catastro minero, el ultimo numero de cada año dice
hasta donde llego la numeracion: la diferencia con el ultimo del año anterior estima
cuantos expedientes se abrieron en total, se publiquen hoy o no.
"""

from __future__ import annotations

import re

import pandas as pd

# Años en que el numero es un correlativo del catastro minero (revisado con la base del
# 29/10/2026). Jujuy ('3428-T-2024'): correlativo desde 2002. Salta ('18746'): correlativo
# hasta 2019; desde mediados de 2020 los expedientes nuevos usan el numerador general de la
# provincia (700.000 en adelante), que no cuenta solo los de mineria. Antes de 1990 hay
# pocos expedientes por año y el ultimo numero no es confiable.
SERIES_CORRELATIVAS: dict[str, tuple[int, int | None]] = {
    "jujuy": (2002, None),
    "salta": (1990, 2019),
}
_NUMERO = {
    "jujuy": re.compile(r"^(\d+)\s*-\s*[A-Z]+\s*-\s*(?:19|20)\d{2}$"),
    "salta": re.compile(r"^(\d+)$"),
}
COLUMNAS = ["provincia", "anio", "publicados", "ultimo_numero", "abiertos_estimados"]


def numero_expediente(provincia: str, expediente) -> int | None:
    """Numero correlativo del expediente, o None si la provincia no usa uno reconocible."""
    patron = _NUMERO.get(provincia)
    m = patron.match(expediente.strip()) if patron and isinstance(expediente, str) else None
    return int(m.group(1)) if m else None


def _en_serie(provincia: str, anio: int) -> bool:
    desde, hasta = SERIES_CORRELATIVAS.get(provincia, (None, None))
    return desde is not None and anio >= desde and (hasta is None or anio <= hasta)


def expedientes_por_anio(base: pd.DataFrame) -> pd.DataFrame:
    """Una fila por provincia y año de expediente.

    - `publicados`: derechos de ese año que la provincia publica hoy.
    - `ultimo_numero`: el numero mas alto de ese año (solo dentro de la serie correlativa).
    - `abiertos_estimados`: `ultimo_numero` menos el del año anterior. Vacio en el primer año
      de la serie, si falta el año anterior o fuera de la serie.
    """
    b = base[["provincia", "expediente", "anio_expediente"]].copy()
    b["anio"] = pd.to_numeric(b["anio_expediente"], errors="coerce")
    b = b.dropna(subset=["anio"]).astype({"anio": int})
    b["numero"] = [numero_expediente(p, e) if _en_serie(p, a) else None
                   for p, e, a in zip(b["provincia"], b["expediente"], b["anio"])]
    b["numero"] = pd.to_numeric(b["numero"])

    t = (b.groupby(["provincia", "anio"])
         .agg(publicados=("expediente", "size"), ultimo_numero=("numero", "max"))
         .reset_index())
    anterior = t.assign(anio=t["anio"] + 1)[["provincia", "anio", "ultimo_numero"]]
    t = t.merge(anterior, on=["provincia", "anio"], how="left", suffixes=("", "_anterior"))
    abiertos = t["ultimo_numero"] - t["ultimo_numero_anterior"]
    t["abiertos_estimados"] = abiertos.where(abiertos > 0)  # un salto hacia atras no estima nada
    t["ultimo_numero"] = t["ultimo_numero"].astype("Int64")
    t["abiertos_estimados"] = t["abiertos_estimados"].astype("Int64")
    return t[COLUMNAS].sort_values(["provincia", "anio"]).reset_index(drop=True)
