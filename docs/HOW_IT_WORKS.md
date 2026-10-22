# How hypolab works

```
 hypothesis card ──► bind to YOUR data ──► lint ──► simulate ──► diagnose ──► (climb ladder | flip | stop)
 (library/*.yaml)    (catalog + concepts)  (Gold     (BRAIN or     (one next                │
                                            ops)     sandbox)      action)                  ▼
                                                                          robustness ──► gate ──► you submit
 journal.sqlite records every step  ◄───────────────────────────────────────────────────────────┘
 pyramid planner reads your diversity and steers which ideas are generated next
```

## 1. Hypothesis cards: `hypolab/library/hypotheses.yaml`
A card is an *idea*, not a formula. Each card has:

| Field | What it holds |
|---|---|
| `story` | The mechanism: who makes the mistake and why prices adjust slowly. |
| `why_persists` | Why it hasn't been arbitraged away. |
| `references` | Papers, so you can read the original. |
| `roles` | Data *concepts* the idea needs, e.g. `est_eps` or `cfo`, rather than field names. That's what makes one card work in every region. |
| `ladder` | 2–4 rungs from simplest to refined. Each rung teaches one thing. You climb only when the diagnosis says so. |
| `settings`, `expected_turnover`, `watch_out` | Defaults, the turnover range to expect, and known traps. |

The 47 cards cover all 13 Pyramid categories. Add your own in the same format; `validate_library()` checks them.

## 2. Binding: `catalog.py`, `concepts.py`, `ideas.py`
- The catalog (SQLite) holds every dataset and field for each region/universe/delay you sync. The GLB snapshot from
  your zip is bundled.
- Each field gets a *nature*: estimate, flow, stock, ratio, price, count, flag, identifier, date…
- Each field also gets matched to about 70 *concepts* by its id and description.
- A card's roles are filled with the best-matching, best-covered, least-crowded fields.
- Paired roles (e.g. revisions up/down) must come from mirrored fields.
- Ideas are ranked by:
  - the card's strength;
  - how well the data fits, and its coverage;
  - crowding (how many alphas already use the field);
  - which **Pyramid cells you still need**;
  - what your journal says you've already done.

## 3. Linter: `linter.py`
It blocks, *before spending a simulation*:
- operators not on your Gold PDF;
- wrong arity, or positional use of named-only parameters;
- vector fields used without `vec_*`;
- IDs or dates used as signals;
- unused variables.

It warns about:
- low coverage;
- arbitrary or too-short windows on quarterly data;
- deep nesting;
- too many fields;
- unbounded outputs.

## 4. Simulate: `brain.py` (live) or `mock.py` + `sandbox/` (offline)
- `BrainClient` logs in (including biometric/persona), retries on 429/5xx, polls `Retry-After`, batches
  multi-simulations (2–10), and runs at most 3 concurrent requests.
- **Submitting requires typing `SUBMIT <alpha_id>`.**
- The sandbox is a synthetic 500-stock, 6-year market with planted effects (value, quality, revisions, PEAD,
  reversal, sentiment, low-vol) and 40 pure-noise fields. A full FastExpression evaluator and a BRAIN-like backtester
  with the same checks run on it.

## 5. Diagnosis: `diagnose.py`
Every result gets a verdict and *one* recommended next action:

| Verdict | Meaning | Next action |
|---|---|---|
| ERROR | the platform error, translated | the fix |
| INVERTED | strongly negative | flip only if the reverse mechanism makes sense |
| NOISE | \|Sharpe\| < ~0.5 | stop; next idea |
| WEAK | some signal, far from the bar | next rung, or a second independent leg |
| NEAR | close to the bar, e.g. fitness-bound | economic decay, etc. Uses fitness arithmetic: decay can't help below 12.5% turnover |
| PASS | clears the bar | robustness, then the gate |

## 5a. Boosting a weak alpha: `research.boost()`
A Sharpe around 1.0 is often a real but weak signal. `R.boost(result)` adds **one independent second signal**:
- Candidates are other idea cards, from a *different data category* first, each tested alone (a normal, journaled
  test of that idea).
- It measures the PnL correlation with your alpha and **predicts** the combined Sharpe:
  (S1 + S2) / √(2·(1 + ρ)). On the sandbox this predicted 1.39 vs an actual 1.39, and 2.41 vs 2.46.
- It refuses boosters with no signal of their own, boosters too correlated with yours (ρ > 0.7), predicted gains
  under 10%, and boosters that are better *alone* than the combination (the combination would really be their alpha).
- A fast booster on a slow alpha is smoothed over a month so its trading doesn't wreck fitness.
- Combination: `rank(base) + rank(booster)`, or `mode="and"` for `min(rank(base), rank(booster))`.
- Every combination counts as a try on the base idea, so the gate's deflated Sharpe reflects the search.

Sandbox example: gross profitability, Sharpe 1.02 (WEAK), plus a month-smoothed revision-breadth signal
(ρ = 0.03) gives Sharpe 2.34, fitness 2.01, and passes the gate.

