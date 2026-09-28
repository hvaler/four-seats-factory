# Evidence-Driven Autonomous Factory

**Track:** Pocketful · **Equipo:** four-seats · **Estado inicial:** kit preparado, ejecución pendiente.

Nuestra factory usa cuatro seats de BAND: analyst convierte la especificación en obligaciones, implementer construye, adversary intenta refutar las afirmaciones y auditor reproduce la evidencia antes de aceptar. Una afirmación no hace avanzar un artefacto: lo hace una comprobación independiente sobre una revisión identificada.

Objetivo autorizado: los cuatro stages de Pocketful, en secuencia con un único dispatch humano. Los cuatro seats usan Claude Code con Opus; el ID exacto se registra al configurar BAND. El objetivo de Stage 4 no implica que ya se haya completado.

## Leer este repositorio

- `FACTORY.md`: arquitectura, configuración, decisiones, límites y resultados medidos.
- `mandates/`: instrucciones genéricas realmente cargadas en cada seat.
- `evidence/templates/`: formatos vacíos; no representan resultados.
- `evidence/runs/`: evidencia producida durante el run, cuando exista.
- `room.json`: sesión completa exportada desde BAND al terminar, cuando exista.
- `stage-N/`: servicio autónomo y completo del stage N, creado por la banda, cuando exista.

## Estado de la entrega — completar tras el run

| Dato | Valor |
|---|---|
| Room evaluada | PENDIENTE |
| Commit final publicado | PENDIENTE |
| Mayor cadena de stages reclamada por checks públicos | NO EJECUTADO |
| Decisión interna del auditor | NO EJECUTADO |
| Resultado oficial de jueces | DESCONOCIDO |
| Ejecución isolated y reporte | PENDIENTE |
| Presentación / vídeo | PENDIENTE |

Para iniciar cada servicio, sigue su `stage-N/RUN.md`. Este archivo se completará con datos observados; no afirma que existan stages antes de que la banda los produzca. Antes de publicar, el participante revisa y hace propios README y FACTORY, reemplaza los campos pendientes y conserva únicamente las carpetas de stages completados.

Fuente normativa: [participant guide](https://github.com/band-ai/dark-factory-wearedevs/blob/main/docs/participant-guide.md). El resultado local de los checks distribuidos no sustituye la evaluación oficial.
