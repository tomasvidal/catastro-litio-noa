# Arquitectura: GitHub como base de datos

Cómo funciona el sistema completo, de punta a punta, sin servidores ni costos. El
[diagrama interactivo](diagrama_flujo.html) muestra el mismo recorrido y enlaza cada paso con
su código.

## La idea: *git-scraping*

Git guarda cada versión de cada archivo, con fecha y con el detalle de qué líneas
cambiaron. Si cada día se guarda (commitea) el catastro como un CSV ordenado, con
una línea por derecho minero, **el historial de git se convierte en una serie de tiempo
del catastro**:

```
commit 2026-10-09  "datos: actualización 2026-10-09"
-jujuy,2917-M-2022,MASA 46,AUSTROID ARGENTINA RESOURCES S.A.U.,SOLICITUD DE MINA,EN TRAMITE,...
+jujuy,2917-M-2022,MASA 46,AUSTROID ARGENTINA RESOURCES S.A.U.,MINA CONCEDIDA,CONCEDIDA,...
```

Ese diff dice: "el 9/10 se detectó que el derecho MASA 46 pasó de solicitud de mina a mina
concedida". No hace falta una base de datos: GitHub almacena, versiona y respalda gratis, y un
robot (GitHub Actions) se encarga de descargar y commitear todos los días.

## Flujo completo

```
          todos los días, 06:00 (GitHub Actions, cron)
                        │
   ┌────────────────────▼─────────────────────┐
   │ 1. INGESTA          catastro_noa/fuentes  │  Jujuy SHP, Salta WFS (Catamarca en pausa)
   │ 2. HOMOLOGACIÓN     catastro_noa/...      │  esquema común + diccionarios/*.csv
   │ 3. AUDITORÍA        catastro_noa/auditoria│  compara con el historial
   └────────────────────┬─────────────────────┘
                        │ git commit + push
   ┌────────────────────▼─────────────────────┐
   │ Repositorio GitHub = "base de datos"      │
   │  data/snapshot/catastro_noa.csv    foto de HOY (su historial git = todas las fotos)
   │  data/snapshot/geometrias.parquet  polígonos, uno por geom_hash
   │  data/historial/novedades.csv      registro de eventos (crece, nunca se borra)
   │  data/historial/historial.parquet  cada versión de cada derecho, con vigencia
   │  data/historial/descargas.csv      resultado de cada día y provincia
   │  data/estado_fuentes.csv           última descarga de cada provincia
   └────────────────────┬─────────────────────┘
                        │ cada commit actualiza la app publicada
   ┌────────────────────▼─────────────────────┐
   │ App Streamlit                             │  lee los archivos del repo:
   │  mapa · tabla · novedades · búsqueda ·    │  no consulta git en vivo
   │  descargas                                │
   └───────────────────────────────────────────┘
```

## De los diffs a tablas consultables

Leer diffs de git sirve para auditar, pero no sirve para una app: sería lento y difícil
de filtrar. Por eso, en cada corrida, el pipeline compara la foto nueva con el estado
anterior y **guarda el resultado como tablas** en `data/historial/`. El estado anterior es
el propio historial (no la foto previa de git), así la comparación tolera que falten días.

### 1. `novedades.csv`: registro de eventos

Una fila por cada cambio detectado. Se agregan filas y nunca se borran.

| fecha | provincia | clave | nombre | evento | campo | antes | despues |
|---|---|---|---|---|---|---|---|
| 2026-10-09 | jujuy | jujuy:2911 M 2022:MASA 40 | MASA 40 | cambio_etapa | etapa_administrativa | Solicitud de mina | Mina concedida |
| 2026-10-09 | jujuy | jujuy:2912 M 2022:MASA 41 | MASA 41 | cambio_titular | titular_clave | MINERALES AUSTRALES SA | AUSTROID ARGENTINA RESOURCES SAU |
| 2026-10-20 | salta | salta:18746:MARIANA 9 | MARIANA 9 | cambio_mineral | minerales | Boratos | Boratos; Litio |

