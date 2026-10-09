"""Funciones chicas de limpieza de texto, compartidas por todo el pipeline."""

from __future__ import annotations

import re
import unicodedata

import pandas as pd

# Valores que en las fuentes significan "sin dato".
_VACIOS = re.compile(r"^[\s\-_.?]*$")


def limpiar(v) -> str | None:
    """Texto prolijo: NFC, sin saltos de linea ni espacios repetidos. Vacios -> None."""
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return None
    s = unicodedata.normalize("NFC", str(v))
    s = re.sub(r"\s+", " ", s).strip()
    return None if _VACIOS.match(s) else s


def _base(c: str) -> str:
    """Un caracter -> su letra base en mayuscula ('á' -> 'A', 'º' -> 'O'), o espacio."""
    d = unicodedata.normalize("NFKD", c)
    d = "".join(x for x in d if not unicodedata.combining(x))[:1].upper()
    return d if d.isalnum() else " "


def alinear(s: str) -> str:
    """Mayusculas, sin acentos y con todo lo que no es letra/numero como espacio.

    Mantiene la longitud del texto (un caracter por caracter), asi las posiciones
    de lo que se encuentra en el resultado coinciden con las del original.
    """
    return "".join(_base(c) for c in s)


def clave(v) -> str | None:
    """Version comparable de un texto: 'Doña  Pancha.' -> 'DONA PANCHA'."""
    s = limpiar(v)
    if s is None:
        return None
    s = re.sub(r"\s+", " ", alinear(s)).strip()
    return s or None


def numero(v) -> float | None:
    """'11,5395 ha' -> 11.5395 ; '1.234,5' -> 1234.5 ; 4978.6 -> 4978.6 ; basura -> None."""
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v)
    if "," in s:
        s = s.replace(".", "").replace(",", ".")
    s = re.sub(r"[^\d.\-]", "", s)
    try:
        return float(s)
    except ValueError:
        return None
