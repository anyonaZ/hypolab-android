# HYPOLAB: idea-first alpha research for WorldQuant BRAIN

**Quality ideas first, simulations second.** The notebooks in `WQB.zip` sweep templates over fields. Measured hit
rate: about 0.2%. hypolab instead starts from an economic hypothesis, binds it to *your* data, blocks bad
expressions before they cost a simulation, tells you what each result means and what to do next, and refuses to
call something "submittable" until it has passed robustness and overfitting checks.

Built for: a Gold-level consultant, Arch Linux, a Lenovo T470s, and a Galaxy Tab A9. Python; no GPU, no paid tools.

Two halves, one loop, one app:
- **HYPOLAB** (`hypolab/`) *tests* ideas: bind to your fields, lint, simulate, diagnose, validate, submit.
- **Idea Engine** (`ideaengine/`) decides *what is worth testing*: quarter goals, the weekly plan, the daily
  submission cap, the learning loop (what your journal suggests next), and the collectors (published predictors,
  papers, news themes and under-used datasets as leads for new cards).
- **The web app** (`ideaweb/`, 1.16.0) is the screen for both, on the laptop and on the tablet: thirteen pages in
  four groups. It runs on your own device only (127.0.0.1), never hosted.
- **The Android app** (`android/`) runs the same Python code and the same pages on the tablet (Chaquopy + a WebView);
  GitHub Actions builds the signed APK.
- The old **marimo apps** (`apps/`) still run on the laptop (`python -m hypolab cockpit`) for comparison, until you
  decide to retire them.

## Install (Arch)
```bash
unzip hypolab.zip && cd hypolab
bash setup_arch.sh
source ~/.venvs/hypolab/bin/activate
python -m hypolab web              # HYPOLAB at http://127.0.0.1:2719 (opens your browser)
```
Everything starts in **sandbox mode**: an offline synthetic market with planted signals, so you can learn and
practise the whole loop - Lab included - without spending simulations.

| Group | Pages | What it is for |
|---|---|---|
| Ideas | Week, Leads, Cards, Drafts | The week's plan and Friday review, the learning loop and outside sources, the card library, writing and approving cards. Never simulates |
| Lab | Lab, Play, Basics | Test a rung or your own expression, diagnosis, follow one action, boost, production correlation and Lower correlation, robustness, gate, typed-confirmation submit; random dice; the hands-on quant course |
| Records | Journal, Pyramids, SuperAlpha | Everything simulated and your lessons; the Pyramid grid and next cells; the SuperAlpha builder, gate and submit |
| Account | Data, Account, Setup | Field lists, concepts, the dataset explore/scan; your submitted alphas, tie-breakers, Osmosis, re-runs; login, sandbox/live, status |

Every button that spends simulations runs as a background job (one at a time, never repeated by itself); changing a
control never simulates.

## Going live
Open the **Setup** page:
1. **Log in**: email and password. If BRAIN asks for a face scan, a link appears on the page; do the scan, then
   press *I finished the face scan*. On the laptop the password is saved to `~/.hypolab/credentials.json` (readable
   only by you) only after BRAIN accepts it, and only if you tick the box. On the tablet it is never saved.
