"""
Tipo de tramite y estado legal.

Se generan dos columnas (criterio acordado con el equipo de investigacion):
  - etapa_administrativa : la categoria propia de cada provincia, prolija
                           (permite detectar avances finos, ej. cateo -> manifestacion).
  - etapa_proyecto       : categoria comun para comparar entre provincias
                           (Exploración / Explotación / Canteras y otros).
Ademas se homologa el estado legal (Vigente / En trámite / Vacante / ...).

Las reglas viven en diccionarios/etapas.csv y diccionarios/estados.csv.
"""

from __future__ import annotations

import re
from pathlib import Path

import pandas as pd

from . import DICCIONARIOS
from .texto import clave


class ClasificadorTramites:
    def __init__(self, etapas: Path = DICCIONARIOS / "etapas.csv",
                 estados: Path = DICCIONARIOS / "estados.csv"):
        e = pd.read_csv(etapas, dtype=str, keep_default_na=False)
        self.etapas = {(r.provincia, clave(r.tramite_original)): (r.etapa_administrativa, r.etapa_proyecto)
                       for r in e.itertuples(index=False)}
        s = pd.read_csv(estados, dtype=str, keep_default_na=False)
        self.estados = [(r.provincia, re.compile(r.patron), r.estado) for r in s.itertuples(index=False)]

    def etapa(self, provincia: str, tramite) -> tuple[str | None, str | None]:
        """-> (etapa_administrativa, etapa_proyecto). Si el tramite no esta en el
        diccionario se devuelve (None, None) y aparece en el reporte de revision."""
        k = clave(tramite)
        if k is None:
            return None, None
        return self.etapas.get((provincia, k), (None, None))

    def estado(self, provincia: str, estado) -> str | None:
        k = clave(estado)
        if k is None:
            return None
        for prov, patron, valor in self.estados:
            if prov == provincia and patron.search(k):
                return valor
        return None