Seeing what a boost made (1.4.3): combinations are journaled as `<rung> + boost:<card>`; the report keeps each
booster's solo result (`report.boosters`), and `report.lab_results()` is what the cockpit's Lab adds to its list
(boosters alone, then combinations, the best last so it is selected). `R.performance(result, compare=...)` reads the
cumulative PnL and yearly table (no simulation); the Lab draws the best combination against its base and booster.

## 5b. Dataset scans: `research.scan()`
- Probes every usable field of one dataset once, with the lens that fits its nature, as one batched multi-simulation.
- Prints a **noise bar**: the |Sharpe| that the best of N pure-noise probes beats only 5% of the time. The noise spread
  is the larger of 1/√years and the scan's own robust spread, because real noise has fat tails.
- Every probe is journaled under the dataset's family. An alpha later built from a scanned field is deflated by the
  number of fields scanned.
- This is where BRAIN's expected simulation volume (1000+) is spent best: learning data, not polishing one formula.

## 6. Validation: `robustness.py`, `overfit.py`, `research.gate()`
- **Robustness battery:** rank, binary, winsorize, window ±15%, neighbouring neutralization, liquid universe.
- **Gate:**
  - platform `/check`;
  - self-correlation against your submitted alphas;
  - **production correlation** against BRAIN's pool. This is the originality test: a textbook or copied idea fails
    here however good its Sharpe;
  - train vs test Sharpe;
  - **deflated Sharpe**, using the number of tries the journal recorded for this idea (or the whole dataset scan);
  - robustness score;
  - an auto-written description (idea, data rationale, operator rationale, reference).

## 7. Journal and Pyramids: `journal.py`, `pyramids.py`
- The journal runs in SQLite WAL mode, so the cockpit (and the Idea Engine) can read it while another app writes.
  `Journal.open_readonly()` opens it without the right to write.
- The journal remembers every simulation (with dedupe by canonical expression and settings), every submission and
  every lesson.
- The Pyramid tracker counts **this quarter's** submitted alphas (Genius counts per quarter): from the Account tab
  download, each alpha is placed in every category its fields belong to (or BRAIN's own Pyramid tags when an alpha
  carries them). Without a download it falls back to `/users/{id}/activities/diversity` (all time) or the journal.
  It builds:
  - a region × category matrix;
  - the cells you still need, per delay, in the guide's order or by Pyramid theme multiplier (live from BRAIN, else
    the bundled 2026-Q4 snapshot in `data/pyramid_multipliers_2026Q4.json`); cells BRAIN doesn't offer are left out;
  - a daily plan with the guide's recommended datasets.

## 7a. BRAIN's rules: `rules.py` and `docs/BRAIN_RULES.md` (1.3.2)
- `docs/BRAIN_RULES.md` lists every rule read from BRAIN's own pages, with source, conflicts and HYPOLAB's status.
  It also goes into the knowledge pack as `09_brain_rules.md`.
- `rules.py` holds the numbers: the **single-dataset test** (fields from one dataset, grouping fields excepted ->
  last-2-year Sharpe >= 2.38 at D1 / 3.96 at D0 instead of the IS ladder), the **sub-universe cutoff**
  (0.75 × √(sub/size) × Sharpe), **Fitness labels**, **BRAIN's day** (New York midnight) and the **Osmosis lock
  deadline**. Every ladder rung and every result shows which IS test applies.
- `brain.record_quota()` saves BRAIN's `X-Ratelimit-*` headers after each simulation; the Lab shows the real
  remaining count and HYPOLAB stops at 0.
- `BrainClient.sync_simulation_options()` saves each region's universes, delays and neutralizations (incl. the risk
  sets SLOW / FAST / SLOW_AND_FAST / REVERSION_AND_MOMENTUM / STATISTICAL / CROWDING) to
  `~/.hypolab/sim_options.json`; the Lab offers exactly those. DEU and GBR need this before their first simulation.
- `account.py` adds the Genius views: `tiebreakers()`, `quarter_pyramids()`, `osmosis_check()`.
- `Researcher.rerun(alpha, variants)` re-simulates a submitted alpha with risk sets or at D0; every try counts
  against `rerun:<alpha_id>` and still has to pass the gate.

## 8. Idea Engine and the screens: `ideaengine/`, `ideaweb/` (and the old `apps/`)
HYPOLAB tests ideas; the Idea Engine decides what is worth testing. They meet in two places only:
- **Your card files** (`~/.hypolab/library/*.yaml`): `load_library()` loads them after the built-in library and
  marks them `source = "mine"`. A clashing id or a broken file is skipped and listed in `hypotheses.LOAD_WARNINGS`.
- **The journal**: the Idea Engine reads it to measure the week and (later) to find near-misses and scan candidates.

