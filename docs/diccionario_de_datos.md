# Diccionario de datos

## Base unificada

Archivo: `data/processed/catastro_noa.parquet` (GeoParquet, EPSG:4326). La misma tabla
sin geometría está en `catastro_noa.csv` y en la hoja `BASE` de
`revision_estandarizacion.xlsx`. Un registro = un polígono publicado por la provincia
(en general, un derecho minero).

Lo genera `uv run python -m catastro_noa` (ver [README](../README.md)).

### Columnas

| Columna | Tipo | Descripción |
|---|---|---|
| `provincia` | texto | `jujuy`, `salta` o `catamarca`. |
| `id_fuente` | texto | Identificador interno del registro en la fuente (Jujuy `id`, Salta `fid`). Puede cambiar entre descargas: **no** sirve como clave estable. |
| `expediente` | texto | Número de expediente tal como lo publica la provincia. No es único (ver notas). |
| `nombre` | texto | Nombre del derecho minero (mina, cateo, cantera…). |
| `titular` | texto | Titular / concesionario tal como lo publica la fuente. Vacío si la fuente pone un texto que no es un titular (ej. "Vacancia Solicitada"). |
| `titular_clave` | texto | Titular normalizado para agrupar y cruzar provincias: mayúsculas, sin acentos ni puntuación, formas jurídicas como sigla (`SA`, `SAU`, `SRL`, `SE`, `SAPEM`). |
| `titulares_claves` | texto | Una clave por cada titular del registro, separadas por `\|` (ej. `PEREZ JUAN\|GOMEZ ANA`). Igual a `titular_clave` cuando hay uno solo. Vacío si no hay titular. |
| `n_titulares` | entero | Cantidad de titulares del registro (0 si no hay). |
| `tramite_original` | texto | Tipo de trámite publicado (Jujuy `rg_tipo`, Salta `tipo`). Catamarca no lo publica. |
| `estado_original` | texto | Estado publicado por la fuente. Catamarca no lo publica. |
| `etapa_administrativa` | texto | Trámite propio de cada provincia, con nombre prolijo (Cateo, Manifestación, Solicitud de mina, Mina concedida…). |
| `etapa_proyecto` | texto | Etapa común entre provincias: `Exploración`, `Explotación` o `Canteras y otros`. **Provisoria** hasta que el equipo cierre la planilla de trámites. |
| `estado` | texto | Estado legal homologado: `Vigente`, `En trámite`, `Vacante`, `Anulado`, `Con recurso`, `Otro`. **Propuesta**, a validar. |
| `mineral_original` | texto | Campo de mineral tal como lo publica la fuente (limpio de saltos de línea y espacios). |
| `minerales` | texto | Minerales reconocidos, con nombre canónico, separados por `; ` (ej. `Boratos; Potasio; Litio`). |
| `grupos_minerales` | texto | Grupos del equipo presentes, separados por `; `, en este orden: Metalíferos; Litio y potasio; Depósitos evaporíticos; Tierras raras; Canteras, rocas de aplicación y otros minerales. Los *Subproductos* (cesio, rubidio) no suman grupo. |
| `categoria_codigo` | texto | Categoría del Código de Minería si el texto la menciona: `1`, `2` o `1 y 2`. |
| `tiene_litio` | booleano | `True` si entre los minerales está el litio. |
| `mineral_sin_clasificar` | texto | Palabras del campo mineral que no se pudieron clasificar. Si no está vacío, conviene revisar el diccionario. No se completa cuando el texto describe una instalación de una servidumbre (campamento, colas, relaves, etc.): esos términos no son minerales y figuran en el diccionario como `no_mineral`. En las servidumbres tampoco se completa: el campo describe la instalación o las minas a las que sirve. |
| `departamento` | texto | Departamento, en mayúsculas y sin acentos. |
| `superficie_ha_fuente` | número | Superficie en hectáreas declarada por la fuente (Jujuy `superficie`, Salta `area`). Catamarca no la publica. |
| `superficie_ha_calculada` | número | Superficie en hectáreas calculada desde el polígono (área geodésica sobre el elipsoide WGS84). Disponible para todas las provincias. |
| `fecha_inicio` | fecha | Fecha de inicio del trámite (solo Salta). |
| `anio_expediente` | entero | Año de inicio del expediente: en Salta, el de `fecha_inicio` (o el del número si falta); en Jujuy, el que figura en el número (`3428-T-2024` → 2024). Vacío si no se puede saber. |
| `fecha_actualizacion_fuente` | fecha | Fecha de revisión que informa la fuente (solo Jujuy). |
| `fuente` | texto | De dónde salió el dato (servicio y capa, o archivo crudo reutilizado). |
| `fecha_descarga` | fecha | Día en que se descargó el dato crudo. |
| `geometry` | polígono | Geometría en EPSG:4326 (lat/lon WGS84). Las geometrías inválidas se reparan. |

