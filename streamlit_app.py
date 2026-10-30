"""
App de consulta del catastro minero del NOA.

Lee solo los archivos que versiona el workflow de actualizacion (data/snapshot/,
data/historial/ y data/estado_fuentes.csv), asi que cada commit del robot actualiza la app
sin pasos extra. Las provincias, etapas y estados salen de los datos: si se suma una
provincia o aparece una etapa nueva, la app la muestra sin tocar el codigo.

    uv run streamlit run streamlit_app.py
"""

import datetime as dt
import json

import geopandas as gpd
import pandas as pd
import pydeck as pdk
import streamlit as st

from catastro_noa import DATA_HISTORIAL, DATA_SNAPSHOT, ESTADO_FUENTES
from catastro_noa.expedientes import COLUMNAS as COLUMNAS_POR_ANIO
from catastro_noa.expedientes import expedientes_por_anio
from catastro_noa.minerales import GRUPOS
from catastro_noa.texto import clave

SIN_GRUPO = "Sin mineral informado"
SIN_ETAPA = "Sin etapa asignada"
ETAPAS = ("Exploración", "Explotación", "Canteras y otros")  # orden de la leyenda; otras van al final
# Si el robot no registra ningun intento en estos dias, se avisa que la actualizacion se detuvo.
# Alcanza tanto para la frecuencia diaria como para la semanal.
DIAS_SIN_ACTUALIZAR = 8
COLORES_ETAPA = {  # RGBA para el mapa; mismos tonos que la leyenda
    "Exploración": [242, 183, 5, 150],
    "Explotación": [235, 87, 87, 150],
    "Canteras y otros": [120, 160, 200, 120],
}
COLOR_SIN_ETAPA = [160, 160, 160, 110]
PUBLICADOS, ABIERTOS = "Derechos publicados hoy", "Expedientes abiertos (estimado)"
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
    b["provincia_nombre"] = b["provincia"].str.title()
    b["etapa"] = b["etapa_proyecto"].replace("", SIN_ETAPA)
    b["superficie_ha"] = pd.to_numeric(b["superficie_ha_calculada"], errors="coerce")
    b["tiene_litio"] = b["tiene_litio"].eq("True")
    b["grupos"] = b["grupos_minerales"].map(lambda s: s.split("; ") if s else [SIN_GRUPO])
    b["titular_buscar"] = b["titular"].map(clave).fillna("")
    # La foto previa a la columna no la trae: hasta la siguiente corrida del robot queda vacia.
    b["anio"] = pd.to_numeric(b.get("anio_expediente", pd.Series(pd.NA, index=b.index)), errors="coerce")
    return b


@st.cache_data(ttl="1h")
def cargar_expedientes_por_anio() -> pd.DataFrame:
    """Estimación de expedientes abiertos por año (ver catastro_noa/expedientes.py)."""
    b = cargar_base()
    if "anio_expediente" not in b:
        return pd.DataFrame(columns=[*COLUMNAS_POR_ANIO, "provincia_nombre"])
    t = expedientes_por_anio(b)
    t["provincia_nombre"] = t["provincia"].str.title()
    return t


@st.cache_data(ttl="1h")
def cargar_geometrias() -> gpd.GeoDataFrame:
    g = gpd.read_parquet(DATA_SNAPSHOT / "geometrias.parquet")
    # ~20 m de tolerancia: no cambia nada a la escala del mapa y aliviana el envio al navegador
    g["geometry"] = g.geometry.simplify(0.0002, preserve_topology=True)
    return g


@st.cache_data(ttl="1h")
def cargar_novedades() -> pd.DataFrame:
    ruta = DATA_HISTORIAL / "novedades.csv"
    columnas = ["fecha", "provincia", "clave", "nombre", "evento", "campo", "antes", "despues"]
    n = (pd.read_csv(ruta, dtype=str, keep_default_na=False) if ruta.exists()
         else pd.DataFrame(columns=columnas, dtype=str))
    n["fecha"] = pd.to_datetime(n["fecha"])
    n["provincia_nombre"] = n["provincia"].str.title()
    n["evento_nombre"] = n["evento"].map(EVENTOS).fillna(n["evento"])
    return n.sort_values("fecha", ascending=False)


@st.cache_data(ttl="1h")
def cargar_estado() -> pd.DataFrame:
    """Una fila por provincia: ultimo intento de descarga, ultima descarga buena y resultado."""
    if not ESTADO_FUENTES.exists():
        return pd.DataFrame(columns=["provincia", "ultimo_intento", "ultima_descarga_ok", "resultado"])
    e = pd.read_csv(ESTADO_FUENTES, dtype=str, keep_default_na=False)
    for c in ("ultimo_intento", "ultima_descarga_ok"):
        e[c] = pd.to_datetime(e[c], errors="coerce")
    e["provincia_nombre"] = e["provincia"].str.title()
    return e


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
estado = cargar_estado()
provincias = sorted(base["provincia_nombre"].unique())
etapas = [e for e in ETAPAS if e in set(base["etapa"])] + sorted(set(base["etapa"]) - set(ETAPAS))

