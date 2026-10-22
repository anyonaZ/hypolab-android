# HYPOLAB handoff - read this first in a new chat

State on 2026-10-22: **HYPOLAB 1.14.0 = 1.13.0 + Android phase C2: Journal, Pyramids and SuperAlpha as web
pages** (`ideaweb/records.py`; templates `journal.html`, `pyramids.html`, `superalpha.html`), shared by the laptop
and the tablet, plus a threading fix (the field catalog's SQLite connection now works from the web app's job
threads). 1.13.0 (C1) brought the Lab, Play and Quant basics. The marimo cockpit is still needed on the laptop only
for Account, Data and Setup (phase C3). **367 tests pass.** Code: private repo `anyonaZ/hypolab-android`; GitHub
Actions builds the signed APK. See "Android track" below.

Before that: 1.12.x (22 Oct) Android phase B, the Ideas app on the tablet + the app icon; 1.11.0 phase A (spike) and
no scipy.

Before that: 1.12.x (22 Oct) Android phase B, the Ideas app on the tablet + the app icon; 1.11.0 phase A (spike) and
no scipy.

Before that, 1.11.0 (22 Oct): Android phase A (the feasibility spike, passed on the tablet) and no scipy
(`hypolab/_stats.py`, matched to scipy in `tests/test_stats_noscipy.py`).

Before that, 2026-10-20 (night): **HYPOLAB 1.10.3 = 1.10.2 + the idea team's paste boxes and agent pack v3.** A review
of Zacc's agent pack v2 (prompts only) against the code found that the chats' output is only checked where it is
pasted into HYPOLAB, and that those boxes lost data silently: `# from:` lines were matched to cards by count (a missing
one or a "no card" slot shifted every source), an import overwrote a waiting draft with the same id (and un-binned a
binned one), a rewrite lost its source and kept the old verdict, a PLAN's universe/delay vanished, and the Weekly
Reviewer's lessons and dead ends never reached the Writer or the Critic. All fixed; the pack is now v3 (three
Projects: Library merged into Scout & Writer; the daily brief writes 1 card a day). See "1.10.3: the paste boxes and
agent pack v3" below; regressions in `tests/test_review_1103.py`.

Before that, 1.10.2 (evening): **HYPOLAB 1.10.2 = 1.10.1 + three safety fixes Zacc reported** - the submission gate
could be bypassed (submit() did not check `gate.ready`), missing evidence (no checks, no correlation, no deflated
Sharpe) could leave a gate READY, and POSTs (simulations, submissions) were retried after a lost answer. All fixed to
fail closed; see "Safety fixes (1.10.2)" below and HOW_IT_WORKS section 21.

Before that: **HYPOLAB 1.10.1 = 1.10.0 + a whole-system review** (every file read again; settings keep only
your choices, one meaning of "tries", one lifetime count, SuperAlphas on the Week page and in the DIGEST, a sandbox
Pyramids crash, a faster Week page, a knowledge pack that names what changed, the Claude Projects' instructions synced,
and a plain-words **`docs/USER_GUIDE.md`**; see "Review of 20 Oct (1.10.1)"). 1.10.0 = 1.9.1 + phase 8, the
SuperAlpha builder (cockpit **SuperAlpha** tab; `hypolab/superalpha.py`; see "Phase 8" below). 1.9.1 = 1.9.0 + a
review of phase 7. 1.9.0 = 1.8.1 + phase 7, the collectors (Ideas app **Leads › From outside**). **The full suite
passes: 326 tests (1.10.3), run with `python tests/run_all.py`.** Phases 1-5, 7 and 8 are done; phase 6 (AI layer) stays covered
by the Claude Projects kit and the daily brief. **Next: the first live weeks** (nothing has run against the live BRAIN
API yet; SuperAlphas unlock at 100 lifetime alphas - live use waits for that), then the backlog below. A separate
track may start: **an Android app for the Galaxy Tab A9** (the hand-off prompt is in `docs/ANDROID_HANDOFF_PROMPT.md`).

Before 1.9.0: **HYPOLAB 1.8.1 = 1.8.0 + a full-code review** (every file read; 11 bugs and 6
inefficiencies fixed, regressions in `tests/test_review_181.py`; see "Review of 19 Oct (1.8.1)" below). 1.8.0 merged
two lines of work: Zacc's 1.6.0 (production correlation) and 1.7.0 (Ideas web app `ideaweb/` + marimo cockpit) from
one chat, and phase 4 (Friday review), the EUR-first plan and phase 5 (learning loop) built in another chat on the
1.5.0 zip and released there as "1.6.0-1.7.0" - so **both "1.6.0"s and both "1.7.0"s appear in the history below;
the sections say which is which.** 1.8.1 had 230 tests, incl. the apps smoke test and the Ideas app.

**1.8.1 (19 Oct): the review.** Bugs: delay 0 read as 1 in six places (`rules.delay_of`); a repeated dataset scan
re-simulated a different lens and lost fields; the robustness "liquid universe" test went the wrong way for EUR
TOP800 and counted blocked variants as failures; `BrainClient.simulate` returned mixed-universe results out of order;
a submission BRAIN refused was still recorded; Lower correlation broke multi-statement alphas; the cockpit's field
download skipped the insiders / institutions / short-interest / social-media categories; a moderately negative
Sharpe was diagnosed "climb the ladder" instead of "flip"; Pyramid counts ignored currency/split/adjfactor as grouping
fields; Leads offered "Send to the Lab" for ideas the Lab cannot open; goals never rolled to a new quarter.
Efficiency: settings.json and themes.json cached by mtime; the Cards ranking reads the journal once (was 5 queries
per card); robustness runs as one multi-simulation; the Lab's Pyramid counts cached 10 minutes; the Leads count
cached 30 s. Improvements: cards bind from another downloaded universe of the region (EUR TOP2500 list while TOP800
is the default) with a note; a theme's universe ends with the theme in long-running apps; the Ideas app refuses form
POSTs from other web sites.

**1.8.0 (19 Oct): the merge.** Engine changes from the second line (rules batch 5, follow/boost fixes, themes and EUR
priority datasets, `hypolab/learning.py`, `ideaengine/learn.py`, value-score ranking) sit next to 1.6.0's `decorr`
(the gate keeps BRAIN's correlation checks as the authority; the self-correlation exception now only lifts a `FAIL?`
that HYPOLAB read itself). UI: the phase 4 Week additions (what the week has to respect, the Friday checklist, the text
for the HYPOLAB state doc) and the phase 5 learning loop live in the **Ideas web app** (Week page; new **Leads**
page), not in marimo, following 1.7.0's rule. The cockpit keeps the Data tab's value-score sort. Learning counts
`decorr` tries like the gate does; the learning digest lists families with measured production correlation >= 0.7.

**EUR first (second line "1.6.1"/"1.6.2", Zacc's decision 19 Oct)** while the EUR/D1 TOP800 theme runs (to 8 Nov):
STARTING_PLAN W43 EUR analyst+model, W44 EUR fundamental+analyst, W45 EUR model+pv+risk, then W46-W47 USA, W48-W49
GLB. `config.apply_themes()` makes TOP800 EUR's default universe during the theme (`follow_themes: false` turns it
off). `data/themes.json` holds his 42 priority datasets from both pages of BRAIN's EUR theme page (value >= 3 plus the
AI sets, AI Equity Alpha Forecasts first, Deep Learning Price Signal Dataset second; ids from the GLB catalog where the
names match, else null; same-name datasets kept apart as "(2nd listing)"); cards on them rank higher (+1.25, AI +1.5).
List: `docs/eur_theme_priority_datasets.md`.

Outside the zip (2026-10-19):
- **Daily alpha brief** (1.10.3: its new instructions are `claude_projects/daily_brief_prompt.md` - 1 card a day,
  same id / row / lead rules; until Zacc pastes them, the old prompt below runs): a scheduled task, weekdays 17:55
  Nairobi, writes 3 ideas as pasteable HYPOLAB cards
  (`# from: daily brief <date>`, ids `IE_<MMDD>_...`) after reading the state doc. Until 8 Nov at least 2 of 3 are
  EUR D1 TOP800 on the priority datasets; one idea a day may build on a "Leads from the journal" row ([LEAD]).
- **HYPOLAB state doc** (Claude Docs): https://claude.ai/code/artifact/edd2818c-6d1d-45b5-ac48-c32324a9c8ff -
  goals, this week's PLAN, Pyramid counts, retry / near misses / dead ends, Leads, card ids used. Refresh it every
  Friday from the Ideas Week page's "Text for the HYPOLAB state doc".
- The chat lives in the claude.ai Project HYPOLAB-IDEAS; its instructions are `claude_projects/0_hypolab_project.md`.

**1.9.1 (20 Oct): the phase 7 review.** The inbox mixes kinds (the 212 published predictors filled every top slot;
a new paper ranked ~145th); the state doc's "Fresh outside sources" rows are numbered 1-5, mixed, without news, and
the brief uses row N on weekday N; news themes leave the new list after 14 days and can be muted (rates/inflation
muted by default); two European feeds; feeds decoded from bytes; downloads in a worker thread; used datasets retire;
one item per dataset (D1 first); dataset drafts checked in their own region; counts and the menu badge match the
list (badge is a database count); `S-...` ids match in any case; "same paper as" refreshes when the library changes.
Also removed a time bomb: two phase 7 tests depended on today's date. Tests: `tests/test_review_191.py` (16).

**1.9.0 (20 Oct): phase 7, the collectors.** `ideaengine/collectors.py` (read + fetch: OSAP's bundled signal list,
arXiv API, RSS feeds grouped into 16 weekly news themes, under-used datasets from your field lists),
`ideaengine/sources.py` (the inbox in `ideas.sqlite`: tags, covered-by-a-card check, ranking for the plan, SOURCE
block for Scout & Writer, skeleton drafts, digest and state-doc rows), `ideaengine/collect.py` (CLI; also
`python -m hypolab collect ...`). Ideas app: **Leads** has two tabs, *From your journal* and *From outside*.
Source quality gains "outside: ..." buckets; the DIGEST, state-doc text ("Fresh outside sources") and knowledge pack
(`10_published_predictors.md`) carry the sources. Also fixed: a field BRAIN sends without a description crashed the
catalog's enrichment (`Catalog.fields`). Tests: `tests/test_phase7.py` (19). marimo 0.25.2 also passes the smoke test.

## How to resume in a new chat
1. Attach the latest `hypolab-1.10.2.zip` (or newer) and say: "Continue HYPOLAB. Read HANDOFF.md first."
2. Claude should: unzip into a fresh folder, read this file, `docs/USER_GUIDE.md`, `docs/HOW_IT_WORKS.md` and
   `docs/BRAIN_RULES.md`, run `python tests/run_all.py` (all must pass before changing anything), then build.
3. The design rationale is in the doc "HYPOLAB Idea Engine - Design v2":
   https://claude.ai/code/artifact/90188b46-0f1a-4089-9da6-fb8304b38595
   This handoff as a doc (1.4.3 edition; this file is the current one): https://claude.ai/code/artifact/e920f43f-1ff3-4209-8df6-c82222e353e6
   Cheat sheet (updated for 1.10.1): https://claude.ai/code/artifact/37656bd4-b770-4e7c-b83e-83c57ae4eb28
   HYPOLAB state doc (the daily brief reads it): https://claude.ai/code/artifact/edd2818c-6d1d-45b5-ac48-c32324a9c8ff

## Who and what for
- Zacc: WorldQuant BRAIN research consultant, **Gold** level, new to quant, struggles to find alpha ideas.
- Laptop: Lenovo T470s, Arch Linux, KDE, CPU only. Only computer. Everything must stay light.
- AI available: **Claude Pro** subscription. No paid API key. Plan: Claude Code non-interactive (`claude -p
  --output-format json --json-schema ...`), with `ANTHROPIC_API_KEY` unset so it uses the Pro plan.
- Goal: **Expert by end of 2026-Q4** (Dec 31). Genius page on Oct 10: signals 1/20, Pyramids 0/10,
  combined alpha performance -0.01/0.5 (Master: 120 / 30 / 1.0). All three are counted **per quarter**.
  Tie-breakers: 2 operators/alpha, 2 fields/alpha, streak 5, community 0.7; the quarter's Streak Freeze is already used.
- Regions on his account: USA, GLB, EUR, ASI, CHN, JPN, AMR, IND, DEU, GBR (D0 in USA, EUR, CHN, JPN, AMR, DEU, GBR).
- Osmosis on Oct 10: only IND/D1, 12 alphas but 1,200,000 points (must be exactly 100,000 per scope) - invalid; he
  needs 3 scopes with >= 10 alphas. Last Sunday to lock a valid allocation for 6 weeks in Q4: **15 Nov**.
- Submissions: BRAIN expects up to **4 alphas + 1 SuperAlpha a day**. SuperAlphas unlock at **100 lifetime
  alphas**; Zacc had **58** on Oct 9 (42 to go). The planner treats 4/day as a ceiling, default 10/week.
