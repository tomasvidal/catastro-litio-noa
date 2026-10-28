"""
App de consulta del catastro minero de Jujuy y Salta.

Lee solo los archivos que versiona el workflow de actualizacion (data/snapshot/ y
data/historial/), asi que cada commit del robot actualiza la app sin pasos extra.

    uv run streamlit run streamlit_app.py
"""

import json

import geopandas as gpd
import pandas as pd
import pydeck as pdk
import streamlit as st

from catastro_noa import DATA_HISTORIAL, DATA_SNAPSHOT
from catastro_noa.minerales import GRUPOS
from catastro_noa.texto import clave

SIN_GRUPO = "Sin mineral informado"
PROVINCIAS = {"jujuy": "Jujuy", "salta": "Salta"}
ETAPAS = ("Exploración", "Explotación", "Canteras y otros")
COLORES_ETAPA = {  # RGBA para el mapa; mismos tonos que la leyenda
    "Exploración": [242, 183, 5, 150],
    "Explotación": [235, 87, 87, 150],
    "Canteras y otros": [120, 160, 200, 120],
}
COLOR_SIN_ETAPA = [160, 160, 160, 110]
EVENTOS = {
    "alta": "Alta",
    "baja": "Baja",
    "cambio_estado": "Cambio de estado",
    "cambio_etapa": "Cambio de etapa",
    "cambio_titular": "Cambio de titular",
    "cambio_mineral": "Cambio de mineral",
    "cambio_superficie": "Cambio de superficie",
    "cambio_geometria": "Cambio de límites",
    "cambio_expediente": "Cambio de expediente",
    "cambio_nombre": "Cambio de nombre",
}


@st.cache_data(ttl="1h")
def cargar_base() -> pd.DataFrame:
    b = pd.read_csv(DATA_SNAPSHOT / "catastro_noa.csv", dtype=str, keep_default_na=False)
    b["provincia_nombre"] = b["provincia"].map(PROVINCIAS).fillna(b["provincia"].str.title())
    b["superficie_ha"] = pd.to_numeric(b["superficie_ha_calculada"], errors="coerce")
    b["tiene_litio"] = b["tiene_litio"].eq("True")
    b["grupos"] = b["grupos_minerales"].map(lambda s: s.split("; ") if s else [SIN_GRUPO])
    b["titular_buscar"] = b["titular"].map(clave).fillna("")
    return b


@st.cache_data(ttl="1h")
def cargar_geometrias() -> gpd.GeoDataFrame:
    g = gpd.read_parquet(DATA_SNAPSHOT / "geometrias.parquet")
    # ~20 m de tolerancia: no cambia nada a la escala del mapa y aliviana el envio al navegador
    g["geometry"] = g.geometry.simplify(0.0002, preserve_topology=True)
    return g


@st.cache_data(ttl="1h")
def cargar_novedades() -> pd.DataFrame:
    n = pd.read_csv(DATA_HISTORIAL / "novedades.csv", dtype=str, keep_default_na=False)
    n["fecha"] = pd.to_datetime(n["fecha"])
    n["provincia_nombre"] = n["provincia"].map(PROVINCIAS).fillna(n["provincia"].str.title())
    n["evento_nombre"] = n["evento"].map(EVENTOS).fillna(n["evento"])
    return n.sort_values("fecha", ascending=False)


@st.cache_data(ttl="1h", max_entries=20)
def geojson(claves: tuple[str, ...]) -> dict:
    """GeoJSON de los registros filtrados, con los campos del tooltip y el color."""
    b = cargar_base().set_index("clave").loc[list(claves)].reset_index()
    g = cargar_geometrias().merge(b, on="geom_hash")
    g["color"] = g["etapa_proyecto"].map(COLORES_ETAPA).map(
        lambda c: c if isinstance(c, list) else COLOR_SIN_ETAPA)
    g["sup_txt"] = g["superficie_ha"].map(lambda x: f"{x:,.0f} ha".replace(",", ".") if pd.notna(x) else "s/d")
    campos = ["nombre", "provincia_nombre", "titular", "etapa_proyecto", "etapa_administrativa",
              "estado", "minerales", "departamento", "sup_txt", "color", "geometry"]
    return json.loads(g[campos].to_json())


st.set_page_config(page_title="Catastro minero NOA", page_icon=":material/landscape:", layout="wide")

base = cargar_base()
novedades = cargar_novedades()

# --- Filtros -------------------------------------------------------------------------
with st.sidebar:
    st.header("Filtros")
    f_prov = st.pills("Provincia", list(PROVINCIAS.values()), selection_mode="multi",
                      default=list(PROVINCIAS.values()))
    f_litio = st.toggle("Solo con litio")
    f_grupos = st.multiselect("Grupo de mineral", [*GRUPOS, SIN_GRUPO],
                              placeholder="Todos los grupos")
    f_etapas = st.pills("Etapa del proyecto", ETAPAS, selection_mode="multi", default=list(ETAPAS))
    f_estados = st.multiselect("Estado", sorted(base["estado"].unique()),
                               placeholder="Todos los estados")
    f_deptos = st.multiselect(
        "Departamento",
        sorted(base.loc[base["provincia_nombre"].isin(f_prov), "departamento"].replace("", pd.NA).dropna().unique()),
        placeholder="Todos los departamentos")
    f_titular = st.text_input("Titular contiene", placeholder="Ej.: litio, minera, SA")

