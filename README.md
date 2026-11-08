# catastro-litio-noa

Proyecto interno UNSAM (Escuela de Política y Gobierno, Área de Ambiente y Política),
en el marco del CIAI y de la Licenciatura en Ciencia de Datos:
**"Litio, agua y comunidades: plataforma de datos socioambientales para el monitoreo de
la minería en Argentina"**.

**Aplicación:** <https://catastro-litio-noa.streamlit.app>. Si lleva un tiempo sin visitas, la
plataforma la suspende y muestra un botón para volver a activarla.

## Alcance

Los catastros mineros de las provincias del NOA son públicos, pero cada provincia los
publica en un formato, con un esquema y con una frecuencia distintos. Eso hace difícil
seguir la expansión del litio, ver cómo se concentra la titularidad en grupos económicos o
detectar cambios de titular y de estado legal en el tiempo.

El proyecto construye un **pipeline reproducible y de costo cero** (patrón
*git-scraping*, sin servidores) que:

1. **Ingiere** los catastros oficiales de Jujuy y Salta (descarga directa y WFS).
2. **Homologa** las variables en un esquema común: expediente, titular, mineral,
   trámite/etapa, estado legal, superficie y geometría.
3. **Audita en el tiempo** las diferencias entre descargas: altas, bajas, transferencias
   de titularidad, cambios de estado y de superficie.
4. **Publica** una app web (Streamlit) para consultar y mapear los datos y sus novedades.

**Fuera de alcance:** el CIMA nacional (no respondió durante el relevamiento), las provincias
fuera del NOA y cualquier dato que no sea público y oficial.

## Documentación

| Documento | Qué tiene |
|---|---|
| [`docs/diagrama_flujo.html`](docs/diagrama_flujo.html) | Diagrama interactivo: cómo pasan los datos de las fuentes a la aplicación y qué herramienta interviene en cada paso (abrir en el navegador). |
| [`docs/arquitectura.md`](docs/arquitectura.md) | Cómo funciona el pipeline, cómo se usa GitHub como base de datos y cómo la app lee los datos. |
| [`docs/metodologia.md`](docs/metodologia.md) | Cómo se homologa cada variable y qué criterios faltan validar. |
| [`docs/diccionario_de_datos.md`](docs/diccionario_de_datos.md) | Las columnas de cada tabla y de qué campo sale cada una en cada provincia. |
| [`docs/plan_de_trabajo.md`](docs/plan_de_trabajo.md) | El plan de trabajo original: objetivos, metodología, productos y cronograma por fase. |

## Estado

| Fase | Estado |
|---|---|
| 1. Relevamiento de fuentes y planificación | Hecha |
| 2. Ingesta, homologación y CI/CD | Hecha para Jujuy y Salta, con descarga automática diaria. Quedan criterios por validar con el equipo |
| 3. Auditoría temporal de cambios | Hecha: novedades e historial con vigencias desde el 14/9/2026 en Jujuy y el 9/10/2026 en Salta. Falta cargar los catastros de años anteriores |
| 4. App web, documentación y cierre | App publicada. Faltan las capas de contexto (cuencas, localidades y parajes) y una guía de uso |

## Fuentes

| Provincia | Cómo se obtiene | Registros (5/11/2026) | CRS original |
|---|---|---|---|
| **Jujuy** | SHP del Juzgado Administrativo de Minas en `mineriajujuy.gob.ar` (link con token que se saca de la página de descarga). | 1.781 | EPSG:22183 |
| **Salta** | WFS de `geoportal.salta.gob.ar`. La capa se busca por su título ("Catastro Minero"); si no aparece, se usa el último nombre conocido. | 3.924 | EPSG:4326 |

## Cómo correrlo

