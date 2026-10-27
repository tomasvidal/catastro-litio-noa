"""
Reconstruye el historial a partir de los crudos guardados en data/raw/, en orden de fecha.

Cada fecha se procesa como si fuera una corrida del pipeline: se estandariza, se asignan las
claves, se compara con el historial acumulado y se registran las novedades. La primera vez que
aparece una provincia es su punto de partida (no genera altas).

Uso:
    uv run python scripts/reconstruir_historial.py                    # escribe en data/historial/
    uv run python scripts/reconstruir_historial.py --salida /tmp/prueba
"""

from __future__ import annotations

import argparse
import re
import sys
import warnings
from collections import defaultdict
from pathlib import Path

import geopandas as gpd
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from catastro_noa import DATA_HISTORIAL, DATA_RAW, PROVINCIAS_ACTIVAS, auditoria  # noqa: E402
from catastro_noa.claves import asignar_claves  # noqa: E402
from catastro_noa.estandarizar import estandarizar  # noqa: E402
from catastro_noa.fuentes import Crudo, _fecha_de, leer_crudo  # noqa: E402
from catastro_noa.minerales import ClasificadorMinerales  # noqa: E402
from catastro_noa.snapshot import preparar  # noqa: E402
from catastro_noa.tramites import ClasificadorTramites  # noqa: E402


def crudos_por_fecha(provincias) -> dict:
    fechas = defaultdict(dict)
    for prov in provincias:
        for ruta in sorted((DATA_RAW / prov).glob(f"{prov}_*.*")):
            if re.search(r"_\d{8}\.", ruta.name) and ruta.suffix in (".zip", ".geojson", ".js", ".gpkg"):
                fechas[_fecha_de(ruta)][prov] = ruta
    return dict(sorted(fechas.items()))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--salida", type=Path, default=DATA_HISTORIAL)
    ap.add_argument("--provincias", nargs="+", default=list(PROVINCIAS_ACTIVAS))
    args = ap.parse_args()
    warnings.filterwarnings("ignore")
    sys.stdout.reconfigure(encoding="utf-8")

    for archivo in ("historial.parquet", "novedades.csv"):  # se reconstruye desde cero
        (args.salida / archivo).unlink(missing_ok=True)

    minerales, tramites = ClasificadorMinerales(), ClasificadorTramites()
    historial, todas = None, []
    for fecha, rutas in crudos_por_fecha(args.provincias).items():
        partes = [estandarizar(Crudo(p, leer_crudo(r), r, f"archivo crudo {r.name}", fecha, True), minerales, tramites)
                  for p, r in rutas.items()]
        base = gpd.GeoDataFrame(pd.concat(partes, ignore_index=True), crs="EPSG:4326")
        tabla, _ = preparar(base)
        tabla = asignar_claves(tabla, auditoria.vigentes(historial))
        novedades, historial = auditoria.aplicar(historial, tabla, fecha)
        todas.append(novedades)
        resumen = novedades["evento"].value_counts().to_dict() if len(novedades) else "sin novedades"
        print(f"{fecha}  {'+'.join(rutas)}  {len(tabla)} registros  ->  {resumen}")

    novedades = pd.concat(todas, ignore_index=True)
    auditoria.escribir(historial, novedades, args.salida)
    print(f"\n{len(novedades)} novedades, {len(historial)} versiones ({historial['vigente_hasta'].isna().sum()} vigentes)")
    print(f"Escrito en {args.salida}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