- Settled: a Pyramid needs **3** submitted alphas (BRAIN's Genius documentation); "10" is the number of Pyramids
  Expert needs. `alphas_per_pyramid` = 3 is right.

## The system in one paragraph
**HYPOLAB** (`hypolab/`) tests ideas: hypothesis card -> bind roles to real fields -> lint (Gold operators) ->
simulate (BRAIN or offline sandbox) -> diagnose (PASS/NEAR/WEAK/NOISE/INVERTED + one next action) -> robustness ->
gate (platform checks, self/prod correlation, deflated Sharpe) -> typed-confirmation submit. Everything is
journaled. **Idea Engine** (`ideaengine/`) decides what is worth testing: goals, weekly plan, submission cap, the
Friday review and the learning loop (leads from the journal). Two kinds of screens: the **Ideas web app**
(`ideaweb/`, http://127.0.0.1:2719: Week, Leads, Cards, Drafts - never simulates) and the **marimo apps** (`apps/`,
http://127.0.0.1:2718: cockpit Lab / Pyramids / Play / SuperAlpha / Journal / Account / Data / Setup, dataset scan,
quant basics).
Around them: the **daily alpha brief** (a scheduled Claude task, weekdays 17:55 Nairobi) reads the **HYPOLAB state
doc** and writes 3 cards; Zacc imports them on Drafts. The four **Claude Projects** (Library, Scout & Writer, Critic,
Weekly Reviewer) plus the HYPOLAB-IDEAS project carry the AI side; HYPOLAB never calls an AI itself.

## The loops (how it is used)
- **Daily:** (1.9.0: `python -m hypolab collect news` or Leads › From outside › Fetch; one source -> Copy for Scout &
  Writer, most -> Skip) brief (17:55) -> Ideas > Drafts > Import -> checks + dry-run binding -> (Critic) -> Approve ->
  Ideas > Leads / Cards -> Send to the Lab -> cockpit Lab: rung 1 -> diagnosis -> ONE action (rung, flip, boost,
  Lower correlation) or stop (10 tries per idea) -> robustness -> gate -> Zacc types `SUBMIT <id>` (<= 4 a day).
  Once SuperAlphas unlock (100 lifetime alphas): cockpit SuperAlpha tab -> one recipe pair -> simulate -> ONE change
  per try (10 per pool per quarter) -> SuperAlpha gate -> `SUBMIT <id>` (1 a day, on top of the 4).
- **Friday:** cockpit > Account download -> Ideas > Week: update goals, Friday checklist, copy the DIGEST into the
  Weekly Reviewer, paste its PLAN back, copy "Text for the HYPOLAB state doc" into the state doc -> next week's
  briefs follow it. Rebuild the knowledge pack (Ideas > Drafts) and re-upload changed files to the Projects.
- **Per phase:** tests + smoke test, HANDOFF, version bump, knowledge pack, cheat sheet doc, zip, project docs.

## File map
| Path | What it is |
|---|---|
| `hypolab/research.py` | `Researcher`: ideas, card(id), test, follow, boost, decorrelate, scan, robustness, gate, submit, rerun, play, recover_pending |
| `hypolab/ideas.py` | Binding cards to fields (`build_card`, `data_universe` fallback), ranking (`_score` + `_journal_context`), data-first lenses (`explore_dataset`) |
| `hypolab/hypotheses.py`, `hypolab/library/hypotheses.yaml` | Card format + loader (built-in 47 + `~/.hypolab/library/*.yaml`, cached by mtime); `validate_library` |
| `hypolab/concepts.py` | ~82 economic concepts; field nature classifier; direction hints |
| `hypolab/catalog.py` | `catalog.sqlite`: datasets + fields per region/universe/delay, sync from BRAIN, concept search, disk cache |
| `hypolab/fastexpr.py`, `hypolab/linter.py`, `hypolab/operators.py` | FASTEXPR parser; linter (Gold + live operator list, arity, named params, vectors, groups, windows); operator registry |
| `hypolab/brain.py`, `hypolab/connect.py` | BRAIN API client (login in two steps, retries, multi-simulation, quota); mode switch, CLI/web login |
| `hypolab/diagnose.py` | Verdict + ONE next action per result (fitness arithmetic, checks, theme hints) |
| `hypolab/robustness.py`, `hypolab/overfit.py` | Robustness battery; noise bar, deflated Sharpe |
| `hypolab/decorr.py` | Correlation status (BRAIN check first), theme hints, crowding prior, decorrelation variants |
| `hypolab/rules.py` | BRAIN's numeric rules: single dataset, sub-universe, Fitness labels, BRAIN's day, Osmosis, Pyramid limit, Power Pool, themes, `delay_of` |
| `hypolab/superalpha.py` | Phase 8: SuperAlpha request, selection/combo recipes, checks, selection evaluator, pools + preview, unlock, diagnosis (Researcher: `super_test`, `super_gate`, `super_submit`, `practice_super_pool`) |
| `hypolab/learning.py` | Phase 5 facts from the journal: near misses, inverted, dead ends, scan candidates, check failures, transfers, card adjustments |
| `hypolab/journal.py` | `journal.sqlite` (tables below); WAL; `open_readonly()` |
| `hypolab/account.py`, `hypolab/pyramids.py` | Submitted alphas, operator audit, quarter Pyramids, Osmosis; PyramidTracker, tiers, guide datasets, multipliers |
| `hypolab/play.py`, `hypolab/playground.py` | Play tab (random cards / wild rolls); `mock.py` + `sandbox/` = the offline practice market |
| `hypolab/config.py`, `hypolab/theme.py`, `hypolab/__main__.py` | Settings (mtime-cached), REGION_DEFAULTS, sim options, `apply_themes`; chart palette; `python -m hypolab ...` |
| `ideaengine/planner.py` | ISO weeks, STARTING_PLAN (EUR W43-W45, USA W46-W47, GLB W48-W49), pace, submission cap, evidence, Friday checklist |
| `ideaengine/drafts.py` | Drafts table, form <-> card, `check_card`, approve to `my_cards.yaml`, VERDICT / DIGEST / PLAN, `state_text` |
| `ideaengine/learn.py` | Phase 5 actions: inbox items (Leads), sibling / scan drafts, source quality, learning digest |
| `ideaengine/collectors.py`, `sources.py`, `collect.py` | Phase 7: read/fetch OSAP, arXiv, news themes, datasets; the sources inbox (tags, covered-by, ranking, SOURCE block, skeleton draft); CLI |
| `ideaengine/store.py`, `views.py`, `handoff.py`, `connection.py` | `ideas.sqlite` goals/plans; tables for apps; Send to the Lab (`lab_inbox.json`); `open_researcher()` |
| `ideaengine/knowledge_pack.py` | Builds `claude_projects/knowledge/01-10` from code and live data |
| `ideaweb/` | Ideas web app: `app.py` (Starlette routes + origin guard), `state.py`, `templates/` (week, leads, sources, cards, drafts, editor), `static/` |
| `apps/cockpit.py`, `apps/dataset_scan.py`, `apps/quant_basics.py` | marimo apps (Lab first); `hypolab.css`, `head.html` (reconnect script) |
| `data/` | `catalog_GLB_MINVOL1M_D1.json.gz` (bundled field list), `pyramid_multipliers_2026Q4.json`, `themes.json` (EUR theme + 42 priority datasets), `osap_SignalDoc.csv.gz` + `OSAP_NOTICE.md` (OSAP signal list, GPL-2.0), `THIRD_PARTY_NOTICES.md` (Alpha Harness MIT notice for the SuperAlpha recipes; OSAP) |
| `docs/` | `USER_GUIDE.md` (every capability in plain words, 1.10.1), `BRAIN_RULES.md` (every rule + source + status), `HOW_IT_WORKS.md`, `LEARNING_PATH.md`, `AUDIT.md`, `eur_theme_priority_datasets.md`, `ANDROID_HANDOFF_PROMPT.md` (the prompt that starts the Android track) |
| `claude_projects/` | Instructions for the Projects (0 HYPOLAB, 1-4 team) + generated knowledge pack |
| `tests/` | One file per area (core, pipeline, connect, links, ideaengine, account, brain_rules, play, resume, bin_boost_speed, drafts, decorr, ideaweb, phase4, phase5, review_181, phase7, review_191, phase8, review_1101, review_1102, apps smoke test); `tests/run_all.py` runs each in its own process; `tests/fixtures/` (an arXiv Atom page, an RSS feed) |

## Files in `~/.hypolab/` (one writer each)
| File | Writer | Notes |
|---|---|---|
| `settings.json` | both | **only the keys you changed** (1.10.1; `_settings_version: 2`); defaults in `hypolab/config.py`, listed in `settings.defaults.json` (rewritten at each start) |
| `quota.json` | HYPOLAB | BRAIN's last X-Ratelimit headers (limit, remaining, reset) |
| `sim_options.json` | HYPOLAB | BRAIN's universes / delays / neutralizations per region (Account tab download) |
| `credentials.json`, `session.json` | HYPOLAB | mode 600; cookies only, never pickles |
| `catalog.sqlite` | HYPOLAB | field metadata per region; bundled GLB snapshot loaded on first live use |
| `journal.sqlite` | HYPOLAB | the memory; Idea Engine only reads it |
| `ideas.sqlite` | Idea Engine (Ideas web app, collectors) | goals, plans, drafts (1.5.0), inbox (1.8.0), sources + collector_runs (1.9.0), sources_meta (1.9.1) |
| `lab_inbox.json` | Ideas web app | the last card sent to the Lab (`lab_inbox_seen` in settings.json = picked up) |
| `operators.json` | HYPOLAB | BRAIN's live operator list (Account tab); merged into the linter's registry at import |
| `cache/*.pkl` | HYPOLAB | enriched fields + concept matches per region (rebuilt after a sync or a concept-rule change) |
| `play_last_roll_{sandbox,live}.json` | cockpit | the last Play roll |

Tables: `journal.sqlite` = ideas, experiments, submissions, lessons, binned, pending, account_alphas, correlations;
`ideas.sqlite` = goals, plans, drafts, inbox (Leads decisions), sources, collector_runs; `catalog.sqlite` = datasets, fields, sync_log.
| `library/*.yaml` | Idea Engine (on approval) | Zacc's own cards, loaded by HYPOLAB, `source = "mine"`; Approve appends to `my_cards.yaml` (atomic, previous kept as `my_cards.yaml.bak`) |

## Decisions already made (do not reopen without a reason)
1. **Ideas before expressions.** The AI may draft card text (story, mechanism, roles as concepts); it never
   chooses field ids (the binder does), never sends anything to BRAIN, never approves a card.
2. **No second card format and no second simulation log.** Drafts are HYPOLAB cards; the journal is the catalog.
3. **Trial budget is HYPOLAB's** `max_sims_per_idea` (10). The gate's deflated Sharpe counts every try.
4. Engine card ids start with `IE_`; a user card whose id clashes with a built-in one is skipped (built-in wins).
5. **Screens:** marimo for everything that simulates (every simulation behind a `run_button`); since 1.7.0 the
   idea side (forms, lists) is the Ideas web app. Never move simulations into the web app.
   Submit needs a READY gate, the typed `SUBMIT <alpha_id>`, and fewer than 4 submissions today.
6. Apps never block on `input()`: the Setup tab shows the face-scan link plus a button.
7. Sandbox uses an in-memory journal and an in-memory catalog (never touches the real files).
8. Plan (Zacc, 19 Oct): EUR first while the EUR/D1 TOP800 theme runs - W43 EUR Analyst+Model, W44 EUR
   Fundamental+Analyst, W45 EUR Model+PV+Risk - then W46-W47 USA and W48-W49 GLB (the ten tier-1 USA/GLB cells),
   before December (G8). The Weekly Reviewer's PLAN overrides any week.
9. Combined alpha performance is a Genius bar, so the system discourages filler submissions everywhere.
10. The learning loop only advises: it moves cards in the ranking and lists leads; it never simulates, drafts
    without a click, approves or bins. Its rules live in ONE place (`hypolab/learning.py`).
11. BRAIN's own checks are the authority on correlation; HYPOLAB's reading only blocks when BRAIN has not answered.

## Settings (`~/.hypolab/settings.json` holds only your changes; defaults in `hypolab/config.py`)
| Key | Default | Used for |
|---|---|---|
| `mode`, `live_region` | sandbox, USA | every app follows it (Setup tab / `python -m hypolab live USA`) |
| `account_regions` | USA GLB EUR ASI CHN JPN AMR IND DEU GBR | region pickers, Pyramid grid, Osmosis, transfers |
| `max_sims_per_idea` | 10 | trial budget per idea (tries = `learning.TRY_PURPOSES`: explore, boost, decorr) |
| `max_sims_per_day` | 500 | runaway guard only |
| `max_submissions_per_day`, `superalpha_unlock_after` | 4, 100 | submit refuses a 5th; SuperAlpha countdown and lock |
| `max_super_sims_per_pool` | 10 | SuperAlpha simulations per pool (region, delay) per quarter (1.10.0) |
| `gate_max_age_minutes` | 30 | a gate report older than this cannot submit (1.10.2) |
| `min_sharpe_d1/d0`, `min_fitness_d1/d0` | 1.58/2.69, 1.0/1.5 | fallback bars (BRAIN's limits in each result win) |
| `max_self_corr`, `max_prod_corr` | 0.7, 0.7 | HYPOLAB's own reading when BRAIN's check has not answered |
| `alphas_per_pyramid` | 3 | Pyramid filled |
| `scan_max_fields`, `concurrent_simulations`, `multi_sim_batch` | 40, 2, 5 | scans and multi-simulation |
| `session_ttl_seconds` | 900 | marimo keeps a disconnected session this long (~0.8 GB each) |
| `follow_themes` | true | false keeps a region's usual universe during a BRAIN theme |
| `ideas_port` | 2719 | Ideas web app port |
| `collector_feeds` | MarketWatch top stories, Nasdaq earnings, Yahoo Finance, Euronews business, City AM | RSS/Atom feeds the news collector reads (checked 20 Oct; a settings.json still holding 1.9.0's three gets the five) |
| `news_muted_themes` | rates_inflation | news themes the collector leaves out (Leads › From outside: Mute / Unmute) |
| `arxiv_categories` | q-fin.PM, q-fin.ST, q-fin.TR, q-fin.GN | arXiv categories the paper collector reads |
| `state_doc_url` | the HYPOLAB state doc | the Week page's link to the doc the daily brief reads (1.10.1) |
| `last_lab_card`, `lab_inbox_seen` | - | written by the apps (resume, Send to the Lab) |

## Open questions (collected; check on the first live weeks)
- Pyramids: does a 3-category alpha count in 2 cells or none (P1)? Genius showed 0/10 Pyramids while the diversity API
  had IND/D1/Model at 20 - are diversity counts all-time, or does a cell need the dataDiversity check too?
- Shapes not yet seen live: `/activities/pyramid-multipliers`, `/alphas/{id}/correlations/prod` table, Pyramid tags /
  Osmosis points in the alpha JSON, the Region Agnostic simulation payload (RA1).
- BRAIN rules in conflict: single-dataset cutoff 2.38 (docs) vs 1.58 (a live check, T1); D1 Sharpe bar 1.25 vs 1.58
  (T11); does the < 30% turnover factor 0.85 apply to the single-dataset cutoff (T2); does PROD correlation pass a
  clearly stronger alpha above 0.7 (C6); exact name of the ASI Japan check (T9); what a Cluster Alpha is (C4).
- DEU/GBR universe names and every region's risk sets (filled by the Account tab's options download).
- Learning loop: do the near-miss (NEAR or WEAK >= 1.0) and dead-end (5 tries) rules match what Zacc sees? Per-region
  dead ends instead of per-family? Ranking weights (value score +0.3/point, transfer +1.0, dead end -2.0)?
- Do the daily brief's cards beat the built-in ones (Leads > Source quality after ~a month)? If not, keep the AI for
  reading papers, not writing cards. Same question for the "outside: ..." buckets (1.9.0).
- Collectors (1.9.0), unchecked live: do the five default feeds still answer from the laptop (Yahoo's items looked a
  month old on 20 Oct; Euronews and City AM were checked through a web fetch only)? Does the arXiv relevance filter keep the right papers (tune `ARXIV_KEEP`/`ARXIV_DROP`)? Are the
  news themes useful, or noise? Concept tags on prose are heuristic (e.g. "analyst attention" -> news_volume).

## Known limitations
- No Region Agnostic or Python alpha simulations (not built; the RA payload is now documented by a community source,
  BRAIN_RULES SA9); Python alphas (3x in the EUR theme) are written by hand on BRAIN.
- SuperAlphas (1.10.0) are built from a community-documented request format (BRAIN_RULES SA2-SA7, "verify live"); the
  sandbox's SuperAlpha is an approximation (selection evaluated like BRAIN, HYPOLAB's own combo recipes recognised,
  anything else weighted equally) and its numbers are easy to pass - practise the steps, never judge recipes by them.
- Goals are entered by hand each quarter (the Week page warns when they belong to an old quarter); Pyramid counts come
  from the Account download (else the diversity API, all-time).
- The Weekly Reviewer's dead ends go to the journal as lessons and to the Week page, but the Cards ranking only uses
  dead ends measured in the journal.
- Boosting tests its candidates one by one (each needs its own result before the next decision).
- The sandbox has no risk sets, a 3-alpha production "pool" and an in-memory journal: correlation, resume and learning
  are really tested only live.
- The full self-test in ONE process peaks near 6 GB (282 tests on 20 Oct; `test_pipeline` alone ~2 GB). Since 1.10.1
  `python tests/run_all.py` runs each file in its own process (setup_arch.sh uses it); `unittest discover` still works
  on a machine with room.
- One user, one laptop: the Ideas app has no login (127.0.0.1 only; foreign-site POSTs refused since 1.8.1).

## Roadmap
- **Phase 6 (AI layer)**: mostly covered by the Claude Projects kit and the daily brief. Still possible: Claude Code
  `claude -p` behind buttons (P3 Critic on Approve first), with a cache - only if Zacc wants it automated.
- **Phase 7 (collectors)**: done in 1.9.0 (see below). Possible later: SSRN (no free API - added by hand for now), a
  timer that runs `python -m hypolab collect news` daily. The daily brief reads "Fresh outside sources" (Zacc added
  the [SOURCE] lines to its prompt on 20 Oct; 1.9.1's weekday-row rule is one sentence he pastes).
- **Phase 8 (SuperAlpha builder)**: done in 1.10.0 (see below); live use starts at 100 lifetime alphas. Possible
  later: read BRAIN's own selection/combo operator list once unlocked (an endpoint may list them), and a
  Region Agnostic simulation now that its request shape is documented (SA9).
- Backlog from the 1.8.1 review: use the Reviewer's dead ends in the ranking; batch boost candidates; per-region dead
  ends; show BRAIN's risk-handled / investability stats (S-5); PnL realization horizon check (H1-H2); Osmosis
  correlation pruning (O6); a Region Agnostic payload once its shape is known.

## Android track - phase A (1.11.0, 22 Oct)
Goal: HYPOLAB as a standalone Android app on Zacc's **Galaxy Tab A9 LTE, SM-X115, 4 GB RAM (3642 MB seen), Android 16
(API 36), arm64-v8a, 800 x 1340 screen**. The prompt is `docs/ANDROID_HANDOFF_PROMPT.md`.

Decisions taken with Zacc (21 Oct): the journal moves between devices with a **hand-over token** (one writer at a
time); the cockpit's tabs are ported to **Starlette pages that the desktop shares** (marimo stays on the desktop until
Zacc decides to drop it); the APK is built by **GitHub Actions** in the private repo (this workspace cannot reach
Google/Maven; the laptop is too small for Gradle).

What exists: `android/` = Kotlin + Chaquopy 16.0.0 (AGP 8.5.2, Gradle 8.9, Python 3.11, minSdk 26, targetSdk 35).
A Gradle `Sync` task copies `hypolab/`, `ideaengine/`, `ideaweb/`, `data/` into the build (never edited there).
`android/app/src/main/python/spike.py` + `MainActivity.kt` = one RUN SPIKE button that reports time and memory per step.
Workflow `.github/workflows/android.yml` (ubuntu-24.04 has the SDK; error text is posted as an annotation, readable
without a login). **Signing:** the permanent key is NOT in the repo (a safety check refused it, rightly); the workflow
reads secrets `HYPOLAB_KEYSTORE_B64` + `HYPOLAB_STORE_PASSWORD`, and without them signs with a throwaway debug key.
The spike APK is debug-signed, so it must be uninstalled before the first permanently signed APK (it holds no data).

Spike on the tablet (22 Oct, 00:13): every step ok. Python start 0.4 s; numpy+pandas+matplotlib+starlette+engine
imports ~4 s, RSS 272 MB; half-size market (250 stocks) 2.1 s, peak 571 MB; full market (500) 5.5 s, **peak 878 MB**;
one sandbox simulation 0.65 s; robustness 3.2 s; gate 3.3 s; whole loop 19 s. Memory was released when the run
ended. The device had only ~0.9 GB "available" before the run (Android frees other apps' memory on demand); the
Java heap limit (256/512 MB) does not apply to numpy, which allocates natively.
Reading: everything works with Python 3.11 from Chaquopy's repository (matplotlib included); the only risk is the
practice market's peak on 4 GB together with a WebView.

## Android track - phase C2 (1.14.0, 22 Oct)
- `/journal`: the Researcher's journal (sandbox = in-memory practice journal, labelled so; live without a session =
  the file, read-only). Verdict mix, tries per idea, scoreboard, experiments (region + verdict filters, 30 rows then
  "Show 50 more"), submissions, lessons (add when writable).
- `/pyramids`: `compute_pyramids(refresh)` follows the cockpit's order (quarter's submissions from the Account
  download > BRAIN all-time diversity > journal; sandbox = practice counts). BRAIN is read only by "Refresh counts"
  (a job); the result is kept in `LAB.pyr` per mode. Heatmap is drawn with categories as rows (`matrix().T`) so it
  reads on a portrait screen. "Alphas needed per Pyramid" saves `alphas_per_pyramid`. Guide/multiplier order tabs.
