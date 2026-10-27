"""
Esquema canonico: lleva el catastro crudo de cada provincia a las mismas columnas.

El detalle de cada columna esta en docs/diccionario_de_datos.md.
Campos de contacto personal (ej. `dom_corre` de Jujuy) NO se copian nunca.
"""

from __future__ import annotations

import datetime as dt

import geopandas as gpd
import pandas as pd
import shapely
from pyproj import Geod

from .fuentes import Crudo
from .minerales import ClasificadorMinerales
from .texto import clave, limpiar, numero
from .titulares import clave_titular, titular_publicado
from .tramites import ClasificadorTramites

COLUMNAS = [
    "provincia", "id_fuente", "expediente", "nombre", "titular", "titular_clave",
    "tramite_original", "estado_original", "etapa_administrativa", "etapa_proyecto", "estado",
    "mineral_original", "minerales", "grupos_minerales", "categoria_codigo", "tiene_litio",
    "mineral_sin_clasificar", "departamento", "superficie_ha_fuente", "superficie_ha_calculada",
    "fecha_inicio", "fecha_actualizacion_fuente", "fuente", "fecha_descarga", "geometry",
]

_GEOD = Geod(ellps="WGS84")


def _col(gdf: gpd.GeoDataFrame, *nombres: str) -> pd.Series:
    """Primera columna que exista entre `nombres` (las capas cambian de nombre de campo)."""
    for n in nombres:
        if n in gdf.columns:
            return gdf[n]
    return pd.Series([None] * len(gdf), index=gdf.index, dtype=object)


def _fecha(s: pd.Series) -> pd.Series:
    return pd.to_datetime(s, errors="coerce").dt.date


# --------------------------------------------------------------------------- por provincia
def _jujuy(g: gpd.GeoDataFrame) -> pd.DataFrame:
    return pd.DataFrame({
        "id_fuente": _col(g, "id"),
        "expediente": _col(g, "expediente"),
        "nombre": _col(g, "nombre"),
        "titular": _col(g, "titular_ac"),
        "tramite_original": _col(g, "rg_tipo"),
        "estado_original": _col(g, "estado"),
        "mineral_original": _col(g, "tipo_miner"),
        "departamento": _col(g, "depto"),
        "superficie_ha_fuente": _col(g, "superficie").map(numero),
        "fecha_inicio": None,
        "fecha_actualizacion_fuente": _fecha(_col(g, "revision")),
    }, index=g.index)


def _salta(g: gpd.GeoDataFrame) -> pd.DataFrame:
    return pd.DataFrame({
        "id_fuente": _col(g, "fid"),
        "expediente": _col(g, "expediente"),
        "nombre": _col(g, "nombre"),
        "titular": _col(g, "concesionario"),
        "tramite_original": _col(g, "tipo"),
        "estado_original": _col(g, "estado"),
        "mineral_original": _col(g, "mineral"),
        "departamento": _col(g, "departamento"),
        "superficie_ha_fuente": _col(g, "area").map(numero),  # '22,4675 ha'
        "fecha_inicio": _fecha(_col(g, "fecha_inicio")),
        "fecha_actualizacion_fuente": None,
    }, index=g.index)


def _catamarca(g: gpd.GeoDataFrame) -> pd.DataFrame:
    # WFS: campos en minuscula (exptedgtl, mina, concsrio...). Visor: en mayuscula.
    expediente = _col(g, "EXPEDIENTE", "expediente").map(limpiar)
    expediente = expediente.fillna(_col(g, "EXPTE DGTL", "exptedgtl").map(limpiar))
    return pd.DataFrame({
        "id_fuente": _col(g, "fid", "FID", "id"),
        "expediente": expediente,
        "nombre": _col(g, "MINA", "mina"),
        "titular": _col(g, "CONCSRIO", "concsrio"),
        "tramite_original": _col(g, "TIPO", "tipo"),     # hoy no se publica
        "estado_original": _col(g, "ESTADO", "estado"),  # hoy no se publica
        "mineral_original": _col(g, "MINERAL", "mineral"),
        "departamento": _col(g, "DPTO", "dpto"),
        "superficie_ha_fuente": _col(g, "SUPERFICIE", "superficie").map(numero),
        "fecha_inicio": None,
        "fecha_actualizacion_fuente": None,
    }, index=g.index)


_POR_PROVINCIA = {"jujuy": _jujuy, "salta": _salta, "catamarca": _catamarca}


# --------------------------------------------------------------------------- geometria
def _solo_poligonos(geom):
    """make_valid puede devolver colecciones con lineas/puntos sueltos: se quedan los poligonos."""
    if geom is None or geom.is_empty:
        return None
    if not geom.is_valid:
        geom = shapely.make_valid(geom)
    if geom.geom_type in ("Polygon", "MultiPolygon"):
        return geom
    polis = [p for p in getattr(geom, "geoms", []) if p.geom_type in ("Polygon", "MultiPolygon")]
    return shapely.unary_union(polis) if polis else None


def _hectareas(geom) -> float | None:
    if geom is None:
        return None
    area, _ = _GEOD.geometry_area_perimeter(geom)
    return round(abs(area) / 10_000, 4)


# --------------------------------------------------------------------------- principal
def estandarizar(crudo: Crudo, minerales: ClasificadorMinerales,
                 tramites: ClasificadorTramites, fecha_descarga: dt.date | None = None) -> gpd.GeoDataFrame:
    prov = crudo.provincia
    g = crudo.gdf
    if g.crs is None:
        g = g.set_crs("EPSG:4326")
    g = g.to_crs("EPSG:4326")

    df = _POR_PROVINCIA[prov](g)
    for c in ("expediente", "nombre", "tramite_original", "estado_original", "mineral_original"):
        df[c] = df[c].map(limpiar)
    df["id_fuente"] = df["id_fuente"].map(lambda v: None if v is None or pd.isna(v) else str(v).removesuffix(".0"))
    df.insert(0, "provincia", prov)

    df["titular_clave"] = df["titular"].map(clave_titular)
    df["titular"] = df["titular"].map(titular_publicado)
    df["departamento"] = df["departamento"].map(lambda v: clave(str(v).strip('{}"')) if limpiar(v) else None)

    etapas = df["tramite_original"].map(lambda t: tramites.etapa(prov, t))
    df["etapa_administrativa"] = etapas.str[0]
    df["etapa_proyecto"] = etapas.str[1]
    df["estado"] = [tramites.estado(prov, e, tr) for e, tr in zip(df["estado_original"], df["tramite_original"])]

    res = df["mineral_original"].map(minerales.clasificar)
    df["minerales"] = res.map(lambda r: "; ".join(r.minerales) or None)
    df["grupos_minerales"] = res.map(lambda r: "; ".join(r.grupos) or None)
    df["categoria_codigo"] = res.map(lambda r: r.categoria)
    df["tiene_litio"] = res.map(lambda r: "Litio" in r.minerales)
    df["mineral_sin_clasificar"] = res.map(lambda r: r.sin_clasificar)

    geoms = g.geometry.map(_solo_poligonos)
    df["superficie_ha_calculada"] = geoms.map(_hectareas)
    df["fuente"] = crudo.fuente
    df["fecha_descarga"] = fecha_descarga or crudo.fecha

    out = gpd.GeoDataFrame(df, geometry=geoms.values, crs="EPSG:4326")
    return out[COLUMNAS].reset_index(drop=True)