`ideaengine/` today: `store.py` (quarter goals, weekly plans and drafts in `ideas.sqlite`), `planner.py` (ISO weeks, the
starting plan, pace toward the Expert bars, daily submission cap and SuperAlpha unlock), `drafts.py` (phase 3, see
section 12), `views.py` (tables and charts for the pages), `connection.py` (opens HYPOLAB without ever prompting), and since
1.8.0-1.9.0 the Friday review (section 15), the learning loop (section 16) and the collectors (section 18).

Since 1.16.0 the screen is **the web app** (`ideaweb/`, section 24), on the laptop and the tablet. The three
marimo apps below still run on the laptop for comparison (`python -m hypolab cockpit`):
- `apps/cockpit.py`: Lab, Pyramids, Play, SuperAlpha (1.10.0, section 19), Journal, Account, Data, Setup (1.7.0: Week, Cards and Drafts moved to the Ideas web app, section 14). Setup logs in with `connect.begin_login` / `connect.finish_login`, so a face scan is a link plus a button, never a hidden prompt.
- `apps/dataset_scan.py`: dataset explore and scan, separate so a long live scan never blocks the cockpit.
- `apps/quant_basics.py`: the quant-basics course on the practice market.

In sandbox mode each app has its own in-memory practice journal; in live mode all of them share `~/.hypolab/journal.sqlite`.
`Researcher.card(id, region)` builds the one card the Lab works on. Every simulation is behind a run button, and
submitting needs the gate's READY plus the typed `SUBMIT <alpha_id>`.

## 9. Play: `play.py` (1.4.0)
- `roll()` makes random alphas for free: random idea cards (any family, the Pyramid plan ignored) or wild rolls (a
  random field, or two fields of one dataset, in a random template), linted, with optional shuffled settings and a
  seed to reproduce a roll. `Researcher.play()` simulates them as purpose `play`; each roll counts as a try for its
  `play:...` idea, so the gate's deflated Sharpe knows how many dice were thrown. Cockpit tab **Play**.

## 10. Binning noise cards (1.4.3)
`R.bin(card_id, reason)` puts a card in the journal's `binned` table: it disappears from `R.ideas()` (and so from
boosters), `R.roll()`, the Ideas app's Cards ranking, the Lab's list, and "Restore results". `R.restore(card_id)` brings it
back; nothing is ever deleted. In the cockpit: **Cards > Bin this card** and **The bin**; in the Lab, **Bin card**.

## 11. Speed on a small laptop (1.4.3)
Concept matching and field enrichment for a region are computed once and cached in `~/.hypolab/cache/` (rebuilt
automatically after a catalog sync or a change to the concept rules). 1.7.0 removed the digital rain, glows, scanlines and animations, and closed sessions are freed after 15 minutes
(`session_ttl_seconds`, each kept session holds ~0.8 GB).

