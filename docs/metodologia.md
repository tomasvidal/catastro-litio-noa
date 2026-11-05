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
| Catamarca | WFS de `nodoide.catamarca.gob.ar` (capa `idecat:MINAS_<fecha>`) o el visor estático de minería | **En pausa:** el WFS dejó de publicar la capa del catastro y el visor no trae trámite, estado ni superficie |

- Cada descarga se guarda cruda y fechada en `data/raw/<provincia>/`. Si una fuente
  falla, se usa el último crudo disponible y se avisa.
- El nombre de la capa de Salta es un código interno que puede cambiar: se busca por su título
  en el `GetCapabilities` y, si no aparece, se usa el último nombre conocido.
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
- **Subproductos.** El cesio (Cs) y el rubidio (Rb) aparecen tanto con metalíferos como
  con salmueras: se aprovechan junto con el mineral de interés pero no lo definen. Van al
  grupo *Subproductos*, que figura en `minerales` pero no suma a `grupos_minerales`. Así
  `BORATOS,Cs,K,Li,Na,Rb` da *Litio y potasio; Depósitos evaporíticos*, sin que el cesio
  sume *Metalíferos*. El grupo no aparece en los filtros de la app.
- **Servidumbres.** En las servidumbres el campo mineral describe la instalación o las
  minas a las que sirve (`P/CHINCHILLA Y CHINCHILLA I` = "para las minas Chinchilla y
  Chinchilla I"). Lo que no se reconoce no se marca como sin clasificar; los minerales que
  sí se reconozcan (ej. `ACOPIO DE SAL`) se conservan.

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
curso, y no solo concesiones otorgadas. En Jujuy, "CONCEDIDA", "REGISTRADA",
"INCLUIDA EN G. M. …" y las resoluciones de minas concedidas se tomaron como Vigente.

## Titulares

- `titular` conserva el texto publicado. Se vacía si la fuente pone algo que no es un
  titular (ej. "Vacancia Solicitada").
- `titular_clave` sirve para agrupar y cruzar provincias: mayúsculas, sin acentos ni
  puntuación, y formas jurídicas como sigla. Por ejemplo, `LITHIUM S. CORPORATION S. A.`
  (Jujuy) y `LITHIUM S CORPORATION S.A.` (Salta) quedan los dos como
  `LITHIUM S CORPORATION SA`.
- Los registros con varios titulares se separan en `titulares_claves` (claves separadas por
  `|`) y `n_titulares`. Salta los separa con coma; Jujuy mezcla comas, " Y ", " E " y " - ".
  Las empresas con una "Y" en el nombre (ej. `ARGENTINA LITIO Y ENERGIA S. A.`) no se parten.
  `titular_clave` sigue siendo el texto completo, para que esto no genere cambios de titular.
- Todavía no se agrupan empresas en grupos económicos.

## Geometría y superficie

- Todo se lleva a EPSG:4326 (Jujuy publica en EPSG:22183).
- Las geometrías inválidas se reparan (`make_valid`) y se conservan solo las partes
  poligonales.
- `superficie_ha_calculada` es el área geodésica del polígono sobre el elipsoide WGS84.
  Está disponible para todas las provincias, incluso las que no declaran superficie.
- **Cuál usar:** la calculada es la referencia, porque sale de lo que realmente está dibujado
  y existe en todos los registros. La declarada (`superficie_ha_fuente`) se conserva como
  dato informativo.
- **Cuánto difieren (5/11/2026, tolerancia del 10 %):** en Salta coinciden 3.907 de 3.924
  registros, lo que valida el cálculo. En Jujuy coinciden 1.236 de los 1.478 que declaran
  superficie (84 %); otros 303 no declaran (243 son minas concedidas). De los 242 que difieren,
  en 214 la declarada es mayor que el polígono (muchos con cifras redondas: 500, 10.000 ha) y
  en 28 es menor. Lo más probable es que el polígono vigente haya sido recortado respecto de
  lo solicitado (por superposición con derechos anteriores); queda para confirmar con el
  equipo. Un registro es un error evidente de unidades (`2967-J-2022`: declara 1,95 ha y el
  polígono tiene 1.947,6).

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

## Año del expediente

La columna `anio_expediente` permite contar expedientes por año y provincia:

- **Salta:** el año de `fecha_inicio` (95 % de los registros). Si falta, el que figure
  al final del número (`143-1412/2018`).
- **Jujuy:** no publica fecha de inicio, pero el número lleva el año (`3428-T-2024`).

La base solo tiene los derechos que la provincia publica hoy: los caducados o archivados
no están, así que contar filas subestima los años más viejos.

## Decisiones tras revisar los resultados

Se revisaron con el equipo los textos de mineral, la tabla de etapas y estados, y la
coherencia de la base. Decisiones que cambiaron las reglas:

- **Textos sin clasificar: de 22 a 1.** Las instalaciones pasaron a `no_mineral`, las
  servidumbres tienen su propia regla, cesio y rubidio pasaron a *Subproductos* y
  `CRETACICO (OBSERVADO)` pasó a *Canteras, rocas de aplicación y otros minerales* (mineral
  *Cretácico*; `OBSERVADO` es una marca del catastro y se ignora). Queda `SEMINADO`,
  probable error de tipeo de *diseminado*.
- **Resoluciones como estado en Jujuy:** 31 minas concedidas tienen como estado publicado
  solo un número de resolución (`Res 41-J-2026 (03/06/2026)`). Como la resolución es la que
  concede la mina, se homologan como `Vigente`. Si aparece una resolución con otro trámite,
  queda como `Otro` para revisarla. La regla mira también el trámite (columna `tramite` de
  `diccionarios/estados.csv`).

## Criterios pendientes de validación

1. **Berilio** figura en dos solapas de la planilla (Metalíferos y Canteras). Se dejó
   en Metalíferos.
2. **Antimonio** figura en la planilla con el símbolo Sn, que es el del estaño. Se usó Sb.
3. Regla de **Diseminado** (ver arriba).
4. **Cloruro de sodio, sal de cosecha y sal gema** se asignaron a *Sal* (Depósitos
   evaporíticos) y no a *Cloruros* (Litio y potasio).
5. **Subproductos:** qué otros minerales entran en el grupo además de cesio y rubidio
   (ej. galio, torio, estroncio), y si conviene que sigan figurando en `minerales`.
6. Todas las filas con `origen=propuesta` de `diccionarios/minerales.csv`.
7. **Etapas:** el destino de Grupo minero y de Zona de investigación geológica minera, y
   la lista definitiva de categorías comunes.
8. **Categorías de estado** homologado.
9. **Catamarca:** conseguir una fuente oficial estable con trámite, estado y superficie.
10. **Servidumbres de Jujuy:** el campo mineral describe instalaciones (campamentos,
    diques de colas, acopios). Se tratan como `no_mineral` (propuesta): no suman mineral
    ni quedan para revisar. Confirmar que es lo que el equipo quiere.
11. **Superficies de Jujuy:** en 242 registros la superficie declarada difiere más de 10 %
    de la calculada (en 214 es mayor). Se usa la calculada como referencia; confirmar si la
    diferencia se debe a recortes del polígono (ver "Geometría y superficie").
12. **`SEMINADO`** (Jujuy): se interpreta como un error de tipeo de *diseminado*, pero
    todavía no se clasifica.

## Problemas conocidos de los datos

- **El expediente no es único.** En Salta, 91 expedientes se repiten en 248 registros, sobre
  todo convenios con varios polígonos. Para seguir un derecho en el tiempo hace falta una
  clave estable (ver [`arquitectura.md`](arquitectura.md)).
- **`id_fuente` no es estable**: es un identificador interno de la base de cada provincia.
