# Redaction record for `room.json`

*[Leer en español abajo](#registro-de-redacción)*

`room.json` is the complete session exported from BAND Desktop with **Download full session**. One
class of value was replaced before publishing, under the participant guide's credential exception.

## What was replaced

| | |
|---|---|
| What | BAND receiver lease tokens, `jrx_<hex>` |
| How many | 4 distinct tokens, one per seat, appearing 50 times |
| Replaced with | `jrx_[REDACTED]` |
| Where they appeared | `tool_call` (47) and `tool_result` (3) events only |
| Where they did **not** appear | no `text` message contains one |

A receiver lease authorises reading a seat's message queue. Publishing one would let a reader drain
a seat's inbox, so it is a credential and not a record of what happened.

## What was not touched

Verified programmatically before and after the substitution:

| | Before | After |
|---|---|---|
| Events | 3156 | 3156 |
| `text` messages | 248 | 248 |
| Human messages | 1 | 1 |
| Total characters across all `text` content | 1,662,234 | 1,662,234 |

No message was edited, reordered or removed. No failure was hidden. The narrative of the run — every
handoff, every verdict, both rejections, and the single human dispatch — is byte-for-byte the export
BAND produced.

---

## Registro de redacción

`room.json` es la sesión completa exportada de BAND Desktop con **Download full session**. Antes de
publicar se sustituyó una sola clase de valor, acogiéndose a la excepción de credenciales de la guía
de participantes.

**Qué se sustituyó:** los tokens de lease de receptor de BAND, `jrx_<hex>`. Cuatro distintos, uno por
asiento, que aparecían 50 veces, todas en eventos `tool_call` (47) y `tool_result` (3). **Ningún
mensaje de texto contiene uno.** Se reemplazaron por `jrx_[REDACTED]`.

Un lease de receptor autoriza a leer la cola de mensajes de un asiento. Publicarlo permitiría a
cualquiera vaciar la bandeja de un seat: es una credencial, no un registro de lo que pasó.

**Qué no se tocó:** nada más. Comprobado por programa antes y después: 3.156 eventos, 248 mensajes de
texto, 1 mensaje humano y 1.662.234 caracteres de contenido de texto, idénticos en ambos lados. No se
editó, reordenó ni eliminó ningún mensaje, ni se ocultó ningún fallo.
