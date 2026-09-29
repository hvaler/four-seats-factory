# Runbook — volver a levantar la fábrica

*[Read in English](RUNBOOK.md)*

Cómo ejecutar esta fábrica contra otro problema. En `mandates/` no cambia nada: se cambia el
despacho, y la banda hace el resto. Todo lo que hace falta está en [`setup/`](setup/).

## Qué usó esta tirada

| | |
|---|---|
| BAND Desktop / CLI | `band 0.4.11` (el CLI también responde a `jam`) |
| Runtime de los asientos | Claude Code `2.1.284`, con auto mode |
| Modelo, los cuatro asientos | `claude-opus-5-5` |
| Harness | kickoff `band-ai/dark-factory-wearedevs` en `803560d2`, Python 3.12.3 en WSL2, Playwright 1.63.0 |
| Contenedores | Docker 29.8.0 con integración WSL2 |
| Host | Windows 11, una sola máquina para los cuatro asientos y todos los checks |

## Estructura

Tres ubicaciones separadas, y a cada asiento se le dan las rutas absolutas:

```
<workspace>/
  <kickoff>/            el repositorio de los organizadores, fijado a un commit; no se toca
  <band>/               directorio de trabajo de los asientos — las cuatro ventanas se abren aquí
    .claude/settings.local.json     permisos (setup/claude-settings.example.json)
    result/             este repositorio: el único sitio donde se escribe código de stage
    checks/             todos los directorios --out del harness; nunca dentro de result/
    clones/             los clones limpios de revisores y auditor, uno por candidato
```

Los asientos trabajan **en `<band>/`**, no en `result/`. El fichero de permisos tiene que estar en el
directorio donde se abren los asientos; en el primer intento el nuestro estaba un nivel más abajo y no
sirvió de nada.

## Pasos

1. **Sala.** Crearla en BAND Desktop y apuntar su id.
2. **Asientos.** Abrir cuatro ventanas de Claude Code, todas en `<band>/`. En cada una, en este orden:
   1. `/jam as analyst` (luego `implementer`, `adversary`, `auditor`). **Pasar siempre el rol**; sin él
      el diálogo propone `developer`. El asiento nace *parked*.
   2. En BAND Desktop: la sala → **Participants** → **Add participants** → **Agents** → ese asiento.
   3. Solo entonces, en la ventana: `/jam join this Claude Code session to room <id-de-sala>`.

   Hacer el 3 antes que el 2 da un éxito falso: la ventana dice `binding=bound` y el asiento aparece
   *en otra sala*, lo que además impide añadirlo.
3. **Comprobar que los dos carriles ven cada asiento.** `band room participants <sala>` y
   `band chat participants <sala> --as <owner>/<handle>`. Un `HTTP 404` en el segundo significa que el
   asiento todavía no es miembro de verdad.
4. **Permisos.** Copiar `setup/claude-settings.example.json` a `<band>/.claude/settings.local.json`
   antes de pegar nada. Su lista `deny` impide que un asiento borre su propia identidad (`band rm`),
   suelte su lease (`band detach`), borre BAND (`band reset`), empuje a un remoto (`git push`) o purgue
   Docker. `/permissions` en cada ventana para confirmar que se cargó.
5. **Textos de asiento.** Pegar en cada ventana `setup/preamble.md` seguido del fichero de ese asiento
   en `mandates/`. El preámbulo dice lo único que los mandatos no pueden decir: que la ventana no es la
   sala, y cómo se publica en ella. Si un asiento responde en su ventana y pregunta si adopta el
   mandato, se le dice que sí — dos de los nuestros lo hicieron.
6. **Confirmar desde fuera** que cada asiento escribe y lee: un mensaje suyo en la sala prueba que
   escribe; `band --session <asiento> inbox` mostrando `(inbox empty)` después de los anuncios de los
   demás prueba que lee.
7. **Despacho.** Rellenar `setup/dispatch-template.txt` (todos los `{{…}}` menos los cinco que la banda
   resuelve en ejecución: `N`, `SEAT`, `ATTEMPT`, `REVIEW_CLONE_ABS_CREATED_BY_SEAT`,
   `AUDITOR_CLONE_ABS_CREATED_BY_AUDITOR`) y enviarlo **una vez**, al analyst, como humano:

   ```
   band room send <id-de-sala> "$(cat dispatch.txt)" --mention <id-de-agente-del-analyst>
   ```

   El texto literal que enviamos es el mensaje `3f95ab60` de `room.json`.
8. **Y luego nada.** Ni confirmaciones, ni pistas, ni relanzar. El analyst abre cada stage siguiente
   por su cuenta.
9. **Exportar** cuando llegue el informe final: `⋮` de la sala → **Open in Band** → `⋮` → **Download**
   → **Download full session**, guardado sin cambios como `room.json`. Redactar los leases de receptor
   (`jrx_…`) y dejar constancia, como en [`REDACTION.md`](REDACTION.md).

## Verificar el resultado

`setup/verify-from-clone.sh <dir-del-kickoff>` hace lo mismo que haría un juez: clona este
repositorio desde GitHub en un directorio temporal nuevo, pasa `harness check`, después
`harness run --all --mode isolated`, e imprime el stage que reclama cada carpeta. Termina con error
salvo que las cuatro reclamen el suyo.

## Apuntarla a otro problema

Se cambia el despacho, no los mandatos. En `setup/dispatch-template.txt`:

- las rutas de la especificación y la secuencia de stages;
- los párrafos de *focus* por stage, que son la única prosa específica del track en el fichero;
- los comandos del harness, si el nuevo problema se comprueba de otra forma;
- el bloque `THIS HOST`, que describe esta máquina (WSL, el intérprete del harness, Docker) y es
  falso en cualquier otra.

Los límites, explícitos y fijados antes del despacho: usamos 5 ciclos de reparación por stage, 2
reintentos de infraestructura por comando, 360 minutos por stage y 1440 en total. La tirada usó 254.

## Cosas que van a pasar y no son fallos

- **Los receptores caducan cada 30 minutos.** El host corta las tareas de fondo a 1800 s. Los asientos
  se rearman con el mismo lease; en la sala se ve como un goteo constante de llamadas a herramienta.
- **La memoria se queda corta.** Con los cuatro asientos y sus contenedores, la memoria libre del host
  bajó a 3,5 GB de 31,6, y Claude Code paró por falta de memoria la shell de monitorización del
  operador. La banda no se vio afectada, pero conviene dejar margen.
- **Nunca corrimos dos bandas a la vez en un mismo host**, y no lo haríamos: las sondas de tiempos y de
  concurrencia del auditor dan por hecho que la máquina es suya.
