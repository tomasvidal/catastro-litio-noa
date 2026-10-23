# Tareas del proyecto

Checklist de las cuatro fases del [plan de trabajo](docs/plan_de_trabajo.md).

**Cómo usarlo:** la sección "Dónde estamos" indica la próxima tarea. Al terminar una
tarea, se marca con `[x]`, se agrega en una línea qué se hizo o dónde quedó (archivo o
script) y se actualiza "Dónde estamos". Si una tarea quedó a medias o bloqueada, se marca
con `[~]` y se explica qué falta.

Leyenda: `[x]` hecha · `[~]` parcial o bloqueada · `[ ]` pendiente · `⏸` en pausa ·
👥 depende del equipo de investigación

Documentación relacionada: [README](README.md) (alcance, estructura y cómo correrlo) ·
[metodología](docs/metodologia.md) · [arquitectura](docs/arquitectura.md) ·
[diccionario de datos](docs/diccionario_de_datos.md)

## Dónde estamos

- **Fase actual:** 2. Ingesta, homologación y pipeline CI/CD.
- **Provincias activas:** Jujuy y Salta. Catamarca está en pausa (su servidor no
  responde).
- **Última actualización:** 20/10/2026.
- **Próxima tarea:** 2.12. Enviar la base al equipo para que la revise. Mientras se
  espera la devolución, se puede avanzar con 2.15 y 2.16.

---

## Fase 1: Diagnóstico, relevamiento y planificación ✅

- [x] 1.1 Reunión inicial con dirección, equipo y tutoría.
- [x] 1.2 Plan de trabajo entregado (`docs/plan_de_trabajo.md`).
- [x] 1.3 Verificación de acceso programático a las 3 provincias.
      `scripts/explorar_fuentes.py`, muestras en `data/samples/*.csv`.
- [x] 1.4 Planilla de relevamiento para el equipo (100 filas por provincia, listas de
      minerales y titulares). `scripts/armar_relevamiento.py` →
      `data/samples/catastro_relevamiento.xlsx`.
- [x] 1.5 👥 Criterios de normalización de minerales definidos por el equipo.
      `docs/insumos/Denominaciones_provinciales_minerales.xlsx`.

## Fase 2: Ingesta, homologación y pipeline CI/CD ⏳

Hecho:

- [x] 2.1 Ingesta completa, con geometría, de Jujuy (SHP) y Salta (WFS). Crudos
      fechados en `data/raw/<provincia>/`; si la fuente falla, se usa el último crudo.
      `catastro_noa/fuentes.py`.
- [~] 2.2 ⏸ Ingesta de Catamarca. El código está listo (busca la capa WFS `MINAS_*` más
      reciente o usa el visor estático) y probado con datos sintéticos. Falta correrlo
      con datos reales: el servidor responde error 521. Ver 2.11.
- [x] 2.3 Esquema canónico común. `catastro_noa/estandarizar.py`,
      `docs/diccionario_de_datos.md`.
- [x] 2.4 Minerales: nombres canónicos, grupos del equipo y categoría del Código de
      Minería. `catastro_noa/minerales.py`, `diccionarios/minerales.csv`.
- [x] 2.5 Etapa administrativa (por provincia) y etapa del proyecto (común, provisoria).
      `catastro_noa/tramites.py`, `diccionarios/etapas.csv`.
- [x] 2.6 Estado legal homologado (propuesta). `diccionarios/estados.csv`.
- [x] 2.7 Clave de titular para cruzar provincias. `catastro_noa/titulares.py`.
- [x] 2.8 Geometrías en EPSG:4326, reparación de inválidas y superficie calculada.
- [x] 2.9 Salidas: `data/processed/catastro_noa.parquet`, `.csv` y
      `revision_estandarizacion.xlsx`. `catastro_noa/salidas.py`.
- [x] 2.10 Tests (`uv run pytest`, 75 casos).
- [x] 2.19 Metodología documentada en `docs/metodologia.md` y arquitectura en
      `docs/arquitectura.md`.
- [x] 2.20 Revisión de la clasificación de minerales (20/10/2026): nuevo tipo
      `no_mineral` para las instalaciones de las servidumbres, regla para
      `SALES ALCALINAS TERREAS` y columna `revisar` limitada a lo sin clasificar. Textos
      sin clasificar: de 22 a 5. Detalle en `docs/metodologia.md`, sección "Revisión de
      los resultados".