## 12. Writing cards: `ideaengine/drafts.py` (phase 3, 1.5.0)
A draft IS a HYPOLAB card, kept in `ideas.sqlite` table `drafts` with a state: **draft** (a check fails or it was
never checked), **checked** (every check passes), **approved** (appended to `~/.hypolab/library/my_cards.yaml`),
**binned** (set aside with a reason; restore puts it back to draft).
- `form_defaults(card)` / `card_from_form(values, base)`: the cockpit form and back. Keys the form does not show
  (role `categories`, `pair_with`, `type`, `min_coverage`, a rung's `when`, `beginner` ...) are kept from the base
  card; all 47 built-in cards survive the round trip unchanged (tested).
- `parse_cards(text)`: pasted CARDs (code fences and `# from:` lines are fine, several cards at once); a VERDICT or a
  PLAN pasted in the wrong box is recognised. 1.10.3: each card takes the last `# from:` line above it since the
  previous card; dangling, repeated or missing comments come back as `Parsed.warnings`.
- `check_card(card, catalog, region, journal=...)`, no simulation: required fields and types; id format and
  **clash with any library id** (error); category, horizon, strength, family; concepts exist (with "did you mean");
  `validate_library` (syntax, placeholders, Gold operator errors); linter warnings (odd windows, unbounded output);
  field ids written directly (warning); a **dry-run binding** with `build_card` in the region, each rung's IS test
  (single dataset 2.38 or IS ladder), or which role found no field; same family / same concepts in the library;
  the journal's record for the family (dead end = 5+ tries, none WEAK or better).
- `Drafts(store)`: `save` (rename-aware), `bin`, `restore`, `attach_verdict` (the Critic's block; advice only),
  `approve` (refuses errors; `append_to_my_cards` writes atomically, keeps `.bak`, refuses duplicate ids and anything
  that would not load back).
- Hand-offs: `critic_message` (card + checks + dry run as YAML comments), `digest(journal, store, week)` (the Friday
  DIGEST), `parse_plan` / `apply_plan` (the Reviewer's PLAN: saved for its week with retry / dead ends / lessons;
  lessons and dead ends go to the journal once), `rebuild_knowledge_pack()`.
- Concepts added for the theme datasets: `pretax_income`, `income_tax`, `esg_score`, `credit_spread`,
  `management_change`.

## 13. Correlation: `decorr.py` (1.6.0)
- **Read early, for free.** BRAIN shows the production correlation (max / min vs the pool) right after a simulation.
  `R.correlation(alpha_id, "prod")` reads it without a simulation and keeps it a day in the journal table
  `correlations`; the Lab's **Read production correlation** button does this.
- **BRAIN's check is the authority.** `decorr.corr_status(checks, prod)` reads the SELF / PROD / Power Pool
  correlation rows of BRAIN's checks first (PASS, FAIL, PENDING); HYPOLAB's own reading of the maximum is only used
  when BRAIN has not answered (shown as `FAIL?` / `PASS?`). The gate follows it, so an alpha BRAIN passes at 0.75 is
  never blocked by HYPOLAB, and a PENDING check means "press Check Submission, then re-run the gate".
- **Theme hints.** `decorr.theme_hints(checks)` turns BRAIN warnings like "Theme GLB/D1 Risk Handled Crowding
  Factors/Fast Factors Theme does not match with multiplier of 2.5" into a neutralization (CROWDING / FAST ...).
  Diagnose adds it as an action for any alpha with real signal; it can earn the multiplier and lower correlation at
  once.
- **Lower correlation, keep the signal.** `R.decorrelate(result, k=4)`: measures PnL correlation with five crowded
  style proxies (momentum, reversal, size, low volatility, a value proxy; simulated once per region and
  neutralization, then served from the journal) and with your submitted alphas (free reads); proposes at most k
  changes that keep the idea (`decorr.variants`, in order: the theme's risk set, removing the style it resembles -
  `group_neutralize(x, bucket(style, ...))`, Gold-only -, an equivalent field with fewer alphas, a CROWDING/SLOW
  risk set, a shorter horizon - ts_backfill windows are never touched -, removing overlap with your own alpha,
  another peer group); simulates them as purpose `decorr` (each counts as a try, so the deflated Sharpe stays
  honest); reads each one's production correlation; recommends the highest Sharpe under the limit that keeps
  >= 60% of the original - never a copy - and says what the attempt teaches.
- **Learning.** Measured production correlation per family (`decorr.family_prod_corr`) lowers a family's cards in
  the ranking and warns in the Drafts checks when its median is >= 0.7; textbook families get a note.

## 14. The Ideas web app: `ideaweb/` (1.7.0)
Forms fought marimo (stale inputs after a rebuild, tables crashing when rows appeared, checks re-running per
keystroke), so the idea side is a small Starlette app with server-rendered pages (`ideaweb/templates`, plain CSS,
one script for live checks and copy buttons). It reuses the same Python: `generate_ideas`, `ideaengine.drafts`
(form <-> card, checks, approve), `planner`, `decorr.crowding_prior`.
- Writes: `ideas.sqlite` (plans, goals, drafts), `my_cards.yaml` (Approve), the journal's `binned` and `lessons`
  tables, `lab_inbox.json` (Send to the Lab, `ideaengine.handoff`). It never simulates and never logs in to BRAIN.
- The field list is loaded only when a page needs it (Cards ranking, a draft's dry run); in sandbox mode it builds the
  practice market's catalog in memory.
- `POST /api/check` returns the checks panel, the YAML and the Critic message for the editor's live check.
- Start: `python -m hypolab web` (since 1.16.0 every page; `ideas` is the old name). `python -m hypolab cockpit` adds
  the old marimo screens next to it.

## 15. The Friday review and batch-5 rules (phase 4, 1.8.0)
- `planner.evidence(journal, store, week, tracker)`: retry list (last PLAN + near misses with tries left), dead ends
  (last PLAN + families with 5+ tries and nothing WEAK or better), the closest Pyramid cells, active BRAIN themes
  (`data/themes.json`) and dated warnings (last month of the quarter; Osmosis lock deadline). The Ideas app's Week page shows it;
  the DIGEST carries it with the Pyramid cells that moved this week. In the Ideas app: Week page, "What the week has to
  respect", the Friday checklist (`planner.friday_checklist`) and "Text for the HYPOLAB state doc".
- `drafts.state_text(...)`: the same facts as markdown for the HYPOLAB state doc that the daily alpha brief reads.
- `rules.pyramid_check` (an alpha counts in at most 2 Pyramids), `rules.power_pool_shape` (<= 8 operators, <= 3
  fields), `rules.recommended_neutralization`, `rules.self_corr_exception` (Sharpe 10% above every correlated alpha),
  `rules.RA_UNIVERSES` (Region Agnostic Alphas). Cards, boosts and the gate report them.
- `R.follow()` / `R.boost()` keep the region, universe and delay of the result they start from.

## 16. The learning loop (phase 5, 1.8.0)
Two layers, so HYPOLAB never depends on the Idea Engine:
- **`hypolab/learning.py`** reads the journal (sandbox rows never count, except in the sandbox's own in-memory journal):
  `idea_summary` (tries, best verdict per idea), `near_misses` (NEAR, or WEAK with Sharpe >= 1; `at_budget` = no tries
  left), `inverted` (INVERTED with no later positive result), `dead_end_families` (5+ tries, nothing WEAK or better),
  `scan_candidates` (scan probes above the scan's own noise bar, recomputed per dataset/region/universe/delay, whose
  field no other experiment has used since), `check_failures` (failed checks by region and data category),
  `transfers` (NEAR/PASS in one region, never tried in another; never from or to SBX) and `card_adjustments`.
  `planner.near_misses` / `dead_end_families` now call it, so there is one rule everywhere.
- **`ideaengine/learn.py`** turns the facts into action - on the Ideas app's **Leads** page (`/leads`; Make a draft,
  Send to the Lab via `lab_inbox.json`, Skip, Show it again): `items()` (the inbox: sibling > near miss > scan > transfer >
  inverted; your skip/drafted decisions are kept in `ideas.sqlite` table `inbox` and expire when the evidence
  changes), `sibling_draft()` (the card under a new id with the evidence written into the story and watch_out),
  `scan_draft()` (a card skeleton for the field: `{x}` role, the probe as rung 1, sign from the scan; `why_persists`
  is left empty on purpose - you write the mechanism or bin it), `source_quality()` (built-in, daily brief, Scout &
  Writer, your own, your copies, inbox, lens probes, play: ideas tried, share reaching NEAR or PASS within the trial
  budget, submitted) and `digest()` / `digest_json()` (<= 2.2 KB for the Weekly Reviewer).
- **Ranking** (`ideas._score`): value score of the bound datasets +0.3 per point above 2 (-0.3 to +1.2), Pyramid
  multiplier +0.75 x (m - 1), dead-end family -2.0, near miss here with tries left +0.5, works in another region and
  untried here +1.0. Each adds a note on the card. The Data tab sorts datasets by value score.
- **Hand-offs**: the DIGEST adds a "learning loop" section and the JSON block; the state doc text adds "Leads from the
  journal" (the daily brief may write one idea a day from them); `07_dead_ends.md` adds a Leads table (Scout & Writer
  now reads it); `check_card` adds your own failed-check patterns for the card's region and categories.

## 17. What the 1.8.1 review changed in behaviour
- **Delay 0 is kept everywhere** (`rules.delay_of`): D0 alphas are re-run, diagnosed and counted in D0 Pyramid cells.
- **Binding falls back to another universe of the same region** (`ideas.data_universe`): when the default universe
  has no downloaded field list (EUR TOP800 during the theme), fields come from e.g. EUR TOP2500 and the card says so;
  the simulation still runs on the default universe.
- **Robustness**: the "liquid universe" variant is only a SMALLER TOPn than yours; a variant that could not run
  (blocked by the linter or BRAIN) is "not run", not a failure; all variants go to BRAIN as one multi-simulation.
- **Diagnosis**: a WEAK result with a negative Sharpe says "flip once, only with a reason" first.
- **Submit**: if BRAIN refuses, nothing is journaled and you see BRAIN's reason.
- **Lower correlation** keeps multi-statement alphas valid (the wrapper goes on the final value).
- **Repeated dataset scans** are answered from the journal (same fields, same lenses, no new simulations).
- **Ideas app**: the Week page warns when goals belong to an old quarter; saving goals stamps the current quarter; form
  POSTs from other web sites are refused.

## 18. Collectors: outside sources of ideas (phase 7, 1.9.0; reviewed in 1.9.1)
Design v2's last phase: material from outside the journal, kept as an inbox, never as cards.
- **`ideaengine/collectors.py`** reads four kinds of source into plain items (parsing is separate from fetching, so a
  page you saved yourself works too, and the tests need no network):
  - **Open Source Asset Pricing** (Chen & Zimmermann): their signal list `SignalDoc.csv` is bundled
    (`data/osap_SignalDoc.csv.gz`, GPL-2.0, see `data/OSAP_NOTICE.md`): 212 published predictors with paper, sign,
    t-stat and definition. "Download the latest" fetches the current one from GitHub.
  - **arXiv q-fin** (PM, ST, TR, GN; settings `arxiv_categories`): the newest 100 papers from arXiv's API, kept when
    the title and abstract look cross-sectional (stock returns, anomalies, analysts, earnings ...) and dropped for
    option pricing, crypto, market making and the like (`arxiv_relevance`).
  - **News RSS** (settings `collector_feeds`; MarketWatch, Nasdaq earnings, Yahoo Finance, Euronews business and City
    AM by default; downloaded as bytes so each feed's own encoding is used): headlines are never stored one by one.
    16 themes (guidance cuts, earnings surprises, rating changes, buybacks, issuance, M&A, short sellers, insiders,
    CEO exits, rates, tariffs, credit stress, layoffs, capex, index changes) group them per ISO week; a theme is
    listed once it has 2+ headlines that week, later fetches add to it, and it leaves the new list after 14 days.
    **Mute this theme** leaves a theme out from then on (settings `news_muted_themes`; rates and inflation is muted by
    default - it fires daily and says little about one stock against another).
  - **Under-used datasets** in the field lists you downloaded: value score >= 3, at most 2,000 alphas, coverage >= 30%,
    and no simulation in your journal has touched them (theme priority datasets are flagged). One item per region and
    dataset (Delay-1 preferred); a dataset you use later leaves the new list at the next run.
- **`ideaengine/sources.py`** keeps them in `ideas.sqlite` (tables `sources`, `collector_runs`): each item is tagged
  with the HYPOLAB concepts its text mentions and the BRAIN categories they suggest, marked **covered** when a card in
  your library cites the same paper (first author, second author when both name one, year), scored (OSAP: t-stat,
  predictability, replication; arXiv: relevance; news: headline count; datasets: value score and crowding; covered
  -1.5) and ranked for this week's plan (its categories +2.0). The list mixes the kinds - the best of each kind first,
  then the second of each - so 212 published predictors cannot bury a new paper. "Same paper as" is refreshed when
  your library changes. Your decision (skipped / drafted, note) survives re-collecting. Downloads run in a worker
  thread, so the Ideas app stays responsive while a feed is slow.
- **Actions** (Ideas app, **Leads › From outside**; nothing simulates): **Copy for Scout & Writer** (the SOURCE block,
  format in `claude_projects/README.md`) - its cards come back with `# from: S-<kind>-<key>`, and importing one marks
  the source drafted; **Make a draft** (`source_draft`): a skeleton with the citation as reference and the mentioned
  concepts as roles, the mechanism and rung 1 left empty so the checks keep it a draft until you write them; **Skip**;
  **Add a source by hand** (an SSRN abstract, a forum post).
- **Hand-offs**: Source quality has "outside: ..." buckets per kind; the DIGEST and the learning digest count the
  inbox; the state-doc text adds "Fresh outside sources" (5 numbered rows, kinds mixed, no news - the daily brief uses
  row N on weekday N, so a week sees five different sources); the knowledge pack adds
  `10_published_predictors.md` (OSAP predictors no card covers, and the ones a card does) for Scout & Writer and the
  Critic.
- Terminal: `python -m hypolab collect osap|arxiv|news|datasets|all|list [--file SAVED_PAGE] [--download]`.

## 19. SuperAlphas (phase 8, 1.10.0)
A SuperAlpha is built from alphas you have already **submitted** in one region and delay. Two expressions:
- the **selection** is computed once per submitted alpha from its properties (turnover, self- and production
  correlation, operator count, data categories, long/short counts ...); BRAIN keeps the best `selectionLimit` (at
  least 10). With `POSITIVE` handling only scores above 0 count, so a selection written as a product of conditions
  drops an alpha by scoring it 0;
- the **combo** weights each kept alpha every day (`1` = equal weight; `stats = generate_stats(alpha); ...` reads the
  alpha's own returns, e.g. inverse volatility or a rolling information ratio).

BRAIN unlocks SuperAlphas after 100 submitted alphas and takes one a day, on top of the 4 alphas. The cockpit's
**SuperAlpha** tab (`hypolab/superalpha.py`, `Researcher.super_test / super_gate / super_submit`):
1. **Your pools**: submitted alphas per region and delay (from the Account download), how varied they are, whether a
   SuperAlpha can be built (10+), and a suggested limit (about two thirds of the pool).
2. **Build one**: pick a selection recipe and a weighting recipe - each says why it exists - or write your own. The
   checks run as you type (syntax, settings, names BRAIN's examples use - unknown names only warn, BRAIN decides) and
   a preview shows which of your alphas the selection keeps, when HYPOLAB knows the properties it needs.
3. **Simulate** spends one simulation. Same guard rails as an alpha: never twice the same SuperAlpha, 10 tries per
   pool per quarter (`max_super_sims_per_pool`), the daily guard, BRAIN's quota, and locked until the unlock.
4. **Diagnose**: BRAIN's checks decide the verdict; the next step is ONE change - raise the decay when turnover is
   above 40%, select 'Least correlated' when a correlation check fails, go back to Equal weight when the test period
   collapses, try another weighting when the Sharpe is weak.
5. **The SuperAlpha gate** (BRAIN's checks, correlations, the 2%-40% turnover band, the deflated Sharpe over every
   try on the pool, train vs test, the lock and today's SuperAlpha) and a typed `SUBMIT <id>`.

The request format and several limits come from community code built against the live API, not from BRAIN's pages:
BRAIN_RULES section 13 marks them "verify live". In the sandbox, **Build a practice pool** submits about 20 practice
alphas so the whole flow can be rehearsed now; its numbers are synthetic and easy to pass.

## 20. What the 1.10.1 review changed (the whole system, 20 Oct)
- **Settings hold only your choices.** `config.save_settings` used to write every default into `settings.json`, so a
  default changed in a later release never reached an existing user. Now `settings.json` keeps only the keys you set
  (marked `_settings_version: 2`; an older whole file is reduced to its non-default keys once), and
  `settings.defaults.json` lists the defaults for reference. The unused `pyramid_regions` / `single_country_region`
  are gone; `state_doc_url` is new (the Week page's link).
- **One meaning of "tries"**: `learning.TRY_PURPOSES` (explore, boost, decorr) is used by the Journal tab, the DIGEST,
  the Drafts family check and the learning loop alike (before, three of them left out Lower-correlation tries).
- **One lifetime count**: `planner.lifetime_submitted` takes the larger of (the number on the Week page + HYPOLAB's
  submissions since) and (BRAIN's count from the Account download + HYPOLAB's submissions since). The Week page,
  SuperAlpha tab, DIGEST, state doc and `06_goals_and_rules.md` all show it.
- **SuperAlphas everywhere they matter**: the Week page shows today's SuperAlpha (x/1) once unlocked; the DIGEST has a
  `superalphas:` line and leaves SuperAlpha simulations out of the alpha statistics; the weekly "submitted" count is
  alphas only (SuperAlphas separate). The sandbox Pyramids tab no longer crashes after a practice SuperAlpha.
- **Faster pages**: `learning.live_experiments` is cached on the journal object until SQLite's `data_version` or the
  connection's change count moves (the Week page asked for it a dozen times per load).
- **The knowledge pack names what changed**: a file is rewritten only when its content changed (the date line alone is
  not a change); `INDEX.md` records the rebuild time and the changed files; the Drafts page says which files go to
  which project. The Friday checklist reads INDEX.md's date.
- **Weekly ceiling**: the Week form caps "alphas to submit" at the daily cap x 5 (20), like a pasted PLAN.
- **Tests one file at a time**: `python tests/run_all.py` (each file in its own process with its own `HYPOLAB_HOME`;
  `setup_arch.sh` uses it - the one-process run peaks near 6 GB). `pip install -e ".[cockpit,test]"` adds httpx so
  the Ideas app's tests run instead of being skipped.
- Cockpit: the Lab's never-shown field-download button is gone (download on the Data tab); the SuperAlpha tab no
  longer fails before the Account tab has saved a region's universes; the Setup tab's daily routine names the Ideas
  app's pages; Restore results counts Lower-correlation simulations too.
- The Claude Projects' instructions (`claude_projects/`) match the 1.10.x hand-offs: `# from:` conventions, SuperAlphas
  stay in HYPOLAB, the DIGEST's contents, the PLAN's 20-a-week ceiling, the knowledge files each project needs.
- Plain-words guide to every capability: `docs/USER_GUIDE.md`.

## 21. Submissions fail closed (1.10.2, 20 Oct)
Three findings Zacc reproduced offline, fixed and covered by `tests/test_review_1102.py`:
- **The gate cannot be bypassed.** `R.gate()` / `R.super_gate()` record each report they issue (token, alpha, kind,
  READY or not, time). `R.submit()` / `R.super_submit()` accept only a report recorded READY by this Researcher, for
  the same alpha and kind, issued within `gate_max_age_minutes` (30), and each report once. Setting `gate.ready = True`
  or building a `GateReport` by hand changes nothing. `force` lifts only the daily cap (and the SuperAlpha lock), never
  the gate.
- **Missing evidence is never a pass.** An empty /check answer, a self or production correlation with neither a BRAIN
  check row nor a reading, a deflated Sharpe that cannot be computed, a missing train/test split (and a train Sharpe of
  0, which 1.10.1 skipped as if missing) or a SuperAlpha without turnover each keep the gate NOT READY, with the reason
  named. Power Pool correlation stays informational.
- **No blind retries of actions.** `BrainClient._req` repeats GET/PUT/PATCH/DELETE as before, but a POST (a simulation,
  a submission) only when BRAIN certainly did not act: the connection was never made, 401 (log in, send again) or 429.
  A read timeout, a dropped connection or a 5xx raises `UncertainOutcome`. A simulation then comes back as `UNCERTAIN`
  (journaled as an error, never served as a result, with a note to look on BRAIN before simulating again); a
  submission is checked by reading the alpha back (`dateSubmitted` = submitted and recorded; otherwise the outcome is
  reported unknown and nothing is recorded or re-sent). How BRAIN itself behaves after a lost answer is still
  unverified live.

## 22. The idea team's paste boxes (1.10.3, 20 Oct)
The Claude chats (agent pack v3: Scout & Writer, Critic, Weekly Reviewer, the daily brief) are prompts, not programs;
their output is checked only where Zacc pastes it. 1.10.3 makes those boxes lose nothing silently:
- Drafts import: `# from:` bound by position; an id that is already a waiting or binned draft is refused unless
  "This is a rewrite" is ticked; `Drafts.replace` keeps the source, clears the old verdict; every verdict is kept in
  the `verdicts` table of `ideas.sqlite`; the dry-run region is chosen on the form (default: the week's plan).
- Week page PLAN: `universe`, `delay` and unknown keys are named in the note instead of dropped.
- The loop: `learning.declared_dead_ends` / `recent_lessons` read the PLAN's dead ends and lessons from the journal's
  `lessons` table; `07_dead_ends.md`, the state doc and `check_card` (a warning) use them.
- The state doc carries the card reference (concept names, Gold operators) and the theme's priority datasets, so the
  daily brief writes importable cards from the doc alone; waiting draft ids are listed as used.
- Measuring the team: `learn._bucket` keeps `daily brief ... via S-...` as "daily brief + outside: ...";
  `learn.critic_calibration` compares the Critic's latest decision per card with NEAR/PASS within the budget (DIGEST).
- Copy for the Critic adds the week's plan and a NOTE when the dry run ran in another region.

## 23. analyst_skill (1.10.4, 22 Oct)
A new concept for forecasters' track records (anl93's per-analyst price-target accuracy and consistency, EUR):
`concepts.analyst_skill`, with a nature rule that keeps such fields numeric when their description mentions a
"horizon date", and `target_price` taught not to take them. Most are VECTOR fields: a card reduces them with `vec_*`
(`vec_avg({acc})`) and scales price-unit measures by `close`. See HANDOFF "1.10.4: analyst_skill".

## 24. The web app is HYPOLAB's main screen (1.13.0-1.16.0, 22 Oct)
The Android track (HANDOFF "Android track") ported every marimo screen to the Starlette app, so one set of pages runs
on the laptop and, inside an Android app, on the tablet.
- **Pages** (`ideaweb/templates`): Ideas = Week, Leads, Cards, Drafts (`app.py`); Lab = Lab, Play, Basics
  (`lab.py`); Records = Journal, Pyramids, SuperAlpha (`records.py`); Account = Data (with the old dataset scan),
  Account, Setup (`account.py`). Same engine calls as the marimo cells; the idea pages still never simulate.
- **One Researcher per process** (`lab.LAB`): opened with `ideaengine.connection.open_researcher()` and opened again
  when the mode or live region changes, after a login or a logout. It holds what the cockpit kept in marimo state:
  the Lab's results (stable keys, `?focus=`), boost / lower-correlation / gate reports, robustness, PnL panels,
  the Play roll, Pyramid counts, the SuperAlpha form and results, explore/scan results, messages.
- **Jobs** (`jobs.py`): every button that simulates or reads BRAIN runs one background job; the page shows a banner and
  reloads every 3 s; a second job is refused, never queued; a failure is reported, never retried; nothing starts by
  itself. Submissions still go only through `Researcher.submit()` / `super_submit()`, which hold every check.
- **Threads**: the journal, the idea store and (since 1.14.0) the catalog open SQLite with `check_same_thread=False`,
  because a Researcher opened in one thread is used by job threads.
- **One practice market per process** (`sandbox.market.shared_market`): MockBrain, the Ideas pages' sandbox catalog and
  Basics share it; its size is the setting `sandbox_stocks` (500 on the laptop, 250 on the tablet).
- **Charts** are matplotlib PNGs inlined as data URIs (`lab.fig_uri`); tables are `views.html_table`.
- **Security**: 127.0.0.1 only; `LocalOriginOnly` refuses POSTs from other sites; on Android `LaunchKey` also requires a
  per-launch secret cookie (other apps on the tablet can reach 127.0.0.1). Fonts are bundled (no Google Fonts).
- **Android** (`android/`): Kotlin + Chaquopy (Python 3.11, numpy 1.26.2, pandas 2.1.3); `hl_android.start()` sets
  HYPOLAB_HOME to the app's private files, HYPOLAB_PLATFORM=android, 250 stocks, the secret, and runs uvicorn (h11) on a
  random port; `MainActivity` shows it in a WebView with a copy / paste / share bridge. The password is never saved
  on the tablet. GitHub Actions builds the APK, signed with Zacc's key from repository secrets.

## Files you own
| File | Contents |
|---|---|
| `~/.hypolab/credentials.json` | `{"email": ..., "password": ...}`, mode 600. Or use the env vars `BRAIN_EMAIL` and `BRAIN_PASSWORD`. |
| `~/.hypolab/session.json` | Cookies only. |
| `~/.hypolab/catalog.sqlite` | Synced metadata. |
| `~/.hypolab/journal.sqlite` | Your research history. **Back this up.** |
| `~/.hypolab/settings.json` | Only the settings you changed (mode, live region, budgets ...); `settings.defaults.json` next to it lists every default. |
| `~/.hypolab/ideas.sqlite` | The Idea Engine: quarter goals, weekly plans, card drafts, Leads decisions, outside sources (1.9.0). |
| `~/.hypolab/operators.json` | BRAIN's live operator list (Account tab). |
| `~/.hypolab/cache/` | Enriched field lists per region (safe to delete; rebuilt). |
| `~/.hypolab/lab_inbox.json` | The last card sent from the Ideas app to the Lab. |
| `~/.hypolab/library/*.yaml` | Your own hypothesis cards (`my_cards.yaml` is written by Approve, `.bak` = the previous version). **Back these up.** |
