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
4. **Lo que no se reconoció**, que queda en `mineral_sin_clasificar` para revisar.

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
    diques de colas, acopios), así que quedan sin clasificar.
11. **Superficies de Jujuy:** en algunos registros la superficie declarada difiere mucho
    de la calculada (hasta ×1000; ¿m² en lugar de ha?).

## Problemas conocidos de los datos

- **El expediente no es único.** En Salta hay 158 expedientes repetidos, sobre todo
  convenios con varios polígonos. Para seguir un derecho en el tiempo hace falta una
  clave estable (ver [`arquitectura.md`](arquitectura.md)).
- **`id_fuente` no es estable**: es un identificador interno de la base de cada provincia.
