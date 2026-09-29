# Cuatro asientos que no se creen la palabra del otro

*[Read in English](FACTORY.md)*

Una fábrica de software levantada sobre BAND Desktop. Cuatro asientos de agente en una sala: uno
decide cuál es el trabajo, otro lo construye, otro intenta romperlo, y otro reproduce todo antes de
que se acepte nada. Ningún asiento acepta su propio trabajo, y una afirmación nunca mueve un
artefacto — lo mueve una reproducción.

En toda la sala existe un solo mensaje humano. Autorizó cuatro stages y no volvió a hablar.

## Lo que produjo

| | |
|---|---|
| Stages entregados | **4 de 4**, cada uno congelado y aceptado por el auditor |
| Harness público, `--all --mode isolated`, clon nuevo | cada carpeta reclama su stage con **el 100% de sus checks públicos** |
| Candidatos rechazados | **2**, con **3 hallazgos distintos**, todos reparados y reauditados dentro de la tirada |
| Mensajes humanos en la sala | **1** |
| Tiempo de pared, del despacho al informe final | **4 h 14 min** |
| Gasto en modelo, precios de catálogo | **~136 $** (estimación, no factura) |

Lo que pasó cada carpeta en la tirada final del auditor, según los informes originales en
[`evidence/runs/fskit-001/final/harness-isolated/`](evidence/runs/fskit-001/final/harness-isolated/INDEX.md):

| Carpeta | Suite 1 | Suite 2 | Suite 3 | Suite 4 | Reclama |
|---|---|---|---|---|---|
| `stage-1/` | 147/147 | *falla, como debe* | | | stage 1 |
| `stage-2/` | 147/147 | 35/35 | *falla, como debe* | | stage 2 |
| `stage-3/` | 147/147 | 35/35 | 6/6 | *falla, como debe* | stage 3 |
| `stage-4/` | 147/147 | 35/35 | 6/6 | 5/5 | stage 4 |

Que los stages 1 a 3 fallen la suite siguiente es la regla de congelación aguantando: cada carpeta es
la solución de su propio stage y no de uno posterior. El stage 4 no tiene suite siguiente, así que no
hay nada que pueda fallar. Son los checks **públicos** del kickoff (`preview: true`); el propio
harness avisa de que son una parte de lo que se aplica antes de juzgar, y no afirmamos nada sobre la
evaluación oculta.

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
| analyst | hugo.valer/analyst-thgs | fd5095ef-bafa-4039-b597-3f160b75cf21 | Claude Code | claude-opus-5-5 |
| implementer | hugo.valer/implementer-thgt | 156a2fed-f92e-4453-8e6c-75ecdb48ef20 | Claude Code | claude-opus-5-5 |
| adversary | hugo.valer/adversary-thgz | f603ac21-88ea-434a-844e-bb621f8da63e | Claude Code | claude-opus-5-5 |
| auditor | hugo.valer/auditor-thgx | f6bf20d6-c769-4d36-bb79-47d5e384287a | Claude Code | claude-opus-5-5 |

Nombre visible, @handle e id de agente son tres cosas distintas. Los mandatos se dirigen entre sí
por el segundo y la sala registra el tercero. Nada en `mandates/` nombra un pago, una pantalla, una
ruta ni este track: para apuntar la fábrica a otro problema se cambia el despacho, y ningún mandato
necesita edición. [`RUNBOOK.es.md`](RUNBOOK.es.md) explica cómo.

**Sobre el modelo.** Claude Code es el runtime; el modelo que ejecutó cada sesión fue
`claude-opus-5-5`, que es lo que los asientos registran en su propia evidencia (63 veces). Antes del
despacho, la configuración del operador decía `claude-opus-5` y las cabeceras de los mandatos solo
`Model: Opus`, nombrando la familia y no el ID exacto. El analyst lo advirtió y registró la
discrepancia como decisión D-17 del registro del stage 1, en vez de resolverla adivinando. Las
cabeceras llevan ahora el ID exacto; el cuerpo de cada mandato es el texto que se cargó, sin cambios.

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

