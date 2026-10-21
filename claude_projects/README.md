# HYPOLAB's idea team on Claude Projects (agent pack v3, HYPOLAB 1.10.3)

The "agents" are Claude chats with fixed instructions, not programs. Three Claude Projects and one scheduled task;
a fifth Project, the HYPOLAB hub where the code is built and the quarter is planned, is set up from
`0_hypolab_project.md`. They cannot see HYPOLAB or each other: **you carry the messages**, and every message has a
fixed format (`HANDOFF_CONTRACTS.md`) so it pastes straight into the next chat or into the Ideas app. HYPOLAB never
calls an AI.

| Project | Role | Instructions | Knowledge files to upload |
|---|---|---|---|
| HYPOLAB - Scout & Writer | Enki: BRIEFs and SHORTLISTs from BRAIN pages; hypothesis cards from sources, briefs and leads | `1_scout_writer.md` | 01, 02, 03, 04, 05, 06, 07, 08, 09, 10, `HANDOFF_CONTRACTS.md`, `briefs.md`, your BRAIN pages |
| HYPOLAB - Critic | Shamash: attacks checked cards it did not write | `2_critic.md` | 01, 02, 03, 04, 06, 07, 09, 10, `HANDOFF_CONTRACTS.md`, `briefs.md` |
| HYPOLAB - Weekly Reviewer | Weekly Strategist: reads the week's DIGEST, writes next week's PLAN | `3_weekly_reviewer.md` | 04, 05, 06, 07, 08, 09, `HANDOFF_CONTRACTS.md` |

The numbered files are in `knowledge/` (generated: rebuild them, don't edit them). `knowledge/INDEX.md` says which
file goes where and, after each rebuild, which files changed. `briefs.md` is a file you keep.

Plus the **daily alpha brief**, a scheduled task at 17:55 Nairobi on weekdays: its instructions are in
`daily_brief_prompt.md`. It reads only the "HYPOLAB state" doc, which since 1.10.3 carries everything a card needs to
import (concept names, operators, the theme's priority datasets, lessons, dead ends, card ids in use).

## Setting up (claude.ai)
1. Scout & Writer: paste `1_scout_writer.md` below `--- paste from here ---` into the existing project's
   instructions and upload its files. **Archive the old "HYPOLAB - BRAIN Library" project** - Scout & Writer now
   writes BRIEFs and SHORTLISTs (one fewer hand-off).
2. Critic and Weekly Reviewer: paste their new instructions; upload their files.
3. The scheduled task: replace its instructions with the text in `daily_brief_prompt.md`.
4. Keep the projects private: BRAIN material may be confidential under your consultant agreement.

## The loops
1. **Ideas (daily).** Source -> Scout & Writer -> CARD -> Ideas app **Drafts > Import** (pick the dry-run region; it
   defaults to this week's plan region) -> HYPOLAB checks and binds it. Errors: back to Scout & Writer with them.
   `checked` and you are unsure: **Copy for the Critic** -> Critic -> VERDICT -> paste it on the draft. `rewrite`:
   give the fixes to Scout & Writer, import the result with **This is a rewrite** ticked. Same tick when Scout & Writer
   finishes a draft HYPOLAB made itself (Leads > Make a draft). Then **Approve** ->
   **Cards > Send to the Lab** -> rung 1 in the cockpit. Sources: a SOURCE block from **Leads > From outside**, a
   BRIEF, a lead, or a paper. Most sources should give no card.
2. **The daily brief (weekdays).** Import its card the same way (no tick: its id is new every day).
3. **BRAIN reading (when you read something).** Upload the page to Scout & Writer, say `brief` (or `shortlist` for a
   Data > Datasets listing), keep the useful BRIEFs in `briefs.md`, re-upload it to Scout & Writer and the Critic.
4. **Friday.** Cockpit > Account download -> Ideas > Week: copy the **DIGEST** into the Weekly Reviewer -> paste its
   **PLAN** on the Week page (its lessons and dead ends now reach the knowledge pack and the state doc) -> **Rebuild
   the knowledge pack** (Drafts page) -> re-upload the files INDEX.md lists as changed -> paste the Week page's
   **Text for the HYPOLAB state doc** into the state doc.
5. **SuperAlphas** (after 100 lifetime alphas): built in the cockpit's SuperAlpha tab from fixed recipes. No chat
   writes selection or combo code.

## Measuring whether the team helps
After a few weeks of live results, the Leads page and the DIGEST answer two questions. **Source quality**: do the
daily brief's and the writer's cards reach NEAR or PASS as often as the built-in ones? **Critic decisions vs
results**: do `keep` cards do better than cards nobody reviewed? If not, cut that step: each one costs your time and
your Claude Pro usage.

## What stays outside the chats
Field ids, simulations, the gate, SuperAlphas and submissions stay in HYPOLAB. The chats write hypotheses, never
expressions bound to fields, and never decide to submit.