- [x] 2.21 Planilla de revisión: hoja `RESUMEN` con una tabla por provincia y hoja
      `LEER` con la descripción de cada hoja. `catastro_noa/salidas.py`.

Pendiente:

- [ ] 2.11 ⏸ Catamarca: cuando vuelva el servidor (o con un archivo dejado a mano en
      `data/raw/catamarca/`), correr `uv run python -m catastro_noa --provincias jujuy
      salta catamarca`, revisar sus minerales sin clasificar y sus departamentos, y
      volver a sumarla a `PROVINCIAS_ACTIVAS` (`catastro_noa/__init__.py`).
- [ ] 2.12 👥 Enviar al equipo la planilla de revisión (`revision_estandarizacion.xlsx`,
      con la fecha en el nombre; ver `docs/metodologia.md`, sección "Planilla de
      revisión") y los criterios pendientes de validación (última sección). Pedir una
      decisión sobre los textos con `revisar` verdadero (cesio y rubidio, dos textos
      mal cargados). Versión lista del 20/10/2026.
- [ ] 2.13 👥 Incorporar la devolución del equipo a `diccionarios/`: resolver los
      criterios pendientes y pasar las filas validadas de `origen=propuesta` a
      `origen=investigadores`.
- [ ] 2.14 👥 Cerrar con el equipo la lista definitiva de etapas (la planilla
      `Denominaciones_provinciales_tramites.xlsx` está en pausa) y ajustar
      `diccionarios/etapas.csv`.
- [ ] 2.15 Definir qué se versiona de `data/processed/` (ver `docs/arquitectura.md`,
      sección "Qué se versiona"): CSV diario con la geometría como WKT, ¿parquet?,
      ¿Excel? Ajustar `.gitignore` y `salidas.py`.
- [ ] 2.16 GitHub Actions: workflow con cron diario que corra `uv sync`, `uv run pytest`
      y `uv run python -m catastro_noa`, y commitee si hubo cambios.
- [ ] 2.17 ⏸ Catamarca: averiguar si el visor tiene otras capas (`MINAS_1..4`) separadas
      por tipo de trámite, para completar `etapa_administrativa`.
- [ ] 2.18 Revisar las superficies declaradas de Jujuy que no coinciden con las
      calculadas (diferencias de hasta ×1000).

## Fase 3: Auditoría temporal y detección de cambios

Diseño en `docs/arquitectura.md`.

- [ ] 3.1 Clave estable por derecho minero entre snapshots: provincia + expediente +
      nombre normalizados, con desempate por geometría.
- [ ] 3.2 Comparación entre dos snapshots: altas, bajas y cambios de titular, etapa,
      estado, mineral, superficie y geometría.
- [ ] 3.3 Tabla de eventos `data/historial/novedades.csv` (solo se agregan filas).
- [ ] 3.4 Tabla histórica con vigencias (SCD 2) `data/historial/historial.parquet`.
- [ ] 3.5 👥 Cargar los catastros de años anteriores del equipo como snapshots
      fechados, para reconstruir la historia hacia atrás.
- [ ] 3.6 Integrar la auditoría al workflow diario (2.16).
- [ ] 3.7 Separar los registros con varios titulares (cada provincia usa otro
      separador).
- [ ] 3.8 👥 Agrupar titulares en grupos económicos (requiere criterio del equipo).
- [ ] 3.9 Tests de la detección de cambios.

## Fase 4: Plataforma web, documentación y cierre

- [ ] 4.1 App Streamlit: mapa, filtros (provincia, grupo de mineral, litio, etapa,
      estado, titular, departamento) y tabla descargable.
- [ ] 4.2 Vista de novedades por zona y por período (ver `docs/arquitectura.md`).
- [ ] 4.3 👥 Capas de contexto: localidades de Jujuy y cuencas de las 3 provincias.
      Cruces espaciales: qué localidades o parajes caen en cada derecho y en qué cuenca
      está cada uno.
- [ ] 4.4 Antes de publicar: revisar que el historial de git no tenga credenciales ni
      datos personales, y pasar el repo a público.
- [ ] 4.5 Deploy en Streamlit Community Cloud (gratuito).
- [ ] 4.6 👥 Pruebas de la app con el equipo de investigación.
- [ ] 4.7 Documentación final: guía de reproducibilidad y guía de uso de la app.
- [ ] 4.8 Informe final y avales de cierre.
