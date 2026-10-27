# catastro-litio-noa

Proyecto interno UNSAM (Escuela de Política y Gobierno, Área de Ambiente y Política),
en el marco del CIAI y de la Licenciatura en Ciencia de Datos:
**"Litio, agua y comunidades: plataforma de datos socioambientales para el monitoreo de
la minería en Argentina"**.

## Alcance

Los catastros mineros de **Jujuy, Salta y Catamarca** son públicos, pero cada provincia
los publica en un formato, con un esquema y con una frecuencia distintos. Eso hace
difícil seguir la expansión del litio, ver cómo se concentra la titularidad en grupos
económicos o detectar cambios de titular y de estado legal en el tiempo.

El proyecto construye un **pipeline reproducible y de costo cero** (patrón
*git-scraping*, sin servidores) que:

1. **Ingiere** los catastros oficiales de las tres provincias (WFS / descargas directas).
2. **Homologa** las variables en un esquema común: expediente, titular, mineral,
   trámite/etapa, estado legal, superficie y geometría.
3. **Audita en el tiempo** las diferencias entre descargas: altas, bajas, transferencias
   de titularidad, cambios de estado y de superficie.
4. **Publica** una app web (Streamlit) para consultar y mapear los datos y sus novedades.

**Fuera de alcance:** el CIMA nacional (no responde desde nuestro entorno), las
provincias fuera del NOA y cualquier dato que no sea público y oficial.

## Documentación

| Documento | Qué tiene |
|---|---|
| [`docs/plan_de_trabajo.md`](docs/plan_de_trabajo.md) | El plan de trabajo: objetivos, metodología, productos y cronograma por fase. |
| [`TAREAS.md`](TAREAS.md) | El avance: checklist de las 4 fases y la próxima tarea. |
| [`docs/metodologia.md`](docs/metodologia.md) | Cómo se homologa cada variable y qué criterios faltan validar. |
| [`docs/arquitectura.md`](docs/arquitectura.md) | Cómo funciona el pipeline y cómo se usa GitHub como base de datos para detectar cambios. |
| [`docs/diagrama_app.html`](docs/diagrama_app.html) | Diagrama interactivo de la app final por fase: qué está hecho y qué falta (abrir en el navegador). |
| [`docs/diccionario_de_datos.md`](docs/diccionario_de_datos.md) | Las columnas de la base unificada y de qué campo sale cada una en cada provincia. |

## Estado

| Fase | Estado |
|---|---|
| 1. Relevamiento de fuentes y planificación | ✅ Hecha |
| 2. Ingesta, homologación y CI/CD | ⏳ En curso: estandarización hecha para Jujuy y Salta. Falta la validación del equipo y GitHub Actions. Catamarca, en pausa |
| 3. Auditoría temporal de cambios | Pendiente |
| 4. App web, documentación y cierre | Pendiente |

El checklist detallado y la próxima tarea están en **[`TAREAS.md`](TAREAS.md)**.

## Fuentes

| Provincia | Cómo se obtiene | Registros (20/10/2026) | CRS original |
|---|---|---|---|
| **Jujuy** | SHP del Juzgado Administrativo de Minas en `mineriajujuy.gob.ar` (link con token que se saca de la landing). Se actualiza a diario. | 1.780 | EPSG:22183 |
| **Salta** | WFS de `geoportal.salta.gob.ar`, capa `geonode:poligonos_adaf55f39328ff45c8c60e94eb13a7a0` ("Catastro Minero"). | 3.924 | EPSG:4326 |
| **Catamarca** | WFS de `nodoide.catamarca.gob.ar`, capa `idecat:MINAS_<fecha>` (el nombre cambia con cada actualización); si no hay capa, el visor estático de minería. Detrás de Cloudflare (`cloudscraper`). No publica trámite, estado ni superficie. | ⏸ En pausa: el servidor no responde | EPSG:4326 |

## Cómo correrlo

