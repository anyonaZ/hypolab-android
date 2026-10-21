# HYPOLAB user guide (1.10.3)

HYPOLAB helps you find WorldQuant BRAIN alphas the way good researchers do: **an idea first, simulations second.**
You start from a reason why some stocks should beat others, HYPOLAB turns that reason into an expression on *your*
BRAIN data, checks it before it costs a simulation, tells you what each result means and what to try next, counts
every try so luck is not mistaken for skill, and only then lets you submit - by hand.

This guide lists everything the system can do, screen by screen, in plain words. Technical detail lives in
`docs/HOW_IT_WORKS.md`; BRAIN's own rules, with sources, in `docs/BRAIN_RULES.md`; where the project stands in
`HANDOFF.md`.

---

## 1. The big picture

HYPOLAB has three parts that pass work to each other:

| Part | Where | What it is for | Does it simulate? |
|---|---|---|---|
| **Ideas app** | browser, http://127.0.0.1:2719 | Plan the week, find and write ideas (cards), review the week | Never |
| **Cockpit** and two helper apps | browser, http://127.0.0.1:2718 | Test, improve, validate and submit alphas; Pyramids; SuperAlphas; your account | Yes, always behind a button |
| **The idea team** | your Claude Projects + a daily scheduled brief | Read sources, write cards, criticise them, plan the next week | No - and HYPOLAB never calls an AI itself |

The idea team cannot talk to HYPOLAB or to each other: **you carry every message** by copying and pasting. Each
message has a fixed format (CARD, VERDICT, SOURCE, BRIEF, DIGEST, PLAN), so pasting always works.

### What the AI never does
The Claude Projects write *hypotheses*: the story, the mechanism, which kinds of data it needs (concept roles) and a
short ladder of formulas with placeholders. They never choose BRAIN field ids, never send anything to BRAIN, never
approve a card and never decide to submit. HYPOLAB picks the fields, lints, simulates and gates; you approve and submit.

### Sandbox and live
Everything starts in **sandbox mode**: an offline practice market (region `SBX`) with planted signals and 40 pure-noise
fields. You can learn the whole loop - including submitting - without touching your BRAIN account. Switch to **live**
on the cockpit's **Setup** tab when you are ready. Every app follows the switch.

---

## 2. Starting and stopping

```bash
source ~/.venvs/hypolab/bin/activate
cd ~/hypolab                      # wherever you unzipped it
python -m hypolab cockpit         # starts the Ideas app AND the marimo apps
```

Your browser opens marimo's gallery (cockpit, dataset scan, quant basics). The Ideas app runs at the same time on
port 2719; the cockpit's header links to it. Stop both with **Ctrl+C** in the terminal.

Other terminal commands (`python -m hypolab <command>`):

| Command | What it does |
|---|---|
| `status` | Mode, region, where your credentials come from, how long the BRAIN session has left |
| `login` | Asks for your email and password, checks them with BRAIN, saves them only if BRAIN accepts |
| `live USA` / `sandbox` | Switch every app to your account (in a region) or back to practice |
| `logout` | Deletes the saved credentials and session |
| `options` | The regions, universes, delays and neutralizations your account may use |
| `ideas` | Only the Ideas app |
| `collect all` | Reads outside sources into *Leads › From outside* (`osap`, `arxiv`, `news`, `datasets`, `list`) |
| `cockpit --no-ideas` | Only the marimo apps |

**If the laptop slept** and a tab says "kernel not found", HYPOLAB reloads it into a fresh session by itself. Nothing is
lost: every simulation is in the journal, and the Lab's **Restore results** brings them back. If HYPOLAB was closed
while BRAIN was still simulating, the Lab offers **Fetch them from BRAIN** - you get the results without paying again.

---

## 3. The Ideas app (port 2719) - deciding what to test

A side rail lists four pages. Nothing here simulates or talks to BRAIN.

### 3.1 Week
Your control room for the week and the quarter.
- **Quarter goals**: the Expert bars (signals, Pyramids, combined alpha performance), where you are, and how many
  per week you need from here. Edit the numbers when your Genius page changes.