# --- Filtros -------------------------------------------------------------------------
with st.sidebar:
    st.header("Filtros")
    f_prov = st.pills("Provincia", provincias, selection_mode="multi", default=provincias)
    f_litio = st.toggle("Solo con litio")
    f_grupos = st.multiselect("Grupo de mineral", [*GRUPOS, SIN_GRUPO],
                              placeholder="Todos los grupos")
    f_etapas = st.pills("Etapa del proyecto", etapas, selection_mode="multi", default=etapas)
    f_estados = st.multiselect("Estado", sorted(base["estado"].unique()),
                               placeholder="Todos los estados")
    f_deptos = st.multiselect(
        "Departamento",
        sorted(base.loc[base["provincia_nombre"].isin(f_prov), "departamento"].replace("", pd.NA).dropna().unique()),
        placeholder="Todos los departamentos")
    f_titular = st.text_input("Titular contiene", placeholder="Ej.: litio, minera, SA")

filtro = base["provincia_nombre"].isin(f_prov) & base["etapa"].isin(f_etapas)
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
st.title("Catastro minero del NOA")
fechas = [f"{r.provincia_nombre}: datos al **{r.ultima_descarga_ok:%d/%m/%Y}**"
          for r in estado.itertuples() if pd.notna(r.ultima_descarga_ok)]
st.caption(
    f"Derechos mineros publicados por los catastros oficiales de {' y '.join(provincias)}, "
    "unificados y homologados. Se descargan automáticamente de las fuentes oficiales."
    + (" " + " · ".join(fechas) + "." if fechas else ""))

ultimo_intento = estado["ultimo_intento"].max()
if pd.notna(ultimo_intento) and (pd.Timestamp(dt.date.today()) - ultimo_intento).days > DIAS_SIN_ACTUALIZAR:
    st.warning(f"La actualización automática no corre desde el {ultimo_intento:%d/%m/%Y}: "
               "los datos pueden estar desactualizados.", icon=":material/sync_problem:")
for r in estado[estado["resultado"] == "error"].itertuples():
    desde = f"del {r.ultima_descarga_ok:%d/%m/%Y}" if pd.notna(r.ultima_descarga_ok) else "anteriores"
    st.warning(f"No se pudieron descargar datos nuevos de {r.provincia_nombre} en el último intento "
               f"({r.ultimo_intento:%d/%m/%Y}). Se muestran los datos {desde}.",
               icon=":material/cloud_off:")

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
    [":material/map: Mapa", ":material/table: Tabla", ":material/bar_chart: Por año",
     ":material/history: Novedades"],
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
            [f":{c}[■] {e}" for e, c in zip(ETAPAS, ("orange", "red", "blue"))]
            + [f":gray[■] {e}" for e in sorted(set(sel["etapa"]) - set(ETAPAS))]))

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

# --- Por año -------------------------------------------------------------------------
elif vista == ":material/bar_chart: Por año":
    medida = st.segmented_control(
        "Qué contar", [PUBLICADOS, ABIERTOS], default=PUBLICADOS, required=True)
    if medida == PUBLICADOS:
        st.caption("Derechos vigentes según el año de inicio del expediente (en Jujuy, el que "
                   "figura en el número; en Salta, la fecha de inicio). Solo cuenta los que la "
                   "provincia publica hoy: los caducados o archivados no están, así que los años "
                   "más viejos quedan subrepresentados.")
        con_anio = sel.dropna(subset=["anio"])
    else:
        st.caption("Cuántos expedientes se abrieron cada año, se publiquen hoy o no: la diferencia "
                   "entre el último número de expediente del año y el del año anterior. Solo donde "
                   "la numeración es un correlativo del catastro minero (Jujuy desde 2003; Salta "
                   "de 1991 a 2019, antes del cambio de numeración). Es una estimación sobre todos "
                   "los expedientes, así que solo se aplica el filtro de provincia.")
        estimados = cargar_expedientes_por_anio()
        con_anio = estimados[estimados["provincia_nombre"].isin(f_prov)].dropna(
            subset=["abiertos_estimados"]).rename(columns={"abiertos_estimados": "valor"})
    if con_anio.empty:
        st.info("No hay datos por año para los filtros elegidos.", icon=":material/filter_alt_off:")
    else:
        desde = st.slider("Desde el año", int(con_anio["anio"].min()), int(con_anio["anio"].max()),
                          max(int(con_anio["anio"].min()), 1990))
        recorte = con_anio[con_anio["anio"] >= desde]
        if medida == PUBLICADOS:
            por_anio = recorte.groupby(["anio", "provincia_nombre"]).size().unstack(fill_value=0)
        else:
            por_anio = recorte.pivot(index="anio", columns="provincia_nombre", values="valor")
        por_anio.index = por_anio.index.astype(int).astype(str)
        st.bar_chart(por_anio.astype(float), x_label="Año de inicio del expediente",
                     y_label="Derechos" if medida == PUBLICADOS else "Expedientes abiertos (estimado)",
                     stack=False, height=480)
        if medida == PUBLICADOS:
            st.caption(f"{len(sel) - len(con_anio):,} derechos filtrados sin año de expediente."
                       .replace(",", "."))

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
