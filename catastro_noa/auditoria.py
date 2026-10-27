"""
Auditoria temporal: compara la foto nueva con el historial y registra que cambio.

  data/historial/historial.parquet   cada version de cada derecho, con vigencia (SCD tipo 2):
                                     vigente_desde (inclusive) y vigente_hasta (exclusivo;
                                     vacio = version vigente).
  data/historial/novedades.csv       una fila por cambio detectado. Solo se agregan filas.

El historial es la fuente de verdad del estado anterior. Asi la comparacion no depende de que
la foto previa este disponible y tolera que falten semanas.

Un cambio solo cuenta como novedad si cambio lo que publica la fuente. Si cambia un diccionario
de `diccionarios/` (ej. se reclasifica un mineral) el valor homologado cambia pero la fuente no:
eso no es una novedad del catastro y la version vigente se actualiza sin registrar nada.
Por la misma razon, un cambio de texto que no altera el valor homologado (ej. "S.A." por "SA")
tampoco lo es.
"""

from __future__ import annotations

import datetime as dt
import io
from pathlib import Path

import pandas as pd

from . import DATA_HISTORIAL

NOVEDADES = ["fecha", "provincia", "clave", "nombre", "evento", "campo", "antes", "despues"]
# (evento, columna de la fuente que debe haber cambiado, columnas homologadas que se informan)
CAMBIOS = [
    ("cambio_titular", "titular", ["titular_clave"]),
    ("cambio_etapa", "tramite_original", ["etapa_administrativa", "etapa_proyecto"]),
    ("cambio_estado", "estado_original", ["estado"]),
    ("cambio_mineral", "mineral_original", ["minerales"]),
]
TOLERANCIA_HA = 0.01  # la superficie calculada se redondea a 4 decimales
VIGENCIA = ["vigente_desde", "vigente_hasta"]


def _texto(s: pd.Series) -> pd.Series:
    return s.astype("object").where(s.notna(), "").astype(str)


def detectar(viejos: pd.DataFrame, nuevos: pd.DataFrame, fecha: dt.date) -> pd.DataFrame:
    """Novedades entre dos tablas indexadas por clave (viejos = versiones vigentes)."""
    filas = []

    def agregar(df, evento, campo="", antes=None, despues=None):
        out = pd.DataFrame({"fecha": fecha, "provincia": df["provincia"].values, "clave": df.index.values,
                            "nombre": df["nombre"].values, "evento": evento, "campo": campo})
        out["antes"] = antes.values if antes is not None else ""
        out["despues"] = despues.values if despues is not None else ""
        filas.append(out)

    altas = nuevos.loc[nuevos.index.difference(viejos.index)]
    bajas = viejos.loc[viejos.index.difference(nuevos.index)]
    if len(altas):
        agregar(altas, "alta")
    if len(bajas):
        agregar(bajas, "baja")

    comunes = viejos.index.intersection(nuevos.index)
    v, n = viejos.loc[comunes], nuevos.loc[comunes]
    for evento, fuente, campos in CAMBIOS:
        cambio_fuente = _texto(v[fuente]) != _texto(n[fuente])
        for campo in campos:
            m = cambio_fuente & (_texto(v[campo]) != _texto(n[campo]))
            if m.any():
                agregar(n[m], evento, campo, _texto(v.loc[m, campo]), _texto(n.loc[m, campo]))
    for evento, campo in (("cambio_expediente", "expediente"), ("cambio_nombre", "nombre")):
        m = _texto(v[campo]) != _texto(n[campo])
        if m.any():
            agregar(n[m], evento, campo, _texto(v.loc[m, campo]), _texto(n.loc[m, campo]))
    dif = (v["superficie_ha_calculada"].astype(float) - n["superficie_ha_calculada"].astype(float)).abs()
    m = dif > TOLERANCIA_HA
    if m.any():
        agregar(n[m], "cambio_superficie", "superficie_ha_calculada",
                v.loc[m, "superficie_ha_calculada"].astype(str), n.loc[m, "superficie_ha_calculada"].astype(str))
    m = _texto(v["geom_hash"]) != _texto(n["geom_hash"])
    if m.any():
        agregar(n[m], "cambio_geometria", "geom_hash", _texto(v.loc[m, "geom_hash"]), _texto(n.loc[m, "geom_hash"]))

    if not filas:
        return pd.DataFrame(columns=NOVEDADES)
    return (pd.concat(filas, ignore_index=True)[NOVEDADES]
            .sort_values(["provincia", "clave", "evento", "campo"]).reset_index(drop=True))