Se rechazaron dos candidatos, con tres hallazgos distintos. **El adversary encontró `F2-01` y
`F3-01`; el auditor reprodujo los dos y encontró él mismo `F3-A01`.** Todos estaban en candidatos en
los que el harness oficial ya había pasado. Ese es el argumento entero de este diseño, así que van
completos.

### Stage 3 — el servicio se moría y todas las suites estaban en verde

`F3-A01`, encontrado por la sonda del propio auditor. Con lecturas sostenidas de extracto, el
proceso **se caía por desbordamiento del heap de V8**. Con 500 pagos de historial murió tras **4.761
lecturas**, exit 139, con 1,06 GiB, y perdió todo el estado. La memoria no se liberaba nunca.

Lo que ese mismo candidato ya había pasado, todo reproducido por el auditor en contenedores nuevos:

| Comprobación | Resultado |
|---|---|
| Harness oficial `--stage 3`, modo host **y aislado** | 147 + 35 + 6, **0 omitidos** |
| Regresión de stage 1 y 2 sobre `stage-3/`, API e interfaz a 375 px y 1280 px | **150/150** |
| Probe de stage 3 con historial calculado a mano | 33/33 |
| Migraciones 1→3 y 2→3 en contenedores nuevos | 14/14 |

Todo verde, y el servicio no aguantaba que lo usaran. La suite entregada nunca leía suficientes
extractos para enterarse. En el mismo veredicto viajó un segundo defecto: `F3-01`, que informó el
adversary y reprodujo el auditor — una retención cerrada vista a través de un `known_at` anterior no
expiraba nunca en su fecha límite. `held` se quedaba en 1000 en `expires_at` + 1 ms, y seguía ahí en
el año 2099.

La reparación se enrutó junto con las obligaciones incumplidas, se reconstruyó y se reauditó contra
un commit nuevo. El analyst fijó la puerta: **20.000 lecturas de extracto** sobre 500 pagos, 20 en
vuelo, en un contenedor limitado a 2 CPU y 2 GiB. En el candidato reparado las 20.000 devolvieron 200
y el contenedor seguía corriendo con **39,7 MiB**. `stage-3/test/perf/statement_memory.js` existe por
esto, y lo llevan todos los stages posteriores.

### Stage 2 — pequeño, y aun así bloqueó

`F2-01`, encontrado por la suite del adversary (sus dos únicos fallos en ese candidato) y reproducido
por el auditor a 375 px y 1280 px. Un capture rechazado no conservaba el importe tecleado:
prellenado `20.00`, tecleado `25.00`, se muestra el rechazo, y el campo volvía sin avisar a `20.00`.
No se movía dinero; severidad baja.

No es un incumplimiento del texto de la especificación. Rompía **D2-19**, una decisión que la propia
banda había hecho vinculante en su registro. El candidato no podía aceptarse con ella abierta, así que
la fábrica hizo cumplir sus propios criterios con el mismo rigor que los de los organizadores. Y nadie
negoció la severidad a la baja para entregar a tiempo.

## Lo que costó

Estimado por BAND (`band usage agents`, que usa ccusage) a precios de catálogo del proveedor a partir
de los recuentos de tokens del runtime. **Esto no es una factura**, no se aplicó ningún límite de
gasto, y la atribución de BAND puede moverse entre reinicios, así que trátese como un orden de
magnitud. Las cifras en bruto, con la hora de captura, están en
[`evidence/runs/fskit-001/final/USAGE.json`](evidence/runs/fskit-001/final/USAGE.json).