- `/superalpha`: the form is kept in `LAB.super_form`; "Check and preview (free)" runs `SA.check` + `SA.preview`;
  "Simulate" re-checks on the server and refuses on an error before spending; one SuperAlpha simulation per press
  (a job). Practice pool (sandbox), restore, the SuperAlpha gate (a job), and submit only through
  `Researcher.super_submit()` (typed confirmation, 1 a day, unlock at 100 lifetime alphas) - the form appears only
  under a READY gate while unlocked with today's one unused. Selection/combo come from HYPOLAB's recipes or code you
  type; nothing AI-written (decision unchanged).
- **Fix:** `hypolab/catalog.py` opens SQLite with `check_same_thread=False` (as the journal and idea store already
  did). Without it a Researcher opened in one thread failed every simulation run in a job thread ("SQLite objects
  created in a thread can only be used in that same thread"); regression in `tests/test_android_c2.py::Threads`.
- Tests: `tests/test_android_c2.py` (journal page, filters, lessons; Pyramids heatmap, k, refresh job; SuperAlpha
  free check, an error never simulates, pool > simulate > gate > wrong confirmation refused; nav; the thread fix).

## Android track - phase C1 (1.13.0, 22 Oct)
**Decision changed (Zacc approved shared pages on 21 Oct):** the web app is no longer "never simulates". Its idea
pages (Week, Leads, Cards, Drafts) still never simulate; the new Lab-side pages do, each simulation behind its own
button. On the laptop, do live work in EITHER the marimo cockpit's Lab OR the web Lab at one time (two processes, one
journal; SQLite copes, but the Lab lists and pending recovery are per process).
- `ideaweb/jobs.py`: `JOBS.start(title, page, fn)` runs fn in a thread; a second start while one runs is refused
  (the page says what is running); a failure is reported, never retried; the message shows once on its page.
  Pages show a banner with a spinner and `<meta refresh 3>` while a job runs, and disable the spend buttons.
- `ideaweb/lab.py` `LAB` (one per process): opens the Researcher with `ideaengine.connection.open_researcher()`
  again when the mode or live region changes (a live problem is re-checked at most every 30 s); keeps the Lab results
  (stable keys, `?focus=<key>`), boost / lower-correlation / gate reports, robustness tables, PnL panels (PNG data
  URIs), the Play roll and results. Card in the Lab = setting `last_lab_card` (same as the cockpit); `lab_region` in
  live mode. A card sent from Cards ("Send to the Lab", `lab_inbox.json`) is picked up when /lab opens; on Android
  "Send to the Lab" goes straight to /lab.
- Lab routes: /lab, /lab/card, /lab/card/act (remove, bin), /lab/simulate, /lab/results, /lab/follow, /lab/boost,
  /lab/perf, /lab/corr, /lab/decorr, /lab/robust, /lab/gate, /lab/submit, /lab/restore, /lab/recover. Submit: the
  form appears only under a READY gate below the daily cap, and every check stays in `Researcher.submit()`
  (typed `SUBMIT <alpha id>`, freshness, cap). Play: /play, /play/roll (free), /play/sim, /play/tolab. Quant
  basics: /basics, /basics/build (lessons 1-5), /basics/sweep (6-7), /basics/try (8; lint + backtest).
- `hypolab/sandbox/market.py` `shared_market(seed, n)`: MockBrain, the Ideas pages' sandbox catalog and Quant
  basics share one market (read-only) - on the tablet one 250-stock market instead of two or three.
- `render_md` adds the blank line python-markdown needs before a list (engine reports were written for marimo).
  `theme.apply_matplotlib` lists only installed fonts (no findfont warnings). CSS: verdict colours, tables keep words
  whole and scroll sideways, the bottom bar scrolls (7 tabs) and keeps the open tab in view.
