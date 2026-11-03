"""
App de consulta del catastro minero del NOA.

Lee solo los archivos que versiona el workflow de actualizacion (data/snapshot/,
data/historial/ y data/estado_fuentes.csv), asi que cada commit del robot actualiza la app
sin pasos extra. Las provincias, etapas y estados salen de los datos: si se suma una
provincia o aparece una etapa nueva, la app la muestra sin tocar el codigo.

    uv run streamlit run streamlit_app.py
"""

import datetime as dt
import io
import json
import tempfile
from pathlib import Path

import geopandas as gpd
import pandas as pd
import pydeck as pdk
import streamlit as st

from catastro_noa import DATA_HISTORIAL, DATA_SNAPSHOT, ESTADO_FUENTES, REGISTRO_DESCARGAS
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
CAMPOS = {  # campo de la novedad -> como se lee en la app
    "estado": "Estado", "etapa_administrativa": "Etapa administrativa",
    "etapa_proyecto": "Etapa del proyecto", "titular_clave": "Titular", "minerales": "Minerales",
    "expediente": "Expediente", "nombre": "Nombre", "superficie_ha_calculada": "Superficie",
}
MAPA, TABLA, NOVEDADES, BUSCAR, DESCARGAS = (
    ":material/map: Mapa", ":material/table: Tabla", ":material/history: Novedades",
    ":material/manage_search: Buscar expediente", ":material/cloud_sync: Descargas")
SIN_CORRIDA = "⚪ Sin corrida"


@st.cache_data(ttl="1h")
def cargar_base() -> pd.DataFrame:
    b = pd.read_csv(DATA_SNAPSHOT / "catastro_noa.csv", dtype=str, keep_default_na=False)
    b["provincia_nombre"] = b["provincia"].str.title()
    b["etapa"] = b["etapa_proyecto"].replace("", SIN_ETAPA)
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
def cargar_historial() -> pd.DataFrame:
    """Todas las versiones de cada derecho, con su vigencia (una fila por version)."""
    ruta = DATA_HISTORIAL / "historial.parquet"
    if ruta.exists():
        h = pd.read_parquet(ruta)
    else:
        h = pd.DataFrame(columns=["clave", "provincia", "expediente", "nombre", "titular",
                                  "etapa_proyecto", "etapa_administrativa", "estado", "minerales",
                                  "departamento", "superficie_ha_calculada",
                                  "vigente_desde", "vigente_hasta"])
    for c in ("vigente_desde", "vigente_hasta"):
        h[c] = pd.to_datetime(h[c])
    h["provincia_nombre"] = h["provincia"].str.title()
    # Para buscar sin importar guiones, barras ni mayusculas: '143-1412/18' -> '143 1412 18'
    h["expediente_buscar"] = h["expediente"].map(clave).fillna("")
    return h.sort_values(["clave", "vigente_desde"])


@st.cache_data(ttl="1h")
def cargar_novedades() -> pd.DataFrame:
    ruta = DATA_HISTORIAL / "novedades.csv"
    columnas = ["fecha", "provincia", "clave", "nombre", "evento", "campo", "antes", "despues"]
    n = (pd.read_csv(ruta, dtype=str, keep_default_na=False) if ruta.exists()
         else pd.DataFrame(columns=columnas, dtype=str))
    n["fecha"] = pd.to_datetime(n["fecha"])
    # Expediente tal como lo publica la provincia, para buscar el derecho en el catastro oficial.
    # Sale del historial porque las bajas ya no estan en la foto actual; se toma la ultima
    # version de cada clave (si el expediente cambio de formato, el viejo queda en "antes").
    expedientes = cargar_historial().drop_duplicates("clave", keep="last")[["clave", "expediente"]]
    n = n.merge(expedientes, on="clave", how="left")
    n["expediente"] = n["expediente"].fillna("")
    n["provincia_nombre"] = n["provincia"].str.title()
    n["evento_nombre"] = n["evento"].map(EVENTOS).fillna(n["evento"])
    n["campo_nombre"] = n["campo"].map(CAMPOS).fillna("")
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