### Correspondencia con los campos de cada fuente

| Columna | Jujuy (SHP) | Salta (WFS) | Catamarca (WFS / visor) |
|---|---|---|---|
| `id_fuente` | `id` | `fid` | — |
| `expediente` | `expediente` | `expediente` | `EXPEDIENTE`, o `EXPTE DGTL` / `exptedgtl` |
| `nombre` | `nombre` | `nombre` | `MINA` / `mina` |
| `titular` | `titular_ac` | `concesionario` | `CONCSRIO` / `concsrio` |
| `tramite_original` | `rg_tipo` | `tipo` | — |
| `estado_original` | `estado` | `estado` | — |
| `mineral_original` | `tipo_miner` | `mineral` | `MINERAL` / `mineral` |
| `departamento` | `depto` | `departamento` | `DPTO` / `dpto` |
| `superficie_ha_fuente` | `superficie` | `area` ("22,4675 ha") | — |
| `fecha_inicio` | — | `fecha_inicio` | — |
| `fecha_actualizacion_fuente` | `revision` | — | — |
| CRS original | EPSG:22183 | EPSG:4326 | EPSG:4326 |

**Campos de la fuente que se descartan:**

- Jujuy `dom_corre`: mails de contacto (dato personal). **Nunca se persiste.**
- Jujuy `objectid`, `tipo` (sigla de `rg_tipo`), `area`, `gm`, `reconstruc`: internos o
  redundantes. Siguen disponibles en el crudo.
- Salta `coordenadas` (WKT duplicado de la geometría), `municipio`, `lugar`,
  `resolucion`: no tienen equivalente en las otras provincias. Siguen en el crudo.

### Notas

- **El expediente no es una clave única.** Un mismo expediente puede tener varios
  polígonos (ej. convenios de Salta, demasías en Jujuy). La clave para seguir un derecho
  en el tiempo está explicada en [`arquitectura.md`](arquitectura.md).
- La clasificación de minerales, etapas y estados sale de los CSV de
  [`diccionarios/`](../diccionarios/). Para corregir una clasificación se edita el CSV y
  se vuelve a correr el pipeline. No hay que tocar código.

## Foto versionada

`data/snapshot/catastro_noa.csv` tiene las mismas columnas que la base, con estas diferencias:

- Agrega `clave` (identificador estable del derecho entre fotos) y `geom_hash` (huella del
  polígono normalizado).
- No tiene `geometry`: los polígonos están en `data/snapshot/geometrias.parquet`, uno por
  `geom_hash`.
- No tiene las columnas que cambian en cada descarga: `id_fuente`, `fuente`, `fecha_descarga` y
  `fecha_actualizacion_fuente`.

## Historial

`data/historial/historial.parquet` tiene las columnas de la foto más `vigente_desde` (inclusive)
y `vigente_hasta` (exclusivo; vacío si la versión está vigente).

`data/historial/novedades.csv`:

| Columna | Descripción |
|---|---|
| `fecha` | Día de la descarga en que se detectó el cambio, no el del acto administrativo. |
| `provincia` | Provincia del derecho. |
| `clave` | Clave estable del derecho. |
| `nombre` | Nombre del derecho. |
| `evento` | `alta`, `baja`, `cambio_titular`, `cambio_etapa`, `cambio_estado`, `cambio_mineral`, `cambio_superficie`, `cambio_geometria`, `cambio_expediente` o `cambio_nombre`. |
| `campo` | Columna que cambió. Vacío en altas y bajas. |
| `antes`, `despues` | Valor anterior y nuevo. |

## Estado de las fuentes

`data/estado_fuentes.csv` (una fila por provincia):

| Columna | Descripción |
|---|---|
| `provincia` | Provincia. |
| `ultimo_intento` | Fecha del último intento de descarga. |
| `ultima_descarga_ok` | Fecha de la última descarga correcta. |
| `resultado` | Resultado del último intento: `ok` o `error`. |
| `registros` | Registros de la última descarga correcta. |
| `registros_intento` | Registros del último intento; sirve para aceptar una caída grande si se repite. |
| `fuente` | Servicio y capa de origen. |
| `detalle` | Motivo del error, si lo hubo. |

`data/historial/descargas.csv` (una fila por día y provincia): `fecha`, `provincia`, `resultado`,
`registros`, `fuente` y `detalle`. Un día sin filas es un día en que el workflow no corrió.
