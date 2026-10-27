"""
Foto versionada del catastro, en data/snapshot/ (es lo que commitea el robot):

  catastro_noa.csv     atributos de cada derecho + geom_hash. Sin geometria, ordenado y sin
                       columnas que cambian en cada corrida: un diff de git muestra solo
                       cambios reales.
  geometrias.parquet   un poligono por geom_hash (GeoParquet, EPSG:4326). Solo se reescribe si
                       cambia el conjunto de poligonos.

El hash se calcula sobre el poligono normalizado (coordenadas a 6 decimales, ~0.1 m, y vertices
en orden canonico), asi que no cambia por ruido de punto flotante ni por el orden de los
vertices: cambia solo si cambia la forma.
"""

from __future__ import annotations

import hashlib

import geopandas as gpd
import pandas as pd
import shapely

from . import DATA_SNAPSHOT

PRECISION = 1e-6
# Cambian en cada corrida aunque el catastro sea el mismo. fecha_actualizacion_fuente es la
# fecha de generacion del archivo de Jujuy: se repite igual en todas las filas.
VOLATILES = ["fuente", "fecha_descarga", "fecha_actualizacion_fuente"]
ORDEN = ["provincia", "expediente", "nombre", "geom_hash", "id_fuente"]


def normalizar(geom):
    """Poligono con coordenadas a PRECISION y orden canonico de vertices (None si no hay)."""
    if geom is None or geom.is_empty:
        return None
    return shapely.normalize(shapely.set_precision(geom, PRECISION))


def hash_geometria(geom) -> str | None:
    g = normalizar(geom)
    return None if g is None else hashlib.sha1(shapely.to_wkb(g)).hexdigest()[:16]


def preparar(base: gpd.GeoDataFrame) -> tuple[pd.DataFrame, gpd.GeoDataFrame]:
    """Devuelve (tabla de atributos con geom_hash, tabla hash -> poligono)."""
    normalizadas = base.geometry.map(normalizar)
    hashes = normalizadas.map(lambda g: None if g is None else hashlib.sha1(shapely.to_wkb(g)).hexdigest()[:16])

    tabla = pd.DataFrame(base.drop(columns=["geometry", *VOLATILES]))
    tabla["geom_hash"] = hashes.values
    tabla = tabla.sort_values(ORDEN, na_position="last").reset_index(drop=True)

    geoms = (gpd.GeoDataFrame({"geom_hash": hashes.values}, geometry=normalizadas.values, crs=base.crs)
             .dropna(subset=["geom_hash"]).drop_duplicates("geom_hash")
             .sort_values("geom_hash").reset_index(drop=True))
    return tabla, geoms


def escribir_snapshot(base: gpd.GeoDataFrame) -> dict[str, str]:
    DATA_SNAPSHOT.mkdir(parents=True, exist_ok=True)
    ruta_csv = DATA_SNAPSHOT / "catastro_noa.csv"
    ruta_geo = DATA_SNAPSHOT / "geometrias.parquet"

    tabla, geoms = preparar(base)
    # lineterminator fijo: el default depende del SO y el robot corre en Linux.
    tabla.to_csv(ruta_csv, index=False, encoding="utf-8", lineterminator="\n")

    previos = set(pd.read_parquet(ruta_geo, columns=["geom_hash"])["geom_hash"]) if ruta_geo.exists() else None
    if previos != set(geoms["geom_hash"]):
        geoms.to_parquet(ruta_geo, index=False)
    return {"snapshot_csv": str(ruta_csv), "snapshot_geometrias": str(ruta_geo)}
