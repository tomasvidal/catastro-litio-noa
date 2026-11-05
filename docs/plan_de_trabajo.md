# Plan de Trabajo (Anexo II)

> Plan de trabajo presentado a la Licenciatura en Ciencia de Datos (UNSAM). El estado
> de cada fase está en el [`README`](../README.md).

## Datos generales

| | |
|---|---|
| **Responsable** | Estudiante de la Licenciatura en Ciencia de Datos (UNSAM) |
| **Tipo de actividad** | Proyecto interno de la UNSAM |
| **Dirección del proyecto** | Investigador del Área de Ambiente y Política |
| **Tutoría académica** | Tutor académico de la optativa |
| **Institución / equipo** | Escuela de Política y Gobierno, Área de Ambiente y Política (AAP-UNSAM) |
| **Marco** | CIAI (Inteligencia Artificial Interdisciplinaria) y optativas de la Licenciatura en Ciencia de Datos |
| **Carga horaria** | 128 hs, 8 créditos |
| **Inicio** | 1 de agosto de 2026 |

**Título:** *Litio, agua y comunidades: construcción de una plataforma de datos
socioambientales para el monitoreo de la minería en Argentina.*

## Pregunta de investigación / problema

La información pública sobre catastros mineros y derechos de explotación en Argentina
está descentralizada y fragmentada, con esquemas, formatos y frecuencias de
actualización distintos entre las provincias del Noroeste Argentino (Jujuy, Salta y
Catamarca).

Esta dispersión dificulta el monitoreo sistemático de la expansión minera del litio,
el análisis de la concentración territorial de grupos económicos y el seguimiento de
las transferencias de titularidad o de los cambios de estado legal de las concesiones
a lo largo del tiempo.

## Objetivo general

Diseñar e implementar un pipeline automatizado, reproducible y de costo cero para la
ingesta, estandarización, detección de cambios históricos y visualización analítica de
los catastros mineros de Jujuy, Salta y Catamarca.

## Objetivos específicos

1. Automatizar la extracción de capas vectoriales oficiales desde los servicios
   interoperables (WFS y APIs geoespaciales REST) de los geoportales provinciales.
2. Diseñar un modelo de datos unificado que homologue semántica y espacialmente las
   variables de titularidad, mineral, expediente, estado legal y geometrías.
3. Desarrollar una lógica de seguimiento temporal (auditoría incremental de cambios)
   para identificar transferencias de derechos, modificaciones de estado y variaciones
   de superficie.
4. Desplegar una aplicación web interactiva que permita la consulta territorial
   dinámica y la visualización de novedades para la investigación interdisciplinaria.

## Metodología

Arquitectura ETL geoespacial basada en el patrón *git-scraping*:

- **Ingesta programática:** consumo de servicios vectoriales WFS y endpoints
  geoespaciales en Python, sin depender de scraping web.
- **Normalización y almacenamiento:** procesamiento y tipado de datos vectoriales con
  formatos columnares optimizados.
- **Orquestación y versionado:** flujos de integración continua (CI/CD) con GitHub
  Actions para la ejecución periódica y el versionado de snapshots, sin servidores
  dedicados.
- **Auditoría temporal:** modelado de dimensiones de cambio lento (SCD) para preservar
  y consultar eventos históricos.
- **Capa de consumo:** interfaz de exploración analítica y espacial en Streamlit,
  desplegada en la nube.

## Resultados y productos esperados

- **Repositorio de código estructurado:** módulos en Python para extracción, limpieza,
  normalización y detección de cambios.
- **Base de datos consolidada y versionada:** archivo unificado de los catastros de las
  tres provincias y tabla histórica de modificaciones.
- **Plataforma web de monitoreo:** aplicación interactiva desplegada para consulta y
  filtrado espacial.
- **Documento metodológico:** diccionario de variables y guía de reproducibilidad del
  flujo de datos y del uso de la aplicación.

## Cronograma

| Fase | Semanas | Actividades | Hito / entregables |
|---|---|---|---|
| **1. Diagnóstico, relevamiento y planificación** | 1 a 4 | Articulación con el equipo de investigación, delimitación de preguntas analíticas, relevamiento de la infraestructura de datos espaciales (endpoints WFS/REST) de Catamarca, Salta y Jujuy, diseño de la arquitectura general. | Plan de trabajo acordado, viabilidad de fuentes confirmada e inventario técnico inicial. |
| **2. Ingesta, homologación y pipeline CI/CD** | 5 a 8 | Scripts de ingesta automatizada, estandarización semántica/espacial bajo un esquema canónico (titular, mineral, expediente, estado y geometrías), generación de la base unificada y automatización con GitHub Actions. | Base de datos integrada de las tres provincias y pipeline de extracción continua funcionando. |
| **3. Auditoría temporal y detección de cambios** | 9 a 12 | Comparación incremental entre snapshots para detectar novedades automáticamente (transferencias de titularidad, variaciones de superficie y cambios de estado legal). | Tabla histórica de cambios y auditoría temporal consolidada. |
| **4. Plataforma web, documentación y cierre** | 13 a 16 | Aplicación web interactiva en Streamlit, despliegue en la nube, pruebas con el equipo de investigación y documentación. | Repositorio estructurado, plataforma web pública en producción y documentación final. |

## Riesgos y resguardo de datos

El proyecto usa exclusivamente información pública provista por organismos estatales
y geoportales oficiales. No involucra datos personales sensibles ni información bajo
secreto comercial o confidencialidad.

Los procedimientos de extracción y transformación priorizan la trazabilidad, la
reproducibilidad y el acceso abierto a la información ambiental.
