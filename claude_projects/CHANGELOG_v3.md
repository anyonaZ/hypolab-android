# Agent pack v3 (with HYPOLAB 1.10.3) - what changed from v2

v2 was a prompt-only revision. v3 changes the prompts and HYPOLAB's paste boxes together, because the chats' output
is only checked when it enters HYPOLAB.

## Fewer hand-offs
- Three Projects instead of four: the BRAIN Library merged into Scout & Writer. No BRIEF paste between chats, and no
  BRIEF id register (ids are `B-YYYYMMDD-HHMM`).
- The Critic is used only on `checked` cards you are unsure about.
- The daily brief writes 1 card a day (was 3) for the first live weeks; one sentence in its prompt changes it back.
- The daily brief reads only the state doc, which now carries the concept names, operators, priority datasets,
  lessons, dead ends and every card id in use.

## Rules v2 had dropped, restored
- Scout & Writer: Power Pool / 2-category shape, `ts_backfill`, peer comparison, horizon 1-120 days, Region
  Agnostic preference, `08_my_operator_usage.md`, published predictors lose about a third, lead drafts keep their id
  and `# from: inbox: ...` line.
- Critic: the same shape checks and the `known_factor_in_disguise` names.
- Daily brief: ids `IE_<MMDD>_...`, outside-source row N on weekday N, at most one idea from the journal's Leads.

## Source attribution
- `# from:` conventions per writer (HANDOFF_CONTRACTS.md): `scout: <title>` (was a bare title, counted as "your own
  cards"); `daily brief <date> via S-...` (was `S-...` alone, which hid the daily brief inside "outside: ...").
- NO CARD never goes inside the YAML block and never has a `# from:` line.
- SHORTLIST labels are `L-...` (an `S-...` label looks like a collector source id).

## Packaging
- Lives in the HYPOLAB zip (`claude_projects/`), with the README table the tests check. The generated knowledge files
  are not copied into the pack: take them from `claude_projects/knowledge/` after **Rebuild the knowledge pack**.
- `HANDOFF_CONTRACTS.md` and `briefs.md` are listed in `knowledge/INDEX.md`.
