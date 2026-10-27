"""
Clasificacion del campo "mineral" de los catastros.

Cada provincia escribe los minerales a su manera:
  - Jujuy     : 'DISEMINADO DE COBRE, ORO, PLATA Y SALES ALCALINAS', '1 Y 2'
  - Salta     : 'BORATOS,K,Li' (simbolos quimicos + nombres, separados por coma)
  - Catamarca : 'Litio, Potasio y Cloruros'

A partir de diccionarios/minerales.csv (armado con las planillas del equipo de
investigacion) se obtiene, para cada texto:
  - minerales        : nombres canonicos encontrados ('Cobre; Oro; Plata')
  - grupos           : grupos del equipo ('Metalíferos; Litio y potasio')
  - categoria        : categoria del Codigo de Mineria si el texto la menciona ('1', '2', '1 y 2')
  - sin_clasificar   : lo que quedo sin reconocer, para revisar y sumar al diccionario

Reglas:
  - Los nombres se buscan como palabras completas, sin acentos ni mayusculas, y
    primero los mas largos ('SULFATO DE SODIO' gana sobre 'SODIO'). Cada palabra
    admite plural ('BORATOS' matchea 'Borato').
  - Los simbolos ('Li', 'Cu') se buscan respetando mayusculas. Los de una sola
    letra ('K', 'U', 'Y') solo cuentan si son un item suelto de una lista
    separada por comas, para no confundir la 'Y' de 'ORO Y PLATA' con el itrio.
  - 'Diseminado' es un tipo de deposito: solo se cuenta como mineral (grupo
    Metalíferos) cuando no aparece ningun otro mineral en el texto.
  - Los terminos de tipo 'no_mineral' (campamento, colas, relaves...) son instalaciones
    de las servidumbres: no suman minerales y, si aparecen, lo que sobra del texto
    (nombres de minas, expedientes) no se marca como sin clasificar.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from . import DICCIONARIOS
from .texto import alinear, limpiar

GRUPOS = (
    "Metalíferos",
    "Litio y potasio",
    "Depósitos evaporíticos",
    "Tierras raras",
    "Canteras, rocas de aplicación y otros minerales",
)
DISEMINADO = "Diseminado"

# Palabras que no aportan y no deben figurar como "sin clasificar".
_RELLENO = {"DE", "DEL", "Y", "E", "O", "CON", "LOS", "LAS", "LA", "EL", "OTROS", "OTRAS",
            "OTRO", "OTRA", "MINERALES", "MINERAL", "ASOCIADOS", "MISMOS", "SUS", "SU"}

_ORD1 = r"(?:1|1RA|1ERA|1O|PRIMERA)"
_ORD2 = r"(?:2|2DA|2RA|2O|SEGUNDA)"
_CAT = r"(?:CAT|CATEG|CATEGORIA|CATEGORIAS)"
_CATEGORIAS = [  # (patron sobre el texto alineado, categorias que indica)
    (re.compile(rf"\b{_ORD1}\s+Y\s+{_ORD2}\s+{_CAT}\b"), {"1", "2"}),
    (re.compile(rf"\b{_CAT}\s+1\s+Y\s+2\b"), {"1", "2"}),
    (re.compile(rf"\b{_ORD1}\s+{_CAT}\b|\b{_CAT}\s+1\b"), {"1"}),
    (re.compile(rf"\b{_ORD2}\s+{_CAT}\b|\b{_CAT}\s+2\b"), {"2"}),
]
# Textos que son solo la categoria: '1', '2', '1 Y 2', '1 y2', '12.0', '1.0'
_SOLO_CATEGORIA = re.compile(r"\s*(1|2|12|1\s*Y\s*2)(\s+0)?\s*")


@dataclass
class Resultado:
    minerales: list[str] = field(default_factory=list)
    grupos: list[str] = field(default_factory=list)
    categoria: str | None = None
    sin_clasificar: str | None = None


def _patron_nombre(termino: str) -> re.Pattern:
    palabras = alinear(termino).split()
    cuerpo = r"\s+".join(re.escape(p) + r"(?:S|ES)?" for p in palabras)
    return re.compile(rf"(?<![A-Z0-9]){cuerpo}(?![A-Z0-9])")


def _texto_categoria(cats: set[str]) -> str | None:
    if not cats:
        return None
    return "1 y 2" if cats == {"1", "2"} else next(iter(cats))


class ClasificadorMinerales:
    def __init__(self, ruta: Path = DICCIONARIOS / "minerales.csv"):
        d = pd.read_csv(ruta, dtype=str, keep_default_na=False)
        self.grupo_de: dict[str, str] = {}
        self.simbolos: dict[str, str] = {}
        nombres: list[tuple[int, re.Pattern, str | None, bool]] = []
        for r in d.itertuples(index=False):
            if r.tipo == "simbolo":
                self.simbolos[r.termino.strip()] = r.mineral
            else:
                mineral = r.mineral or None  # los modificadores y no_mineral no tienen mineral
                nombres.append((len(alinear(r.termino).strip()), _patron_nombre(r.termino),
                                mineral, r.tipo == "no_mineral"))
            if r.mineral:
                self.grupo_de[r.mineral] = r.grupo
        # Primero los terminos mas largos.
        self.nombres = [(p, m, nm) for _, p, m, nm in sorted(nombres, key=lambda x: -x[0])]

    def clasificar(self, valor) -> Resultado:
        s = limpiar(valor)
        if s is None:
            return Resultado()

        texto = alinear(s)
        if _SOLO_CATEGORIA.fullmatch(texto):
            n = re.sub(r"\s+0$", "", texto.strip())
            return Resultado(categoria={"1": "1", "2": "2"}.get(n, "1 y 2"))

        encontrados: list[tuple[int, str]] = []  # (posicion, mineral)
        tapado = list(texto)

        def tapar(ini: int, fin: int) -> None:
            tapado[ini:fin] = " " * (fin - ini)

        # 1) Simbolos (respetando mayusculas), sobre el texto original.
        for m in re.finditer(r"[^,;/?]+", s):
            item = m.group(0).strip()
            if item in self.simbolos:
                encontrados.append((m.start(), self.simbolos[item]))
                tapar(m.start(), m.end())
                continue
            for w in re.finditer(r"[A-Za-z]+", m.group(0)):
                if len(w.group(0)) > 1 and w.group(0) in self.simbolos:
                    ini = m.start() + w.start()
                    encontrados.append((ini, self.simbolos[w.group(0)]))
                    tapar(ini, ini + len(w.group(0)))

        # 2) Categoria del Codigo de Mineria.
        cats: set[str] = set()
        for patron, indica in _CATEGORIAS:
            for m in patron.finditer("".join(tapado)):
                cats |= indica
                tapar(m.start(), m.end())

        # 3) Nombres, de mas largo a mas corto.
        es_no_mineral = False
        for patron, mineral, no_mineral in self.nombres:
            for m in patron.finditer("".join(tapado)):
                if mineral:
                    encontrados.append((m.start(), mineral))
                es_no_mineral |= no_mineral
                tapar(m.start(), m.end())

        minerales: list[str] = []
        for _, mineral in sorted(encontrados):
            if mineral not in minerales:
                minerales.append(mineral)
        if len(minerales) > 1 and DISEMINADO in minerales:
            minerales.remove(DISEMINADO)

        grupos_presentes = {self.grupo_de[m] for m in minerales}
        resto = [w for w in "".join(tapado).split() if w not in _RELLENO]
        return Resultado(
            minerales=minerales,
            grupos=[g for g in GRUPOS if g in grupos_presentes],
            categoria=_texto_categoria(cats),
            # Si el texto describe una instalacion, el resto son nombres de minas y expedientes.
            sin_clasificar=None if es_no_mineral else (" ".join(resto) or None),
        )
