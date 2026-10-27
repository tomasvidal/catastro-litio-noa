"""
Clave estable de cada derecho minero, para reconocerlo de una foto a la otra.

Base: `provincia:expediente:nombre`, normalizados (mayusculas, sin acentos ni signos).
Alcanza para casi todo, pero no es unica: en Salta hay expedientes sin nombre con varios
poligonos (convenios, servidumbres). En esos grupos se desempata asi:

  1. Un poligono que sigue igual (mismo geom_hash) conserva la clave que ya tenia.
  2. Si en el grupo sobra un solo derecho viejo y un solo derecho nuevo, son el mismo
     (le cambio la forma).
  3. Los que quedan sin pareja son altas nuevas: clave base + "#" + geom_hash.

Despues, un alta y una baja de la misma provincia que comparten un poligono que ninguna otra
cosa usa, y ademas el nombre o el titular, son el mismo derecho con otro expediente (ej.
"143-1412/18" pasa a "143-1412/2018"): el alta hereda la clave de la baja. Si cambian a la vez
el expediente, el nombre y el titular es otro derecho sobre el mismo terreno: baja y alta.

Las claves ya asignadas viven en el historial (`vigentes`), asi una clave no cambia aunque
el poligono cambie. Si un grupo con varios poligonos cambia mas de uno a la vez, no hay forma
de saber cuales corresponden: se registran como bajas y altas.
"""

from __future__ import annotations

from collections import Counter

import pandas as pd

from .texto import clave as _norm


def clave_base(provincia, expediente, nombre) -> str:
    return f"{provincia}:{_norm(expediente) or ''}:{_norm(nombre) or ''}"


def _bases(df: pd.DataFrame) -> pd.Series:
    return pd.Series([clave_base(p, e, n) for p, e, n in zip(df["provincia"], df["expediente"], df["nombre"])],
                     index=df.index)


def asignar_claves(tabla: pd.DataFrame, vigentes: pd.DataFrame | None = None) -> pd.DataFrame:
    """Devuelve `tabla` con la columna `clave` (primera). `vigentes`: versiones vigentes del
    historial, con sus claves; sin ellas, todas las claves se arman desde cero."""
    tabla = tabla.drop(columns="clave", errors="ignore").copy()
    base = _bases(tabla)
    viejos: dict[str, list[tuple[str, str | None]]] = {}
    todos: list[tuple] = []  # (provincia, clave, geom_hash, nombre, titular_clave) de las versiones vigentes
    if vigentes is not None and len(vigentes):
        v = vigentes[vigentes["provincia"].isin(tabla["provincia"].unique())]
        titulares = v["titular_clave"] if "titular_clave" in v else pd.Series(None, index=v.index)
        for b, p, k, h, n, ti in zip(_bases(v), v["provincia"], v["clave"], v["geom_hash"], v["nombre"], titulares):
            h = h if pd.notna(h) else None
            viejos.setdefault(b, []).append((k, h))
            todos.append((p, k, h, _norm(n), ti if pd.notna(ti) else None))

    claves = pd.Series(index=tabla.index, dtype=object)
    usadas: set[str] = set()
    emparejadas: set[str] = set()  # claves viejas que encontraron su derecho
    altas: list = []
    for b, idx in tabla.groupby(base, sort=False).groups.items():
        idx = list(idx)
        pendientes = [(k, h) for k, h in viejos.get(b, [])]
        sin_pareja = []
        for i in idx:  # 1. mismo poligono
            h = tabla.at[i, "geom_hash"]
            h = h if pd.notna(h) else None
            hallado = next((p for p in pendientes if p[1] == h), None)
            if hallado is None:
                sin_pareja.append(i)
            else:
                pendientes.remove(hallado)
                claves[i] = hallado[0]
                usadas.add(hallado[0])
                emparejadas.add(hallado[0])
        if len(sin_pareja) == 1 and len(pendientes) == 1:  # 2. cambio la forma
            claves[sin_pareja[0]] = pendientes[0][0]
            usadas.add(pendientes[0][0])
            emparejadas.add(pendientes[0][0])
            sin_pareja = []
        for i in sin_pareja:  # 3. alta
            h = tabla.at[i, "geom_hash"]
            nueva = b if len(idx) == 1 else f"{b}#{h if pd.notna(h) else 'sin_geometria'}"
            n, candidata = 2, nueva
            while candidata in usadas:  # dos poligonos identicos en el mismo grupo
                candidata, n = f"{nueva}~{n}", n + 1
            claves[i] = candidata
            usadas.add(candidata)
            altas.append(i)

    # Altas y bajas que comparten un poligono unico: el mismo derecho con otro expediente o nombre.
    libres = Counter((p, h) for p, k, h, _, _ in todos if h and k not in emparejadas)
    dueno = {(p, h): (k, n, ti) for p, k, h, n, ti in todos if h and k not in emparejadas}
    nuevas = Counter((tabla.at[i, "provincia"], tabla.at[i, "geom_hash"]) for i in altas)
    tit = tabla["titular_clave"] if "titular_clave" in tabla else pd.Series(None, index=tabla.index)
    for i in altas:
        par = (tabla.at[i, "provincia"], tabla.at[i, "geom_hash"])
        if libres[par] != 1 or nuevas[par] != 1:
            continue
        k, nombre, titular = dueno[par]
        mismo_nombre = _norm(tabla.at[i, "nombre"]) == nombre
        mismo_titular = titular is not None and tit[i] == titular
        if mismo_nombre or mismo_titular:
            usadas.discard(claves[i])
            claves[i] = k
            usadas.add(k)

    repetidas = claves[claves.duplicated(keep=False)]
    if len(repetidas):
        raise ValueError(f"claves repetidas: {sorted(repetidas.unique())[:5]}")
    tabla.insert(0, "clave", claves)
    return tabla
