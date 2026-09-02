# catastro-litio-noa

Proyecto interno UNSAM (Escuela de Politica y Gobierno / Area de Ambiente y Politica).
Objetivo general: pipeline reproducible y de costo cero para ingerir, homologar,
auditar y visualizar los catastros mineros de **Jujuy, Salta y Catamarca**.

## Estado: Fase 1 - verificacion de acceso a las fuentes

Confirmado que se puede obtener el catastro minero de las tres provincias de
forma programatica:

| Provincia | Como se obtiene | Formato | Registros | CRS |
|---|---|---|---|---|
| **Jujuy** | Descarga directa del SHP en `mineriajujuy.gob.ar` (link con token que se resuelve scrapeando la landing). Se actualiza a diario. | Shapefile (zip) | ~1.784 | EPSG:22183 |
| **Salta** | WFS del GeoServer `geoportal.salta.gob.ar` — capa `geonode:poligonos_adaf55f39328ff45c8c60e94eb13a7a0` ("Catastro Minero"). | GeoJSON / WFS | ~3.947 | EPSG:4326 |
| **Catamarca** | WFS del GeoServer `nodoide.catamarca.gob.ar` — capa `idecat:MINAS_19022026`. El host esta detras de Cloudflare, hay que usar un cliente que resuelva el challenge (`cloudscraper`). | GeoJSON / WFS | ~2.385 | EPSG:4326 |

Notas:
- No se pudo usar el CIMA nacional (`cima.minem.gob.ar`): no responde desde este
  entorno. Las fuentes provinciales alcanzan.
- El GeoServer de Salta esta en `geoportal.salta.gob.ar`, **no** en
  `geoportal.idesa.gob.ar` (ese solo sirve el visor).
- La capa de Catamarca no trae `estado` ni `superficie`; el resto de los campos si.
- En las muestras se descartan columnas de contacto (mails / domicilio).

## Correr

```bash
uv sync
uv run python scripts/explorar_fuentes.py --n 50
```

Deja una muestra por provincia en `data/samples/{jujuy,salta,catamarca}.csv` con
columnas: `provincia, expediente, nombre, titular, mineral, tipo, estado,
departamento, superficie_ha, fuente`.

## Estructura

```
scripts/explorar_fuentes.py   verificacion de acceso a las 3 fuentes (Fase 1)
data/samples/                 muestras chicas versionadas (para revisar a ojo)
data/raw/                     descargas crudas (ignoradas por git)
```
