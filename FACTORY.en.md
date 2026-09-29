# Four seats that refuse to take each other's word

*[Leer en español](FACTORY.md)*

A software factory built on BAND Desktop. Four agent seats in one room: one decides what the work
is, one builds it, one tries to break it, and one reproduces everything before anything is
accepted. No seat accepts its own work, and a claim never moves an artefact — a reproduction does.

One human message exists in the whole room. It authorised four stages and said nothing after that.

## What it produced

| | |
|---|---|
| Stages delivered | **4 of 4**, each frozen and independently audited |
| Public harness, `--all --mode isolated`, fresh clone | **every folder claims its own stage, 100% of its checks, no overshoot** |
| Rejections by the auditor | **2**, both repaired and re-audited inside the run |
| Human messages in the room | **1** |
| Wall-clock, dispatch to final report | **4 h 14 min** |
| Model spend, list prices | **~$136** |

```
stage-1 -> claims 1   share 1.0   overshoot null
stage-2 -> claims 2   share 1.0   overshoot null
stage-3 -> claims 3   share 1.0   overshoot null
stage-4 -> claims 4   share 1.0   overshoot null
```

`share 1.0` is every check of that stage. `overshoot null` is the freeze rule holding: no folder
passes a later stage's suite, so each one is the solution to its own stage and not a later one.

## The seats

| Seat | Owns | Writes | Cannot decide |
|---|---|---|---|
| analyst | coverage, coordination, limits | obligations, decisions, evidence index | whether the product is accepted |
| implementer | implementation and packaging | production code, Dockerfile, RUN.md, its own tests | whether its own work is good |
| adversary | independent challenge | its own test suites and failure reports | production fixes, or release |
| auditor | reproduction and integrity | audit records and verdicts | it may not change product or tests to make them pass |

The roster for this run:

| Visible name | @handle | Band agent id | Harness | Model |
|---|---|---|---|---|
| analyst | hugo.valer/analyst-thgs | fd5095ef-bafa-4039-b597-3f160b75cf21 | Claude Code | claude-opus-5 |
| implementer | hugo.valer/implementer-thgt | 156a2fed-f92e-4453-8e6c-75ecdb48ef20 | Claude Code | claude-opus-5 |
| adversary | hugo.valer/adversary-thgz | f603ac21-88ea-434a-844e-bb621f8da63e | Claude Code | claude-opus-5 |
| auditor | hugo.valer/auditor-thgx | f6bf20d6-c769-4d36-bb79-47d5e384287a | Claude Code | claude-opus-5 |

Visible name, @handle and agent id are three different things. The mandates address each other by
the second and the room records the third. Nothing in `mandates/` names a payment, a screen, an
endpoint or this track: point the factory at a different problem by changing the dispatch, and no
mandate needs editing.

## Why it catches things

Four filters, in order, and each one is owned by a seat that does not own the previous.

1. **The obligation register comes before the code.** The analyst turns every specification section
   into numbered obligations with source references and an acceptance method. The adversary
   challenges that register for omissions *before* implementation is accepted. On stage 2 it filed
   twenty coverage objections before a line was written.
2. **A candidate is frozen at a commit.** The implementer publishes a full commit id and stops
   touching it. Reviewers never read a working tree.
3. **The adversary verifies from its own clean clone**, with its own test suites, versioned in
   `verification/adversary/stage-N/`, and hands over a bundle that includes an explicit list of what
   it did **not** test.
4. **The auditor reproduces everything itself** in a fresh clone, with its own `--no-cache` images
   and its own containers, and only then decides. Copying someone else's report is not reproduction.

The rule that makes this more than ceremony: **a green check set is not evidence that a requirement
holds.** Under this dispatch a specification row with no evidence stays open even when every public
test passes. The analyst had to say so out loud during stage 1:

> Some items on your "untested" list are spec rows, not decisions. Under the dispatch they count as
> open until evidence exists, even though every public test passes.

## The two rejections

Both were found by the auditor's own probes, on candidates where the official harness had already
passed. That is the whole argument for this design, so here it is in full.

### Stage 3 — the service died and every suite was green

`F3-A01`. Under sustained statement reads the process **crashed with a V8 heap out-of-memory**.
With 500 payments of history it died after **4,761 reads**, exit 139, and lost all state. Memory
was never released.

What that same candidate had already passed, all reproduced by the auditor in fresh containers:

| Check | Result |
|---|---|
| Official harness `--stage 3`, host **and isolated** | 147 + 35 + 6, **0 skipped** |
| Stage-1 and stage-2 regression on `stage-3/`, API and UI at 375 px and 1280 px | **150/150** |
| Stage-3 probe with hand-computed history | 33/33 |
| Upgrades 1 to 3 and 2 to 3 in fresh containers | 14/14 |

Everything green, and the service could not survive being used. The shipped suite never read enough
statements to find out. A second defect rode along in the same verdict: `F3-01`, a closed hold seen
through an earlier `known_at` never expired at its deadline — `held` stayed at 1000 at
`expires_at` + 1 ms, and still at the year 2099.

The repair was routed with the obligation it broke, rebuilt, and re-audited against a new commit.
`stage-3/test/perf/statement_memory.js` exists because of this.

### Stage 2 — small, and it still blocked

`F2-01`. A refused capture did not keep the amount the user had typed: prefill `20.00`, typed
`25.00`, refusal shown, and the field silently reset to `20.00`. No money moved; severity low. The
analyst had ruled that the register row binds, so the candidate could not be accepted with it open.

We record it because the interesting part is what did **not** happen: nobody argued the severity
down in order to ship on time.

