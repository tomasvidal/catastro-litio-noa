"""
Clave comparable del titular (concesionario).

No reemplaza al titular publicado: es una columna extra pensada para agrupar y
cruzar entre provincias. Ej.:
    'LITHIUM S. CORPORATION S. A.' (Jujuy) y 'LITHIUM S CORPORATION S.A.' (Salta)
    -> 'LITHIUM S CORPORATION SA'
"""

from __future__ import annotations

import re

from .texto import clave, limpiar

# Textos que aparecen en el campo titular pero no son un titular.
_NO_TITULAR = {"VACANCIA SOLICITADA", "SIN DATOS", "SIN TITULAR", "S D"}

_FORMAS = [  # forma juridica larga -> sigla (sobre texto ya en mayusculas y sin acentos)
    (r"\bSOCIEDAD ANONIMA CON PARTICIPACION ESTATAL MAYORITARIA\b", "SAPEM"),
    (r"\bSOCIEDAD ANONIMA UNIPERSONAL\b", "SAU"),
    (r"\bSOCIEDAD ANONIMA\b", "SA"),
    (r"\bSOCIEDAD DE RESPONSABILIDAD LIMITADA\b", "SRL"),
    (r"\bSOCIEDAD DEL ESTADO\b", "SE"),
]


def _juntar_siglas(s: str) -> str:
    """'S A U' -> 'SAU', 'Y M A D' -> 'YMAD' (secuencias de letras sueltas)."""
    return re.sub(r"\b[A-Z](?: [A-Z]\b)+", lambda m: m.group(0).replace(" ", ""), s)


def clave_titular(v) -> str | None:
    s = limpiar(v)
    if s is None:
        return None
    k = clave(s)
    if k is None or k in _NO_TITULAR:
        return None
    for patron, sigla in _FORMAS:
        k = re.sub(patron, sigla, k)
    return _juntar_siglas(k)


def titular_publicado(v) -> str | None:
    """Titular tal cual lo publica la fuente, salvo los textos que no son titulares."""
    s = limpiar(v)
    return None if s is None or clave(s) in _NO_TITULAR else s