@st.cache_data(ttl="1h")
def cargar_descargas() -> pd.DataFrame:
    """Resultado de la descarga de cada dia y provincia (una fila por dia y provincia)."""
    columnas = ["fecha", "provincia", "resultado", "registros", "fuente", "detalle"]
    d = (pd.read_csv(REGISTRO_DESCARGAS, dtype=str, keep_default_na=False) if REGISTRO_DESCARGAS.exists()
         else pd.DataFrame(columns=columnas, dtype=str))
    d["fecha"] = pd.to_datetime(d["fecha"])
    d["provincia_nombre"] = d["provincia"].str.title()
    return d


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


@st.cache_data(ttl="1h", max_entries=20)
def excel(claves: tuple[str, ...]) -> bytes:
    """Los registros filtrados en un .xlsx, con las mismas columnas que el CSV."""
    b = (cargar_base().set_index("clave").loc[list(claves)].reset_index()
         .drop(columns=["grupos", "titular_buscar", "provincia_nombre"]))
    salida = io.BytesIO()
    with pd.ExcelWriter(salida, engine="openpyxl") as w:
        b.to_excel(w, sheet_name="derechos", index=False)
        hoja = w.sheets["derechos"]
        hoja.freeze_panes = "A2"
        hoja.auto_filter.ref = hoja.dimensions
    return salida.getvalue()


@st.cache_data(ttl="1h", max_entries=5)
def geopackage(claves: tuple[str, ...]) -> bytes:
    """Los registros filtrados con su poligono, en un GeoPackage para QGIS u otro SIG.

    Usa la geometria original, no la simplificada del mapa."""
    b = (cargar_base().set_index("clave").loc[list(claves)].reset_index()
         .drop(columns=["grupos", "titular_buscar", "provincia_nombre"]))
    geoms = gpd.read_parquet(DATA_SNAPSHOT / "geometrias.parquet")[["geom_hash", "geometry"]]
    g = gpd.GeoDataFrame(b.merge(geoms, on="geom_hash", how="left"), geometry="geometry", crs=geoms.crs)
    with tempfile.TemporaryDirectory() as carpeta:
        ruta = Path(carpeta) / "derechos.gpkg"
        g.to_file(ruta, driver="GPKG", layer="derechos_mineros")
        return ruta.read_bytes()


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
    "Vista", [MAPA, TABLA, NOVEDADES, BUSCAR, DESCARGAS], default=MAPA,
    label_visibility="collapsed")

