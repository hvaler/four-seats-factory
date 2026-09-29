# Runbook — standing the factory up again

*[Leer en español](RUNBOOK.es.md)*

How to run this factory against a different problem. Nothing in `mandates/` changes: you change the
dispatch, and the band does the rest. Every file you need is in [`setup/`](setup/).

## What this run used

| | |
|---|---|
| BAND Desktop / CLI | `band 0.4.11` (the CLI also answers to `jam`) |
| Seat runtime | Claude Code `2.1.284`, auto mode on |
| Model, all four seats | `claude-opus-5-5` |
| Harness | kickoff `band-ai/dark-factory-wearedevs` at `803560d2`, Python 3.12.3 in WSL2, Playwright 1.63.0 |
| Containers | Docker 29.8.0 with WSL2 integration |
| Host | Windows 11, one machine, all four seats and every check on it |

## Layout

Keep three locations apart, and give every seat the absolute paths:

```
<workspace>/
  <kickoff>/            the organisers' repository, pinned to one commit; never modified
  <band>/               the seats' working directory — all four windows open here
    .claude/settings.local.json     permissions (setup/claude-settings.example.json)
    result/             this repository: the only place stage code is written
    checks/             every harness --out directory; never inside result/
    clones/             reviewers' and auditor's clean clones, one per candidate
```

The seats work **in `<band>/`**, not in `result/`. The permissions file has to be in the directory the
seats are opened in; ours was one level too deep for the first attempt and did nothing.

## Steps

1. **Room.** Create one in BAND Desktop. Note its id.
2. **Seats.** Open four Claude Code windows, all in `<band>/`. In each, in this order:
   1. `/jam as analyst` (then `implementer`, `adversary`, `auditor`). **Always pass the role**; without
      it the dialog suggests `developer`. The seat is minted *parked*.
   2. In BAND Desktop: the room → **Participants** → **Add participants** → **Agents** → that seat.
   3. Only then, in the window: `/jam join this Claude Code session to room <room-id>`.

   Doing 3 before 2 gives a false success: the window reports `binding=bound` and the seat shows as
   *in another room*, which also stops you adding it.
3. **Check both lanes see each seat.** `band room participants <room>` and
   `band chat participants <room> --as <owner>/<handle>`. An `HTTP 404` on the second means the seat
   is not really a member yet.
4. **Permissions.** Copy `setup/claude-settings.example.json` to `<band>/.claude/settings.local.json`
   before pasting anything. Its `deny` list stops a seat deleting its own identity (`band rm`),
   releasing its lease (`band detach`), wiping BAND (`band reset`), pushing (`git push`) or pruning
   Docker. Run `/permissions` in each window to confirm it loaded.
5. **Seat texts.** Paste into each window `setup/preamble.md` followed by that seat's file from
   `mandates/`. The preamble says the one thing the mandates cannot: that the window is not the room,
   and how to post to it. If a seat answers in its window and asks whether to adopt the mandate, tell
   it yes — two of ours did.
6. **Confirm from outside** that each seat both writes and reads: a message of its own in the room
   proves writing; `band --session <seat> inbox` showing `(inbox empty)` after the others' announcements
   proves reading.
7. **Dispatch.** Fill `setup/dispatch-template.txt` (every `{{…}}` except the five the band resolves at
   run time: `N`, `SEAT`, `ATTEMPT`, `REVIEW_CLONE_ABS_CREATED_BY_SEAT`,
   `AUDITOR_CLONE_ABS_CREATED_BY_AUDITOR`) and send it **once**, to the analyst, as the human:

   ```
   band room send <room-id> "$(cat dispatch.txt)" --mention <analyst-band-agent-id>
   ```

   The literal text we sent is message `3f95ab60` in `room.json`.
8. **Then nothing.** No confirmations, no hints, no reruns. The analyst opens each next stage itself.
9. **Export** when the final report is in: the room's `⋮` → **Open in Band** → `⋮` → **Download** →
   **Download full session**, saved unchanged as `room.json`. Redact receiver leases (`jrx_…`) and
   record it, as in [`REDACTION.md`](REDACTION.md).

## Pointing it at a different problem

Change the dispatch, not the mandates. In `setup/dispatch-template.txt`:

- the specification paths and the stage sequence;
- the per-stage *focus* paragraphs, which are the only track-specific prose in the file;
- the harness commands, if the new problem is checked differently;
- the `THIS HOST` block, which describes this machine (WSL, the harness interpreter, Docker) and is
  wrong anywhere else.

Keep the limits explicit and fixed before dispatch: we used 5 repair cycles per stage, 2
infrastructure retries per command, 360 minutes per stage and 1440 in total. The run used 254.

## Things that will happen and are not faults

- **Receivers expire every 30 minutes.** The host caps background watchers at 1800 s. Seats re-arm
  on the same lease; the room shows it as a steady trickle of tool calls.
- **Memory runs short.** With four seats and their containers running, free memory on the host fell to
  3.5 GB of 31.6, and the operator's own monitoring shell was stopped by Claude Code for lack of memory.
  The band itself was unaffected, but leave headroom.
- **We never ran two bands on one host at once**, and would not: the auditor's timing and
  concurrency probes assume the machine is theirs.
