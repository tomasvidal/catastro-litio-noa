# Arquitectura: GitHub como base de datos

Cómo funciona el pipeline completo, de punta a punta, sin servidores ni costos. La Fase 2
ya está implementada. Lo que corresponde a las Fases 3 y 4 es el **diseño previsto**.

## La idea: *git-scraping*

Git guarda cada versión de cada archivo, con fecha y con el detalle de qué líneas
cambiaron. Si todos los días se guarda (commitea) el catastro como un CSV ordenado, con
una línea por derecho minero, **el historial de git se convierte en una serie de tiempo
del catastro**:

```
commit 2026-11-03  "snapshot 2026-11-03"
-jujuy,2917-M-2022,MASA 46,AUSTROID ARGENTINA RESOURCES S.A.U.,SOLICITUD DE MINA,EN TRAMITE,...
+jujuy,2917-M-2022,MASA 46,AUSTROID ARGENTINA RESOURCES S.A.U.,MINA CONCEDIDA,CONCEDIDA,...
```

Ese diff dice: "el 3/11 el derecho MASA 46 pasó de solicitud de mina a mina concedida".
No hace falta una base de datos: GitHub almacena, versiona y respalda gratis, y un robot
(GitHub Actions) se encarga de descargar y commitear todos los días.

## Flujo completo

```
          todos los días (GitHub Actions, cron)
                        │
   ┌────────────────────▼─────────────────────┐
   │ 1. INGESTA          catastro_noa/fuentes  │  Jujuy SHP, Salta WFS (Catamarca en pausa)
   │ 2. HOMOLOGACIÓN     catastro_noa/...      │  esquema común + diccionarios/*.csv
   │ 3. AUDITORÍA        (Fase 3)              │  compara con el snapshot anterior
   └────────────────────┬─────────────────────┘
                        │ git commit + push (solo si algo cambió)
   ┌────────────────────▼─────────────────────┐
   │ Repositorio GitHub = "base de datos"      │
   │  data/processed/catastro_noa.csv   foto de HOY (su historial git = todas las fotos)
   │  data/historial/novedades.csv      registro de eventos (crece, nunca se borra)
   │  data/historial/historial.parquet  cada versión de cada derecho, con vigencia
   └────────────────────┬─────────────────────┘
                        │ cada push actualiza la app
   ┌────────────────────▼─────────────────────┐
   │ App Streamlit (Fase 4)                    │  lee los archivos del repo:
   │  mapa · filtros · novedades por zona      │  no consulta git en vivo
   └───────────────────────────────────────────┘
```

## Fase 3: de los diffs a tablas consultables

Leer diffs de git sirve para auditar, pero no sirve para una app: sería lento y difícil
de filtrar. Por eso, en cada corrida, el pipeline compara la foto nueva con la anterior y
**guarda el resultado como tablas**:

### 1. `novedades.csv`: registro de eventos

Una fila por cada cambio detectado. Se agregan filas y nunca se borran.

| fecha | provincia | clave | nombre | evento | campo | antes | después |
|---|---|---|---|---|---|---|---|
| 2026-11-03 | jujuy | jujuy:2917-M-2022:MASA 46 | MASA 46 | cambio_etapa | etapa_administrativa | Solicitud de mina | Mina concedida |
| 2026-11-03 | salta | salta:19944:TABALIZARO 09 | TABALIZARO 09 | cambio_titular | titular_clave | ALPHA LITHIUM ARGENTINA SA | OTRA EMPRESA SA |
| 2026-11-04 | salta | salta:25001:NUEVA I | NUEVA I | alta | | | |

Tipos de evento: `alta`, `baja`, `cambio_titular`, `cambio_etapa`, `cambio_estado`,
`cambio_mineral`, `cambio_superficie`, `cambio_geometria`.

### 2. `historial.parquet`: versiones con vigencia (SCD tipo 2)

Cada vez que un derecho cambia, se cierra su versión anterior y se abre una nueva. Así se
puede reconstruir el catastro **tal como estaba en cualquier fecha**:

| clave | etapa_administrativa | titular_clave | vigente_desde | vigente_hasta |
|---|---|---|---|---|
| jujuy:2917-M-2022:MASA 46 | Solicitud de mina | AUSTROID ARGENTINA RESOURCES SAU | 2022-05-10 | 2026-11-02 |
| jujuy:2917-M-2022:MASA 46 | Mina concedida | AUSTROID ARGENTINA RESOURCES SAU | 2026-11-03 | (vigente) |

### 3. La clave estable (requisito previo)

Para decir "este derecho cambió" hay que reconocerlo de una foto a la otra. El expediente
solo no alcanza (en Salta hay expedientes repetidos) y el `id_fuente` de cada provincia no
es estable. La propuesta es `provincia + expediente + nombre`, normalizados, con
desempate por geometría cuando haya repetidos.

### 4. Historia hacia atrás

Los catastros de años anteriores que tiene el equipo de investigación se procesan como
si fueran fotos viejas, con su fecha. Así, desde el primer día la tabla de novedades
cubre varios años (ej. 2022 → hoy) y no solo desde que arranca el robot.

## Fase 4: cómo responde la app "qué cambió en esta zona"

La app (Streamlit) carga tres cosas del repo: la foto actual con polígonos
(`catastro_noa.parquet`), las novedades y las capas de contexto (cuencas, localidades,
departamentos). Para una pregunta como *"¿qué derechos de litio de la cuenca X pasaron de
exploración a explotación en 2026?"*:

1. **Zona:** el usuario elige una cuenca o un departamento del menú, o dibuja un área
   en el mapa.
2. **Cruce espacial:** se toman los derechos cuyo polígono toca esa zona
   (`geopandas.sjoin` / `intersects`).
3. **Filtros de atributos:** `tiene_litio`, grupo de mineral, provincia, etc.
4. **Cruce con novedades** por `clave`: se filtra por fechas y tipo de evento (ej.
   `cambio_etapa` con `después = Explotación`).
5. **Resultado:** un mapa coloreado por tipo de evento, una tabla con antes y después, y
   un gráfico de eventos por mes.

Como el historial tiene vigencias, la app también puede mostrar la zona **en una fecha
pasada** (un deslizador de fecha) y comparar dos fechas.

## Qué se versiona y cuánto pesa

| Archivo | ¿Se versiona? | Motivo |
|---|---|---|
| `data/raw/` | No | Crudos grandes; se pueden volver a bajar. |
| `catastro_noa.csv` | **Sí, todos los días** | Es texto ordenado: git guarda solo las líneas que cambian (unos KB por día). Es la fuente del historial. |
| `novedades.csv`, `historial.parquet` | Sí | Chicos; son lo que consume la app. |
| `catastro_noa.parquet` | A definir | Es binario: git guarda una copia entera (~1 MB) en cada cambio. Conviene regenerarlo en cada corrida, o versionarlo solo si la app lo necesita del repo. |
| `revision_estandarizacion.xlsx` | A definir | Solo sirve para revisiones puntuales con el equipo. |

Para que el CSV registre también los **cambios de polígono**, conviene incluir la
geometría como texto (WKT) en una columna (decisión de la tarea 2.15).

Límites de GitHub: 100 MB por archivo y se recomienda un repo de menos de 1 GB. Con este
esquema se está muy lejos de ambos durante años. GitHub Actions es gratis para repos
públicos; para privados alcanzan los 2.000 minutos mensuales gratuitos (cada corrida
toma unos pocos minutos).

**Importante:** cuando el repo pase a público, también queda público todo su
historial.
