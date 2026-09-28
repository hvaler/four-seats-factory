# Evidence-Driven Autonomous Factory

## Estado y objetivo

Diseño preparado para una ejecución en BAND; no hay todavía resultados medidos. La aplicación objetivo es Pocketful, pero los mandates no contienen conocimiento del track. Para reutilizar la factory se cambia el dispatch, la especificación y el entorno, manteniendo el procedimiento de los seats.

La regla de aceptación es: una afirmación solo puede convertirse en aceptación cuando otro seat reproduce evidencia suficiente sobre la misma revisión. Esta es una política interna más exigente que el umbral de puntuación del evento; no promete superar tests que no hemos visto.

## Seats y propiedad

| Seat visible | Propiedad | Puede escribir | No puede decidir |
|---|---|---|---|
| analyst | cobertura, coordinación, límites | obligaciones, decisiones, índice de evidencia | aceptación del producto |
| implementer | implementación y empaquetado | código de producción, Dockerfile, RUN.md y tests propios | aceptación de su trabajo |
| adversary | crítica de cobertura y comprobaciones independientes | tests independientes y reportes de fallo | arreglos de producción o release |
| auditor | reproducción e integridad | registros de auditoría y veredictos | modificar producto o tests para pasar |

Registrar antes del dispatch, sin inventar valores:

| Nombre visible real | @handle real | Seat ID | Harness real | Modelo exacto |
|---|---|---|---|---|
| analyst | PENDIENTE | PENDIENTE | Claude Code | Opus |
| implementer | PENDIENTE | PENDIENTE | Claude Code | Opus |
| adversary | PENDIENTE | PENDIENTE | Claude Code | Opus |
| auditor | PENDIENTE | PENDIENTE | Claude Code | Opus |

La identidad visible determina el nombre de su mandate. El handle real determina las menciones. No suponer que son iguales. Todo seat participante debe tener su mandate correspondiente.

## Montaje reproducible

1. Preparar Python 3.12+, Git, Docker en ejecución, BAND Desktop y acceso al proveedor de modelos. En Windows, los comandos del harness se preparan en WSL2. El lenguaje del servicio lo elige la banda según los requisitos.
2. Obtener el kickoff oficial de `band-ai/dark-factory-wearedevs`, registrar su commit y crear allí un entorno Python. Instalar `harness/requirements.txt` y Chromium de Playwright. Verificar `python -m harness --help`.
3. Mantener tres ubicaciones distintas: kickoff oficial, repo de resultados y salidas de checks. Dar rutas absolutas accesibles para todos los seats. Mantener las credenciales fuera del repo y de la room.
4. Configurar los cuatro seats con los mandates de este directorio, completando primero Harness y Model reales. Configurar sus identidades Git. Comprobar permisos para crear archivos, commits, contenedores y clones de revisión sin prompts durante el run.
5. Ensayar toda la cadena, incluidas menciones y exportación, en una room y repo de práctica. Para la ejecución evaluada usar una room nueva y repo nuevo, sin código reutilizado del ensayo.
6. Cargar el dispatch con rutas, handles, especificación, límites y destino. Tras enviarlo no introducir steering humano. Analyst coordina y concluye sin pedir decisiones humanas.

Los permisos en los mandates son una separación procedimental. Si la plataforma permite restringir rutas por seat, configurarlos también allí. No se afirma que los prompts impongan aislamiento técnico. Los clones de revisión impiden que una edición en curso se confunda con el candidato auditado.

## Flujo y evidencia

El alcance autorizado es Stage 1 → Stage 2 → Stage 3 → Stage 4 mediante un único dispatch inicial. Una aceptación de etapa es un checkpoint interno: analyst inicia la siguiente sin pedir confirmación. Solo termina tras verificar la cadena completa o registrar un límite/bloqueo. Por cada etapa se suministran las specs completas acumuladas; la carpeta anterior se conserva y su copia se amplía. Se registra una decisión por etapa y las migraciones 1→2, 1→3, 2→3, 1→4, 2→4 y 3→4. La auditoría final ejecuta todas las carpetas en modo isolated desde un clone nuevo. Los formatos STAGE-REGISTER y UPGRADE-REPORT están en evidence/templates.

```text
analyst: contrato y obligaciones
   -> adversary: crítica de cobertura
   -> implementer: candidato comprometido
   -> adversary: comprobación independiente
   -> auditor: reproducción y decisión
        REJECTED -> analyst -> implementer -> nueva revisión y nueva auditoría
        BLOCKED  -> analyst -> resultado final con evidencia disponible
        ACCEPTED -> analyst -> siguiente etapa autorizada
        etapa 4 aceptada -> auditoría global -> analyst -> informe final
```

Cada handoff contiene la tarea y la spec completas, alcance, restricciones, rutas absolutas, revisión de entrada, resultados esperados y límites. Se dirige al @handle literal y requiere respuesta al emisor. Los mensajes largos se numeran; el receptor confirma que recibió todos antes de actuar. El enlace a una spec o mensaje no sustituye su contenido.

Cada obligación enlaza sección de spec, claim de implementer, evidencia de adversary, reproducción de auditor y decisión. Los formatos están en `evidence/templates/`; `evidence/README.md` define estados y reglas de integridad. Ningún ejemplo o plantilla cuenta como evidencia.

## Git y concurrencia

Analyst concede un único permiso de escritura temporal en el checkout de resultados. El propietario publica commit completo y devuelve el permiso. Nunca se hacen checkouts, commits o staging simultáneos en ese checkout. El implementer es el único escritor de `stage-N/`; los otros seats trabajan en sus áreas documentales o en clones separados.