Tipos de evento: `alta`, `baja`, `cambio_titular`, `cambio_etapa`, `cambio_estado`,
`cambio_mineral`, `cambio_superficie`, `cambio_geometria`, `cambio_expediente`, `cambio_nombre`.
Un cambio de trámite ocupa una fila por cada columna de etapa que cambia.

**Qué cuenta como novedad.** Solo un cambio en lo que publica la fuente. Si cambia un
diccionario de `diccionarios/` (ej. se reclasifica un mineral) el valor homologado cambia,
pero la fuente no: no se registra y la versión vigente se actualiza sin más. Los eventos
de etapa, estado, mineral y titular se informan con el valor homologado, y solo si cambió
también el texto original. La superficie calculada cambia como novedad con una diferencia
mayor a 0,01 ha.

**Primera vez que se ve una provincia:** entra como punto de partida, sin altas. Si una
provincia falta en una foto, no se la da de baja.

### 2. `historial.parquet`: versiones con vigencia (SCD tipo 2)

Cada vez que un derecho cambia, se cierra su versión anterior y se abre una nueva. Así se
puede reconstruir el catastro **tal como estaba en cualquier fecha**. `vigente_desde` es
inclusive y `vigente_hasta` exclusivo; vacío significa que la versión está vigente. La fecha es
la de la descarga en que se detectó el cambio, no la del cambio real en la provincia.

| clave | etapa_administrativa | titular_clave | vigente_desde | vigente_hasta |
|---|---|---|---|---|
| jujuy:2911 M 2022:MASA 40 | Solicitud de mina | AUSTROID ARGENTINA RESOURCES SAU | 2026-09-14 | 2026-10-09 |
| jujuy:2911 M 2022:MASA 40 | Mina concedida | AUSTROID ARGENTINA RESOURCES SAU | 2026-10-09 | (vigente) |

### 3. La clave estable

Para decir "este derecho cambió" hay que reconocerlo de una foto a la otra. El `id_fuente`
de cada provincia no es estable (Salta lo regenera entero entre descargas). La clave es
`provincia:expediente:nombre` normalizados (mayúsculas, sin acentos ni signos) y se calcula en
`catastro_noa/claves.py`. No alcanza sola: en Salta hay expedientes sin nombre con varios
polígonos. Reglas de desempate:

1. Un polígono que sigue igual (mismo `geom_hash`) conserva la clave que ya tenía.
2. Si en el grupo sobra un solo derecho viejo y uno nuevo, son el mismo (cambió la forma).
3. Los que quedan sin pareja son altas, con clave base + `#` + `geom_hash`.
4. Un alta y una baja de la misma provincia que comparten un polígono único, y además el
   nombre o el titular, son el mismo derecho con otro expediente (ej. `143-1412/18` pasa a
   `143-1412/2018`): conserva la clave y se registra `cambio_expediente` o `cambio_nombre`.
   Si cambian a la vez expediente, nombre y titular es otro derecho sobre el mismo terreno:
   baja y alta.

Las claves ya asignadas viven en el historial, así que una clave no cambia aunque cambie
el polígono. Limitación: si en un grupo con varios polígonos cambia más de uno a la vez, no
hay forma de saber cuáles corresponden y se registran como bajas y altas.

### 4. Historia hacia atrás

`scripts/reconstruir_historial.py` procesa los crudos guardados en `data/raw/` como si
fueran fotos con su fecha y arma el historial desde cero. Los catastros de años anteriores
que tiene el equipo de investigación se podrían cargar igual, para que la tabla de novedades
cubra varios años y no solo desde que arrancó el seguimiento. Falta acordar el formato de
esos archivos.

## La aplicación

`streamlit_app.py` está publicada en Streamlit Community Cloud (rama `main`, instala desde
`uv.lock`). Lee solo los archivos que versiona el workflow, con una caché de una hora, y no
tiene base de datos ni servidor propio:

