# Cuatro asientos, y el servicio de pagos que construyeron

*[Read in English](README.md)*

**Track:** Pocketful · **Equipo:** four-seats · **Licencia:** MIT

Cuatro asientos de agente en una sala de BAND Desktop: un **analyst** que convierte la
especificación en obligaciones numeradas, un **implementer** que construye, un **adversary** que
intenta refutar lo construido, y un **auditor** que reproduce la evidencia antes de que se acepte
nada. Ningún asiento acepta su propio trabajo.

**En esta sala existe un solo mensaje humano.** Autorizó los cuatro stages y no dijo nada más. Cada
stage posterior al primero lo abrió el propio analyst, cuatro minutos después de que se aceptara el
anterior.

## Qué hay aquí

| | |
|---|---|
| Stages | **4 de 4**, cada uno congelado y auditado de forma independiente |
| Harness público, `--all --mode isolated`, desde un clon nuevo | cada carpeta reclama su stage, **el 100% de sus checks**, sin desbordar al siguiente |
| Rechazos del auditor | **2**, los dos reparados y reauditados dentro de la tirada |
| Tiempo de pared | **4 h 14 min**, del despacho al informe final |
| Gasto en modelo | **~136 $**, estimado a precios de catálogo |

Uno de esos rechazos es la razón por la que merece la pena leer este repositorio. Sobre un candidato
del stage 3 el harness oficial lo pasó todo —147 + 35 + 6 checks en modo aislado, cero omitidos, más
150/150 de regresión y 14/14 de migraciones— y el auditor lo rechazó igualmente, porque su propia
sonda hizo que el servicio **se cayera con un desbordamiento de heap tras 4.761 lecturas de
extracto** y perdiera todo el estado. `FACTORY.es.md` los cuenta enteros.

## Mapa

- **`FACTORY.es.md`** — el diseño, los resultados medidos, los dos rechazos, lo que costó y las cuatro
  cosas que le diríamos al siguiente equipo. Empieza por ahí.
- `mandates/` — las cuatro instrucciones permanentes, tal cual se cargaron en los asientos. Lee una
  entera: en ningún momento dice cuál es el producto.
- `stage-1/` … `stage-4/` — un servicio autónomo por stage. Cada uno se construye y arranca solo,
  sin depender de los demás.
- `verification/adversary/stage-N/` — las suites propias del adversary, versionadas y separadas del
  código de producción.
- `evidence/runs/fskit-001/` — el registro: obligaciones, handoffs, veredictos, tiradas del harness
  e informes de migración. Cada afirmación enlaza una obligación, una revisión de producto, una
  revisión de tests, un comando y un resultado real.
- `room.json` — la sesión completa exportada de BAND. El único mensaje humano es fácil de encontrar.

## Cómo ejecutarlo

Cada carpeta de stage trae su `RUN.md` y se construye en un solo comando, sin red en tiempo de
ejecución. Para comprobar un stage contra el harness oficial, desde el checkout del kickoff:

```
python -m harness run --track pocketful --repo <este repo> --stage 1 --mode isolated --out <dir nuevo>
```

`--stage 2`, `3` y `4` hacen lo mismo con las carpetas posteriores, y `--all` verifica la cadena
entera. Los stages 2 a 4 sirven una interfaz de navegador; el harness la recorre a 375 px y 1280 px.

## Lo que no afirmamos

Dos rechazos no son muchos, y desde dentro de la tirada no podemos saber si un tercer defecto se
coló entre los cuatro filtros. Una tirada es un solo dato. El auditor reproduce, pero no hace
pruebas de mutación: un check que pasara contra código roto a propósito seguiría pareciendo correcto
aquí. Las cifras de coste son estimaciones a partir de recuentos de tokens, no una factura.
`FACTORY.es.md` dice todo esto con más detalle, porque una fábrica que esconde sus límites no es una
que nadie vaya a reutilizar.