## What it cost

Estimated at provider list prices from runtime token counts. **This is not a bill**, and BAND's
attribution is not stable across restarts, so treat it as an order of magnitude.

| Seat | Tokens | Estimate |
|---|---|---|
| auditor | 130,989,459 | $38.50 |
| adversary | 125,995,041 | $38.30 |
| implementer | 107,065,994 | $32.81 |
| analyst | 92,935,707 | $26.31 |
| **Total** | **456,986,201** | **~$136** |

The spend is almost flat across the four seats, and the two verification seats together cost more
than the builder. That is the design showing up in the bill: most of the money goes into deciding
whether the work holds, not into producing it.

No hard provider cap was configured, so no financial ceiling could be enforced during the run. The
enforceable limits were wall-clock: 360 minutes per stage and 1440 in total. The run used 254.

## Timeline

All times UTC, 2026-09-28 into 2026-09-29.

| | |
|---|---|
| 20:40 | Dispatch. One message, four stages authorised |
| 21:35 | Stage 1 **ACCEPTED**, no repair cycle |
| 21:39 | Analyst opens stage 2 by itself, 10-part handoff, no human input |
| 22:22 | Stage 2 candidate 1 **REJECTED** (`F2-01`) |
| 22:45 | Stage 2 **ACCEPTED**, upgrade 1 to 2 verified |
| 23:41 | Stage 3 candidate 1 **REJECTED** (`F3-A01` heap OOM, and `F3-01`) |
| 00:07 | Stage 3 **ACCEPTED**, upgrades 1 to 3 and 2 to 3 |
| 00:42 | Stage 4 **ACCEPTED**, upgrades 1 to 4, 2 to 4, 3 to 4 |
| 00:54 | All-stage verification **PASS** on a fresh clone; analyst final report |
| 00:55 | Auditor verifies the final report independently |

Four minutes between accepting a stage and dispatching the next, every time, with nobody watching.

## Standing it up

1. Create a room every seat can read and write.
2. **Grant every permission a mandate obliges a seat to use, before the first task.** A seat that
   must start a container and has to ask is a seat stopped in front of a dialog nobody is watching,
   and a permission granted mid-run is a second human input in a run that is supposed to have one.
3. Give each session one file from `mandates/` and nothing else about the problem. Name the session
   after its seat, so every message is attributable in the export.
4. **Tell each seat how to speak in the room.** This is the step we got wrong, and it cost a round
   trip: the mandates require directed handoffs to a resolved `@handle`, but nothing in them says
   that a seat's own window is not the room. Two of the four answered in their windows and waited to
   be told to adopt the mandate. A room whose seats reply in their own windows exports as tool calls
   and no conversation.
5. Confirm from **outside** the sessions that every seat both writes and reads, before dispatching.
   Writing is proved by a message of its own in the room; reading by a drained queue.
6. Dispatch once. Then do nothing.

### What we would tell the next team

**The 30-minute receiver is a host limit, not a mistake.** Our mandates ask for a receiver armed
persistently with no timeout. On this host the background-task classifier caps a watcher at 1800
seconds, so every seat re-arms every half hour for as long as it lives. The seats handled it
correctly and said so:

> The mandate asks for a receiver with no timeout, but this host stops a watcher after 30 minutes at
> most. I'll restart it with the same lease each time it expires.

Write the mandate to expect that, rather than to forbid it.

**Put the permissions file where the seats actually work.** Ours sat one directory below their
working directory and did nothing at all until it was moved.

**Deny a few things explicitly.** An agent holding a shell for twelve unattended hours should not be
able to delete its own identity, release its room lease, push to a remote or prune Docker. Those are
four lines and they cost nothing.

## Honest limits

**Two rejections is not many.** They are real and both were reproduced, but we cannot tell from
inside the run whether a third defect exists that all four filters missed. The auditor's own probes
found both, which means the ceiling of this design is the imagination of one seat.

**One run is one data point.** Nothing here shows the factory is repeatable at this speed against a
different specification, and this specification was published by the organisers, so a model may have
had a head start on the domain.

**The auditor does not run mutation, and we know what that costs.** A stronger gate would, for each
criterion, break the behaviour that criterion describes in a private copy and confirm the mapped
check is the one that fails. This factory reproduces instead. Reproduction caught a heap crash that
every suite missed, so it is not nothing — but a check that passes against deliberately broken code
would still look fine here.

This is not a hypothesis. Before this run we operated **another band of ours**, also four seats, in
which the verifier did mutate: for each criterion it deliberately broke the behaviour described and
required the mapped check to be the one that failed. Across three stages it produced **thirteen
rejections, and not one was a fault in the service**. All thirteen were check sets that ran green and
did not test what they claimed. Three of them, because the pattern matters more than the anecdote:

- A contrast meter that did not composite `opacity` down the tree, so text at 1.8:1 passed as
  legible.
- A load harness whose `except` caught only `HTTPError`, so forty-three unanswered requests left no
  trace and the summary read `slow_responses: 0`.
- An idempotency key built from the parsed amount, so `"15.00"` and `"15"` collided and the retry
  moved no money.

Reproduction would have found none of them: all three checks ran, finished, and reported that
everything was fine. Breaking the behaviour was what revealed that the check was not holding it. That
is the step this factory is missing, and it is where we would extend it first: mutate the criteria a
delivery **adds**, not the whole accumulated set, and let the auditor's full reproduction stay as the
regression gate.

**Cost figures are estimates**, from token counts at list prices, and BAND's per-agent attribution
moves across restarts. They are honest to an order of magnitude and no further.