- **Today**: alphas submitted today against the ceiling of 4, and the **SuperAlpha countdown** (lifetime alphas
  toward the 100 that unlock them; after the unlock: today's SuperAlpha, 0/1 or 1/1). The lifetime count is BRAIN's
  own (from the cockpit's Account download) plus whatever you submitted through HYPOLAB since.
- **This week's plan**: region, data categories, dataset focus, how many cards to approve, how many alphas to submit
  (at most 20 a week). HYPOLAB proposes one from the Pyramid guide and the evidence; you can change and save it.
- **What the week has to respect**: active BRAIN themes and their multipliers, the last month of the quarter, the
  Osmosis lock deadline, the closest Pyramid cells, near misses worth a retry, dead ends.
- **The Friday review**: **Copy the DIGEST** for the Weekly Reviewer project, then paste its **PLAN** back into
  *The Reviewer's plan*. The plan is saved for its week; its lessons and dead ends go to your journal once.
- **The Friday checklist**: account downloaded, goal numbers updated, knowledge pack rebuilt, digest copied, next
  week's plan pasted, state doc refreshed - the ones HYPOLAB can see tick themselves.
- **Text for the HYPOLAB state doc**: paste it into the state doc (link on the page); the daily alpha brief reads that
  doc every weekday at 17:55 Nairobi time.

### 3.2 Leads
Two tabs of things worth turning into cards.

**From your journal** (the learning loop) - what your own results suggest:
- *Near misses with tries left*: one more rung or a boost could get there.
- *Near misses that used their budget*: **Make a draft** opens a sibling card that changes one thing.
- *Scanned fields above the noise bar with no card*: **Make a draft**; you write the mechanism, or skip it.
- *Inverted results*: the signal works the other way round - does the reverse story make sense?
- *Transfers*: a card that worked in one region and was never tried in another - **Send to the Lab**.
- Folds underneath: **source quality** (which source of cards - built-in, the daily brief, yours, the Writer's, each
  outside source - reaches NEAR or PASS within the trial budget), the checks that fail most, dead ends, the digest.
- **Skip** hides a lead until new results change it.

**From outside** (the collectors) - fresh material, ranked for this week's plan:
- *Published predictors*: Open Source Asset Pricing's 200+ signals (bundled, no internet needed), each with its paper,
  sign and t-statistic, and whether a card already cites the paper.
- *arXiv papers*: new q-fin papers, filtered for stock-selection ideas.
- *News themes*: patterns across many firms this week (e.g. guidance cuts, buybacks), never one company's story.
  **Mute this theme** if you never want to see it.
- *Under-used datasets*: datasets in your field lists with a high value score and few alphas.
- **Copy for Scout & Writer** gives you a SOURCE block to paste into that project; **Make a draft** starts a card
  here; **Skip** (and **Show it again**); paste anything you found yourself and **Add to the inbox**. Most sources should produce no card -
  skipping is normal.
- Refresh with **Download the latest** on the page or `python -m hypolab collect all`.

### 3.3 Cards
The idea library (47 built-in cards plus yours), ranked for a region and categories. Each card shows its story first,
then why it should persist, the expected sign, the fields each role binds to in that region (coverage, crowding),
and the ladder of rungs.
- **Send to the Lab**: the cockpit's Lab picks it up (button *Pick up the card sent from Ideas*, or on start).
- **Copy into a draft**: a starting point for your own variation.
- **Bin**: hide a card you judged noise; **The bin** restores it.

### 3.4 Drafts
Where cards are written, checked and approved.
- **New card** (blank form), **copy of** an existing card, or **Import from Scout & Writer** (paste the CARD).
- Checks run as you type: the format, Gold operators only, concept names, economic windows, the fields each role binds
  to in your region (a dry run), same family as an existing card, dead ends, crowding.
- **Copy for the Critic**: the card plus HYPOLAB's checks as comment lines. Paste the Critic's **VERDICT** back on
  the draft: *keep* -> **Approve** (appends to `~/.hypolab/library/my_cards.yaml`, previous copy kept as `.bak`);
  *rewrite* -> give the fixes to the Writer and import again; *bin* -> **Bin** with the reason.
- **Rebuild the knowledge pack**: regenerates the files your Claude Projects read and tells you exactly which files
  changed and which projects need them.

---

## 4. The cockpit (port 2718) - testing and submitting

The header shows SANDBOX or LIVE and links to the Ideas app. Eight tabs:

### 4.1 Lab - test one idea at a time
1. **Pick a card** (or the card sent from Ideas), choose the **region**, read the story.
2. Choose a **rung** (or write your own expression - it is still linted, budgeted and journaled), set decay,
   neutralization (every set BRAIN offers in that region, including the risk sets), delay, truncation.
3. **Simulate** - one simulation, only when you click. Changing a control never simulates.
4. Read the **diagnosis**: a verdict and *why*, the numbers BRAIN judges (Sharpe, fitness, turnover, returns), the
   checks that failed, and the suggested next actions.

| Verdict | Meaning |
|---|---|
| PASS | Clears Sharpe and fitness: validate it |
| NEAR | Good signal, one thing short (fitness, a check): one principled fix |
| WEAK | Some signal, not enough yet |
| INVERTED | Strong signal the *other* way round: flip it only if the reverse story makes sense |
| NOISE | No reliable signal (abs Sharpe below 0.5): stop climbing this ladder |
| ERROR / BLOCKED / BUDGET | BRAIN error / stopped by the linter before costing anything / the idea used its trial budget |

Then, on the result you are looking at:
- **Follow ONE suggested action** (1 simulation): e.g. more decay for a fast signal, a peer comparison, the flip.
- **Boost**: a weak-but-real alpha plus ONE independent second signal; shows the predicted vs actual combined Sharpe.
- **Show its performance**: the PnL chart and a year-by-year table (free).
- **Read production correlation** (free): is the idea already taken in BRAIN's pool?
- **Lower correlation, keep the signal**: tries up to k principled changes in BRAIN's own order (a theme's risk set,
  removing a crowded style, an equivalent field with fewer alphas, a CROWDING/SLOW risk set, a shorter horizon...),
  reads each one's correlation, and recommends the one that keeps the most Sharpe under the limit.
- **Robustness battery** (about 7 simulations in one go): rank test, binary test, winsorizing, window twists, another
  neutralization, a liquid universe. Real signals survive most of them.
- **Gate report**: BRAIN's checks (the authority), self- and production correlation, the deflated Sharpe (corrected
  for every try on this idea), train vs test, robustness, the daily ceiling. Only a READY gate enables submitting.
