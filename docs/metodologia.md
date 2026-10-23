# Metodología de homologación

Criterios con los que se lleva el catastro de cada provincia al esquema común. Las
columnas resultantes están en [`diccionario_de_datos.md`](diccionario_de_datos.md);
la arquitectura general, en [`arquitectura.md`](arquitectura.md).

Todas las reglas están en CSV editables dentro de [`diccionarios/`](../diccionarios/).
La columna `origen` de cada CSV indica de dónde sale la regla:

- `investigadores`: viene de las planillas de criterios del equipo de investigación
  (`docs/insumos/`).
- `propuesta`: variante que aparece en los datos y no estaba en las planillas (plurales,
  abreviaturas, errores de tipeo, minerales no listados). Está **pendiente de
  validación** por el equipo.

## Fuentes

| Provincia | Fuente | Qué publica |
|---|---|---|
| Jujuy | SHP del Juzgado Administrativo de Minas (`mineriajujuy.gob.ar`) | Todo: trámite, estado, mineral, superficie, polígono |
| Salta | WFS de `geoportal.salta.gob.ar`, capa "Catastro Minero" | Todo, además de la fecha de inicio |
| Catamarca | WFS de `nodoide.catamarca.gob.ar` (capa `idecat:MINAS_<fecha>`) o el visor estático de minería | Sin trámite, estado ni superficie. **En pausa:** el servidor no responde |

- Cada descarga se guarda cruda y fechada en `data/raw/<provincia>/`. Si una fuente
  falla, se usa el último crudo disponible y se avisa.
- El nombre de la capa de Catamarca cambia con cada actualización. El código busca la
  más reciente en el `GetCapabilities`.
- No se usa el CIMA nacional (`cima.minem.gob.ar`) porque no respondió durante el
  relevamiento.
- Los campos de contacto personal (ej. `dom_corre` de Jujuy, con mails) se descartan
  siempre.

## Minerales

Cada provincia escribe el mineral de una forma distinta:

| Provincia | Ejemplo del campo mineral |
|---|---|
| Jujuy | `DISEMINADO DE COBRE, ORO, PLATA Y SALES ALCALINAS`, `1 Y 2` |
| Salta | `BORATOS,K,Li` (símbolos químicos y nombres) |
| Catamarca | `Litio, Potasio y Cloruros` |

De cada texto se obtiene:

1. **Minerales** con nombre canónico (`Cobre; Oro; Plata; Sales alcalinas`).
2. **Grupos**, que son los definidos por el equipo de investigación:
   *Metalíferos*, *Litio y potasio*, *Depósitos evaporíticos*, *Tierras raras* y
   *Canteras, rocas de aplicación y otros minerales*. Un registro puede tener varios.
3. **Categoría del Código de Minería** (1ra, 2da o ambas) cuando el texto la menciona.
   Va en una columna aparte porque no es un tipo de mineral. En Jujuy muchos cateos solo
   dicen `1 Y 2`.
4. **Lo que no se reconoció**, que queda en `mineral_sin_clasificar` para revisar. Es
   lo que sobra del texto después de reconocer minerales, categorías e instalaciones.

Reglas de reconocimiento (`catastro_noa/minerales.py`):

- Los nombres se buscan como palabras completas, sin distinguir mayúsculas ni acentos, y
  primero los más largos. Así `SULFATO DE SODIO` gana sobre `SODIO` y `CLORURO DE SODIO`
  gana sobre `CLORURO`. Cada palabra acepta plural (`BORATOS` → *Borato*).
- Los símbolos (`Li`, `Cu`) respetan mayúsculas. Los de una sola letra (`K`, `U`, `Y`)
  solo cuentan si son un ítem suelto de una lista separada por comas. Así la `Y` de
  `ORO Y PLATA` no se confunde con el itrio.
- *Diseminado* es un tipo de depósito: solo se cuenta como mineral (grupo Metalíferos)
  cuando el texto no menciona ningún otro mineral.
- Algunos términos son modificadores (aluvión, aluvional, veta): se reconocen pero no
  suman mineral.
