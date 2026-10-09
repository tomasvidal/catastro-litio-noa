# Diccionario de datos: base unificada

Archivo: `data/processed/catastro_noa.parquet` (GeoParquet, EPSG:4326). La misma tabla
sin geometría está en `catastro_noa.csv` y en la hoja `BASE` de
`revision_estandarizacion.xlsx`. Un registro = un polígono publicado por la provincia
(en general, un derecho minero).

Lo genera `uv run python -m catastro_noa` (ver [README](../README.md)).

## Columnas

| Columna | Tipo | Descripción |
|---|---|---|
| `provincia` | texto | `jujuy`, `salta` o `catamarca`. |
| `id_fuente` | texto | Identificador interno del registro en la fuente (Jujuy `id`, Salta `fid`). Puede cambiar entre descargas: **no** sirve como clave estable. |
| `expediente` | texto | Número de expediente tal como lo publica la provincia. No es único (ver notas). |
| `nombre` | texto | Nombre del derecho minero (mina, cateo, cantera…). |
| `titular` | texto | Titular / concesionario tal como lo publica la fuente. Vacío si la fuente pone un texto que no es un titular (ej. "Vacancia Solicitada"). |
| `titular_clave` | texto | Titular normalizado para agrupar y cruzar provincias: mayúsculas, sin acentos ni puntuación, formas jurídicas como sigla (`SA`, `SAU`, `SRL`, `SE`, `SAPEM`). |
| `tramite_original` | texto | Tipo de trámite publicado (Jujuy `rg_tipo`, Salta `tipo`). Catamarca no lo publica. |
| `estado_original` | texto | Estado publicado por la fuente. Catamarca no lo publica. |
| `etapa_administrativa` | texto | Trámite propio de cada provincia, con nombre prolijo (Cateo, Manifestación, Solicitud de mina, Mina concedida…). |
| `etapa_proyecto` | texto | Etapa común entre provincias: `Exploración`, `Explotación` o `Canteras y otros`. **Provisoria** hasta que el equipo cierre la planilla de trámites. |
| `estado` | texto | Estado legal homologado: `Vigente`, `En trámite`, `Vacante`, `Anulado`, `Con recurso`, `Otro`. **Propuesta**, a validar. |
| `mineral_original` | texto | Campo de mineral tal como lo publica la fuente (limpio de saltos de línea y espacios). |
| `minerales` | texto | Minerales reconocidos, con nombre canónico, separados por `; ` (ej. `Boratos; Potasio; Litio`). |
| `grupos_minerales` | texto | Grupos del equipo presentes, separados por `; `, en este orden: Metalíferos; Litio y potasio; Depósitos evaporíticos; Tierras raras; Canteras, rocas de aplicación y otros minerales. |
| `categoria_codigo` | texto | Categoría del Código de Minería si el texto la menciona: `1`, `2` o `1 y 2`. |
| `tiene_litio` | booleano | `True` si entre los minerales está el litio. |
| `mineral_sin_clasificar` | texto | Palabras del campo mineral que no se pudieron clasificar. Si no está vacío, conviene revisar el diccionario. |
| `departamento` | texto | Departamento, en mayúsculas y sin acentos. |
| `superficie_ha_fuente` | número | Superficie en hectáreas declarada por la fuente (Jujuy `superficie`, Salta `area`). Catamarca no la publica. |
| `superficie_ha_calculada` | número | Superficie en hectáreas calculada desde el polígono (área geodésica sobre el elipsoide WGS84). Disponible para todas las provincias. |
| `fecha_inicio` | fecha | Fecha de inicio del trámite (solo Salta). |
| `fecha_actualizacion_fuente` | fecha | Fecha de revisión que informa la fuente (solo Jujuy). |
| `fuente` | texto | De dónde salió el dato (servicio y capa, o archivo crudo reutilizado). |
| `fecha_descarga` | fecha | Día en que se descargó el dato crudo. |
| `geometry` | polígono | Geometría en EPSG:4326 (lat/lon WGS84). Las geometrías inválidas se reparan. |

## Correspondencia con los campos de cada fuente

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

## Notas

- **El expediente no es una clave única.** Un mismo expediente puede tener varios
  polígonos (ej. convenios de Salta, demasías en Jujuy). La clave para seguir un derecho
  en el tiempo se define en la Fase 3.
- La clasificación de minerales, etapas y estados sale de los CSV de
  [`diccionarios/`](../diccionarios/). Para corregir una clasificación se edita el CSV y
  se vuelve a correr el pipeline. No hay que tocar código.