- **Submit**: type `SUBMIT <alpha id>` to confirm. Permanent on live; practice in the sandbox. At most 4 a day.
- **Remove card from the Lab** or **Bin card (noise)**; tidy the results list (the journal keeps everything).

The line above the controls shows BRAIN's remaining simulation quota today (it resets at midnight New York time =
07:00/08:00 Nairobi).

### 4.2 Pyramids
A region x category heatmap of your alphas this quarter (from the Account download; BRAIN's all-time counts as a
fallback), how many alphas a Pyramid needs (3), the next cells to work on (guide order or highest multiplier first,
for delay 1 and delay 0), BRAIN's live Pyramid multipliers, and the datasets the Pyramids guide recommends per category.

### 4.3 Play
Rolling dice is free: random idea cards, or "wild" rolls (a random field from a random dataset in a random template).
Tick the ones you like and **Simulate**; send a good one to the Lab. Every roll is journaled as a try, so the gate
stays honest. A good roll is a *lead*: find its economic story before you submit.

### 4.4 SuperAlpha (after 100 lifetime alphas)
A SuperAlpha combines alphas you have **already submitted** in one region and delay. A **selection** expression
scores each alpha (e.g. least correlated, highest fitness) and keeps the top ones; a **combo** expression weights them
day by day (equal weight, inverse volatility, ...).
- **Your pools**: submitted alphas per region and delay; a pool needs 10+ to be worth it, with a suggested limit.
- Pick a **selection recipe** and a **weighting recipe** (each shows why it exists) or write your own; set decay,
  truncation, selection limit and handling, IS or OS activation.
- Checks and a **preview** run as you type: which of your alphas the selection would keep.
- **Simulate this SuperAlpha** (1 simulation; at most 10 per pool per quarter), **Run the SuperAlpha gate** (BRAIN's
  checks, correlations, the 2-40% turnover band, deflated Sharpe over every try on the pool, train vs test), then a
  typed-confirmation **Submit** - one a day, on top of your 4 alphas. The gate's description is not sent with the
  submission yet: paste it on the alpha's page on BRAIN.
- Sandbox: SuperAlphas are open for practice; **Build a practice pool** submits ~24 sandbox alphas to play with.