filtro = base["provincia_nombre"].isin(f_prov) & base["etapa_proyecto"].isin(f_etapas)
if f_litio:
    filtro &= base["tiene_litio"]
if f_grupos:
    filtro &= base["grupos"].map(lambda gs: bool(set(gs) & set(f_grupos)))
if f_estados:
    filtro &= base["estado"].isin(f_estados)
if f_deptos:
    filtro &= base["departamento"].isin(f_deptos)
if f_titular.strip():
    filtro &= base["titular_buscar"].str.contains(clave(f_titular) or "", regex=False)
sel = base[filtro]

# --- Encabezado ----------------------------------------------------------------------
st.title("Catastro minero de Jujuy y Salta")
ultimo = novedades["fecha"].max()
st.caption(
    "Derechos mineros publicados por los catastros oficiales de cada provincia, unificados "
    "y homologados. Se descargan automáticamente todos los días."
    + (f" Último cambio registrado: **{ultimo:%d/%m/%Y}**." if pd.notna(ultimo) else ""))

with st.container(horizontal=True):
    st.metric("Derechos mineros", f"{len(sel):,}".replace(",", "."), border=True)
    st.metric("Superficie", f"{sel['superficie_ha'].sum() / 1000:,.0f} mil ha".replace(",", "."),
              border=True, help="Suma de la superficie de cada derecho. Donde se superponen, "
                                "esa área se cuenta más de una vez.")
    st.metric("Titulares", f"{sel['titular_clave'].replace('', pd.NA).nunique():,}".replace(",", "."),
              border=True)
    st.metric("Con litio", f"{sel['tiene_litio'].sum():,}".replace(",", "."), border=True)

vista = st.segmented_control(
    "Vista",
    [":material/map: Mapa", ":material/table: Tabla", ":material/history: Novedades"],
    default=":material/map: Mapa", label_visibility="collapsed")

# --- Mapa ----------------------------------------------------------------------------
if vista == ":material/map: Mapa":
    if sel.empty:
        st.info("No hay derechos que cumplan los filtros.", icon=":material/filter_alt_off:")
    else:
        capa = pdk.Layer(
            "GeoJsonLayer", geojson(tuple(sel["clave"])), id="derechos",
            get_fill_color="properties.color", get_line_color=[255, 255, 255, 60],
            line_width_min_pixels=0.5, pickable=True, auto_highlight=True)
        tooltip = {
            "html": "<b>{nombre}</b> · {provincia_nombre}<br/>"
                    "Titular: {titular}<br/>"
                    "Etapa: {etapa_proyecto} ({etapa_administrativa})<br/>"
                    "Estado: {estado}<br/>"
                    "Minerales: {minerales}<br/>"
                    "Departamento: {departamento} · {sup_txt}",
            "style": {"fontSize": "12px"},
        }
        vista_inicial = pdk.ViewState(latitude=-24.3, longitude=-66.3, zoom=6)
        st.pydeck_chart(
            pdk.Deck(layers=[capa], initial_view_state=vista_inicial, tooltip=tooltip,
                     map_provider="carto", map_style=None),  # None: sigue el tema claro/oscuro
            height=620, alt="Mapa de los derechos mineros filtrados, coloreados por etapa")
        st.markdown(" · ".join(
            f":{c}[■] {e}" for e, c in zip(ETAPAS, ("orange", "red", "blue"))))

# --- Tabla ---------------------------------------------------------------------------
elif vista == ":material/table: Tabla":
    columnas = {
        "provincia_nombre": "Provincia", "expediente": "Expediente", "nombre": "Nombre",
        "titular": "Titular", "etapa_proyecto": "Etapa del proyecto",
        "etapa_administrativa": "Etapa administrativa", "estado": "Estado",
        "minerales": "Minerales", "grupos_minerales": "Grupos de mineral",
        "departamento": "Departamento", "superficie_ha": "Superficie (ha)",
    }
    tabla = sel[list(columnas)].rename(columns=columnas)
    st.dataframe(
        tabla, hide_index=True, height=560,
        column_config={"Superficie (ha)": st.column_config.NumberColumn(format="localized")},
        alt="Tabla de los derechos mineros filtrados")
    st.download_button(
        "Descargar CSV", sel.drop(columns=["grupos", "titular_buscar", "provincia_nombre"])
        .to_csv(index=False).encode("utf-8-sig"),
        file_name="catastro_noa_filtrado.csv", mime="text/csv", icon=":material/download:")

# --- Novedades -----------------------------------------------------------------------
elif vista == ":material/history: Novedades":
    st.caption("Cambios detectados entre descargas sucesivas: altas, bajas y cambios de "
               "titular, etapa, estado o mineral. Solo filtra por provincia.")
    nov = novedades[novedades["provincia_nombre"].isin(f_prov)]
    f_eventos = st.pills("Tipo de cambio", sorted(nov["evento_nombre"].unique()),
                         selection_mode="multi")
    if f_eventos:
        nov = nov[nov["evento_nombre"].isin(f_eventos)]
    st.dataframe(
        nov[["fecha", "provincia_nombre", "nombre", "evento_nombre", "antes", "despues"]],
        hide_index=True, height=520,
        column_config={
            "fecha": st.column_config.DateColumn("Fecha", format="DD/MM/YYYY"),
            "provincia_nombre": "Provincia", "nombre": "Derecho", "evento_nombre": "Cambio",
            "antes": "Antes", "despues": "Después",
        },
        alt="Tabla de novedades detectadas en el catastro")