| Archivo | Para qué lo usa |
|---|---|
| `data/snapshot/catastro_noa.csv` | Filtros, indicadores, tabla y ficha de cada derecho. |
| `data/snapshot/geometrias.parquet` | Mapa (polígonos simplificados con una tolerancia de unos 20 m, para que sea ágil) y descarga en GeoPackage (sin simplificar). |
| `data/historial/novedades.csv` | Vistas Novedades y Buscar expediente. |
| `data/historial/historial.parquet` | Vista Buscar expediente y expediente de cada novedad, incluso de derechos dados de baja. |
| `data/historial/descargas.csv` | Vista Descargas. Un día sin filas es un día en que el workflow no corrió. |
| `data/estado_fuentes.csv` | Fecha de los datos de cada provincia y avisos si una fuente falló o si la actualización se detuvo. |

Las provincias, etapas y estados salen de los datos: si se suma una provincia, la app la
muestra sin tocar el código. Los filtros se aplican a Mapa y Tabla; Novedades solo filtra por
provincia, y Buscar expediente y Descargas no los usan.

**Pendiente:** las capas de contexto (cuencas, localidades y parajes) y los cruces espaciales.
La base ya tiene los polígonos, así que el cruce sería con `geopandas.sjoin`.

## Qué se versiona y cuánto pesa

| Archivo | ¿Se versiona? | Motivo |
|---|---|---|
| `data/raw/` | No | Crudos grandes; se pueden volver a bajar. |
| `data/snapshot/catastro_noa.csv` | **Sí, cuando cambia** | Atributos de cada derecho más `clave` y `geom_hash`. Es texto ordenado y sin columnas que cambian en cada corrida (`fuente`, `fecha_descarga`, `fecha_actualizacion_fuente`, `id_fuente`): git guarda solo las líneas que cambian. Es la fuente del historial. |
| `data/snapshot/geometrias.parquet` | Sí, solo si cambia alguna forma | Un polígono por `geom_hash`. Es binario (~1 MB), por eso solo se reescribe cuando el conjunto de hashes cambia. |
| `data/historial/novedades.csv`, `historial.parquet` | Sí, solo si hay novedades | Chicos (el parquet ~0,5 MB); son lo que consume la app. |
| `data/historial/descargas.csv` | Sí, en cada corrida | Una fila por día y provincia: resultado, registros, fuente y motivo del error. |
| `data/estado_fuentes.csv` | Sí, en cada corrida | Una fila por provincia: último intento, última descarga buena, resultado y motivo del error. Como cambia en cada corrida, siempre hay un commit: GitHub desactiva los cron de los repos públicos sin actividad en 60 días. |
| `data/processed/` | No | Salidas locales: parquet completo y planilla de revisión. Se regeneran con el pipeline. |

**Por qué la geometría va aparte.** Poner el polígono como texto (WKT) en el CSV haría que
cualquier diferencia de decimales o de orden de vértices ensucie el diff. En cambio, el
`geom_hash` se calcula sobre el polígono normalizado (coordenadas a 6 decimales, unos
0,1 m, y vértices en orden canónico): cambia solo si cambia la forma.

**Frecuencia.** La descarga es diaria (06:00 en Argentina). Se puede pasar a semanal cambiando
el cron del workflow, y se puede lanzar a mano desde la pestaña Actions.

**Si una provincia falla.** Cada provincia es independiente: si una no responde, cambia su
formato (le faltan columnas indispensables) o trae menos de la mitad de los derechos que tenía,
las demás se actualizan igual y la que falló conserva en la foto sus filas y polígonos
anteriores (no se registran bajas: una foto incompleta se leería como la baja de todos sus
derechos). Una caída de más de la mitad se acepta si la descarga siguiente trae la misma
cantidad, para que una baja masiva real no deje a la provincia congelada. El resultado queda
en `data/estado_fuentes.csv` y, con `--estricto`, la corrida termina en rojo después de
commitear, así GitHub avisa por mail.

**Versiones fijas.** `uv.lock` fija todas las dependencias, `.python-version` la versión de
Python y el workflow la de uv: una versión nueva de cualquiera de ellas no puede romper el
pipeline sin que nadie haya tocado nada. Los tests de la app no corren en el workflow, para que
una falla en ella no frene los datos.

**Límites de GitHub.** 100 MB por archivo y se recomienda un repo de menos de 1 GB. Con este
esquema se está muy lejos de ambos durante años. GitHub Actions es gratis para repos públicos.
