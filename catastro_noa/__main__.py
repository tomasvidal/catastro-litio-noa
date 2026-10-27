"""
Pipeline de la Fase 2: descarga + estandarizacion de los tres catastros.

Uso:
    uv run python -m catastro_noa                 # descarga las provincias activas y estandariza
    uv run python -m catastro_noa --offline       # usa los ultimos crudos de data/raw/
    uv run python -m catastro_noa --provincias jujuy salta catamarca
    uv run python -m catastro_noa --estricto      # falla si alguna provincia no se pudo descargar

La foto versionada (data/snapshot/) solo se escribe si estan todas las provincias activas:
una foto parcial parecería que a las otras se les dieron de baja todos los derechos.
"""

from __future__ import annotations

import argparse
import sys
import warnings

import geopandas as gpd
import pandas as pd

from . import PROVINCIAS, PROVINCIAS_ACTIVAS, auditoria
from .claves import asignar_claves
from .estandarizar import estandarizar
from .fuentes import obtener
from .minerales import ClasificadorMinerales
from .salidas import escribir
from .snapshot import escribir_snapshot, preparar
from .tramites import ClasificadorTramites


def main() -> int:
    ap = argparse.ArgumentParser(prog="catastro_noa")
    ap.add_argument("--offline", action="store_true", help="no descargar; usar los crudos guardados")
    ap.add_argument("--provincias", nargs="+", choices=PROVINCIAS, default=list(PROVINCIAS_ACTIVAS))
    ap.add_argument("--estricto", action="store_true",
                    help="terminar con error (sin escribir nada) si una provincia no se pudo descargar")
    args = ap.parse_args()

    warnings.filterwarnings("ignore", message="Unverified HTTPS request")
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    minerales = ClasificadorMinerales()
    tramites = ClasificadorTramites()

    partes, problemas, ok = [], [], []
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
        if not (crudo.reutilizado and not args.offline):
            ok.append(prov)
        aviso = "  (crudo reutilizado)" if crudo.reutilizado and not args.offline else ""
        print(f"[{prov}] {len(df)} registros <- {crudo.fuente}{aviso}")

    if not partes:
        print("No se obtuvo ninguna provincia.")
        return 1
    if args.estricto and problemas:
        for p in problemas:
            print(f"ERROR: {p}")
        return 1

    base = gpd.GeoDataFrame(pd.concat(partes, ignore_index=True), crs="EPSG:4326")
    rutas = escribir(base)
    novedades = None
    if set(PROVINCIAS_ACTIVAS) <= set(ok):
        fecha = base["fecha_descarga"].max()
        tabla, geoms = preparar(base)
        historial = auditoria.leer_historial()
        tabla = asignar_claves(tabla, auditoria.vigentes(historial))
        novedades, historial = auditoria.aplicar(historial, tabla, fecha)
        rutas |= escribir_snapshot(tabla, geoms)
        rutas |= auditoria.escribir(historial, novedades)
    else:
        problemas.append("no se actualizó data/snapshot/: faltan provincias activas o se usó un crudo viejo")

    sin_min = base["mineral_sin_clasificar"].notna().sum()
    sin_etapa = (base["tramite_original"].notna() & base["etapa_proyecto"].isna()).sum()
    sin_estado = (base["estado_original"].notna() & base["estado"].isna()).sum()
    print(f"\nTotal: {len(base)} registros | con litio: {int(base['tiene_litio'].sum())}")
    print(f"Revisar: {sin_min} con texto de mineral sin clasificar, "
          f"{sin_etapa} con trámite sin etapa, {sin_estado} con estado sin homologar")
    for k, v in rutas.items():
        print(f"  {k:8s} -> {v}")
    if novedades is not None:
        print(f"Novedades: {len(novedades)}" + (f" ({novedades['evento'].value_counts().to_dict()})" if len(novedades) else ""))
    for p in problemas:
        print(f"ATENCION: {p}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