Requiere [uv](https://docs.astral.sh/uv/).

```bash
uv sync                                   # instala dependencias
uv run python -m catastro_noa             # descarga las provincias activas (Jujuy y Salta) y genera la base
uv run python -m catastro_noa --offline   # reprocesa con los últimos crudos descargados
uv run python -m catastro_noa --provincias jujuy salta catamarca   # incluye Catamarca
uv run python -m catastro_noa --estricto  # falla si alguna provincia no se pudo descargar
uv run pytest                             # tests
```

Una vez por semana, un workflow de GitHub Actions (`.github/workflows/actualizar.yml`)
corre el pipeline con `--estricto` y commitea la foto en `data/snapshot/` si hubo cambios.
También se puede lanzar a mano desde la pestaña Actions.

Foto versionada en `data/snapshot/` (es lo que commitea el workflow):

- `catastro_noa.csv`: un registro por derecho, sin geometría y con la columna `geom_hash`.
  Está ordenado y no tiene columnas que cambian en cada corrida, así que un diff de git
  muestra solo cambios reales.
- `geometrias.parquet`: un polígono por `geom_hash`. Solo se reescribe si cambia alguna
  forma.

Y en `data/historial/`, la auditoría temporal:

- `novedades.csv`: un evento por cada cambio detectado (altas, bajas y cambios de titular,
  etapa, estado, mineral, superficie, geometría, expediente o nombre). Solo se agregan filas.
- `historial.parquet`: cada versión de cada derecho con `vigente_desde` y `vigente_hasta`.

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
├── TAREAS.md                 checklist de todas las fases y próxima tarea a retomar
├── pyproject.toml / uv.lock  dependencias (uv)
│
├── catastro_noa/             paquete del pipeline (Fase 2 en adelante)
│   ├── __init__.py           rutas y provincias activas
│   ├── __main__.py           punto de entrada: uv run python -m catastro_noa
│   ├── fuentes.py            descarga de cada provincia + snapshots crudos fechados
│   ├── estandarizar.py       esquema canónico: crudo de cada provincia -> columnas comunes
│   ├── minerales.py          clasificación del campo mineral (grupos + categoría del Código)
│   ├── tramites.py           etapa administrativa, etapa del proyecto y estado legal
│   ├── titulares.py          clave comparable del titular
│   ├── texto.py              limpieza de texto y números
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
├── scripts/                  scripts de la Fase 1 (se mantienen como registro)
│   ├── explorar_fuentes.py   verificación de acceso a las 3 fuentes
│   ├── armar_relevamiento.py planilla de relevamiento para el equipo
│   └── reconstruir_historial.py  arma el historial desde los crudos de data/raw/
│
├── data/
│   ├── raw/                  descargas crudas por provincia y fecha (ignorado por git)
│   ├── samples/              muestras chicas de la Fase 1 (versionadas)
│   ├── processed/            salidas locales del pipeline (ignorado por git)
│   ├── snapshot/             foto versionada del catastro, la actualiza el workflow
│   └── historial/            novedades.csv e historial.parquet (versiones con vigencia)
│
├── .github/workflows/        actualizar.yml: descarga semanal y commit de la foto
│
└── docs/
    ├── plan_de_trabajo.md        plan de trabajo: objetivos, metodología y cronograma
    ├── metodologia.md            criterios de homologación y pendientes de validación
    ├── arquitectura.md           pipeline, git-scraping y diseño de las fases 3 y 4
    ├── diagrama_app.html         diagrama interactivo de la app final por fase (hecho / falta)
    ├── diccionario_de_datos.md   columnas de la base unificada y su origen en cada fuente
    └── insumos/                  planillas de criterios del equipo de investigación
        ├── Denominaciones_provinciales_minerales.xlsx
        └── Denominaciones_provinciales_tramites.xlsx   (todavía no definida)
```

## Datos y ética

- Solo información pública de organismos oficiales.
- Los campos de contacto personal de las fuentes (ej. mails en `dom_corre` de Jujuy)
  se descartan y nunca se guardan en las salidas.
- Si alguna fuente llegara a pedir credenciales, van en `.env` (ignorado) o en los
  Secrets de GitHub Actions, nunca en el código.
