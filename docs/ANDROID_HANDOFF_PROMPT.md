# Prompt for a new chat: HYPOLAB as a standalone Android app

Copy everything below the line into a new chat, and attach `hypolab-1.10.3.zip` (or newer).

---

I want to run HYPOLAB - my idea-first research system for WorldQuant BRAIN - as a **standalone Android app on my
Samsung Galaxy Tab A9 (Android 16, One UI 8)**. Standalone means: **no hosting, no server anywhere but on the tablet,
no account with any third party.** The app talks only to BRAIN's own API (and, for the collectors, to the public
feeds HYPOLAB already reads). My laptop (Lenovo T470s, Arch Linux, 8 GB) stays the main HYPOLAB machine for now; the
tablet must be able to do the whole loop on its own when I'm away from the laptop.

## Read first (in the attached zip)
1. `HANDOFF.md` - where the project stands and the **decisions not to reopen**.
2. `docs/USER_GUIDE.md` - every capability, page by page. The Android app must offer all of it.
3. `docs/HOW_IT_WORKS.md` - the architecture; `docs/BRAIN_RULES.md` - BRAIN's rules HYPOLAB follows.
4. Run `python tests/run_all.py` on the desktop code first: all ~312 tests must pass before anything changes.

## What HYPOLAB is today (so you don't have to guess)
- Python 3.10+ engine: `hypolab/` (cards, binding to BRAIN fields, linter, BRAIN client, offline sandbox market,
  diagnosis, robustness, deflated Sharpe, gate, journal in SQLite, Pyramids, SuperAlphas) and `ideaengine/` (goals,
  weekly plan, drafts, learning loop, collectors, knowledge pack).
- Two UIs on 127.0.0.1: the **Ideas web app** (`ideaweb/`: Starlette + Jinja2 templates, already responsive, never
  simulates) and **marimo apps** (`apps/cockpit.py` with Lab, Pyramids, Play, SuperAlpha, Journal, Account, Data,
  Setup tabs; `apps/dataset_scan.py`; `apps/quant_basics.py`). Every simulation sits behind a button.
- Data in `~/.hypolab/` (overridable with the env var `HYPOLAB_HOME`): `journal.sqlite`, `ideas.sqlite`,
  `catalog.sqlite`, `settings.json` (only my own choices), `library/my_cards.yaml`, small JSON files, pickle caches.
- Dependencies: numpy, pandas, scipy (only `scipy.stats.norm/skew/kurtosis` in `hypolab/overfit.py` and
  `scipy.special.ndtri` in `hypolab/sandbox/evaluator.py`), matplotlib (PnL chart, Pyramid heatmap, quant basics),
  pyyaml, requests; starlette, uvicorn, jinja2, markdown, python-multipart; marimo for the cockpit.

## Decisions that stay (from HANDOFF.md)
The AI never picks field ids, never sends anything to BRAIN, never approves a card, never submits; HYPOLAB never calls
an AI (hand-offs to my Claude Projects are copy and paste); one card format, one journal; every simulation behind an
explicit button; typed confirmation (`SUBMIT <alpha id>`) for every submission; at most 4 alphas + 1 SuperAlpha a day,
as ceilings; only a READY gate report HYPOLAB issued recently can submit, missing evidence never passes the gate,
and a simulation or submission whose answer was lost is never re-sent automatically (1.10.2; keep this on a phone's
flaky network). Credentials never leave the device except to BRAIN.

## The device (check these facts on the tablet before designing; tell me if any is wrong)
- Galaxy Tab A9 = SM-X110 (Wi-Fi) / SM-X115 (LTE): **8.7-inch screen, 800 x 1340 px**, MediaTek Helio G99 (2x A76 +
  6x A55, arm64-v8a), **4 GB RAM** (64/128 GB) or 8 GB RAM (128 GB), microSD slot. (If it is really the Tab A9+,
  SM-X210/X216, it is 11-inch 1200 x 1920 - ask me.) Settings › About tablet shows the model and RAM.
- So: a small screen, portrait first; and on the 4 GB model about 1-1.5 GB is a safe budget for the app. On the laptop
  one marimo session holds ~0.8 GB and the sandbox market dominates memory - measure on the device.