- Build note (22 Oct): `android/app/build.gradle.kts` pins numpy==1.26.2 and pandas==2.1.3 (Chaquopy's prebuilt
  wheels). Two builds failed when pip fell back to PyPI source (Chaquopy's server briefly unreachable); a plain re-run
  passed. If "Chaquopy_cannot_compile_native_code" appears again, re-run the workflow before changing anything.
- Tests: `tests/test_android_c1.py` (Lab flow with a card: simulate, perf, robustness, gate, wrong confirmation
  refused; one job at a time; no simulation without a button; card hand-off; bin; Play roll/sim/to-Lab; rolling is
  free; Quant basics build/try; shared market). Checked at tablet size in a headless browser, not yet on the tablet.
- Live mode on the tablet still needs phase D (login); the Lab then shows why and stays in sandbox.

## Android track - phase B (1.12.0, 22 Oct)
- `android/app/src/main/python/hl_android.py`: `start(files_dir)` sets HYPOLAB_HOME = <app files>/hypolab,
  HYPOLAB_PLATFORM=android, HYPOLAB_SANDBOX_STOCKS=250, a fresh HYPOLAB_LAUNCH_SECRET, binds 127.0.0.1:0 and runs
  uvicorn (h11, asyncio, no websockets, no lifespan) in a daemon thread; returns `http://127.0.0.1:<port>/?k=<secret>`.
  It must not import hypolab at module level (config reads HYPOLAB_HOME on import).
- `ideaweb/app.py` `LaunchKey` (outermost middleware): only when HYPOLAB_LAUNCH_SECRET is set, `/?k=` sets an
  HttpOnly SameSite=Strict cookie `hl_k`; every other request without it gets 403 (other apps can reach 127.0.0.1).
  `LocalOriginOnly` still refuses POSTs from other origins.
- `hypolab/config.py`: `platform()` ("android"/"desktop") and `sandbox_stocks()` (setting `sandbox_stocks`, default
  500 or HYPOLAB_SANDBOX_STOCKS; MockBrain builds its market with it). The marimo quant basics still builds 500 (desktop
  only; ported in phase C).
- Pages: `base.html` loads `/static/fonts/fonts.css` (IBM Plex Sans/Mono, Newsreader; latin 400/500/600 + Newsreader
  italic; Fontsource v5 files, OFL texts beside them) - no Google Fonts anywhere. `<body class="android|desktop">`.
  A `.topbar` (brand, Sandbox/Live, version) shows at <= 760 px, where the rail becomes a fixed bottom bar of four tabs;
  tables scroll sideways; `@media (pointer: coarse)` makes controls >= 48 px. On Android the cockpit link is replaced
  by "The Lab is on the laptop for now" (the Lab arrives in phase C).
- Copy/Paste/Share: `ideas.js` uses `window.HypolabAndroid` when present: copy() for every Copy button, a Share
  button after each Copy button (Android's share sheet, e.g. to the Claude app), and a "Paste from clipboard" button
  under every `textarea[data-paste]` (drafts import, verdict, Reviewer's plan, source text).
- `MainActivity.kt`: starts Python on a background thread, then a WebView (JS + DOM storage on; file and content
  access off; no multiple windows). Links to anything but 127.0.0.1 open in the browser. Back = page back, then close.
  Edge-to-edge insets (status bar, gesture bar, keyboard) are applied as padding (Android 15+ forces edge to edge).
  `network_security_config.xml`: clear text only to 127.0.0.1. `configChanges` keeps the page on rotation.
- Tests: `tests/test_android_phase_b.py` runs the real launcher on the laptop (secret, cookie, pages, fonts, POST
  guard); `tests/test_platform_desktop.py` proves the desktop is unchanged (no secret, cockpit link, 500 stocks).
- **Checked on the tablet (22 Oct, 00:57): everything works** - start, the four pages, Copy, Share to the Claude
  app, Paste, the keyboard. Installed from run 39680957346, signed with the permanent key (SHA-256 D4:4F:D3:CE...
  78:C0, shown by the workflow's "signer" notice). Not yet measured: memory of WebView + server + market together.

### App icon (1.12.1)
Adaptive icon in `android/app/src/main/res/`: background = Matrix ink with faint chart rules; foreground = a lab
flask whose green signal line breaks out through the glass (an idea that survives testing); a monochrome layer for
Android's themed icons. Vector drawables only (no PNGs). Zacc asked for it on 22 Oct.

### Signing (needed before data matters)
The permanent key is never in the repo. Workflow secrets: `HYPOLAB_KEYSTORE_B64` (base64 of the .jks, alias
`hypolab`) and `HYPOLAB_STORE_PASSWORD` (store and key password). Without them the APK is debug-signed with a key that
changes per build machine, so it cannot update an installed app: uninstalling first loses the app's data.

## Phase 7 - collectors (1.9.0, Oct 20)
Design v2's "Idea sources" table, built without any AI call (decision 1): the collectors read, HYPOLAB tags and ranks,
Scout & Writer (or Zacc) writes the mechanism.
- **Sources** (`ideaengine/collectors.py`, parsing separate from fetching; every collector also reads a saved file):
  - Open Source Asset Pricing: `data/osap_SignalDoc.csv.gz` is OSAP's `SignalDoc.csv` (downloaded 20 Oct from
    github.com/OpenSourceAP/CrossSection; 331 signals, **212 predictors** kept, placebos/drops left out). Fields used:
    Acronym, Authors, Year, Journal, LongDescription, Detailed Definition (first 600 chars), Cat.Data (-> BRAIN
    category: Accounting fundamental, Analyst analyst, Price/Trading pv, Options option, 13F institutions, Event/Other
    other), Cat.Economic, Sign, T-Stat, Return, Predictability in OP, Signal Rep Quality, sample years, portfolio
    period. Licence GPL-2.0 (`data/OSAP_NOTICE.md`).
  - arXiv: `export.arxiv.org/api/query`, newest 100 in `arxiv_categories`; `arxiv_relevance` = keep-patterns minus
    2x drop-patterns, kept at >= 2. Ids without version (`arxiv:2610.01234`).
  - News: RSS 2.0 or Atom; `NEWS_THEMES` (16) with patterns, concepts, BRAIN category and the cross-sectional question;
    one item per theme per ISO week (`news:<theme>:<week>`), headlines older than 14 days ignored; re-collecting merges
    headlines (`sources._merge_news`); listed from 2 headlines (`items(min_news=2)`).
  - Datasets: `catalog.contexts()` per region/delay, value score >= 3, alphas <= 2,000, coverage >= 30%, not in any
    non-sandbox journal expression; theme priority ids flagged.
- **Inbox** (`ideaengine/sources.py`, `ideas.sqlite` tables `sources`, `collector_runs`): `upsert` keeps state/note/
  draft; `tag` = concepts the text mentions (`text_concepts`, generic and vendor-score concepts skipped) + categories
  (`CONCEPT_CATEGORY`); `covered_by` = a library card whose reference has the same first author (second too when both
  name one) and year - 43 of 212 OSAP predictors on the built-in library; `base_score` (OSAP t-stat/predictability/
  replication, arXiv relevance, news count, dataset value score/crowding, manual +2, covered -1.5); `items()` adds +2.0
  for this week's categories (+0.5 region for datasets). States new / skipped / drafted.
- **Actions**: `writer_message` (SOURCE block, format in `claude_projects/README.md`; ids `S-<kind>-<key>` via
  `source_tag`), `source_draft` (skeleton: citation, sign, horizon, suggested roles; story/why_persists/rung 1 left
  for Zacc so the checks keep it a draft), `link_draft` (an imported card's `# from: S-...` marks its source drafted),
  `add_manual`. Source quality: `learn._bucket` maps `S-...` sources to "outside: published predictors (OSAP)", "...
  arXiv papers", "... news themes", "... under-used datasets", "... sources you added".
- **Ideas app**: `/leads/sources` (filters src/show/q, Collect fold with per-collector buttons and last run, add by
  hand), `/leads/sources/fetch|act|add`, `/leads/sources/{id}/writer` (a dataset's SOURCE block with its field list).
  Query parameter for the kind filter is `src` (`kind` carries the flash colour). Rail count = journal leads; the tab
  shows new sources.
- **Hand-offs**: DIGEST line + `outside_sources` in the learning digest JSON; state-doc text "## Fresh outside sources"
  (top 5 new items for the plan); knowledge pack `10_published_predictors.md` (Scout & Writer, Critic); Projects
  instructions 0/2/3 + README updated (SOURCE format, workflow 2b).
- **CLI**: `python -m hypolab collect osap|arxiv|news|datasets|all|list [--file F] [--download]`.
- Checked in this workspace: OSAP from the real file; arXiv/RSS parsing on fixtures (the workspace cannot reach arXiv;
  the three default feeds answered through a web fetch on 20 Oct); screens with Playwright (list, filters, Collect
  fold, copy button, Make a draft -> editor).
- Also fixed: `Catalog.fields(enrich=True)` crashed on a field with no description (NaN is truthy in `d or ""`);
  descriptions are now "" there, which also protects `concept_map`, group binding and the linter's field info.
- The daily brief's prompt (scheduled task, outside the zip): Zacc added the [SOURCE] lines himself on 20 Oct (the
  assistant's edit of a scheduled task was blocked). 1.9.1 numbers the rows; the prompt sentence "ONE of the 3 ideas
  may build on the row whose number is today's weekday (Monday = 1 ... Friday = 5; if that row gets "no card", the
  next row)" goes in with it.

## 1.10.3: the paste boxes and agent pack v3 (20 Oct, night)
The "agents" are Claude chats with fixed instructions (Zacc has no API key); every message crosses by hand, and the
only checks are HYPOLAB's paste boxes. Measured with pack-v2-compliant pastes through the Ideas app (sandbox):

| Where | Was | Now |
|---|---|---|
| `drafts.parse_cards` | `# from:` lines matched to cards by count: one missing comment or a comment above a "no card" slot shifted every later source | each card takes the last `# from:` above it since the previous card (`_sources_for`); dangling / several / missing comments give `Parsed.warnings`, shown after import; one comment above the first card still covers a list; flow-style lists fall back to the old rule with a warning |
| `app.draft_import` | an id already used by a waiting draft was overwritten (title, source); a binned one silently came back | refused unless the form's "This is a rewrite" box is ticked |
| `Drafts.replace` (new) | a rewrite without `# from:` became source "imported"; the old verdict stayed on the new text | keeps the stored source, clears verdict + decision; `verdicts` table keeps every verdict (`Drafts.verdict_history`) |
| `parse_plan` | `universe`, `delay`, unknown keys dropped silently | named in the "Adjusted" note (`PLAN_KEYS`) |
| `knowledge_pack.dead_ends` | lessons and PLAN dead ends stayed in the journal | 07 adds "Dead ends declared by the Weekly Reviewer" and "Lessons" (`learning.declared_dead_ends`, `recent_lessons`) |
| `check_card` | - | warns on a family the Reviewer declared a dead end |
| `state_text` | "Card ids already used" lacked waiting drafts; the brief had no concept / operator list | waiting ids listed; theme priority datasets, lessons, dead ends and a "Card reference" (concepts, operators, standard fields, groups) |
| `learn._bucket` | a daily-brief card citing `S-...` counted as "outside: ...", hiding the brief | `daily brief <date> via S-...` -> "daily brief + outside: ..." |
| `learn.critic_calibration` (new) | the Critic was never measured | latest decision per draft vs NEAR/PASS within the budget; in the DIGEST and its JSON |
| `critic_message` | no plan context | `# this week's plan: ...` and a NOTE when the dry run ran in another region |
| `State.default_region` | saved plan, else the live region (USA) | the week's proposed plan (starting plan included), so EUR weeks dry-run in EUR; the Drafts form lets you pick |
| `knowledge_pack.USED_BY` | four projects; Scout & Writer lacked 05 and 06 | three projects (Scout & Writer gets all ten); INDEX lists `HANDOFF_CONTRACTS.md` and `briefs.md` (`STATIC_USED_BY`) |

Agent pack v3 (`claude_projects/`): `1_scout_writer.md` (Enki; also BRIEFs `B-YYYYMMDD-HHMM` and SHORTLISTs `L-...`),
`2_critic.md` (Shamash; Power Pool / 2-category / ts_backfill / peer checks restored; data_fit <= 2 when the NOTE
line says the dry run ran elsewhere), `3_weekly_reviewer.md` (lessons and dead ends now steer next week: at most 3
lessons, dead ends only with evidence), `daily_brief_prompt.md` (1 card a day; ids `IE_<MMDD>_`, row N on weekday N,
one Leads idea at most; reads only the state doc), `HANDOFF_CONTRACTS.md`, `CHANGELOG_v3.md`. `# from:` conventions:
`S-...`, `B-...`, `inbox: ...` kept, `scout: <title>`, `daily brief <date> [via S-...]`. Not yet checked live: whether
the scheduled task follows the doc's card reference well enough that its cards import without errors.

## Phase 8 - the SuperAlpha builder (1.10.0, Oct 20)
A SuperAlpha combines submitted alphas of one region and delay: a **selection** expression ranks them (BRAIN keeps the
top `selectionLimit`), a **combo** expression weights the kept ones each day. BRAIN: unlock at 100 lifetime alpha
submissions, 1 SuperAlpha a day (G11). The request format and limits come from community code built against the live
API (Alpha Harness, MIT; wqbkit) - BRAIN_RULES section 13 (SA1-SA9) says which facts are "verify live".
- **`hypolab/superalpha.py`**: `make_payload` (`type: SUPER`, top-level `selection` / `combo`, settings
  `selectionLimit` >= 10, `selectionHandling` POSITIVE/NON_ZERO/NON_NAN, `componentActivation` IS/OS; truncation 0.05,
  decay 4 by default); recipes - 5 selections (`least_corr`, `tradeable`, `many_sources`, `slow_core`,
  `broad_books`), each capping operators at 8,000 / limit, and 5 combos (`equal`, `inv_vol`, `rolling_ir`,
  `least_crowded`, `combo_a`), each with a reason (structure after Alpha Harness); `check` (syntax, settings, unknown
  names = warnings, operator cap, last combo statement must be the weight); `eval_selection` / `apply_selection` (a
  safe AST evaluator of the selection language: `&&`, `||`, `!`, `in(...)`, `not(...)`, `universe_size(...)`; used by
  the sandbox and the preview); `pool_alphas` (from the Account download: turnover, Sharpe, operators, categories via
  the catalog - correlations are only known in the sandbox) and `pools` (per region/delay: count, categories,
  ready >= 10, suggested limit ~2/3 of the pool); `preview` (which alphas a selection keeps, or "needs X, which only
  BRAIN knows"); `unlock_status` (lifetime REGULAR submissions from the account download or the Week count, today's
  SuperAlpha); `diagnose` (BRAIN's checks decide: PASS / NEAR / WEAK / NOISE / ERROR, ONE next change: decay for the
  turnover band, 'Least correlated' for correlation, Equal weight when test < train/2, another weighting for weak
  Sharpe); `pool_id` = `SUPER@<region>-D<delay>@<year>Q<q>` (the journal idea every try counts against).
- **Researcher**: `super_test` (checks -> lock (live) -> duplicate (journal text = both expressions + the three
  settings) -> budget `max_super_sims_per_pool` (10) -> daily guard/quota -> one simulation -> diagnose -> journal,
  purpose `super`), `super_results`, `super_gate` (lock, today's SuperAlpha, BRAIN checks, self/prod correlation,
  2%-40% turnover, deflated Sharpe over the pool's tries, train vs test; never a robustness battery), `super_submit`
  (typed confirmation, 1 a day, never while locked; recorded with family `superalpha`), `practice_super_pool`
  (sandbox: submits ~20 rung-1 alphas of the built-in cards, nothing journaled); `recover_pending` reads an
  interrupted SuperAlpha back as one.
- **Journal / planner**: `submissions_today` leaves SuperAlphas out (the 4-a-day cap is for alphas);
  `super_submissions_today`; `planner.lifetime_submitted` leaves them out (the 100 that unlock them are alphas);
  quarter signal counts keep them (G2). Pyramids: no cell (SA8).
- **Sandbox** (`MockBrain`): `seed_practice_pool`, `super_pool_props` (self/prod correlation, counts, categories per
  submitted alpha), `_simulate_super` (selection like BRAIN, recipes' weights, decay as smoothing, LOW_SHARPE /
  LOW_FITNESS / turnover-band checks); a SuperAlpha's self-correlation is measured against other SuperAlphas.
- **Cockpit SuperAlpha tab** (between Play and Journal): unlock line, pools table, "Build a practice pool"
  (sandbox), the form (region, delay, universe, neutralization, decay, truncation, limit, handling, activation, a
  selection recipe and a combo recipe with their reasons, or your own text), live checks + preview, Simulate (1),
  Restore results, results list, gate, typed submit. Marimo gotcha met again: a form cell that depended on the pool
  re-rendered after "Build a practice pool" and showed 30 while 11 was used - the form now depends only on the region.
- Checked: sandbox flow in Python and in a browser (Playwright: practice pool -> simulate -> gate READY -> typed submit
  -> button disabled for the day). Tests: `tests/test_phase8.py` (17).
- Finished in a second pass (the first ran out of session time during the docs): every phase 8 file re-read; one fix -
  `Researcher._own_corr` (Lower correlation's "own alphas") now leaves SuperAlphas out (their journal text is two
  expressions, not FASTEXPR, and BRAIN compares SuperAlphas only with SuperAlphas; regression `test_5_...`); the
  recipes adapted from Alpha Harness carry its MIT notice (`data/THIRD_PARTY_NOTICES.md`).
- Open: everything marked VERIFY LIVE in BRAIN_RULES 13; does BRAIN offer a SuperAlpha operator list (Gold may differ);
  what the SuperAlpha's checks are called; does a SuperAlpha count in Pyramids (SA8); how a SuperAlpha's description
  is sent (the gate writes one; `super_submit` does not send it - paste it on the platform); does a SuperAlpha count
  in an Osmosis scope (the Account tab's Osmosis check counts every submitted alpha it downloads, SUPER included).

## Safety fixes (1.10.2, 20 Oct evening)
Zacc reproduced three weaknesses offline in the sandbox; each is fixed with regressions in `tests/test_review_1102.py`.
| Finding | Cause | Fix |
|---|---|---|
| The gate can be bypassed | `submit()` / `super_submit()` checked the daily cap and BRAIN's answer, never `gate.ready`; a report marked ready by hand went through | Reports are recorded when issued; submit accepts only a recorded READY report for that alpha and kind, under `gate_max_age_minutes` (30) old, once. `force` never lifts the gate |
| Missing evidence leaves a gate READY | an empty /check frame skipped the platform-check block; UNKNOWN correlations and a failed deflated-Sharpe computation only added a line; `if trs and ...` skipped the holdout test when train Sharpe was 0 or missing | each missing piece blocks with a named reason (`_platform_checks`, `_NO_EVIDENCE`, `_NO_DSR`, `_holdout`); SuperAlpha gate the same, plus missing turnover |
| API retries can duplicate actions | `_req` retried every method on network errors and 5xx | POST retried only when BRAIN cannot have acted (no connection, 401, 429); otherwise `UncertainOutcome`: a simulation returns `UNCERTAIN`, a submission is verified by reading the alpha back. BRAIN's own behaviour after a lost answer is still unverified |
Also: `submit()` now checks the typed confirmation itself before calling BRAIN, and a report is used up even when the
call fails (run the gate again). Open question: does BRAIN de-duplicate a repeated `POST /alphas/{id}/submit`, and how
long does a submission take to show `dateSubmitted`?

## Review of 20 Oct (1.10.1)
Zacc asked for every file and line to be checked against 1.10.0 for things out of sync, design flaws, user-experience
issues, poor logic and performance, the Claude Projects' instructions synced, and every capability documented in a
friendly way. Regressions in `tests/test_review_1101.py` (14) and `test_phase8.test_6_...`.
| Where | Problem | Fix |
|---|---|---|
| config.save_settings | wrote every default into settings.json: later default changes never reached existing users (the 1.4.2 TTL and 1.9.0 feed hacks were symptoms) | only your keys are written (`_settings_version: 2`); an old whole file is reduced once; `settings.defaults.json` for reference |
| config.DEFAULTS | `pyramid_regions`, `single_country_region` unused since 1.3.2 | removed (and dropped from old files) |
| MockBrain.diversity | `a["regular"]["code"]` on a sandbox SuperAlpha: the Pyramids tab and `R.pyramids()` crashed after a practice SuperAlpha | REGULAR alphas only |
| views.tries_per_idea, drafts.digest, drafts.family_journal | counted explore + boost only; the gate and learning loop also count decorr | all use `learning.TRY_PURPOSES` |
| planner.lifetime_submitted vs superalpha.unlock_status vs 06_goals_and_rules | three different lifetime numbers (Week page base, account download, "as entered") | one function: max(typed + HYPOLAB since, BRAIN's download + HYPOLAB since) |
| Week page / DIGEST | no SuperAlpha count after the unlock; SuperAlpha simulations mixed into the alpha statistics; weekly "submitted" counted SuperAlphas | `super_today` x/1 on the Week page; a `superalphas:` DIGEST line; week_progress splits alphas and SuperAlphas |
| learning.live_experiments | re-read and re-joined the journal a dozen times per Week page | cached on the journal object until `PRAGMA data_version` / `total_changes` move |
| knowledge_pack.build | rewrote every file (dates only) so "re-upload the changed ones" meant all; the message named a fixed list | unchanged files keep their date; INDEX.md stamps the rebuild and lists the changed files; the Drafts message names file -> projects; the Friday checklist reads INDEX.md |
| week.html / week_plan | "alphas to submit" allowed 28 a week; a pasted PLAN is capped at 20 | form max and server clamp = daily cap x 5 |
| app.week_page | the state doc URL hardcoded | setting `state_doc_url` |
| cockpit | a field-download button and `catalog_ok` never shown or used; SuperAlpha universe `None` before the Account options download; the Setup tab's routine still named Week/Cards tabs in the cockpit; "Restore results" ignored decorr rows | removed; falls back to the region's default universe; routine rewritten for the Ideas app + SuperAlpha; counted |
| wording | "Data tab" / "Cards or Data tab" in Ideas-app messages; "cockpit's Cards" docstrings; "Week tab" in BRAIN_RULES | "the cockpit's Data tab"; "the Ideas app's Cards / Week page" |
| super_gate | the description it writes is never sent (SuperAlpha description shape unknown) and nothing said so | a gate line says to paste it on the platform |
| setup_arch.sh / pyproject | self-test in one process (~6 GB on an 8 GB laptop); httpx missing, so the Ideas app's tests were skipped on a fresh install | `tests/run_all.py` (one process per file); `[test]` extra with httpx; `.gitignore` covers *.sqlite, *.bak, settings.json |
| store.py docstring | promised a model-call cache that will never exist (HYPOLAB never calls an AI) | says which modules add which tables |
| claude_projects/ | README's knowledge-file table disagreed with INDEX.md (Library and Reviewer missing 09); no `# from:` conventions for briefs and the daily brief; DIGEST description from 1.6; nothing about SuperAlphas; Writer and Critic lacked the 2-category / Power-Pool shape rules the hub uses; PLAN ceiling unstated | synced (a test now checks the files each project lists against INDEX.md) |
| docs | no single plain-words description of every capability; README's tab table without SuperAlpha | `docs/USER_GUIDE.md`; README, LEARNING_PATH, HOW_IT_WORKS section 20 updated |

## Review of 20 Oct (1.9.1)
Phase 7's code read again for bugs, inefficiencies and design weaknesses; Zacc chose the fixes (all but link-scheme
hardening: a feed link starting `javascript:` would still be clickable - judged unlikely). Regressions in
`tests/test_review_191.py`.
| Where | Problem | Fix |
|---|---|---|
| sources.items / state_rows | 212 OSAP predictors filled every top slot (state doc: 5/5 OSAP for W43-W45; best arXiv ~145th) | `_balance`: best of each kind first, then the second of each...; one kind listed = pure ranking |
| state_rows + the brief | the doc changes on Fridays and the brief has no memory: the same top row all week | rows numbered 1-5, brief uses row N on weekday N; news left out (stale by then); `|` escaped |
| collectors.http_get | requests guesses ISO-8859-1 for `text/xml` without a charset: garbled quotes/euro signs | feeds and arXiv downloaded as bytes; the XML parser reads the declaration; `--file` read as bytes |
| app source_fetch | downloads ran on the event loop: every page frozen up to a minute | `sources.fetch()` (no database) in `run_in_threadpool`; storing stays on the app's connection |
| fetch_feeds | a page that is not RSS (a cookie wall) counted as a feed and silently gave nothing | parsed at fetch time and reported with the failed feeds |
| datasets collector | a dataset used after collection stayed "new" ("none of your simulations has used it") | `retire_used_datasets`: skipped with a note on each datasets run |
| read_datasets | D0 and D1 lists made the same id; the second overwrote the first's delay | one item per region+dataset, Delay-1 first, `delays` lists both |
| app source_action | a dataset's draft was checked in the week's region | checked in the dataset's own region when it is on the account |
| counts / digest line | counted single-headline news themes the list hides | same rules as the list (`news_listed`) |
| new_count (menu badge) | built and JSON-decoded the whole list on every page view | a database count + the news rows only |
| find_by_tag | `s-osap-accruals` did not link to S-osap-Accruals | case-insensitive |
| news themes | stayed "new" forever, ranked by count not date; "Rates and inflation" fired daily; skip lasted a week | leave "new" after 14 days (`NEWS_FRESH_DAYS`); Mute / Unmute a theme (`news_muted_themes`, rates muted by default) |
| feeds | all three US while the plan is EUR | Euronews business and City AM added (1.9.0's untouched list migrates) |
| covered_by | not refreshed when a card citing the paper was approved later | `refresh_covered` when the library's references change (signature in `sources_meta`) |
| tests | two phase 7 tests used today's date and would fail after 3 Nov | dates passed in (`today=`) |

## Review of 19 Oct (1.8.1)
Every file was read for bugs, inefficiencies and improvements; `ruff` (F, E9, B) is clean apart from cosmetic test
asserts. Fixed (each with a regression test in `tests/test_review_181.py`):
| Where | Problem | Fix |
|---|---|---|
| research, account | `int(delay or 1)`: delay 0 became 1 - D0 alphas re-run, diagnosed and counted as D1 | `rules.delay_of()` |
| research.scan | repeated scan dropped already-simulated lenses: new simulations on another lens, fields lost | scan builds lens cards without the journal and serves repeats via `already_run` |
| robustness | liquid-universe variant TOP1200 for EUR TOP800 (bigger, not more liquid); blocked variants counted as failures | only a smaller TOPn; "not run" excluded from the score; one multi-simulation |
| brain.simulate | results came back grouped by region/delay/universe, not in input order | results indexed by input position |
| research.submit | a submission BRAIN refused was recorded in the journal | records only on HTTP < 300, else raises |
| decorr | residual/own-overlap variants wrapped the whole multi-statement text (invalid FASTEXPR) | `wrap_result` on the final value; multi-statement own alphas skipped |
| cockpit Data | field download skipped insiders, institutions, short interest, social media | downloads every category |
| diagnose | Sharpe between -0.8 x bar and -0.5: "climb the ladder" | finding + "flip once (with a reason)" first; no "switch to INDUSTRY" when already INDUSTRY |
| account.quarter_pyramids | grouping set missed currency/split/adjfactor; 3+ category alphas silently counted in every cell | `rules.GROUPING_FIELDS`; a note when cells may be overstated |
| learn.items | Send to the Lab offered for lens / wild / re-run ideas the Lab cannot open | only library cards |
| planner / Ideas Week | goals never rolled over to a new quarter | warning when goals are from another quarter; updating goals stamps the current quarter |
| ideas._score | 5 whole-journal queries + settings/themes file reads per card | `_journal_context()` once per ranking; settings/themes cached by mtime |
| research.card | Lab asked BRAIN for Pyramid counts on every card | cached 10 min |
| Ideas app | Leads count rebuilt on every page; any website could POST to the app | 30 s cache; origin guard |
| binding | no field list for the default universe (EUR TOP800) -> cards fell back to standard names | `ideas.data_universe()`: bind from another downloaded universe of the region, with a note |
| config | a theme's universe stayed after the theme ended in a running app | `apply_themes()` restores `base_universe`; the Ideas app re-applies per page |

## What changed in HYPOLAB since v1.0 (all tested)
- `load_library()` also loads `~/.hypolab/library/*.yaml`; `LOAD_WARNINGS` lists skipped files/ids.
- `Researcher.card(id, region)`; `Researcher.submit` refuses the 5th submission of the day.
- Journal: WAL, `open_readonly()`, `idea()`, `submissions_today()`, `sims_today()` from local midnight.
- Bugs fixed: submit after a kernel restart recorded family "manual"; stray keys in `REGION_DEFAULTS`;
  **sandbox wrote practice fields into the real catalog, so live mode never loaded the bundled GLB catalog**.
- Login split in two steps for web pages; `python -m hypolab cockpit` command.
- Jupyter notebooks, `scripts/build_notebooks.py` and the Jupyter dependencies removed.

## The idea team on Claude Projects (added 2026-10-10)
No API key, so AI runs as four Claude Projects that Zacc sets up from `claude_projects/` (instructions + a
knowledge pack generated by `python -m ideaengine.knowledge_pack`): **BRAIN Library** (briefs from BRAIN
material), **Scout & Writer** (cards in HYPOLAB YAML, ids `IE_`), **Critic** (VERDICT YAML: keep/rewrite/bin),
**Weekly Reviewer** (DIGEST in, PLAN YAML out). Zacc carries messages between them; formats are in
`claude_projects/README.md`. This replaces phase 6's Claude Code automation for now (it can still come later).

## First live run (Oct 10) - fixed in 1.2.1
- Pyramids tab crashed: BRAIN's `/activities/diversity` returned rows with no `delay`. `PyramidTracker` now cleans
  counts (missing delay -> 1, missing count -> 0, no region -> dropped) and lists what it cleaned; the Pyramids
  tab shows BRAIN's raw rows (first 20) so the real format can be checked. If the raw rows show a different
  shape (e.g. delay nested elsewhere), fix `BrainClient.diversity()`.
- Every app page started its own face-scan request when the saved session had expired (links printed in the
  terminal, none usable). Now `connect.resume_saved_login()` starts at most one request, `connect.pending()`
  exposes it, and the Setup tab shows its link and the "I finished the face scan" button.

## Account tab and live operator list (1.3.0, Oct 10)
- `hypolab/account.py`: `BrainClient.submitted_alphas()` pages `/users/self/alphas` filtered on `dateSubmitted`;
  rows go to `journal.sqlite` table `account_alphas` with parsed operators and fields. `operator_audit(journal, y, q)`
  gives used/unused operators per quarter by BRAIN category (rules from Zacc's "ALPHA_ITERATOR (Unused Ops)"
  notebook: REGULAR only, symbols -> operator names, ts_backfill/group_backfill not counted, `=` in named args is
  not an operator). `field_usage()` lists the fields his submissions lean on.
- `operators.sync_operators(brain)` caches GET /operators in `~/.hypolab/operators.json` and merges it into
  `GOLD` at import, so the linter accepts every operator his account has (the PDF list had 82; BRAIN shows 131
  REGULAR operators in 8 categories). API-only operators get light checks.
- Cockpit **Account** tab: one button downloads both; lifetime count replaces the hand-typed 58 in the SuperAlpha
  countdown. Knowledge pack file `08_my_operator_usage.md` feeds the Writer and Reviewer.
- Claude in this cloud workspace cannot reach BRAIN (no credentials, network allowlist); everything account-related
  runs on Zacc's laptop through HYPOLAB.

## Pyramid counts: BRAIN's real format (1.3.1, Oct 10)
Zacc sent the raw rows of `GET /users/{id}/activities/diversity?grouping=region,delay,dataCategory`. Each item is
`{region, delay, alphaCount, dataCategory: {id, name}, dataDiversity: {check, limit}}`. BRAIN also sends subtotals:
`dataCategory.id = null` with a delay = all categories of that region+delay; `delay = null` too = the whole region.
Until 1.3.1 those subtotals were counted as the "Other" category (and the delay-null one as delay 1), which inflated
Other (IND Other would have shown 40). Now `diversity()` tags rows `kind` = cell / region_delay_total /
region_total, `PyramidTracker.totals` keeps the subtotals and the Pyramids tab shows them in their own table.
His rows: GLB D1 = 2 alphas touching fundamental, model, other and pv (one alpha counts in every category it uses);
IND D1 = 20 alphas, all Model. Open question: his Genius page showed Pyramids 0/10 while IND/D1/Model has 20, so
either these counts are not limited to the current quarter or a Pyramid needs more than an alpha count (e.g. the
dataDiversity check). Ask Zacc what BRAIN's Pyramids page shows for IND Model before trusting "filled".

## Theme datasets (Zacc's uploads, Oct 10)
BRAIN's Data > Datasets pages show per dataset: fields, Pyramid theme multiplier (1.1 on most theme sets), coverage,
value score (1-5), alpha count, last field added. Zacc uploads these per region to the BRAIN Library project, which
returns a SHORTLIST (high value, few alphas, coverage >= 30%). First read (USA page 1 of 3, ASI, EUR): top targets
include EUR Europe Relation Dataset (value 5, 25 alphas, 100% coverage), USA ESG (4, 79), ASI Earnings Tax Data
(4, 134), USA Deep Learning Chart Return Prediction (4, 205), Management and Executive Data (USA/EUR, 4, ~300).
HYPOLAB already syncs `value_score`, `pyramid_multiplier` and `alpha_count` per dataset from the API
(`catalog.sqlite`), but the card ranking (`ideas._score`) ignores value score and multiplier: phase 5 should add
them, and the Data tab should sort by them. Concept gaps found: management/executive changes, tax (book-tax), ESG
score, bond/credit spread - add concepts in phase 3 or 7 so cards on these datasets can bind.

## BRAIN's rules and 1.3.2 (Oct 10)
Zacc sent 24 BRAIN documentation/tips pages and his Genius status page. Every rule is in **`docs/BRAIN_RULES.md`**
(project doc `hypolab/BRAIN_RULES.md`) with its source, conflicts between pages, and HYPOLAB's status; it is also
`09_brain_rules.md` in the knowledge pack. **Read it before changing anything rule-related.** BRAIN's docs pages lag
his account (regions, D0 scopes): his account wins.

What 1.3.2 changed (all tested in `tests/test_brain_rules.py`):
- `hypolab/rules.py` (new): single-dataset detection and cutoffs (2.38 D1 / 3.96 D0), sub-universe formula, Fitness
  labels, BRAIN's day (New York midnight), quarter bounds, Osmosis lock deadline.
- Every ladder rung has `profile` / `is_test`; every result's diagnosis says which IS test applies; the sandbox
  applies the 2.38 cutoff to single-dataset alphas and BRAIN's sub-universe formula (was a flat 0.35).
- Journal counts simulations and submissions from New York midnight (was local midnight).
- `brain.record_quota()` / `quota()`: X-Ratelimit headers -> `~/.hypolab/quota.json`; Lab shows it; test() stops at 0.
- `config.account_regions()` (new setting `account_regions`; old `pyramid_regions`/`single_country_region` unused),
  DEU/GBR/JPN/AMR with D0; `BrainClient.sync_simulation_options()` -> `~/.hypolab/sim_options.json` ->
  `config.apply_sim_options()` fills universes/neutralizations per region. DEU/GBR universes are unknown until that
  sync: `make_payload` refuses them with a clear message.
- Lab: neutralization list = the region's real options (risk sets included) and a delay picker.
- Diagnose: Fitness label; correlation advice in BRAIN's order (equivalent field -> similar operator -> meaningful
  grouping) plus a risk set (SLOW if turnover < 20%, else SLOW_AND_FAST) when offered; split-decay fix for the
  sub-universe test; single-dataset note on LOW_2Y_SHARPE.
- Pyramids: counted for the **current quarter** from `account_alphas` (field categories via the catalog, or BRAIN's
  own Pyramid tags if an alpha carries them); diversity API (all time) is only a fallback. `TIERS` now has all 17
  categories. Multipliers: live parse of `/activities/pyramid-multipliers`, else `data/pyramid_multipliers_2026Q4.json`
  (transcribed from his Genius page); `plan(by="guide"|"multiplier")`, per delay, skips cells BRAIN doesn't offer.
- Account tab: one download now also saves simulation options; new sections **Genius tie-breakers**, **Osmosis check**
  (`account.osmosis_check`), **Re-run a submitted alpha** (`Researcher.rerun_variants` / `rerun`, idea id
  `rerun:<alpha_id>`, results go to the Lab). `account_alphas.extra` keeps BRAIN's pyramid/osmosis keys (migrated).
- Knowledge pack: `09_brain_rules.md`; project instructions list it.

Unknowns to check on the first live run of 1.3.2:
- The shape of `/activities/pyramid-multipliers` (if not parsed, the snapshot is used - the Pyramids tab says which).
- Whether BRAIN's alpha JSON carries Pyramid tags / Osmosis points (if yes, `extra` holds them and they are used).
- DEU/GBR universe names (filled by the Account tab download).
- Whether the < 30% turnover factor 0.85 also lowers the single-dataset cutoff (BRAIN_RULES T2).
- Which risk sets JPN/AMR/IND/DEU/GBR offer (the sync answers it).

Still open from BRAIN_RULES (good phase 3-5 material): planner should front-load quality submissions before 1 Dec
(December may not count toward Q4 performance, G8); USA D0 should default to TOP1000 (S-8); show the risk-handled /
investability stats BRAIN returns (S-5); PnL realization horizon check (H1-H2); value score + multiplier in card
ranking (D4); Osmosis correlation pruning (O6).

Settled 19 Oct (decision 8: EUR first). Original note: the starting plan (W42-W46) put USA/GLB first - the lowest multipliers (mostly 1.0-1.4)
but the easiest to pass; DEU/GBR/JPN/AMR/CHN and all D0 cells pay 1.6-1.9. The Pyramids tab can sort either way.

## UI theme "Matrix" (1.4.0, Oct 10; replaced 1.3.3's "Phosphor")
Zacc asked for greener, "another world", not boring during simulations. All three apps share:
- `apps/hypolab.css` (`marimo.App(css_file="hypolab.css", html_head_file="head.html")`): near-black green background,
  code green #00ff9c (primary), mint body text #d2f5e1 (readability), cyan #5ef2ff (links/info), lime #c4ff3d
  (PASS/LIVE; 1.4.1: solid green instead), violet warnings (1.4.1, was amber), coral. Monospace glowing headings (JetBrains Mono; h1 uppercase with "> " and a blinking cursor),
  uppercase tabs, faint CRT scanlines, a dark glass panel behind the content. Verdicts and the gate status render as
  badges: `<span class="hl-verdict hl-v-<verdict>">` from `Diagnosis.markdown()` / `GateReport.markdown()`.
- `apps/head.html`: fonts + a **digital-rain canvas** (katakana + quant glyphs, ~18 fps, paused when hidden, static
  under prefers-reduced-motion, z-index -1). It speeds up while marimo shows a spinner (`.animate-spin`). The `html`
  element carries the background; `body` must stay transparent or the canvas is hidden.
- `hypolab/theme.py`: palette for charts (`apply_matplotlib()`), `PYRAMID_LEVELS`, and `loading_line()` - random
  spinner titles ("Following the white rabbit through the order book ...") used by Lab, re-run and Play spinners.
- Selector notes: marimo copies the custom CSS into shadow roots. Callouts `.admonition.<kind>`; tabs
  `[role=tab][data-state=active]`; form panels `div[class*="--amber-1"][class*="--amber-7"]`; buttons by class
  (`--grass-9` success, `bg-action` form submit, `--red-9` danger) - their children need the dark text colour too;
  checkboxes `[role=checkbox][data-state=checked]`. Never style bare `[data-kind]`.
- `mo.ui.table(initial_selection=...)` does not show ticks on screen; Play uses "tick none = all" instead.

## Play tab (1.4.0, Oct 10)
A playground outside the Pyramid plan: `hypolab/play.py` + cockpit tab **Play** (between Lab and Journal).
- `roll(catalog, region, n, mode, seed, shuffle_settings)` (also `Researcher.roll`): free, linted, reproducible by seed.
  mode "cards" = any card from the library (built-in + mine), random rung; "wild" = random field (or two fields of the
  SAME dataset, so still single-dataset) from a random dataset into a random template (`TEMPLATES_ONE/TWO`, windows
  5..252, groups industry/subindustry/sector, random sign); "mix" = either. Settings shuffle: decay {0,2,4,6,10},
  any non-NONE neutralization the region offers, truncation {0.05,0.08,0.1}.
- `Researcher.play(items)`: simulates via `test(purpose="play", idea_id="play:<card>@R" | "play:wild:<dataset>@R")`,
  logs an ideas row (family "play"). No per-idea cap (BRAIN's daily quota still applies). `journal.trials()` now counts
  purpose "play" too, so the gate's deflated Sharpe includes every die thrown on that idea.
- Tab: dice options, Roll (free), table (tick none = simulate all), Simulate, results with verdict badges, "Send this
  one to the Lab" (gate/submit there), score strip `play_stats()` (dice thrown, today, PASS, NEAR, best Sharpe) read
  from `R.journal` (the sandbox's journal is in memory).
- Tests: `tests/test_play.py`.

## Resume after a shutdown + no yellow (1.4.1, Oct 10)
Zacc asked: can he shut the laptop down mid-alpha and resume? And yellow did not sit with the green.
- **Interrupted simulations:** `BrainClient.simulate(..., on_submitted=cb)` calls `cb(payloads, location)` as soon as
  BRAIN accepts a simulation (it is counted from then). `Researcher.test` writes it to the journal table `pending`
  and clears it after reading the result. After a restart the Lab shows "N simulation(s) were still running" and
  **Fetch them from BRAIN** -> `Researcher.recover_pending()` uses `BrainClient.peek(loc)` (one GET: result if done,
  None if still running, GONE on 404) and `_finish()` (shared with `test`) to diagnose + journal - no new simulation.
- **Recent results:** `Researcher.recent_results(n)` rebuilds TestResults from the journal (diagnosis recomputed,
  card rebuilt from `HYP@REGION` ids via `_card_for`; play/rerun ids keep `idea_id`). Lab box "Pick up where you left
  off" -> **Restore results** when the results list is empty.
- **Last Lab card:** settings.json `last_lab_card`, saved when the Lab card changes, preselected on start.
- **Play:** the last roll is saved to `~/.hypolab/play_last_roll_{sandbox|live}.json` (`play.save_roll/load_roll`,
  card objects not stored; items still play without them).
- Sandbox has an in-memory journal, so resume is a live-mode feature (the sandbox only keeps the Play roll and card).
- Colours: warnings are soft violet `#c3a6ff`; PASS/READY/LIVE are solid code green `#00ff9c` with dark text;
  INVERTED magenta `#ff7ad9`; marimo's radix `--amber-*`, `--yellow-*`, `--orange-*` scales are remapped to a dark
  violet scale in `apps/hypolab.css`. `theme.PASS/WARN/MAGENTA` (old `LIME/AMBER` names alias them).
- Tests: `tests/test_resume.py` (incl. a real HTTP fake BRAIN for the hook and `peek`).

## "kernel not found" (1.4.2, Oct 10)
Zacc saw marimo's "kernel not found": the browser tab outlived its app session. marimo closes a session 120 s after
the websocket drops (laptop asleep, Wi-Fi blip) or when the server restarts. Fixes:
- `python -m hypolab cockpit` passes `--session-ttl` from settings `session_ttl_seconds` (default 3600; each kept
  session ~0.8 GB) unless the user gives one.
- `apps/head.html` self-heal script: if the page text shows "kernel not found" / "Failed to send function request",
  it overlays "session lost while you were away" and reloads into a fresh session (max one reload per 20 s; after 3
  tries in 3 min it stops and tells him to restart the cockpit). The Lab's resume box then restores the work.
- Verified with Playwright by restarting the server under an open page.

## Engine flaws fixed (1.4.3, Oct 11)
Zacc reported: can't discard noise cards, can't remove a card from the Lab, can't see the alpha a boost made or its
performance, and the system is slow.
- **Bin** (`journal.binned` table; `R.bin(id, reason)`, `R.restore(id)`, `R.binned()`): Cards tab "Bin this card"
  with a reason, and "The bin" accordion to restore. Binned cards leave the Cards ranking, the Lab dropdown,
  `R.ideas()` (so boosters), `R.roll()` (Play, `play.roll(exclude=)`), and "Restore results". Nothing is deleted.
  Sandbox bins live only for the session (in-memory journal). `research.card_of_idea()` maps idea ids to cards.
- **Lab**: "Remove card from the Lab" (dropdown shows "(no card: write your own expression)"; settings
  `last_lab_card` = "" remembers it) and "Bin card (noise)". With no card the Lab tests your own expression as
  `manual@<region>`. Results list: "Remove the selected result" / "Clear the list" (journal keeps them).
  `get_lab_card` now holds `(id, time)` so re-sending the same card always switches.
- **Boost visible**: `R.test(rung_name=)`; combinations are journaled as `<rung> + boost:<card>` under the base
  idea; `BoostReport.boosters` (each booster alone, rung "booster alone: ..."), `lab_results()` (boosters, combos,
  best LAST so it is selected), `alpha_ids()`, table columns `booster_alpha`/`combined_alpha`. The Lab keeps the
  boost report on screen while any of its alphas is shown, plus an "Open a boosted alpha" dropdown (`get_focus`).
  The list shows a ▶ on the row displayed below.
- **Performance**: `R.performance(result, compare={label: alpha_id})` -> cumulative PnL + yearly table (API reads,
  never a simulation); `views.pnl_figure`. The best boost is drawn automatically against its base and booster;
  any other result has a "Show its performance" button.
- **Speed** (profiled on the 27k-field GLB catalog): Cards ranking 9 s -> 3.6 s cold, 0.3 s after the first run
  (T470s roughly 2-3x slower). `Concept.match_text` with one combined regex per concept; `Catalog._rows` plain-Python
  rows; `Catalog.lookup_map` (rules.catalog_lookup was rebuilding a 27k dict per card); enriched fields and concept
  matches cached on disk in `~/.hypolab/cache/*.pkl`, keyed by field count + last sync + a hash of the concept
  rules (never for `:memory:`); `load_library()` cached until a card file changes. Results identical (checked
  all 82 concepts on GLB). Browser: no `backdrop-filter`, no `mix-blend-mode`, rain at 14 fps (calm 7) at 1x pixels,
  paused when the window loses focus; **[ FX ]** button bottom right cycles full / calm / off (localStorage
  `hypolab-fx`); the self-heal check uses `textContent` first (no forced layout every 2 s).
- Tests: `tests/test_bin_boost_speed.py` (9).

## Phase 3 - the card-writing form (1.5.0, done Oct 11)
Zacc writes his own cards in the cockpit, or imports the Writer's, without hand-editing YAML.
- **`ideaengine/drafts.py`** + table `drafts` in `ideas.sqlite` (id, yaml, state, source, reason, verdict, decision,
  title, family, created, updated). States: draft (a check fails) / checked (all pass) / approved / binned (reason
  kept; restore -> draft). An approved draft is read-only (copy it to a new id to change it).
- **Form <-> card**: `form_defaults` / `card_from_form`. Keys the form does not show (role categories / pair_with /
  type / min_coverage, rung `when`, beginner, settings like max_trade) are carried over from the loaded card. All 47
  built-in cards survive form + YAML unchanged (test). `card_yaml` writes the library's style (folded story, flow
  settings, short expressions quoted). Form: 4 role rows (concept dropdown, searchable), 3 rungs.
- **Checks** (`check_card`, every change, no simulation, ~0.05-0.4 s warm on the 27k-field GLB catalog): required
  fields/types, id format, **id clash with the library = error**, category/horizon/strength/family, concepts exist
  ("did you mean"), `validate_library` (syntax, placeholders, Gold-operator errors such as NAMED_PARAMETER), linter
  warnings (ARBITRARY_WINDOW ...), field ids written directly (warning), **dry-run binding** (`build_card` in the
  chosen region: field, dataset, coverage, alphas on it; each rung's IS test; or which role found no field), same
  family / same concept set in the library, journal record of the family (dead end = 5+ explore/boost tries, none
  WEAK or better -> warning; the decision stays Zacc's).
- **Approve** -> `append_to_my_cards`: atomic write, `.bak`, refuses duplicate ids and anything that would not load
  back; the card appears on Cards (source mine) and in the Lab list; "Send IE_... to the Lab" button.
- **Hand-offs**: Import box (fences, `# from:` lines, several cards; a VERDICT/PLAN pasted there is recognised);
  "Copy for the Critic" = card + checks + dry run as YAML comments (3_critic.md now explains those lines); paste a
  VERDICT -> stored on its draft and shown (advice only, never approves/bins); Week tab "Friday review": **DIGEST**
  of the selected week (plan, goals pace, submissions, simulations by backend/purpose, verdicts, failed checks,
  drafts approved/binned, near misses with tries left, inverted, ideas at budget, best results, lessons) and **paste
  PLAN** (`parse_plan` clips submit_target to 4/day x 5, drops unknown categories; `apply_plan` saves the plan with
  `extra` = retry/dead_ends/lessons, writes lessons + dead ends to the journal once; the Week tab shows them);
  "Rebuild the knowledge pack" button (uses the real journal read-only, also in sandbox).
- New concepts: `pretax_income`, `income_tax`, `esg_score`, `credit_spread`, `management_change` (checked on the
  GLB snapshot: ESG -> anl11 ESG scores, credit spread -> pv173 z-spreads, management -> qfl_corpexec tenure).
- CSS: disabled buttons now look disabled; `.hl-mdtable` for read-only HTML tables.
- Tests: `tests/test_drafts.py` (23). Browser-checked with Playwright: import -> edit -> save -> verdict -> bin ->
  restore -> approve -> Cards/Lab, copy a built-in card, PLAN paste, DIGEST.

**marimo gotcha found here (0.23.16), keep in mind for every cell that rebuilds UI elements:** the browser keeps a
value per element id (`<cell>-<counter>`). A cell that rebuilds a form with new values but the same ids showed the
OLD text; a cell where elements appear/disappear between runs shifts ids and mixes element types ("(c || []).map is
not a function"). Fixes used: the form cell advances the id counter by 1000 x load number
(`get_context()._id_provider._counter`, private API, wrapped in try); the Drafts view does the same per run; read-only
tables in cells that re-run on every keystroke are HTML (`views.html_table`), not `mo.ui.table`; the form cell
depends only on the loaded card (not on the region), so changing region never wipes edits.

Open for later: approving a card does not yet ask the Critic automatically (phase 6); drafts have no inbox source
list yet (phase 5/7); the DIGEST does not include Pyramid progress (add in phase 4).

## Production correlation (1.6.0, Oct 11-18)
Zacc: "a big problem with prod correlation". His screenshots (GLB/D1/MINVOL1M, the 2-year net-issuance alpha
`-group_rank(log(ts_backfill(sharesout,21)/ts_delay(ts_backfill(sharesout,21),504)), subindustry)`): prod correlation
max 0.7802 / min -0.4484 shown right after simulating; SELF/PROD/Power Pool correlation and data overuse checks PENDING
until Check Submission; warning "Theme GLB/D1 Risk Handled Crowding Factors/Fast Factors Theme does not match with
multiplier of 2.5"; "2 year Sharpe of 2.34 is above cutoff of 1.58" on a Single Data Set Alpha (docs say 2.38).
All logged in `docs/BRAIN_RULES.md` (new table C1-C6; T1 marked DISPUTED).
- **Bug fixed**: the gate blocked whenever HYPOLAB's own max >= 0.7, even if BRAIN's check passed. Now
  `decorr.corr_status` reads BRAIN's SELF/PROD/POWER_POOL_CORRELATION rows first; HYPOLAB's reading is a hint
  (`FAIL?`/`PASS?`) only when BRAIN has not answered; PENDING = not ready, re-run after Check Submission.
- `R.correlation(aid, kind)`: free API read, journal table `correlations` (a day). Lab: "Read production
  correlation", status line (also from the journal cache).
- `decorr.theme_hints`: theme warning -> neutralization (CROWDING, FAST, SLOW_AND_FAST, SLOW, RAM, STATISTICAL);
  `diagnose()` now wraps `_diagnose()` and appends "Match the x2.5 theme: neutralization CROWDING" for any
  PASS/NEAR/WEAK with |Sharpe| >= 1 (Follow applies it).
- `R.decorrelate(result, k)` + Lab "Lower correlation, keep the signal": style proxies (momentum, reversal, size,
  low vol, value proxy; simulated once per region+neutralization as purpose `style`, not counted against the idea),
  PnL correlation with own submitted alphas, variants (theme risk set, residual vs the most similar style via
  `group_neutralize(x, bucket(style, range="0,1,0.1"))` - Gold only, less crowded equivalent field via
  `build_card(avoid_fields=)`, CROWDING / SLOW or SLOW_AND_FAST, shorter horizon (longest window >= 126 to the next
  economic window, ts_backfill windows untouched), own-alpha residual, other peer group), simulated as purpose
  `decorr` (counted in `journal.trials`), prod correlation read per variant, `decorr.recommend` = highest Sharpe
  under the limit keeping >= 60% (never a copy), `decorr.lesson` says what it teaches. Table rendered as HTML.
- Learning: `decorr.family_prod_corr` (median per family) -> Cards ranking penalty (median >= 0.7) and Drafts warning;
  textbook families (`decorr.CROWDED_FAMILIES`) get a note.
- Still unknown: whether BRAIN's PROD check passes an alpha above 0.7 with clearly higher Sharpe (C6); the raw shape
  of `/alphas/{id}/correlations/prod` (we use only max/min; the table is kept raw in the journal); what a Cluster
  Alpha is (C4). The sandbox has no risk sets and a 3-alpha "pool", so the real test is live.

## Split in two + lean UI (1.7.0, Oct 18)
Zacc found the marimo Cards/Drafts boring and the forms fought marimo (see the Phase 3 "marimo gotcha"). Decision:
a web app for ideas, marimo for simulations. He chose to strip the rain, glows/scanlines and the 1-hour keep-alive
(kept the Play tab).
- **`ideaweb/`**: Starlette + Jinja2 (+ markdown, python-multipart), all installed with marimo except jinja2 (now in
  requirements). Routes: `/week` (+ `/week/plan`, `/week/goals`, `/week/review`), `/cards` (+ `/cards/{id}/lab|bin|
  restore|draft`), `/drafts`, `/drafts/new`, `/drafts/{id}` (+ `/drafts/save` with `action` save|approve|bin,
  `/drafts/import`, `/drafts/verdict`, `/drafts/{id}/restore`, `/pack`), `POST /api/check` (live checks: HTML panel +
  YAML + Critic text). POST-redirect-GET with `?msg=&kind=` flashes; `lab=<id>` adds a "Send to the Lab" button.
  127.0.0.1 only. Writes ideas.sqlite, my_cards.yaml, the journal's binned/lessons, lab_inbox.json. Never BRAIN.
- Design: green-on-black like the cockpit but calm; Newsreader serif for stories/titles (the card's story leads),
  IBM Plex Sans UI, IBM Plex Mono for ids/expressions; left rail (Week / Cards / Drafts with waiting count); editor =
  form left, sticky live-check panel right; no animation. Fonts from Google Fonts with system fallbacks.
- Concept input is a text field with a datalist of all concepts (typos get "did you mean" from the checks).
- **Cockpit**: Week/Cards/Drafts cells removed (2050 -> 1350 lines); the field-list sync + catalog cells stay for the
  Lab; Lab dropdown re-reads the library and takes `handoff.take_new()` first; button "Pick up the card sent from
  Ideas"; header links the Ideas app; tabs now Lab first.
- **Launcher**: `python -m hypolab cockpit` = Popen(`python -m ideaweb`) + `marimo run apps/ --session-ttl 900`
  (an old saved 3600 is lowered to 900); `--no-ideas` skips the web app; `python -m hypolab ideas` = web app only.
- **Lean CSS/HTML**: rain canvas + [ FX ] removed from `apps/head.html` (the reconnect script stays); every
  text-shadow, animation/keyframe, glow box-shadow, scanline layer and background gradient removed from
  `apps/hypolab.css`; body has a solid background.
- Tests: `tests/test_ideaweb.py` (5, skipped without starlette/jinja2/httpx/markdown/python-multipart); the cockpit
  command test mocks Popen. Browser-checked: write a card with live checks (typo -> "did you mean", Approve enables
  when clean), save, verdict, approve, Send to the Lab -> the cockpit's Lab shows "Picked up IE_INV_BUILD from Ideas",
  bin/restore/copy on Cards, import, PLAN paste.

## Phase 4 - the planner's Friday review + batch-5 fixes (second line "1.6.0", Oct 19; in 1.8.0 its screens are on the Ideas Week page)
Week tab and DIGEST now carry the evidence; nothing in HYPOLAB's decisions moved without Zacc.
- **`ideaengine/planner.py`**: `near_misses()` (NEAR, or WEAK with Sharpe >= 1, tries left), `dead_end_families()`
  (same rule as 07_dead_ends), `themes_in_week()`, `warnings_for()` (G8 last month; Osmosis lock deadline within 4
  weeks), `evidence()` (retry = last PLAN's retry + near misses; dead ends = last PLAN's + journal's; closest Pyramid
  cells; themes; warnings), `propose_from_evidence()` (a saved plan stays as saved; evidence under
  `extra['evidence']`), `week_pyramid_moves()` (cells gained this week, from the Account download;
  `account.quarter_pyramids(alpha_ids=...)`), `friday_checklist()` (6 steps, done where HYPOLAB can tell).
- **DIGEST** adds: Pyramid cells that moved, cards approved vs target, closest cells, active themes, warnings.
  `digest(..., catalog=, tracker=)`.
- **`drafts.state_text()`**: the markdown for the HYPOLAB state doc; Week tab accordion "Text for the HYPOLAB state doc".
- **Week tab**: "What the week has to respect" callout (themes, warnings, closest cells, near misses, dead ends) and
  the Friday checklist.
- **Fixes**: `R.follow()` and `R.boost()` keep region / universe / delay / maxTrade of the result they build on
  (`research._carry_settings`; before, a D0 or other-region result was followed at D1 / the default region);
  USA D0 defaults to TOP1000 unless a universe is given (S-8); gate applies BRAIN's self-correlation exception (Sharpe
  >= 10% above every correlated alpha, T7); grouping fields add currency/split/adjfactor (ATOM rules); Diagnose:
  ASI Japan test (T9), GLB sub-geography tips (T8), correlation advice no longer suggests `ts_median` (not on the
  Gold PDF).
- **New rules** (`hypolab/rules.py`): `pyramid_check` (max 2 Pyramids per alpha - cards rank 3+ categories lower,
  boosts and the gate flag them), `power_pool_shape` (<= 8 operators, <= 3 fields; shown on cards and the gate),
  `recommended_neutralization` (BRAIN's table by category; a card says when its own default differs - card defaults
  were NOT changed), `self_corr_exception`, `RA_UNIVERSES` / `RA_NOTE` (Region Agnostic Alphas; HYPOLAB cannot send
  RA simulations yet), `themes()` from `data/themes.json` (EUR/D1 TOP800, 12 Oct - 8 Nov, 2x / 3x Python: Cards
  ranking bonus when region and dataset match), `last_month_warning`.
- Knowledge pack: 06 adds the 2-Pyramid, Power Pool, Region Agnostic and neutralization rules plus active themes;
  09 = BRAIN_RULES with batch 5.
- Tests: `tests/test_phase4.py` (17).

Decided 19 Oct (1.6.1): EUR moved forward into the theme window (W43-W45).

Open questions from batch 5: does a 3-category alpha still count in 2 Pyramid cells or in none (P1)? The exact name
of the ASI Japan check (T9)? The API payload for Region Agnostic simulations (RA1)? The D1 Sharpe bar 1.25 vs 1.58 (T11)?

## Phase 5 - the learning loop (second line "1.7.0", Oct 19; in 1.8.0 the Inbox is the Ideas app's Leads page)
Built to the design doc's "Learning from the journal" table (all rows: near misses, scan candidates, inverted, dead
ends, check failures, transfer, source quality, lessons) plus the value-score ranking promised in 1.3.x.
- Layering: `hypolab/learning.py` (facts, no Idea Engine import) <- `ideas._score`, `planner`, `knowledge_pack`,
  `drafts`; `ideaengine/learn.py` (actions, inbox state, drafts, digest) <- Ideas app Leads page, DIGEST.
- Rules chosen (change them in one place): near miss = NEAR, or WEAK with Sharpe >= 1.0; budget = settings
  `max_sims_per_idea`; dead end = 5+ explore/boost tries, none WEAK or better (per family, all regions); scan
  candidate = |Sharpe| above `overfit.noise_bar(n, sharpes)` of its own scan and the field absent from every later
  non-scan expression; check-failure pattern = 3+ failures and >= 40% of results for that region x category;
  transfers never use SBX and default to the regions your journal already has (the Inbox adds the plan's regions).
- Inbox decisions expire when the evidence hash changes (new best Sharpe, more tries), so a skipped near miss
  returns after a new result.
- Scan drafts leave `why_persists` empty on purpose (one error in the checks) so a field never becomes a card
  without a written mechanism.
- Source buckets come from the library source and the draft's `# from:` text ("daily brief", "inbox", "copy of",
  "B-yyyymmdd"/Scout). The daily brief writes `# from: daily brief <date>`, so its cards are measured separately.
- Checked by hand: Inbox tab in live mode (not logged in) on a populated journal - items, selection, "Make a draft"
  (sibling saved, hidden from the inbox, open on Drafts). Not checked: a real BRAIN journal.
- After the first live weeks: check that the near-miss and dead-end rules match what Zacc sees; consider a
  per-region dead end (07 used to list family x region); tune the ranking weights if cards jump around too much.

## Phase 4 - original plan (kept for reference)
The DIGEST out / PLAN in loop now exists (1.5.0). Phase 4 makes the planner itself smarter:
1. DIGEST + the Ideas app's Week page: Pyramid progress for the week (cells that moved, from `account_alphas` this quarter), drafts
   approved vs `card_target`, submissions vs `submit_target`, and the pace lines from `goals_view`.
2. `planner.propose()` for the next week from evidence: tracker cells still empty, the retry list and dead ends from
   the last PLAN, near misses with tries left; never push filler (combined performance is a Genius bar).
3. BRAIN_RULES items: front-load quality submissions before 1 Dec (G8), USA D0 default TOP1000 (S-8), the pending
   decision on plan order (guide vs multiplier: ask Zacc).
4. A Friday checklist on the Ideas app's Week page (download account -> rebuild knowledge pack -> copy DIGEST -> paste PLAN).
5. Tests + apps smoke test; update the cheat sheet.

Phases after: 5 learning loop (scan candidates, near-misses, inverted, dead ends,
source quality, digest); 6 AI layer over Claude Code (P3 critic first, then P2 writer, P1 extractor, P4 weekly
review); 7 collectors (Open Source Asset Pricing import, arXiv, news RSS); then a SuperAlpha builder once
Zacc reaches 100 lifetime alphas.

## Standing rule: a cheat sheet after every phase
When a phase is complete (tests pass, apps checked), update the **HYPOLAB cheat sheet** doc
(https://claude.ai/code/artifact/37656bd4-b770-4e7c-b83e-83c57ae4eb28): bump the version and phase line, add the
new screens/commands/numbers, keep it to one page, and say what changed at the top. Phases: 1-2 done (+ 1.3.2 BRAIN rules); 3 card form +
Projects import/export (done, 1.5.0); 4 Friday review (done, second-line 1.6.0, screens in 1.8.0); 5 learning loop (done, 1.8.0); 6 AI layer (mostly covered by the Claude Projects kit and the daily brief);
7 collectors (done, 1.9.0); 8 SuperAlpha builder (done, 1.10.0; live at 100 lifetime alphas); whole-system review
(1.10.1).

## Practical notes for the next session
- marimo **0.23.16** was used. Read the "marimo gotcha" paragraph in Phase 3 before rebuilding UI elements in a cell.
  Tables select rows by the checkbox; `mo.state` holds cross-cell results; a
  `run_button` + `mo.stop(not btn.value)` guards anything that spends simulations.
- The Ideas app is tested with Starlette's TestClient (needs `httpx`; `tests/test_ideaweb.py`); screens were also
  checked with Playwright against `python -m ideaweb` on a populated journal.
- Check UI changes headlessly: `marimo export html apps/X.py` must show no `"ename"` other than
  `ancestor-stopped` (that is what `tests/test_apps.py` does). For clicks, Playwright + Chromium at
  `/opt/pw-browsers` worked; a tiny fake BRAIN server (see `tests/test_connect.py`) tests the login flow.
- Measured on a 2-core, 8 GB box (T470s-like), sandbox: cockpit ~0.8 GB, a scan session ~1 GB, a simulation
  click-to-verdict ~1 s. Live speed is bound by BRAIN, not the UI.
- Lint: `ruff check --select F,E9 hypolab ideaengine ideaweb` must be clean (an unused-variable note caught a
  missing `f` in a knowledge-pack string during the 1.8.1 review). Full suite: `python tests/run_all.py` (~5 min on 2
  cores, one process per file; `python tests/run_all.py phase8 web` runs only matching files).
- Nothing has been run against the real BRAIN API in these sessions; the first live login and sync is Zacc's.
