# Cuatro asientos que no se creen la palabra del otro

*[Read in English](FACTORY.en.md)*

Una fábrica de software levantada sobre BAND Desktop. Cuatro asientos de agente en una sala: uno
decide cuál es el trabajo, otro lo construye, otro intenta romperlo, y otro reproduce todo antes de
que se acepte nada. Ningún asiento acepta su propio trabajo, y una afirmación nunca mueve un
artefacto — lo mueve una reproducción.

En toda la sala existe un solo mensaje humano. Autorizó cuatro stages y no volvió a hablar.

## Lo que produjo

| | |
|---|---|
| Stages entregados | **4 de 4**, cada uno congelado y auditado de forma independiente |
| Harness público, `--all --mode isolated`, clon nuevo | **cada carpeta reclama su stage, el 100% de sus checks, sin desbordar** |
| Rechazos del auditor | **2**, los dos reparados y reauditados dentro de la tirada |
| Mensajes humanos en la sala | **1** |
| Tiempo de pared, del despacho al informe final | **4 h 14 min** |
| Gasto en modelo, precios de catálogo | **~136 $** |

```
stage-1 -> reclama 1   share 1.0   overshoot null
stage-2 -> reclama 2   share 1.0   overshoot null
stage-3 -> reclama 3   share 1.0   overshoot null
stage-4 -> reclama 4   share 1.0   overshoot null
```

`share 1.0` es la totalidad de los checks de ese stage. `overshoot null` es la regla de congelación
aguantando: ninguna carpeta pasa la suite del stage siguiente, así que cada una es la solución de su
propio stage y no de uno posterior.

## Los asientos

| Asiento | Posee | Escribe | No puede decidir |
|---|---|---|---|
| analyst | cobertura, coordinación, límites | obligaciones, decisiones, índice de evidencia | si el producto se acepta |
| implementer | implementación y empaquetado | código de producción, Dockerfile, RUN.md, sus propios tests | si su propio trabajo vale |
| adversary | crítica independiente | sus propias suites y sus informes de fallo | arreglos de producción, ni publicar |
| auditor | reproducción e integridad | registros de auditoría y veredictos | no puede tocar producto ni tests para que pasen |

El roster de esta tirada:

| Nombre visible | @handle | Id de agente en Band | Harness | Modelo |
|---|---|---|---|---|
| analyst | hugo.valer/analyst-thgs | fd5095ef-bafa-4039-b597-3f160b75cf21 | Claude Code | claude-opus-5 |
| implementer | hugo.valer/implementer-thgt | 156a2fed-f92e-4453-8e6c-75ecdb48ef20 | Claude Code | claude-opus-5 |
| adversary | hugo.valer/adversary-thgz | f603ac21-88ea-434a-844e-bb621f8da63e | Claude Code | claude-opus-5 |
| auditor | hugo.valer/auditor-thgx | f6bf20d6-c769-4d36-bb79-47d5e384287a | Claude Code | claude-opus-5 |

Nombre visible, @handle e id de agente son tres cosas distintas. Los mandatos se dirigen entre sí
por el segundo y la sala registra el tercero. Nada en `mandates/` nombra un pago, una pantalla, una
ruta ni este track: para apuntar la fábrica a otro problema se cambia el despacho, y ningún mandato
necesita edición.

## Por qué caza cosas

Cuatro filtros, en orden, y cada uno lo posee un asiento que no posee el anterior.

1. **El registro de obligaciones va antes que el código.** El analyst convierte cada sección de la
   especificación en obligaciones numeradas, con su referencia de origen y su método de aceptación.
   El adversary impugna ese registro buscando omisiones *antes* de que se acepte implementación
   alguna. En el stage 2 presentó veinte objeciones de cobertura antes de que se escribiera una
   línea.
2. **Un candidato se congela en un commit.** El implementer publica el identificador completo y deja
   de tocarlo. Ningún revisor lee un árbol de trabajo.
3. **El adversary verifica desde su propio clon limpio**, con sus propias suites, versionadas en
   `verification/adversary/stage-N/`, y entrega un paquete que incluye la lista explícita de lo que
   **no** probó.
4. **El auditor reproduce todo él mismo** en un clon nuevo, con sus propias imágenes `--no-cache` y
   sus propios contenedores, y solo entonces decide. Copiar el informe de otro no es reproducir.

La regla que convierte esto en algo más que ceremonia: **un check set en verde no es evidencia de
que un requisito se cumpla.** Bajo este despacho, una fila de la especificación sin evidencia sigue
abierta aunque pasen todos los tests públicos. El analyst tuvo que decirlo en voz alta durante el
stage 1:

> Some items on your "untested" list are spec rows, not decisions. Under the dispatch they count as
> open until evidence exists, even though every public test passes.

