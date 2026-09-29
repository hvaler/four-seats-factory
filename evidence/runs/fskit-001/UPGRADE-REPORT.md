# Upgrade report: fskit-001 (analyst index; the authoritative records are linked)

Six source→target pairs are required: 1→2, 1→3, 2→3, 1→4, 2→4, 3→4. Each row points to the auditor's own reproduction; the adversary's runs are corroborating evidence.

| Pair | Source (commit / stage tree) | Target (commit / stage tree) | Verifier (adversary) | Reproducer (auditor) | Result | Records |
|---|---|---|---|---|---|---|
| 1→2 | beeaec72 / stage-1 347efba5 | 68583038 / stage-2 a8e6178d | adversary@4abc62a9 BUNDLE-c2 (XC 1→2 in both D2-18 shapes, D2-13 byte-identical replays) | auditor@fa5f5186 UPGRADE-1to2.md (fresh containers; populated stage-1 export; receipts byte-identical; browser session continuity; lost pay recovered with money moved once; pending request paid from /requests) | PASS | verdict 4ced8436 |
| 1→3 | beeaec72 / stage-1 347efba5 | 51a0bdd1 / stage-3 f586c499 | adversary@6bbed1a3 BUNDLE-c2 (XC 1→3) | auditor@b8b5a9dd UPGRADE-1to3-2to3.md (fresh containers; byte-identical receipts; history, corrections, linked 422s) | PASS | verdict 11dbc577 |
| 2→3 | 68583038 / stage-2 a8e6178d | 51a0bdd1 / stage-3 f586c499 | adversary@6bbed1a3 BUNDLE-c2 (XC 2→3, D3-18) | auditor@b8b5a9dd UPGRADE-1to3-2to3.md (holds imported and capturable; D3-18 void at the import; history) | PASS | verdict 11dbc577 |
| 1→4 | | | | | NOT_RUN | |
| 2→4 | | | | | NOT_RUN | |
| 3→4 | | | | | NOT_RUN | |

Snapshot contents and credentials are never stored here or in the room; the records hold only checksums and booleans.