def vigentes(historial: pd.DataFrame | None) -> pd.DataFrame | None:
    return None if historial is None else historial[historial["vigente_hasta"].isna()]


def aplicar(historial: pd.DataFrame | None, tabla: pd.DataFrame,
            fecha: dt.date) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Aplica la foto de `fecha` (con `clave`) al historial. Devuelve (novedades, historial nuevo).

    - Una provincia que todavia no estaba en el historial entra como punto de partida, sin
      novedades: no son altas reales, es la primera vez que se la ve.
    - Una provincia que esta en el historial pero no en la foto no se toca (no se la da de baja).
    """
    ts = pd.Timestamp(fecha)
    nuevo = tabla.assign(vigente_desde=ts, vigente_hasta=pd.Series(pd.NaT, index=tabla.index, dtype="datetime64[ns]"))
    if historial is None:
        return pd.DataFrame(columns=NOVEDADES), nuevo

    comunes = sorted(set(tabla["provincia"]) & set(historial["provincia"]))
    iniciales = nuevo[~nuevo["provincia"].isin(historial["provincia"])]
    vig = vigentes(historial)
    viejos = vig[vig["provincia"].isin(comunes)].set_index("clave")
    nuevos = tabla[tabla["provincia"].isin(comunes)].set_index("clave")
    novedades = detectar(viejos, nuevos, fecha)

    con_novedad = set(novedades["clave"])
    cerrar = historial["vigente_hasta"].isna() & historial["clave"].isin(con_novedad)
    historial = historial.copy()
    historial.loc[cerrar, "vigente_hasta"] = ts

    # Sin novedad: se refrescan los datos de la version vigente (ej. tras cambiar un diccionario).
    # Se reconstruyen las filas en vez de pisar valores: asi no importan diferencias de tipo.
    sin_novedad = nuevos.index.intersection(viejos.index).difference(list(con_novedad))
    es_refresco = historial["vigente_hasta"].isna() & historial["clave"].isin(sin_novedad)
    desde = historial.loc[es_refresco].set_index("clave")["vigente_desde"]
    refrescadas = nuevos.loc[sin_novedad].reset_index()
    if len(refrescadas):
        refrescadas["vigente_desde"] = refrescadas["clave"].map(desde)
        refrescadas["vigente_hasta"] = pd.NaT

    abrir = nuevo[nuevo["clave"].isin(con_novedad) & ~nuevo["clave"].isin(set(novedades.loc[novedades["evento"] == "baja", "clave"]))]
    partes = [df for df in (historial[~es_refresco], refrescadas, abrir, iniciales) if len(df)]
    historial = pd.concat(partes, ignore_index=True)
    historial = historial[[*tabla.columns, *VIGENCIA]].sort_values(["clave", "vigente_desde"]).reset_index(drop=True)
    return novedades, historial


# --------------------------------------------------------------------------- archivos
def leer_historial(carpeta: Path | None = None) -> pd.DataFrame | None:
    ruta = (carpeta or DATA_HISTORIAL) / "historial.parquet"
    return pd.read_parquet(ruta) if ruta.exists() else None


def escribir(historial: pd.DataFrame, novedades: pd.DataFrame, carpeta: Path | None = None) -> dict[str, str]:
    carpeta = carpeta or DATA_HISTORIAL
    carpeta.mkdir(parents=True, exist_ok=True)
    ruta_h, ruta_n = carpeta / "historial.parquet", carpeta / "novedades.csv"

    # Se compara despues de pasar por parquet: en memoria los tipos pueden diferir de los leidos
    # (ej. fechas en ns vs ms) y se reescribiria el archivo en cada corrida sin que cambie nada.
    buffer = io.BytesIO()
    historial.to_parquet(buffer, index=False)
    buffer.seek(0)
    nuevo = pd.read_parquet(buffer)
    if not ruta_h.exists() or not pd.read_parquet(ruta_h).equals(nuevo):
        historial.to_parquet(ruta_h, index=False)
    if len(novedades):
        novedades.to_csv(ruta_n, mode="a", header=not ruta_n.exists(), index=False,
                         encoding="utf-8", lineterminator="\n")
    return {"historial": str(ruta_h), "novedades": str(ruta_n)}