Requiere [uv](https://docs.astral.sh/uv/).

```bash
uv sync                                   # instala dependencias
uv run python -m catastro_noa             # descarga Jujuy y Salta y genera la base
uv run python -m catastro_noa --offline   # reprocesa con los últimos crudos descargados
uv run python -m catastro_noa --estricto  # termina con error si alguna provincia no se pudo actualizar
uv run pytest                             # tests
uv run python run.py                      # app de consulta (lee data/snapshot/ y data/historial/)
```

Todos los días a las 06:00 (hora argentina), un workflow de GitHub Actions
(`.github/workflows/actualizar.yml`) corre los tests y el pipeline con `--estricto`, y commitea
`data/snapshot/`, `data/historial/` y `data/estado_fuentes.csv`. También se puede lanzar a mano
desde la pestaña Actions. Cada commit actualiza la app publicada.

Si una provincia falla (no responde, cambia su formato o trae muchos menos registros que antes),
las demás se actualizan igual, la que falló conserva sus datos anteriores, el problema queda en
`data/estado_fuentes.csv` y la corrida termina en rojo para que GitHub avise por mail. La app
lee ese archivo: muestra de qué fecha son los datos de cada provincia y avisa si una fuente
falló o si la actualización dejó de correr.

### La aplicación

Tiene filtros por provincia, litio, grupo de mineral, etapa, estado, departamento y titular,
cuatro indicadores y cinco vistas:

| Vista | Qué muestra |
|---|---|
| **Mapa** | Derechos coloreados por etapa, con la ficha de cada uno al pasar el cursor. |
| **Tabla** | Registros filtrados, descargables en CSV, Excel y GeoPackage (con la geometría original). |
| **Novedades** | Cambios detectados entre descargas, filtrables por tipo. |
| **Buscar expediente** | Datos actuales y cambios registrados de un derecho, aunque ya no figure en el catastro. |
| **Descargas** | Resultado de la descarga de cada día y provincia. |

### Los archivos

Foto versionada en `data/snapshot/` (es lo que commitea el workflow):

- `catastro_noa.csv`: un registro por derecho, sin geometría y con las columnas `clave` y
  `geom_hash`. Está ordenado y no tiene columnas que cambian en cada corrida, así que un diff de
  git muestra solo cambios reales.
- `geometrias.parquet`: un polígono por `geom_hash`. Solo se reescribe si cambia alguna forma.

En `data/historial/`, la auditoría temporal:

- `novedades.csv`: un evento por cada cambio detectado (altas, bajas y cambios de titular,
  etapa, estado, mineral, superficie, geometría, expediente o nombre). Solo se agregan filas.
- `historial.parquet`: cada versión de cada derecho con `vigente_desde` y `vigente_hasta`.
- `descargas.csv`: el resultado de la descarga de cada día y provincia.

Para reconstruir el historial desde los crudos guardados:
`uv run python scripts/reconstruir_historial.py`.

Salidas locales en `data/processed/` (ignoradas por git):

- `catastro_noa.parquet`: base unificada con geometría (GeoParquet, EPSG:4326).
- `catastro_noa.csv`: la misma base, sin geometría.
- `revision_estandarizacion.xlsx`: planilla para que el equipo revise la clasificación
  de minerales, etapas y estados.

Las columnas están descriptas en [`docs/diccionario_de_datos.md`](docs/diccionario_de_datos.md).

### Corregir una clasificación

Las reglas de homologación no están en el código: están en CSV editables en
`diccionarios/`. Para corregir cómo se clasifica un mineral, un trámite o un estado, se
edita el CSV y se vuelve a correr el pipeline. Por ejemplo, para que `"SAL DE MESA"`
cuente como *Sal* (Depósitos evaporíticos), se agrega a `diccionarios/minerales.csv`:

```csv
Sal de mesa,nombre,Sal,Depósitos evaporíticos,investigadores,
```

## Estructura del repositorio

```
catastro-litio-noa/
├── README.md                 este archivo: alcance, estado, cómo correrlo y estructura
├── pyproject.toml / uv.lock  dependencias (uv)
├── .python-version           versión de Python fija (3.12)
├── streamlit_app.py          app de consulta: mapa, filtros, tabla, novedades, búsqueda y descargas
├── run.py                    abre la app desde cualquier carpeta
│
├── catastro_noa/             paquete del pipeline
│   ├── __init__.py           rutas y provincias activas
│   ├── __main__.py           punto de entrada: uv run python -m catastro_noa
│   ├── fuentes.py            descarga de cada provincia + crudos fechados
│   ├── estandarizar.py       esquema canónico: crudo de cada provincia -> columnas comunes
│   ├── minerales.py          clasificación del campo mineral (grupos + categoría del Código)
│   ├── tramites.py           etapa administrativa, etapa del proyecto y estado legal
│   ├── titulares.py          clave comparable del titular y separación de cotitulares
│   ├── texto.py              limpieza de texto y números
│   ├── estado.py             estado de cada fuente y registro diario de descargas
│   ├── salidas.py            escritura de parquet, csv y planilla de revisión
│   ├── snapshot.py           foto versionada: csv de atributos + geometrías por hash
│   ├── claves.py             clave estable de cada derecho entre fotos
│   └── auditoria.py          comparación con el historial: novedades y versiones con vigencia
│
├── diccionarios/             reglas de homologación, editables y versionadas
│   ├── minerales.csv         término -> mineral canónico -> grupo (origen: investigadores/propuesta)
│   ├── etapas.csv            trámite de cada provincia -> etapa administrativa / del proyecto
│   └── estados.csv           estado de cada provincia -> estado homologado
│
├── tests/                    pytest (uv run pytest)
│
├── scripts/                  scripts sueltos (los de la Fase 1 se mantienen como registro)
│   ├── explorar_fuentes.py   verificación de acceso a las fuentes
│   ├── armar_relevamiento.py planilla de relevamiento para el equipo
│   ├── reconstruir_historial.py  arma el historial desde los crudos de data/raw/
│   └── armar_planilla_titulares.py  planilla para clasificar titulares (tipo de actor, capital)
│
├── data/
│   ├── raw/                  descargas crudas por provincia y fecha (ignorado por git)
│   ├── samples/              muestras chicas de la Fase 1 (versionadas)
│   ├── processed/            salidas locales del pipeline (ignorado por git)
│   ├── snapshot/             foto versionada del catastro, la actualiza el workflow
│   ├── historial/            novedades, versiones con vigencia y registro de descargas
│   └── estado_fuentes.csv    resultado de la última descarga de cada provincia
│
├── .github/workflows/        actualizar.yml: descarga diaria y commit de los datos
│
└── docs/
    ├── diagrama_flujo.html       diagrama interactivo del flujo de datos
    ├── arquitectura.md           pipeline, git-scraping y lectura de los datos desde la app
    ├── metodologia.md            criterios de homologación y pendientes de validación
    ├── diccionario_de_datos.md   columnas de cada tabla y su origen en cada fuente
    ├── plan_de_trabajo.md        plan de trabajo original
    └── insumos/                  planillas de criterios del equipo de investigación
```

## Datos y ética

- Solo información pública de organismos oficiales.
- Los campos de contacto personal de las fuentes (ej. mails en `dom_corre` de Jujuy)
  se descartan y nunca se guardan en las salidas.
- Si alguna fuente llegara a pedir credenciales, van en `.env` (ignorado) o en los
  Secrets de GitHub Actions, nunca en el código.
