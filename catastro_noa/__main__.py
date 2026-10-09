"""
Pipeline de la Fase 2: descarga + estandarizacion de los tres catastros.

Uso:
    uv run python -m catastro_noa                 # descarga las provincias activas y estandariza
    uv run python -m catastro_noa --offline       # usa los ultimos crudos de data/raw/
    uv run python -m catastro_noa --provincias jujuy salta catamarca
"""

from __future__ import annotations

import argparse
import sys
import warnings

import geopandas as gpd
import pandas as pd

from . import PROVINCIAS, PROVINCIAS_ACTIVAS
from .estandarizar import estandarizar
from .fuentes import obtener
from .minerales import ClasificadorMinerales
from .salidas import escribir
from .tramites import ClasificadorTramites


def main() -> int:
    ap = argparse.ArgumentParser(prog="catastro_noa")
    ap.add_argument("--offline", action="store_true", help="no descargar; usar los crudos guardados")
    ap.add_argument("--provincias", nargs="+", choices=PROVINCIAS, default=list(PROVINCIAS_ACTIVAS))
    args = ap.parse_args()

    warnings.filterwarnings("ignore", message="Unverified HTTPS request")
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    minerales = ClasificadorMinerales()
    tramites = ClasificadorTramites()

    partes, problemas = [], []
    for prov in args.provincias:
        try:
            crudo = obtener(prov, offline=args.offline)
        except RuntimeError as e:
            problemas.append(str(e))
            print(f"[{prov}] SIN DATOS: {e}")
            continue
        if crudo.reutilizado and not args.offline:
            problemas.append(f"{prov}: no se pudo descargar; se usó {crudo.archivo.name}")
        df = estandarizar(crudo, minerales, tramites)
        partes.append(df)
        aviso = "  (crudo reutilizado)" if crudo.reutilizado and not args.offline else ""
        print(f"[{prov}] {len(df)} registros <- {crudo.fuente}{aviso}")

    if not partes:
        print("No se obtuvo ninguna provincia.")
        return 1

    base = gpd.GeoDataFrame(pd.concat(partes, ignore_index=True), crs="EPSG:4326")
    rutas = escribir(base)

    sin_min = base["mineral_sin_clasificar"].notna().sum()
    sin_etapa = (base["tramite_original"].notna() & base["etapa_proyecto"].isna()).sum()
    sin_estado = (base["estado_original"].notna() & base["estado"].isna()).sum()
    print(f"\nTotal: {len(base)} registros | con litio: {int(base['tiene_litio'].sum())}")
    print(f"Revisar: {sin_min} con texto de mineral sin clasificar, "
          f"{sin_etapa} con trámite sin etapa, {sin_estado} con estado sin homologar")
    for k, v in rutas.items():
        print(f"  {k:8s} -> {v}")
    for p in problemas:
        print(f"ATENCION: {p}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