- Algunos términos son de tipo `no_mineral`: describen instalaciones u obras de las
  servidumbres de Jujuy (campamento, acopio, cancha, colas, relaves, desmonte, dique,
  escorial, escombrera, planta de beneficio, playa de secado, gasoducto, instalación,
  construcción). No suman mineral y, si el texto trae alguno, lo que sobra (nombres de
  minas, números de expediente) no se marca como sin clasificar. Si el texto trae además
  minerales reales, se conservan: `DESMONTES Y RELAVES DE PLOMO, ZINC Y PLATA` da
  *Plomo; Zinc; Plata*. Antes de esta regla, esas instalaciones quedaban como "sin
  clasificar" aunque claramente no eran minerales.
- Un error de tipeo frecuente (`SALES ALCALINAS TERREAS`) se trata como *Alcalinotérreos*;
  sin esa regla sumaba un *Sal* de más.

Un test (`tests/test_diccionarios.py`) verifica que todo término de la planilla del
equipo esté en el diccionario y en el mismo grupo. Si la planilla se actualiza, el test
avisa qué falta.

## Trámite y etapa

Se generan dos columnas:

- **`etapa_administrativa`**: el trámite propio de cada provincia, con nombre prolijo.
  Conserva todo el detalle y permite detectar avances finos, como el pase de cateo a
  manifestación, que funcionan como alerta temprana.
- **`etapa_proyecto`**: una categoría común para comparar entre provincias (ej. qué
  zonas pasaron de exploración a explotación entre dos fechas).

| Provincia | Trámite publicado | Etapa del proyecto |
|---|---|---|
| Jujuy | Cateo, Solicitud de mina | Exploración |
| Jujuy | Mina concedida, Mina vacante solicitada, Grupo minero* | Explotación |
| Jujuy | Cantera, Servidumbre, Área de reserva, Solic. grupo minero | Canteras y otros |
| Salta | Cateo, Manifestación, Zona de investigación geológica minera* | Exploración |
| Salta | Mina, Grupo minero* | Explotación |
| Salta | Cantera, Servidumbre, Convenio | Canteras y otros |

\* propuesta, pendiente de validación. Catamarca no publica el trámite. Las categorías
de `etapa_proyecto` son **provisorias** hasta que el equipo cierre la planilla de
trámites. Reglas en [`diccionarios/etapas.csv`](../diccionarios/etapas.csv).

## Estado legal

Estado homologado (propuesta): `Vigente`, `En trámite`, `Vacante`, `Anulado`,
`Con recurso`, `Otro`. Reglas en [`diccionarios/estados.csv`](../diccionarios/estados.csv).

Ojo al comparar provincias: en Salta, "Vigente" incluye manifestaciones y cateos en
curso, y no solo concesiones otorgadas. En Jujuy, "CONCEDIDA", "REGISTRADA" e
"INCLUIDA EN G. M. …" se tomaron como Vigente.

## Titulares

- `titular` conserva el texto publicado. Se vacía si la fuente pone algo que no es un
  titular (ej. "Vacancia Solicitada").
- `titular_clave` sirve para agrupar y cruzar provincias: mayúsculas, sin acentos ni
  puntuación, y formas jurídicas como sigla. Por ejemplo, `LITHIUM S. CORPORATION S. A.`
  (Jujuy) y `LITHIUM S CORPORATION S.A.` (Salta) quedan los dos como
  `LITHIUM S CORPORATION SA`.
- Todavía no se separan los registros con varios titulares ni se agrupan empresas en
  grupos económicos.

## Geometría y superficie

- Todo se lleva a EPSG:4326 (Jujuy publica en EPSG:22183).
- Las geometrías inválidas se reparan (`make_valid`) y se conservan solo las partes
  poligonales.
- `superficie_ha_calculada` es el área geodésica del polígono sobre el elipsoide WGS84.
  Está disponible para todas las provincias, incluso las que no declaran superficie.

## Planilla de revisión

`data/processed/revision_estandarizacion.xlsx` es la planilla que se comparte con el
equipo (para enviar se le pone la fecha en el nombre, ej. `base_catastro_NOA_2026-10-20.xlsx`).
Tiene estas hojas:

