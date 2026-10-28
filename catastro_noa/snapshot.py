"""
Foto versionada del catastro, en data/snapshot/ (es lo que commitea el robot):

  catastro_noa.csv     clave + atributos de cada derecho + geom_hash. Sin geometria, ordenado y sin
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
# fecha de generacion del archivo de Jujuy: se repite igual en todas las filas. id_fuente es el
# id interno de la fuente y Salta lo regenera entero (se vio al comparar dos descargas).
VOLATILES = ["fuente", "fecha_descarga", "fecha_actualizacion_fuente", "id_fuente"]
ORDEN = ["provincia", "expediente", "nombre", "geom_hash", "titular_clave", "tramite_original"]


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
    orden = [c for c in ORDEN if c in tabla]
    tabla = tabla.sort_values(orden, na_position="last", kind="stable").reset_index(drop=True)

    geoms = (gpd.GeoDataFrame({"geom_hash": hashes.values}, geometry=normalizadas.values, crs=base.crs)
             .dropna(subset=["geom_hash"]).drop_duplicates("geom_hash")
             .sort_values("geom_hash").reset_index(drop=True))
    return tabla, geoms


def conservar(tabla: pd.DataFrame, geoms: gpd.GeoDataFrame,
              provincias: list[str]) -> tuple[pd.DataFrame, gpd.GeoDataFrame]:
    """Agrega a la foto nueva las filas y poligonos de la foto anterior de `provincias` (las que no
    se pudieron descargar), para que sigan publicadas con sus ultimos datos."""
    ruta_csv, ruta_geo = DATA_SNAPSHOT / "catastro_noa.csv", DATA_SNAPSHOT / "geometrias.parquet"
    if not provincias or not ruta_csv.exists():
        return tabla, geoms
    # Como texto: las filas conservadas se vuelven a escribir igual que estaban.
    previa = pd.read_csv(ruta_csv, dtype=str)
    previa = previa[previa["provincia"].isin(provincias)]
    if previa.empty:
        return tabla, geoms
    tabla = pd.concat([tabla, previa], ignore_index=True)
    orden = [c for c in ORDEN if c in tabla]
    tabla = tabla.sort_values(orden, na_position="last", kind="stable").reset_index(drop=True)
    if ruta_geo.exists():
        viejas = gpd.read_parquet(ruta_geo)
        viejas = viejas[viejas["geom_hash"].isin(previa["geom_hash"].dropna())]
        geoms = (gpd.GeoDataFrame(pd.concat([geoms, viejas], ignore_index=True), crs=geoms.crs)
                 .drop_duplicates("geom_hash").sort_values("geom_hash").reset_index(drop=True))
    return tabla, geoms


def escribir_snapshot(tabla: pd.DataFrame, geoms: gpd.GeoDataFrame) -> dict[str, str]:
    """Escribe la foto. `tabla` y `geoms` son lo que devuelve `preparar`; la clave
    (catastro_noa.claves) ya tiene que estar asignada."""
    DATA_SNAPSHOT.mkdir(parents=True, exist_ok=True)
    ruta_csv = DATA_SNAPSHOT / "catastro_noa.csv"
    ruta_geo = DATA_SNAPSHOT / "geometrias.parquet"

    # lineterminator fijo: el default depende del SO y el robot corre en Linux.
    tabla.to_csv(ruta_csv, index=False, encoding="utf-8", lineterminator="\n")

    previos = set(pd.read_parquet(ruta_geo, columns=["geom_hash"])["geom_hash"]) if ruta_geo.exists() else None
    if previos != set(geoms["geom_hash"]):
        geoms.to_parquet(ruta_geo, index=False)
    return {"snapshot_csv": str(ruta_csv), "snapshot_geometrias": str(ruta_geo)}
