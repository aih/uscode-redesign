# Build Log

Session-by-session record of how this site was built. One entry per working session, written at the end of that session while context is fresh. Format:

```
## NNN — YYYY-MM-DD — <short title>
- Tool/model:
- Asked: <what the human directed>
- Decided: <key decisions; link ADRs>
- Produced: <commits / files>
- Verified: <what was checked, and how to re-check it>
```

---

## 001 — 2026-07-27 — Research & planning (pre-build)

- **Tool/model:** Claude (Cowork), Fable 5.
- **Asked:** Research USLM structure and uscode.house.gov release points; design a plan for a versioned US Code retrieval site (FastAPI + Postgres, later XCiteDB); specify agent/model orchestration, required accounts, and a documentation regime.
- **Decided:**
  - Sections are the storage atom; sub-section provisions extracted at request time (ADR-0001).
  - Schema-plural parser layer for USLM 1.x and 2.x (ADR-0002).
  - GUIDs treated as globally unique (provision, release point) pins; `@identifier` is the cross-release identity (ADR-0003).
  - Reuse dreamproit/loadusc-xcitedb for release-point download inventory and the future XCiteDB path.
  - Mine dreamproit/versions (older XCiteDB-based USC site) for the temporal diff algorithm and display insights (PLAN §1; GETTING-STARTED Session 1.5).
- **Produced:** PLAN.md, GETTING-STARTED.md, README.md, this file, docs/adr/0001–0003.
- **Verified:**
  - `id0b32dff7-810c-11f1-b7ce-bdea3d14cbdd` ↔ `/us/usc/t16/s45f/c/5` confirmed by grep of usc16.xml.
  - Title 16 counts from source XML: 5,393 sections; 523 repealed / 102 omitted / 19 transferred / 1 reserved.
  - Current release point 119-102not101 and download URL scheme confirmed live at uscode.house.gov/download/download.shtml (2026-07-27).
  - ~324 prior release points, back to the 113th Congress, per priorreleasepoints.htm; compound skip labels observed (e.g. `277not255not268`).
  - USLM 2.x sample location confirmed: https://uscode.house.gov/currency/uscinuslmv2samples.zip.