# --- Mapa ----------------------------------------------------------------------------
if vista == MAPA:
    # Sin derechos filtrados se muestra el mapa vacio, en lugar de un aviso.
    datos = (geojson(tuple(sel["clave"])) if not sel.empty
             else {"type": "FeatureCollection", "features": []})
    capa = pdk.Layer(
        "GeoJsonLayer", datos, id="derechos",
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
elif vista == TABLA:
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
    with st.container(horizontal=True):
        st.download_button(
            "Descargar CSV", sel.drop(columns=["grupos", "titular_buscar", "provincia_nombre"])
            .to_csv(index=False).encode("utf-8-sig"),
            file_name="catastro_noa_filtrado.csv", mime="text/csv", icon=":material/download:")
        st.download_button(
            "Descargar Excel", excel(tuple(sel["clave"])), file_name="catastro_noa_filtrado.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            icon=":material/download:")
        claves_sel = tuple(sel["clave"])
        st.download_button(  # el archivo se arma recien al hacer clic: pesa varios MB
            "Descargar GeoPackage", lambda: geopackage(claves_sel),
            file_name="catastro_noa_filtrado.gpkg", mime="application/geopackage+sqlite3",
            icon=":material/download:", on_click="ignore",
            help="Los mismos datos con el polígono de cada derecho, para abrir en QGIS u otro "
                 "programa de mapas.")

# --- Novedades -----------------------------------------------------------------------
elif vista == NOVEDADES:
    st.caption("Cambios detectados entre descargas sucesivas: altas, bajas y cambios de "
               "titular, etapa, estado o mineral. Solo filtra por provincia. El expediente es "
               "el que publica la provincia: sirve para buscar el derecho en el catastro oficial "
               "o en la vista Tabla.")
    nov = novedades[novedades["provincia_nombre"].isin(f_prov)]
    f_eventos = st.pills("Tipo de cambio", sorted(nov["evento_nombre"].unique()),
                         selection_mode="multi")
    if f_eventos:
        nov = nov[nov["evento_nombre"].isin(f_eventos)]
    st.dataframe(
        nov[["fecha", "provincia_nombre", "expediente", "nombre", "evento_nombre", "antes", "despues"]],
        hide_index=True, height=520,
        column_config={
            "fecha": st.column_config.DateColumn("Fecha", format="DD/MM/YYYY"),
            "provincia_nombre": "Provincia", "expediente": "Expediente", "nombre": "Derecho",
            "evento_nombre": "Cambio",
            "antes": "Antes", "despues": "Después",
        },
        alt="Tabla de novedades detectadas en el catastro")

# --- Buscar expediente ---------------------------------------------------------------
elif vista == BUSCAR:
    historial = cargar_historial()
    inicio = historial.groupby("provincia_nombre")["vigente_desde"].min()
    st.caption(
        "Escribí un número de expediente para ver cómo fue cambiando ese derecho. Los cambios se "
        "registran desde " + " y ".join(f"el {f:%d/%m/%Y} en {p}" for p, f in inicio.items())
        + ". No hace falta respetar guiones ni barras. No usa los filtros de la izquierda.")
    buscado = clave(st.text_input("Expediente", placeholder="Ej.: 2911-M-2022 o 758823")) or ""
    if buscado:
        hallados = historial[historial["expediente_buscar"] == buscado]
        if hallados.empty and len(buscado) >= 3:  # si no hay uno igual, los que lo contienen
            hallados = historial[historial["expediente_buscar"].str.contains(buscado, regex=False)]
        # Ultima version de cada derecho encontrado (puede haberse encontrado por un expediente
        # viejo, si la provincia le cambio el formato)
        ultimas = historial[historial["clave"].isin(hallados["clave"])].groupby("clave").tail(1)
        if ultimas.empty:
            st.info("No se encontró ningún derecho con ese expediente.", icon=":material/search_off:")
        else:
            def _rotulo(k: str) -> str:
                r = ultimas.set_index("clave").loc[k]
                sup = pd.to_numeric(r["superficie_ha_calculada"], errors="coerce")
                return (f"{r['expediente']} · {r['nombre'] or 'Sin nombre'} · {r['provincia_nombre']}"
                        + (f" · {sup:,.0f} ha".replace(",", ".") if pd.notna(sup) else ""))
            if len(ultimas) > 1:
                st.caption(f"{len(ultimas)} derechos coinciden con la búsqueda.")
            elegido = st.selectbox("Derecho", list(ultimas["clave"]), format_func=_rotulo,
                                   label_visibility="collapsed" if len(ultimas) == 1 else "visible")
            versiones = historial[historial["clave"] == elegido]
            actual = versiones.iloc[-1]

            st.subheader(f"{actual['nombre'] or 'Sin nombre'} · {actual['provincia_nombre']}")
            if pd.notna(actual["vigente_hasta"]):
                st.warning(f"Ya no figura en el catastro provincial desde el "
                           f"{actual['vigente_hasta']:%d/%m/%Y}. Abajo, los últimos datos publicados.",
                           icon=":material/block:")
            sup = pd.to_numeric(actual["superficie_ha_calculada"], errors="coerce")
            ficha = {
                "Expediente": actual["expediente"], "Titular": actual["titular"],
                "Etapa del proyecto": actual["etapa_proyecto"],
                "Etapa administrativa": actual["etapa_administrativa"], "Estado": actual["estado"],
                "Minerales": actual["minerales"], "Departamento": actual["departamento"],
                "Superficie": f"{sup:,.0f} ha".replace(",", ".") if pd.notna(sup) else "s/d",
            }
            st.dataframe(pd.DataFrame({"Dato": ficha.keys(), "Valor": ficha.values()}),
                         hide_index=True, height=(len(ficha) + 1) * 35 + 3,  # sin barra de scroll
                         alt="Datos actuales del derecho")

            st.markdown("**Cambios registrados**")
            cambios = novedades[novedades["clave"] == elegido].sort_values("fecha")
            primera = versiones["vigente_desde"].min()
            if cambios.empty:
                st.info(f"Sin cambios desde que se registra ({primera:%d/%m/%Y}).",
                        icon=":material/check_circle:")
            else:
                st.dataframe(
                    cambios[["fecha", "evento_nombre", "campo_nombre", "antes", "despues"]],
                    hide_index=True,
                    column_config={
                        "fecha": st.column_config.DateColumn("Fecha", format="DD/MM/YYYY"),
                        "evento_nombre": "Cambio", "campo_nombre": "Qué cambió",
                        "antes": "Antes", "despues": "Después",
                    },
                    alt="Cambios registrados del derecho, del más viejo al más nuevo")
                if "alta" not in set(cambios["evento"]):
                    st.caption(f"Figura en el catastro desde antes del {primera:%d/%m/%Y}, "
                               "cuando empezó el registro de cambios.")

# --- Descargas -----------------------------------------------------------------------
elif vista == DESCARGAS:
    descargas = cargar_descargas()
    if descargas.empty:
        st.info("Todavía no hay descargas registradas.", icon=":material/hourglass_empty:")
    else:
        st.caption(
            "Resultado de la descarga automática de cada día, desde el "
            f"{descargas['fecha'].min():%d/%m/%Y}. Un día **sin corrida** es un día en que la "
            "actualización no llegó a ejecutarse: el motivo está en la pestaña Actions del "
            "repositorio. No usa los filtros de la izquierda.")
        # Todos los dias hasta ayer (la de hoy puede no haber corrido todavia), para que se vean
        # los dias en que el robot no corrio.
        hasta = max(descargas["fecha"].max(), pd.Timestamp(dt.date.today() - dt.timedelta(days=1)))
        dias = pd.date_range(descargas["fecha"].min(), hasta, freq="D")
        descargas["texto"] = descargas.apply(
            lambda r: (f"✅ {int(r['registros']):,} registros".replace(",", ".")
                       if r["resultado"] == "ok" else "❌ Error"), axis=1)
        tabla = (descargas.pivot(index="fecha", columns="provincia_nombre", values="texto")
                 .reindex(dias).fillna(SIN_CORRIDA))
        errores = descargas[descargas["resultado"] != "ok"]
        tabla["Detalle"] = (errores.assign(t=errores["provincia_nombre"] + ": " + errores["detalle"])
                            .groupby("fecha")["t"].agg(" · ".join).reindex(dias).fillna(""))
        tabla = tabla.rename_axis("Fecha").reset_index().sort_values("Fecha", ascending=False)

        provincias_reg = tabla.columns.drop(["Fecha", "Detalle"])
        con_problemas = ~tabla[provincias_reg].apply(lambda c: c.str.startswith("✅")).all(axis=1)
        if con_problemas.any():
            ultimo = tabla.loc[con_problemas, "Fecha"].max()
            st.warning(f"Último día con problemas: **{ultimo:%d/%m/%Y}**. "
                       f"Días con problemas en el período: {int(con_problemas.sum())} de {len(tabla)}.",
                       icon=":material/sync_problem:")
        else:
            st.success(f"Todas las descargas salieron bien ({len(tabla)} días).",
                       icon=":material/check_circle:")
        st.dataframe(
            tabla, hide_index=True, height=min(560, (len(tabla) + 1) * 35 + 3),
            column_config={"Fecha": st.column_config.DateColumn(format="DD/MM/YYYY")},
            alt="Resultado de la descarga automática de cada día y provincia")