## Los dos rechazos

Los dos los encontraron las sondas del propio auditor, sobre candidatos en los que el harness
oficial ya había pasado. Ese es el argumento entero de este diseño, así que van completos.

### Stage 3 — el servicio se moría y todas las suites estaban en verde

`F3-A01`. Con lecturas sostenidas de extracto, el proceso **se caía por desbordamiento del heap de
V8**. Con 500 pagos de historial murió tras **4.761 lecturas**, exit 139, y perdió todo el estado.
La memoria no se liberaba nunca.

Lo que ese mismo candidato ya había pasado, todo reproducido por el auditor en contenedores nuevos:

| Comprobación | Resultado |
|---|---|
| Harness oficial `--stage 3`, modo host **y aislado** | 147 + 35 + 6, **0 omitidos** |
| Regresión de stage 1 y 2 sobre `stage-3/`, API e interfaz a 375 px y 1280 px | **150/150** |
| Probe de stage 3 con historial calculado a mano | 33/33 |
| Migraciones 1→3 y 2→3 en contenedores nuevos | 14/14 |

Todo verde, y el servicio no aguantaba que lo usaran. La suite entregada nunca leía suficientes
extractos para enterarse. En el mismo veredicto viajó un segundo defecto: `F3-01`, una retención
cerrada vista a través de un `known_at` anterior no expiraba nunca en su fecha límite — `held` se
quedaba en 1000 en `expires_at` + 1 ms, y seguía ahí en el año 2099.

La reparación se enrutó junto con la obligación incumplida, se reconstruyó y se reauditó contra un
commit nuevo. `stage-3/test/perf/statement_memory.js` existe por esto.

### Stage 2 — pequeño, y aun así bloqueó

`F2-01`. Un capture rechazado no conservaba el importe tecleado: prellenado `20.00`, tecleado
`25.00`, se muestra el rechazo, y el campo volvía sin avisar a `20.00`. No se movía dinero;
severidad baja. El analyst había dictaminado que la fila del registro vincula, así que el candidato
no se podía aceptar con ella abierta.

Lo dejamos escrito porque lo interesante es lo que **no** pasó: nadie negoció la severidad a la baja
para entregar a tiempo.

## Lo que costó

Estimado a precios de catálogo del proveedor a partir de los recuentos de tokens del runtime.
**Esto no es una factura**, y la atribución de BAND no es estable entre reinicios, así que trátese
como un orden de magnitud.

| Asiento | Tokens | Estimación |
|---|---|---|
| auditor | 130.989.459 | 38,50 $ |
| adversary | 125.995.041 | 38,30 $ |
| implementer | 107.065.994 | 32,81 $ |
| analyst | 92.935.707 | 26,31 $ |
| **Total** | **456.986.201** | **~136 $** |

El gasto es casi plano entre los cuatro asientos, y los dos de verificación juntos cuestan más que
el que construye. Eso es el diseño apareciendo en la factura: la mayor parte del dinero se va en
decidir si el trabajo se sostiene, no en producirlo.

No había tope duro configurado en el proveedor, así que durante la tirada no se podía imponer ningún
techo económico. Los límites exigibles eran de reloj: 360 minutos por stage y 1440 en total. La
tirada usó 254.

## Cronología

Horas UTC, del 2026-09-28 al 2026-09-29.

| | |
|---|---|
| 20:40 | Despacho. Un mensaje, cuatro stages autorizados |
| 21:35 | Stage 1 **ACEPTADO**, sin ciclo de reparación |
| 21:39 | El analyst abre el stage 2 por su cuenta, handoff en 10 partes, sin intervención humana |
| 22:22 | Candidato 1 del stage 2 **RECHAZADO** (`F2-01`) |
| 22:45 | Stage 2 **ACEPTADO**, migración 1→2 verificada |
| 23:41 | Candidato 1 del stage 3 **RECHAZADO** (`F3-A01` heap OOM, y `F3-01`) |
| 00:07 | Stage 3 **ACEPTADO**, migraciones 1→3 y 2→3 |
| 00:42 | Stage 4 **ACEPTADO**, migraciones 1→4, 2→4, 3→4 |
| 00:54 | Verificación global **PASS** sobre un clon nuevo; informe final del analyst |
| 00:55 | El auditor verifica el informe final de forma independiente |

Cuatro minutos entre aceptar un stage y despachar el siguiente, todas las veces, sin nadie mirando.

## Cómo se levanta

1. Crear una sala que todos los asientos puedan leer y escribir.
2. **Conceder todos los permisos que un mandato obliga a usar, antes de la primera tarea.** Un
   asiento que debe arrancar un contenedor y tiene que pedir permiso es un asiento parado ante un
   diálogo que nadie mira, y un permiso concedido a mitad de tirada es una segunda intervención
   humana en una tirada que debía tener una.