2. **Switch to Live** and pick the region. Every page follows the switch.
3. On the **Account** page, download your account once (it saves your regions' universes), then on the **Data** page
   download the field list for your region (metadata only; reused for 7 days).

The pages never wait on a hidden prompt: if a session expires and BRAIN wants a face scan, they point you to Setup.

Same from a terminal:
```bash
python -m hypolab login        # enter + verify + save credentials
python -m hypolab live USA     # every page uses your account, region USA
python -m hypolab status       # where you stand
python -m hypolab sandbox      # back to practice mode
python -m hypolab logout       # delete saved credentials
python -m hypolab collect all  # outside sources into Leads > From outside (osap | arxiv | news | datasets | list)
python -m hypolab cockpit      # the old marimo screens next to the web app (live work in one of the two at a time)
```

"Send to the Lab" (Cards, Leads) writes `~/.hypolab/lab_inbox.json` and opens the Lab page, which picks the card up.

Your own cards: write or import them on the Ideas app's **Drafts** page; **Approve** appends them to
`~/.hypolab/library/my_cards.yaml` (the previous file is kept as `my_cards.yaml.bak`). Any `*.yaml` in that folder in
the same format as `hypolab/library/hypotheses.yaml` also loads. They sit next to the built-in 47, marked `mine`. A
card whose id clashes with a built-in one is skipped and reported.

## The daily loop in code (what the Lab page does)
```python
from hypolab.research import Researcher
R = Researcher.start()                    # follows the Setup page switch / `python -m hypolab live USA`
cards = R.ideas(n=10)                     # ranked hypotheses bound to USA fields
card = R.card("ANL_EPS_REVISION")         # or one card by id (built-in or yours)
R.show(cards[0])                          # read the story BEFORE simulating
t = R.test(cards[0], rung=0)              # linted, budgeted, journaled
R.show(t)                                 # verdict + one next action
t2 = R.follow(t, 0)                       # or R.test(card, rung=1)
boost = R.boost(t)                        # weak but real (Sharpe ~1)? add ONE independent second signal
R.show(boost)                             # predicted vs actual gain; boost.best is the combined alpha
gate = R.gate(t2, R.robustness(t2))
R.show(gate)
R.submit(gate, confirm=f"SUBMIT {gate.alpha_id}")   # only you can do this
```

## Simulation volume and guard rails (`~/.hypolab/settings.json`)
Since 1.10.1 `settings.json` holds only the settings you changed; `settings.defaults.json` next to it lists every
setting with its default (copy a line into `settings.json` to change it).

BRAIN expects 1000+ simulations from consultants who build ideas from scratch, and hypolab is built to spend them
well:
- **Across ideas and datasets, spend freely.** `R.scan(dataset)` probes every field of a dataset in bulk and
  marks which ones clear the *noise bar*. Many idea cards a day, a few rungs each.
- **Within one idea, stay disciplined.** About 10 tries per hypothesis, then rethink. Picking the best of many
  variants of one idea is what produces alphas that die out of sample.
- **Every try is counted.** The gate deflates the Sharpe by the tries on that idea, including every field scanned
  in the dataset when the alpha came from a scan.
- **Originality is checked.** The gate tests correlation with your own alphas *and* with BRAIN's production pool.
  A copied idea fails there, however good its Sharpe.
- A runaway guard of 500 simulations a day, and 2 concurrent requests.
- Gold operators only, checked against your PDF.
- Duplicate simulations are served from the journal.
- Nothing is ever submitted without the typed confirmation, and only from a READY gate report HYPOLAB issued in the
  last 30 minutes (1.10.2); missing evidence keeps a gate NOT READY, and a simulation or submission whose answer
  was lost is never sent again by itself.
- At most 4 submissions a day (`max_submissions_per_day`), BRAIN's daily expectation used as a ceiling. The Week page tracks lifetime submissions toward the 100 that unlock SuperAlphas.

## Docs
- `claude_projects/`: custom instructions and a knowledge pack for running the idea team as Claude Projects.
- `HANDOFF.md`: where the project stands and what comes next (read first when resuming work).
- `docs/AUDIT.md`: line-by-line findings on the zip, **including a live GitHub token shipped inside `ACE Studio/`**.
- `docs/LEARNING_PATH.md`: a 6-week path built from WorldQuant's own material and the core papers.
- `docs/USER_GUIDE.md`: **start here** - everything HYPOLAB can do, page by page, in plain words.
- `docs/HOW_IT_WORKS.md`: the architecture and where your data lives.
- The design of the Idea Engine (phases, prompts, planner) is in the HYPOLAB Idea Engine design doc.

## Honest limits
- The sandbox teaches judgment; it is not BRAIN. Only live results count.
- BRAIN changes thresholds and adds checks. Its own `/check` is always the authority, and hypolab reads it live.
- The idea cards are well-documented anomalies. Many are crowded, so the edge comes from binding them to less-used
  datasets (the generator penalises crowded fields) and from writing **your own** cards.
- Tests: `python tests/run_all.py` (about 380 tests, one file per process, about five minutes; the marimo apps'
  smoke test needs marimo). `python -m unittest discover -s tests` also works but holds about 6 GB in one process.
