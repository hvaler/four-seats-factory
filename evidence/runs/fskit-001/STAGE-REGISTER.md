# Stage register — fskit-001

Run: fskit-001 · Target: stage 4 · Single dispatch: room 83139981-6931-481f-b8a4-d6f6ca9d41eb, message 3f95ab60-b690-489a-9370-80830f518f3f (enqueued 2026-09-28T20:40:47Z) · Kickoff: C:\nexus\dev\dark-factory-wearedevs @ 803560d2a678ace1414465c098eb0ab5380ffade

Spec checksums (SHA-256, read at the start of stage 1):

- stage-1.md 65497dea09a8b432598c71662320cf66c3550e183cfd76e2d7f97318e0d30aa4
- stage-2.md 39aaf9d7743c6fd831663e5b8363866f7d70795e5efb9000c2803f471397b13f
- stage-3.md 2255d3f2181c22dc6eac6919bf7712197d812248bd9de8a7e59260ede6056e54
- stage-4.md 1894b002f8827fd36623df4ecf3deb204e20d7fafbbfa671894a114db80e6df1

Limits (fixed before dispatch): 5 repair cycles per stage · 2 infrastructure retries per command · 360 min per stage · 1440 min total, including a 30 min final-verification reserve · no financial cap is available; cost is measured afterwards from token counts.
Total deadline: 2026-09-29T20:40:47Z. Stop new work at 2026-09-29T20:10:47Z.

| Stage | State | Candidate commit | stage-N tree | Auditor decision | Specs/suites | Isolated report | Upgrades | Time / usage | Room checkpoint |
|---|---|---|---|---|---|---|---|---|---|
| 1 | ACTIVE since 2026-09-28T20:40:47Z (deadline 2026-09-29T02:40:47Z) | | | | 1 | | same stage | | |
| 2 | NOT_STARTED | | | | 1–2 | | 1→2 | | |
| 3 | NOT_STARTED | | | | 1–3 | | 1→3, 2→3 | | |
| 4 | NOT_STARTED | | | | 1–4 | | 1→4, 2→4, 3→4 | | |

## Event log (append only)

- 2026-09-28T20:40:47Z dispatch received; analyst acknowledged it in the room (af21ebd8-fb14-4780-ab24-22478d19f269).
- 2026-09-28T20:41Z the pinned kickoff commit was verified; the participant guide and stage-1 spec were read.
- 2026-09-28 stage-1 obligation register r1 was published for the adversary challenge.
- Note: the checksums above are for the CRLF working-tree files of the Windows kickoff checkout. LF-normalised SHA-256 / git blob at 803560d2: stage-1 f5e4c644076cf5b480c072bc17a966f3b3e229272c44b301d333763be2c438a6 / dd44280488c44a920dbba08b3ce6e8f6ffe9e45a · stage-2 699fcdd4b410754242945dde50e15d3470160d11b43b84314c042ed26317af12 / bc4acc5a5e8c5af04ccd8540e2005625854fa1b7 · stage-3 70a428536fdc834dc77538ed78168dfd448d2000c91fa2c002e2d7cfd98ebf94 / db2dbabc57fb4fe2ec9255b7fe1f2f37d15d6d59 · stage-4 ff79140fc43818909ee473cd24488604f245b3ce480d04c1862f359dde8e9a48 / 19e76a0372e8ca83dbb817368876ae6dd057a8a0.
- 2026-09-28 stage-1 handoff sent directly to implementer-thgt, adversary-thgz and auditor-thgx as 7 numbered parts: 191ed446-0e0a-4b05-b33a-82fb5211dc34 (1), 1f740beb-6ff8-4355-9622-a390d8491f64 (2), a9d6ba20-6584-4e5e-9779-628f32b44a94 (3), 4c9ec229-6fe1-457b-a086-b3e30f1eb77f (4), 5082e5e5-fe00-4be9-959c-9c33b3ade424 (5), af0d34ed-2f0b-467f-a89d-3368bfd366fc (6), f58d69a0-91e2-4814-9f14-8eafaa9f142a (7). Register r1 is at analyst commit 23698fb530c35327a8916f933f8fa77ae6e56055. Waiting for acknowledgement of all 7 parts from each seat.
- 2026-09-28T21:03:44Z register r2 (8e913edb) acknowledged by all three seats (auditor 70f9a20a, implementer e4e00687, adversary 1205c544). The adversary's independent suite v1 is at adversary@40d6c304aa0d38d2216885fe1c5226cb01a67727 (tree 194d8f7d, 301 tests; message 2f20701d). The auditor's probe tool is at auditor@0ed8f44. Waiting for the implementer's candidate.