## My recommendation to evaluate first (challenge it if you find better)
1. **Embed Python with Chaquopy** (MIT licensed; current 17.x supports Python 3.10-3.15, min API 24) in a small
   Kotlin app. Chaquopy's package repository has numpy 1.26.2 and pandas 2.1.3 for cp310-cp313 arm64, but **scipy
   only up to cp310 (1.8.1)**. Prefer removing the scipy dependency from the shared code (replace `norm.cdf/ppf`,
   `skew`, `kurtosis` and `ndtri` with numpy / `statistics.NormalDist`, with tests proving identical numbers) so the
   app can use a current Python. Check matplotlib, PyYAML and every pure-Python package on the real device.
2. **One UI, not two.** marimo is too heavy and unproven on Android. Port the cockpit's tabs, the dataset scan and quant
   basics to server-rendered pages in the existing Ideas app style (Starlette + Jinja2, same CSS, same origin guard),
   so desktop and tablet share ONE web UI; then the desktop can drop marimo later if I agree. Run uvicorn (pure-Python,
   h11; no uvloop/httptools) inside the app on 127.0.0.1 with a random port and a per-launch secret, and show it in an
   Android **WebView**. Alternative to weigh: no HTTP server at all, a WebView + JavaScript bridge calling Python
   directly. Pick one with evidence (memory, start-up time, simplicity).
3. Keep **one shared Python code base** for laptop and tablet. Android-specific code lives in its own folder
   (e.g. `android/`), and the desktop tests keep passing.

## What the Android app must handle
- **Storage**: `HYPOLAB_HOME` = the app's private files directory. **Export / import** a backup (journal, ideas,
  catalog, my cards, settings - never credentials) through Android's file picker, so I can move my state between laptop
  and tablet. There is no hosting, so there is no live sync: design the hand-over so the two never write the same
  journal at the same time (e.g. "this device has the journal" with a clear warning on import).
- **BRAIN login**: email + password; the face-scan (biometric) step opens BRAIN's link in the browser (Custom Tab) and
  returns to the app; credentials encrypted with an Android Keystore key, never in plain files; session cookies only.
- **Long work**: simulations wait on BRAIN for minutes and a dataset scan can take 10-30 minutes. Android 16 limits
  background work: use a foreground service with a notification (and the right foreground-service type and its time
  limits) or WorkManager; make every job resumable - HYPOLAB already records pending simulations and recovers them
  from BRAIN without paying again.
- **Copy-and-paste hand-offs** (CARD, VERDICT, SOURCE, DIGEST, PLAN, state-doc text): one-tap Copy and Paste buttons
  that work in the WebView, plus Android's **Share** sheet so I can send a DIGEST or SOURCE straight to the Claude app.
- **Small screen**: touch targets of at least 48 dp, no hover-only controls, tables that scroll or collapse into cards,
  the side rail becomes a bottom bar or drawer, readable code blocks, dark theme (HYPOLAB's "Matrix" colours), and
  every action that spends simulations still behind a clear button.
- **Offline**: the sandbox (practice market) and quant basics work with no network; bundle the fonts (Inter, JetBrains
  Mono, both OFL) instead of loading Google Fonts.
- **Collectors**: optional daily `collect news` with WorkManager (Wi-Fi only, battery friendly).
- **Distribution**: a signed APK I install myself (no Play Store). Tell me how to build it - my laptop has only 8 GB,
  so building in your cloud workspace or a private CI may be easier - and how to install and update it without losing
  data.

## How I want you to work
1. Start with a **feasibility spike**, before any UI work: a minimal APK that imports numpy, pandas and the HYPOLAB
   engine with Chaquopy, builds the sandbox market, runs one sandbox simulation and a gate, and reports memory and
   time on the tablet (or the closest emulator: arm64, 4 GB). Tell me the numbers and any blocker before going on.
2. Then propose phases (for example: A spike; B the Ideas app in a WebView; C the cockpit pages ported; D live login,
   Keystore, BRAIN API; E backup/import, foreground service, share sheet; F polish and APK), each ending with tests
   passing, a HANDOFF update, a version bump and an installable APK.
3. Ask me before choices that are hard to undo (dropping marimo on the desktop, the backup format, the sync rule).
4. Keep HYPOLAB's style: plain words in the UI (I am still learning quant), honest about what is untested live,
   never invent BRAIN rules or field ids.

Before you start, ask me anything you need: the exact tablet model and RAM, whether the laptop or the tablet should
own the journal, and whether you may change the desktop UI to share the new pages.
