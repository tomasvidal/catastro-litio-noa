"""
Pipeline: descarga + estandarizacion de los catastros, foto versionada y auditoria temporal.

Uso:
    uv run python -m catastro_noa                 # descarga las provincias activas y estandariza
    uv run python -m catastro_noa --offline       # usa los ultimos crudos de data/raw/
    uv run python -m catastro_noa --provincias jujuy salta catamarca
    uv run python -m catastro_noa --estricto      # termina con error si alguna provincia fallo

Cada provincia es independiente: si una no se puede descargar o procesar, las demas se
actualizan igual y la que fallo conserva en la foto (data/snapshot/) sus ultimos datos, sin
darle de baja ningun derecho. El resultado de cada una queda en data/estado_fuentes.csv.
"""

from __future__ import annotations

import argparse
import datetime as dt
import sys
import warnings

import geopandas as gpd
import pandas as pd

from . import PROVINCIAS, PROVINCIAS_ACTIVAS, auditoria, estado
from .claves import asignar_claves
from .estandarizar import estandarizar
from .fuentes import obtener
from .minerales import ClasificadorMinerales
from .salidas import escribir
from .snapshot import conservar, escribir_snapshot, preparar
from .tramites import ClasificadorTramites

# Si una provincia trae menos de esta fraccion de los derechos que tenia, se descarta la descarga:
# lo mas probable es una respuesta cortada o un cambio en la fuente, no bajas reales. Si la
# descarga siguiente trae la misma cantidad, se toma como real y se acepta (asi una baja masiva
# verdadera no deja a la provincia congelada).
MINIMO_RELATIVO = 0.5


def main() -> int:
    ap = argparse.ArgumentParser(prog="catastro_noa")
    ap.add_argument("--offline", action="store_true", help="no descargar; usar los crudos guardados")
    ap.add_argument("--provincias", nargs="+", choices=PROVINCIAS, default=list(PROVINCIAS_ACTIVAS))
    ap.add_argument("--estricto", action="store_true",
                    help="terminar con error si alguna provincia no se pudo actualizar "
                         "(las demas se escriben igual)")
    args = ap.parse_args()

    warnings.filterwarnings("ignore", message="Unverified HTTPS request")
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    minerales = ClasificadorMinerales()
    tramites = ClasificadorTramites()
    historial = auditoria.leer_historial()
    vig = auditoria.vigentes(historial)
    previos = vig["provincia"].value_counts().to_dict() if vig is not None else {}
    est = estado.leer()
    hoy = dt.date.today()

    partes, problemas, ok = [], [], []
    for prov in args.provincias:
        try:
            crudo = obtener(prov, offline=args.offline)
            df = estandarizar(crudo, minerales, tramites)
        except Exception as e:  # noqa: BLE001 - cualquier falla de una fuente no frena a las demas
            problemas.append(f"{prov}: {e}")
            detalle = str(e) if isinstance(e, (RuntimeError, ValueError)) else f"{type(e).__name__}: {e}"
            est = estado.registrar(est, prov, hoy, ok=False, detalle=detalle)
            print(f"[{prov}] SIN DATOS: {e}")
            continue
        aviso = ""
        if crudo.reutilizado and not args.offline:
            aviso = f"no se pudo descargar; se usó {crudo.archivo.name}"
        elif (previos.get(prov) and len(df) < MINIMO_RELATIVO * previos[prov]
              and len(df) != estado.registros_intento(est, prov)):
            aviso = (f"la descarga trajo {len(df)} registros y había {previos[prov]}: se descarta por "
                     "sospechosa (si la próxima trae lo mismo, se acepta)")
        if aviso:
            problemas.append(f"{prov}: {aviso}")
            est = estado.registrar(est, prov, crudo.fecha, ok=False, registros=len(df), detalle=aviso)
        else:
            ok.append(prov)
            est = estado.registrar(est, prov, crudo.fecha, ok=True, registros=len(df), fuente=crudo.fuente)
        partes.append(df)
        print(f"[{prov}] {len(df)} registros <- {crudo.fuente}" + (f"  ({aviso})" if aviso else ""))

    rutas, novedades = {}, None
    if not args.offline:
        rutas["estado"] = estado.escribir(est)
    if partes:
        base = gpd.GeoDataFrame(pd.concat(partes, ignore_index=True), crs="EPSG:4326")
        rutas |= escribir(base)
        nuevas = base[base["provincia"].isin(ok)]
        if len(nuevas):  # con --offline tambien: sirve para regenerar la foto tras cambiar un diccionario
            fecha = nuevas["fecha_descarga"].max()
            tabla, geoms = preparar(nuevas)
            tabla = asignar_claves(tabla, vig)
            novedades, historial = auditoria.aplicar(historial, tabla, fecha)
            fallidas = [p for p in PROVINCIAS_ACTIVAS if p not in ok]
            tabla, geoms = conservar(tabla, geoms, fallidas)
            rutas |= escribir_snapshot(tabla, geoms)
            rutas |= auditoria.escribir(historial, novedades)

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
        print(f"{'ERROR' if args.estricto else 'ATENCION'}: {p}")
    if not partes:
        print("No se obtuvo ninguna provincia.")
        return 1
    return 1 if args.estricto and problemas else 0


if __name__ == "__main__":
    sys.exit(main())