### 4.5 Journal
Everything you have simulated: the verdict mix, tries per idea against the budget of 10, a scoreboard by family, the
experiments (filter by region and verdict), your submissions, and your **lessons** - add one per idea.

### 4.6 Account (live)
**Download my submitted alphas, operators + simulation options** (do it weekly, and after submitting on the website):
- lifetime and quarter counts (they feed the SuperAlpha countdown and the Pyramids tab);
- Genius tie-breakers: operators and fields per alpha (lower is better), distinct operators and fields this quarter;
- the **Osmosis check**: which region x delay scopes have 10+ alphas, and the last Sunday to lock an allocation;
- operators used and unused per category this quarter, the fields you lean on most;
- **Re-run a submitted alpha** with a risk-neutralization set or at delay 0 (BRAIN's own suggestion) - results land
  in the Lab, where the gate checks correlation with the original.

### 4.7 Data
What each dataset and field measures: nature (balance-sheet stock, flow, estimate, count, vendor score...), economic
concepts, coverage and crowding, BRAIN's value score and multipliers. Find fields by concept, search by text, check
which of the guide's datasets your region has, and **download another region's field list** (metadata only, a few
minutes; reused for 7 days).

### 4.8 Setup
Where you stand (mode, region, credentials, session, versions), the **sandbox/live switch**, **log in** (if BRAIN asks
for a face scan, a link appears; do it, then press *I finished the face scan*), log out, the Gold operator list, and a
suggested 2-hour daily routine.

### The two helper apps
- **Dataset scan**: *Explore* a dataset for free (each field gets only the lenses that suit its nature), then *Scan*:
  one simulation per field, all journaled, against the **noise bar** - the Sharpe the luckiest noise field would
  reach. A scan finds *where to look*; candidates appear in Leads › From your journal.
- **Quant basics**: a hands-on course on the practice market: what an alpha is, what operators do to the numbers,
  the four numbers BRAIN judges, neutralization, why the 12.5% turnover floor matters, how brute force manufactures
  luck, and robustness tests. No BRAIN account needed.

---

## 5. The idea team (Claude chats, agent pack v3)

The "agents" are Claude chats with fixed instructions, not programs: you carry every message, and HYPOLAB never calls
an AI. Set them up once from `claude_projects/` (its README; keep the projects private). The formats and what each
paste box does are in `claude_projects/HANDOFF_CONTRACTS.md`.

| Project | You give it | It gives back |
|---|---|---|
| **Scout & Writer** | a BRAIN page (`brief` / `shortlist`), a paper, a BRIEF, a SOURCE block, a lead draft, a rewrite verdict | a **BRIEF** (`B-<date>-<time>`), a **SHORTLIST** (`L-...`), or 1-2 **CARDs** with a `# from:` line each, or NO CARD |
| **Critic** | a `checked` card from *Copy for the Critic* | a **VERDICT**: keep, rewrite or bin, with scores and fixes |
| **Weekly Reviewer** | Friday's **DIGEST** | an honest review and next week's **PLAN** |
| **HYPOLAB** (hub) | build work, BRAIN pages, planning | code, rule checks, the quarter plan |

Plus the **daily alpha brief** (a scheduled task, weekdays 17:55 Nairobi): it reads the HYPOLAB state doc and writes
one pasteable card a day (`# from: daily brief <date>`, or `... via S-...` when an outside-source row informed it).

The import box (Drafts): each card takes the `# from:` line directly above it; an id that is already a waiting or
binned draft is refused unless you tick **This is a rewrite** (a rewrite keeps the source and clears the old verdict);
you choose the dry-run region (default: this week's plan region). The PLAN's lessons and dead ends reach
`07_dead_ends.md` and the state doc, and a declared dead end warns on every new card in that family. The DIGEST
measures the Critic: its decisions against live results.

The chats read the **knowledge pack** (`claude_projects/knowledge/01-10`): card format, concepts, operators,
existing cards, the Pyramids guide, goals and house rules, dead ends, lessons and leads, your operator usage, BRAIN's
rules and the published predictors. Rebuild it weekly (Drafts page) and re-upload only what INDEX.md says changed.

---

## 6. A day and a week

**A day (about 2 hours)**
1. Read: the daily brief, one paper abstract, or one BRAIN Learn page.
2. Plan: Ideas › Week (today's count, the plan) and the cockpit's Pyramids tab.
3. Ideas: Ideas › Leads - act on one lead or source; import the Writer's card on Drafts, Critic, approve.
4. Research: Ideas › Cards › Send to the Lab 2-3 cards for the week's cells; Lab: rung 1, read the diagnosis, climb
   a few rungs at most. Respect the stop signs.
5. Validate: production correlation (free), robustness, the gate. Submit only what clears it (never more than 4).
6. Write: one lesson per idea in the Journal tab.

**Friday (30 minutes)**: Account download -> rebuild the knowledge pack and re-upload what changed -> copy the DIGEST
into the Weekly Reviewer -> paste its PLAN on the Week page -> paste the state text into the HYPOLAB state doc.

---

## 7. The guard rails (why HYPOLAB says no)

- **Trial budget**: 10 tries per idea, then rethink. Every try is counted - rungs, boosts, lower-correlation changes,
  dice rolls on that card - and the gate deflates the Sharpe by them. Picking the best of many variants of one idea is
  how alphas that die out of sample are made.
- **Spend freely across ideas**: scans and many cards a day are fine; BRAIN expects 1000+ simulations.
- **The linter** blocks non-Gold operators, wrong arguments and windows without meaning *before* a simulation is spent.
- **Duplicates** are served from the journal, never simulated twice.
- **Originality**: the gate checks correlation with your own alphas and with BRAIN's production pool.
- **Ceilings, not quotas**: 4 alphas and 1 SuperAlpha a day at most. Weak submissions lower your combined alpha
  performance, which is one of the Expert bars.
- **A runaway guard** of 500 simulations a day and 2 at once.
- **Only a READY gate can submit.** A submission needs a gate report HYPOLAB itself produced in this session, READY
  when it was produced, less than 30 minutes old (`gate_max_age_minutes`), and used once. Missing evidence is never a
  pass: no platform checks, no correlation reading, no deflated Sharpe or no train/test split keeps the gate NOT READY.
- **Nothing is sent twice by accident.** If BRAIN's answer to a simulation or a submission is lost (a dropped
  connection, a server error), HYPOLAB does not send it again: it says the outcome is unknown, and for a submission it
  reads the alpha back to see whether BRAIN recorded it.
- **Nothing is submitted without your typed confirmation.**

---

## 8. Your data and settings

Everything personal lives in `~/.hypolab/` (private to you, mode 700):

| File | What it holds |
|---|---|
| `journal.sqlite` | Every simulation, submission, lesson, binned card, pending simulation, account download |
| `ideas.sqlite` | Goals, weekly plans, drafts, Leads decisions, collected sources |
| `catalog.sqlite`, `cache/` | Field lists per region and their classification |
| `library/my_cards.yaml` | Your approved cards (`.bak` = the previous version) |
| `credentials.json`, `session.json` | Only if you ticked *Remember*; readable only by you; cookies, never pickles |
| `settings.json` | **Only the settings you changed** (since 1.10.1) |
| `settings.defaults.json` | Every setting with its default, for reference (rewritten at each start) |
| `lab_inbox.json`, `play_last_roll_*.json`, `quota.json`, `sim_options.json`, `operators.json` | Small app state |

To change a setting, copy its line from `settings.defaults.json` into `settings.json` and edit the value. The most
useful ones: `max_sims_per_idea` (10), `max_submissions_per_day` (4), `alphas_per_pyramid` (3), `account_regions`,
`live_region`, `session_ttl_seconds` (900), `gate_max_age_minutes` (30), `collector_feeds`, `news_muted_themes`, `arxiv_categories`,
`state_doc_url`, `follow_themes`. Never share `credentials.json` or `session.json`.

---

## 9. Honest limits

- The sandbox teaches judgment; it is not BRAIN. Only live results count.
- BRAIN changes thresholds and adds checks; its own checks always win over HYPOLAB's numbers.
- Some BRAIN behaviour is still unconfirmed live (SuperAlpha descriptions and bars, some response shapes); the gate
  says when it relies on documentation rather than your results.
- The built-in cards are well-known anomalies and many are crowded: the edge comes from less-used data and your own
  cards.

**Tests**: `python tests/run_all.py` runs every test file in its own process (312 tests, about five minutes, fits in 8 GB).
