"""Pipeline de ingesta y estandarizacion de los catastros mineros del NOA."""

from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
DATA_RAW = RAIZ / "data" / "raw"
DATA_PROCESSED = RAIZ / "data" / "processed"
DATA_SNAPSHOT = RAIZ / "data" / "snapshot"
DATA_HISTORIAL = RAIZ / "data" / "historial"
ESTADO_FUENTES = RAIZ / "data" / "estado_fuentes.csv"
DICCIONARIOS = RAIZ / "diccionarios"

PROVINCIAS = ("jujuy", "salta", "catamarca")
# Catamarca queda en pausa: su servidor no responde (ver TAREAS.md). Se puede
# correr igual con `--provincias catamarca` o dejando un crudo en data/raw/catamarca/.
PROVINCIAS_ACTIVAS = ("jujuy", "salta")