Al publicar candidato se congela su árbol de producto. Adversary y auditor clonan el repo en ubicaciones externas distintas, extraen el commit exacto y levantan procesos nuevos. Los scripts de verificación también quedan versionados. El informe registra por separado revisión del producto, revisión de los tests y revisión que incorpora la evidencia: no intenta introducir el hash de un commit dentro de ese mismo commit.

Un cambio en el producto exige nueva revisión. Un commit posterior que solo añade evidencia no modifica la aceptación del árbol del producto: auditor compara `stage-N/` entre ambos commits y registra ese resultado. No se modifica historial mediante amend, rebase o squash. Las salidas grandes quedan identificadas y se conservan; nunca se reemplaza un directorio de run fallido.

## Puertas internas

1. **Contrato:** obligaciones de todas las secciones, supuestos explícitos y crítica de cobertura.
2. **Candidato:** árbol limpio y completo, Dockerfile y RUN reproducibles, alcance correcto.
3. **Challenge:** checks públicos y pruebas propias derivadas de la spec, con resultados reales.
4. **Auditoría:** reproducción en entorno nuevo del mismo candidato; ningún fallo bloqueante o vacío de evidencia.
5. **Entrega:** evidencia indexada y correspondencia comprobada entre producto aceptado y commit publicado.

La política interna exige comprobar todas las obligaciones y resolver todos los fallos aplicables; no optimiza para el umbral mínimo del evento. El probe del stage siguiente se interpreta según la guía: su fallo esperado por funcionalidad posterior no implementada no bloquea el stage actual. Nunca se introduce una rotura deliberada para engañar ese probe.

## Correspondencia con la rúbrica

Factory (50%): montaje reutilizable, alcance realmente alcanzado, decisiones y costes medidos. App (25%): calidad de la aplicación y, a partir de Stage 2, experiencia de uso. Agent Teamwork (25%): trabajo distribuido, handoffs completos, revisión con efecto real cuando procede y autonomía demostrada por room e historial. Tener cuatro seats o muchos mensajes no prueba esos resultados.

## Decisiones y costes de diseño

- Cuatro roles permiten separar interpretación, escritura, challenge y aceptación. El coste es más comunicación y arranques de verificación.
- Un escritor de producción facilita atribución y evita conflictos. Puede convertirse en cuello de botella: los otros seats tienen trabajo sustantivo en obligaciones, tests y auditoría, no son simples aprobadores.
- El auditor repite comprobaciones en entornos nuevos. Aumenta tiempo y coste de infraestructura, pero detecta evidencia desactualizada o dependiente de estado compartido.
- Los handoffs completos consumen contexto. Se prefieren a referencias incompletas porque cada revisión necesita conocer íntegro el contrato.
- El ledger facilita navegar de un fallo a su reparación; requiere disciplina y no sustituye el log auténtico de BAND ni el historial Git.

## Fallos, recuperación y límites

Valores de partida: 5 ciclos de reparación por stage, 2 reintentos de infraestructura por comando, 180 minutos por stage y 720 minutos totales, incluyendo 30 minutos reservados para verificación global e informe. Se fijan antes del dispatch; el presupuesto monetario lo fija el participante para el run completo y no se reinicia entre etapas. Son techos de operación de esta factory, no estimaciones ni reglas oficiales. Un límite financiero solo se considera controlado si existe medición fiable o límite duro en el proveedor; en caso contrario declarar esa limitación y apoyarse en los límites verificables. Una reparación de una etapa anterior consume su presupuesto restante original; invalida y exige revisar la evidencia afectada de las etapas posteriores.

Un defecto de producto vuelve al implementer con reproducción y obligación incumplida. Un defecto de test vuelve a adversary y obliga a repetir el resultado. Un error de entorno no cuenta como test pasado; los reintentos usan nuevos directorios y quedan registrados. Agotar límites produce un resultado parcial o BLOCKED, sin solicitar al humano un rerun. No se fabrica un fallo para el vídeo; aceptar correctamente a la primera es válido.

## Resultados reales — completar después

| Medida | Valor inicial | Evidencia que debe respaldarla |
|---|---|---|
| Inicio y fin UTC por stage | NO MEDIDO | eventos de room |
| Tiempo de pared y tiempo de checks | NO MEDIDO | marcas temporales / logs |
| Modelo y tokens por seat | NO MEDIDO | datos del runtime/proveedor |
| Gasto por seat, moneda y total | NO MEDIDO | usage/billing; indicar estimación si aplica |
| Ciclos de reparación | NO EJECUTADO | ledger + mensajes |
| Stages internos aceptados | NINGUNO | veredictos auditor |
| Stages reclamados por harness público | NO EJECUTADO | report.json aislado |
| Resultado oficial | DESCONOCIDO | evaluación del organizador |

Documentar qué se probó durante el desarrollo de la factory, qué falló y qué cambio produjo, separándolo del run evaluado. Para un fallo real del run: requisito -> commit rechazado -> prueba -> mensaje -> reparación -> commit nuevo -> reproducción -> decisión. Si no hubo fallo reproducible, indicarlo sin inventarlo. Nunca convertir falta de datos de coste en cero euros.

La guía pide que el participante redacte README y FACTORY: este documento es una base que debe revisar, completar y hacer propia con su configuración y experiencia real antes de entregar. Fuente: https://github.com/band-ai/dark-factory-wearedevs/blob/main/docs/participant-guide.md