| Asiento | Entrada | Salida | Escritura caché | Lectura caché | Estimación |
|---|---:|---:|---:|---:|---:|
| auditor | 716 | 335.048 | 726.650 | 129.927.045 | 38,50 $ |
| adversary | 664 | 377.432 | 721.558 | 124.895.387 | 38,30 $ |
| implementer | 628 | 325.382 | 635.114 | 106.104.870 | 32,81 $ |
| analyst | 762 | 200.909 | 479.992 | 92.254.044 | 26,31 $ |
| **Total** | **2.770** | **1.238.771** | **2.563.314** | **453.181.346** | **135,93 $** |

Más del 99 % de los tokens son lecturas de caché, que se cobran muy por debajo de la entrada nueva.
Por eso 457 millones de tokens salen por unos 136 $: cada asiento relee su propio contexto largo en
cada turno, y el proveedor cobra poco por eso.

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
| 20:40:49 | Despacho. Un mensaje, cuatro stages autorizados (`3f95ab60`) |
| 21:34:58 | Stage 1 **ACEPTADO**, sin ciclo de reparación (`72be202b`) |
| 21:39:14 | El analyst abre el stage 2 por su cuenta, handoff en 10 partes |
| 22:23:08 | Candidato 1 del stage 2 **RECHAZADO**, `F2-01` (`4fc4757a`) |
| 22:45:46 | Stage 2 **ACEPTADO**, migración 1→2 verificada (`4ced8436`) |
| 23:10:50 | El analyst abre el stage 3, handoff en 13 partes |
| 23:41:10 | Candidato 1 del stage 3 **RECHAZADO**, `F3-A01` heap OOM y `F3-01` (`b8d9c67c`) |
| 00:08:00 | Stage 3 **ACEPTADO**, migraciones 1→3 y 2→3 (`11dbc577`) |
| 00:10:43 | El analyst abre el stage 4 |
| 00:42:52 | Stage 4 **ACEPTADO**, migraciones 1→4, 2→4, 3→4 (`10381cd3`) |
| 00:54 | Verificación global **PASS** sobre un clon nuevo; informe final del analyst |
| 00:55:10 | El auditor verifica el informe final de forma independiente (`d828d505`) |

Los ids son ids de mensaje de `room.json`. El analyst abrió cada stage siguiente sin ninguna
intervención humana. Los tiempos entre aceptación y handoff fueron **4 min 16 s, 25 min 4 s y 2 min
43 s**. El largo es el del stage 3: su handoff llevaba tres especificaciones literales en 13 partes. A
las 23:10:02 el implementer señaló la espera en la sala —*"I am idle and listening… I have received
no stage-3 handoff since"*— y el handoff llegó 48 segundos después. La coordinación no salió de la
banda.

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

**Tres hallazgos no son muchos.** Son reales y los tres se reprodujeron, pero desde dentro de la
tirada no podemos saber si existe un cuarto defecto que los cuatro filtros dejaron pasar. Los
encontraron dos asientos —el adversary dos, el auditor uno—, así que el techo de este diseño es la
imaginación de dos asientos independientes, y no más.

**Dos áreas merecen trabajo en una siguiente tirada**, señaladas por una auditoría externa y no
reproducidas como defectos:

- *Memoria de los snapshots.* La reparación de `F3-A01` dejó de copiar el extracto entero por token,
  pero cada lectura nueva sigue guardando un registro pequeño y nada borra tokens. El espacio por
  token es constante; el total crece con el número de tokens emitidos. La puerta de 20.000 lecturas
  pasó con 39,7 MiB, pero el crecimiento sostenido más allá no está medido. Cualquier arreglo tiene
  que mantener vivos los tokens anteriores, como exige la especificación.
- *Sobregiro histórico.* La decisión D3-21 acepta una corrección cuando una frontera pasada ya era
  negativa y la corrección no la empeora. Es una interpretación del texto del stage 3, implementada
  en `ledger.overdraws`, y debería probarse de forma explícita con fixtures que reconstruyan un saldo
  de apertura negativo.

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