3. Dar a cada sesión un solo fichero de `mandates/` y nada más sobre el problema. Nombrar la sesión
   como su asiento, para que en el export cada mensaje sea atribuible.
4. **Decirle a cada asiento cómo se habla en la sala.** Este es el paso que hicimos mal, y costó una
   ida y vuelta: los mandatos exigen handoffs dirigidos a un `@handle` resuelto, pero ninguno dice
   que la ventana de un asiento no es la sala. Dos de los cuatro contestaron en su ventana y se
   quedaron esperando a que les dijeran que adoptaran el mandato. Una sala cuyos asientos responden
   en sus ventanas se exporta como llamadas a herramienta y ninguna conversación.
5. Confirmar **desde fuera** de las sesiones que cada asiento escribe y lee, antes de despachar. Que
   escribe se prueba con un mensaje suyo en la sala; que lee, con la cola vacía.
6. Despachar una vez. Y luego no hacer nada.

### Lo que le diríamos al siguiente equipo

**El receptor de 30 minutos es un límite del host, no un error.** Nuestros mandatos piden un
receptor armado de forma persistente y sin timeout. En este host el clasificador de tareas de fondo
corta cualquier vigía a 1800 segundos, así que cada asiento se rearma cada media hora mientras vive.
Los asientos lo gestionaron bien y lo dijeron:

> The mandate asks for a receiver with no timeout, but this host stops a watcher after 30 minutes at
> most. I'll restart it with the same lease each time it expires.

Conviene escribir el mandato contando con eso, en vez de prohibirlo.

**Poner el fichero de permisos donde los asientos trabajan de verdad.** El nuestro estaba un
directorio por debajo de su directorio de trabajo y no sirvió absolutamente de nada hasta que se
movió.

**Denegar unas pocas cosas de forma explícita.** Un agente con una shell durante doce horas sin
vigilancia no debería poder borrar su propia identidad, soltar el lease de su sala, empujar a un
remoto ni purgar Docker. Son cuatro líneas y no cuestan nada.

## Límites honestos

**Dos rechazos no son muchos.** Son reales y los dos se reprodujeron, pero desde dentro de la tirada
no podemos saber si existe un tercer defecto que los cuatro filtros dejaron pasar. Los dos los
encontraron las sondas del propio auditor, lo que significa que el techo de este diseño es la
imaginación de un solo asiento.

**Una tirada es un solo dato.** Nada de esto demuestra que la fábrica sea repetible a esta velocidad
contra otra especificación, y esta la publicaron los organizadores, así que un modelo pudo llegar
con ventaja sobre el dominio.

**El auditor no hace mutación, y sabemos lo que eso cuesta.** Una puerta más exigente rompería, para
cada criterio, el comportamiento que ese criterio describe en una copia privada, y confirmaría que el
check mapeado es el que falla. Esta fábrica reproduce en vez de eso. Reproducir cazó una caída de
heap que ninguna suite vio, así que no es poco — pero un check que pasara contra código roto a
propósito seguiría pareciendo correcto aquí.

No es una hipótesis. Antes de esta tirada corrimos **otra banda nuestra**, de cuatro asientos, en la
que el verificador sí mutaba: para cada criterio rompía a propósito el comportamiento descrito y
exigía que fallara justo el check mapeado. En tres stages produjo **trece rechazos, y ninguno era un
fallo del servicio**. Los trece eran check sets que corrían en verde y no probaban lo que decían
probar. Tres ejemplos, porque el patrón importa más que la anécdota:

- Un medidor de contraste que no componía `opacity` hacia abajo en el árbol, así que texto a 1,8:1
  pasaba como legible.
- Un arnés de carga cuyo `except` solo capturaba `HTTPError`, así que cuarenta y tres peticiones sin
  respuesta no dejaban rastro y el resumen decía `slow_responses: 0`.
- Una clave de idempotencia construida desde el importe ya parseado, así que `"15.00"` y `"15"`
  colisionaban y el reintento no movía dinero.

Ninguno lo habría encontrado la reproducción: los tres checks se ejecutaban, terminaban y decían que
todo estaba bien. Hacía falta romper el comportamiento para ver que el check no lo sujetaba. Ese es
el escalón que le falta a esta fábrica, y es por donde la ampliaríamos primero: mutar los criterios
que **añade** una entrega, no el conjunto acumulado, y dejar que la reproducción completa del auditor
siga siendo la puerta de regresión.

**Las cifras de coste son estimaciones**, sacadas de recuentos de tokens a precios de catálogo, y la
atribución por agente de BAND se mueve entre reinicios. Son honestas en orden de magnitud y no más
allá.