| Hoja | Contenido |
|---|---|
| `LEER` | Qué es cada hoja. |
| `BASE` | Un registro por derecho minero, sin geometrías. En esta hoja, en `MINERALES` y en `ETAPAS` el encabezado va en azul si la columna es el dato tal como lo publica la provincia, en verde si se construyó al homologar y en gris si es información de control o un conteo (provincia, fecha de descarga, registros, revisar). |
| `MINERALES` | Cada texto de mineral distinto, cómo se clasificó y cuántos registros lo usan. La columna `revisar` es verdadera cuando algo del texto quedó sin clasificar; son los únicos casos que piden una decisión. Un texto sin minerales y con `revisar` falso es una instalación (`no_mineral`) o una categoría suelta (`1 Y 2`). |
| `ETAPAS` | Cada combinación provincia / trámite / estado y la etapa y el estado homologado que se le asignó. |
| `RESUMEN` | Conteos por etapa, estado, categoría y grupo de minerales, una tabla por provincia. |

Los anchos de columna y el nombre de las hojas se fijan en `catastro_noa/salidas.py`, así
que se mantienen cada vez que se regenera.

## Revisión de los resultados (20/10/2026)

Se revisaron todos los textos de mineral, la tabla de etapas y estados, y la coherencia
de la base (identificadores, nulos, superficies). Resultado y decisiones:

- **Textos sin clasificar: de 22 a 5.** Las instalaciones pasaron a `no_mineral` (ver
  arriba). Quedan: tres textos de Salta con cesio y rubidio, y dos de Jujuy que parecen
  datos mal cargados (`CRETACICO (OBSERVADO)` y `P/CHINCHILLA Y CHINCHILLA I`).
- **Cesio, rubidio y estroncio siguen sin grupo.** Se evaluó asignarles uno (los metales
  alcalinos se asocian a las pegmatitas de litio), pero la planilla del equipo no los
  lista y se dejó la decisión al equipo (ver pendiente 5).
- **Estado "Otro" en Jujuy:** 30 minas concedidas tienen como estado publicado solo
  un número de resolución (`Res 41-J-2026 (03/06/2026)`), sin el estado en sí. Quedan
  como `Otro`.
- **Superficies de Jujuy:** en 1.188 de 1.478 registros con superficie declarada, esta
  coincide con la calculada (±5 %). Los demás difieren por la propia fuente; la base
  conserva las dos columnas.

## Criterios pendientes de validación

1. **Berilio** figura en dos solapas de la planilla (Metalíferos y Canteras). Se dejó
   en Metalíferos.
2. **Antimonio** figura en la planilla con el símbolo Sn, que es el del estaño. Se usó Sb.
3. Regla de **Diseminado** (ver arriba).
4. **Cloruro de sodio, sal de cosecha y sal gema** se asignaron a *Sal* (Depósitos
   evaporíticos) y no a *Cloruros* (Litio y potasio).
5. **Cesio (Cs), rubidio (Rb) y estroncio** quedaron sin grupo a propósito.
6. Todas las filas con `origen=propuesta` de `diccionarios/minerales.csv`.
7. **Etapas:** el destino de Grupo minero y de Zona de investigación geológica minera, y
   la lista definitiva de categorías comunes.
8. **Categorías de estado** homologado.
9. **Catamarca:** buscar otra fuente oficial con trámite, estado y superficie.
10. **Servidumbres de Jujuy:** el campo mineral describe instalaciones (campamentos,
    diques de colas, acopios). Se tratan como `no_mineral` (propuesta): no suman mineral
    ni quedan para revisar. Confirmar que es lo que el equipo quiere.
11. **Superficies de Jujuy:** en 191 registros la superficie declarada difiere más de
    20 % de la calculada (hasta ×1000; ¿m² en lugar de ha?).
12. **Textos de mineral que parecen mal cargados:** `CRETACICO (OBSERVADO)` y
    `P/CHINCHILLA Y CHINCHILLA I` (Jujuy) no describen un mineral.

## Problemas conocidos de los datos

- **El expediente no es único.** En Salta hay 158 expedientes repetidos, sobre todo
  convenios con varios polígonos. Para seguir un derecho en el tiempo hace falta una
  clave estable (ver [`arquitectura.md`](arquitectura.md)).
- **`id_fuente` no es estable**: es un identificador interno de la base de cada provincia.
