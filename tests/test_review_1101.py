"""HYPOLAB 1.10.1: the whole-system review - regressions for each fix (settings that keep only your choices, the
sandbox Pyramids after a SuperAlpha (in test_phase8), one definition of "tries", the cached journal view, one lifetime
count everywhere, the SuperAlpha line on the Week page and in the DIGEST, the knowledge pack that names what changed,
the weekly submission ceiling, the state doc link setting, the cockpit's text). No network."""
import importlib.util
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

os.environ.setdefault("HYPOLAB_HOME", tempfile.mkdtemp(prefix="hypolab_test_"))

from hypolab import config, learning  # noqa: E402
from hypolab import hypotheses as hyp  # noqa: E402
from hypolab.journal import Journal  # noqa: E402
from ideaengine import drafts, knowledge_pack, planner, views  # noqa: E402
from ideaengine.store import IdeaStore  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
HAVE_WEB = all(importlib.util.find_spec(m) for m in ("starlette", "jinja2", "httpx", "markdown", "multipart"))
ST = {"region": "USA", "universe": "TOP3000", "delay": 1, "decay": 0, "neutralization": "SUBINDUSTRY"}


class _Home(unittest.TestCase):
    def setUp(self):
        self._old = config.HOME
        self._tmp = tempfile.TemporaryDirectory()
        config.HOME = Path(self._tmp.name)
        config._SETTINGS_CACHE.clear()

    def tearDown(self):
        config.HOME = self._old
        config._SETTINGS_CACHE.clear()
        self._tmp.cleanup()

    def raw(self):
        return json.loads((config.HOME / "settings.json").read_text())


class TestSettingsKeepOnlyYourChoices(_Home):
    def test_first_run_and_save_write_only_your_keys(self):
        self.assertEqual(config.settings()["max_sims_per_idea"], config.DEFAULTS["max_sims_per_idea"])
        self.assertNotIn("max_sims_per_idea", self.raw())
        self.assertTrue((config.HOME / "settings.defaults.json").exists())
        config.save_settings(live_region="EUR")
        raw = self.raw()
        self.assertEqual(raw["live_region"], "EUR")
        self.assertNotIn("collector_feeds", raw)
        self.assertEqual(config.settings()["live_region"], "EUR")
        self.assertNotIn("_about", config.settings())

    def test_a_later_default_reaches_you(self):
        config.save_settings(mode="sandbox")
        with mock.patch.dict(config.DEFAULTS, {"scan_max_fields": 55}):
            config._SETTINGS_CACHE.clear()
            self.assertEqual(config.settings()["scan_max_fields"], 55)      # 1.10.0 froze the old default here

    def test_old_whole_defaults_file_is_migrated(self):
        old = dict(config.DEFAULTS, pyramid_regions=["USA"], single_country_region="KOR", max_sims_per_idea=7)
        (config.HOME / "settings.json").write_text(json.dumps(old))
        self.assertEqual(config.settings()["max_sims_per_idea"], 7)            # your change kept
        raw = self.raw()
        self.assertEqual({k for k in raw if not k.startswith("_")}, {"max_sims_per_idea"})
        self.assertNotIn("pyramid_regions", config.settings())

    def test_obsolete_defaults_are_gone(self):
        self.assertNotIn("pyramid_regions", config.DEFAULTS)
        self.assertIn("state_doc_url", config.DEFAULTS)


class TestOneDefinitionOfTries(unittest.TestCase):
    def setUp(self):
        self.j = Journal(":memory:")
        for i, purpose in enumerate(["explore", "boost", "decorr", "play", "scan", "super"]):
            self.j.record("IDEA@USA", f"r{i}", purpose, f"rank(close + {i})", ST, {"is_sharpe": 1.0}, verdict="WEAK",
                          backend="sandbox")

    def test_tries_per_idea_counts_decorr(self):
        t = views.tries_per_idea(self.j.experiments(), 10)
        self.assertEqual(int(t.iloc[0]["tries"]), 3)                 # explore, boost, decorr

    def test_family_journal_counts_decorr(self):
        self.j.db.execute("INSERT INTO ideas (id, hypothesis_id, region, family) VALUES ('IDEA@USA','IDEA','USA','fam')")
        self.assertEqual(drafts.family_journal(self.j, "fam")["tries"], 3)

    def test_live_experiments_is_cached_until_the_journal_changes(self):
        a = learning.live_experiments(self.j, learning.TRY_PURPOSES)
        b = learning.live_experiments(self.j, learning.TRY_PURPOSES)
        self.assertEqual(len(a), len(b))
        a.drop(a.index, inplace=True)                                  # a caller's change never reaches the cache
        self.assertEqual(len(learning.live_experiments(self.j, learning.TRY_PURPOSES)), 3)
        self.j.record("IDEA@USA", "r9", "explore", "rank(open)", ST, {"is_sharpe": 1.2}, verdict="NEAR",
                      backend="sandbox")
        self.assertEqual(len(learning.live_experiments(self.j, learning.TRY_PURPOSES)), 4)


class TestLifetimeAndSuperAlphaLines(_Home):
    def setUp(self):
        super().setUp()
        self.st = IdeaStore(":memory:")
        self.j = Journal(config.HOME / "journal.sqlite")

    def tearDown(self):
        self.j.db.close()
        super().tearDown()

    def test_lifetime_uses_brains_count_when_larger(self):
        self.st.set_goal("lifetime_alphas", 12, 100)
        self.assertEqual(planner.lifetime_submitted(self.st, self.j), 12)
        from hypolab import account
        with mock.patch.object(account, "last_sync", return_value=1.0), \
                mock.patch.object(account, "counts", return_value={"lifetime_regular": 40}):
            self.assertEqual(planner.lifetime_submitted(self.st, self.j), 40)
            from hypolab import superalpha as SA
            self.assertEqual(SA.unlock_status(self.st, self.j)["lifetime"], 40)

    def test_week_progress_and_summary_split_superalphas(self):
        self.j.record_submission("A1", "IDEA@USA", "fam", "USA", 1, [])
        self.j.record_submission("S1", "SUPER@USA-D1@2026Q4", "superalpha", "USA", 1, [])
        prog = planner.week_progress(self.j, planner.iso_week())
        self.assertEqual((prog["submitted"], prog["super_submitted"]), (1, 1))
        self.st.set_goal("lifetime_alphas", 120, 100)
        s = planner.submission_status(self.st, self.j)
        self.assertEqual(s["super_today"], 1)
        self.assertIn("1/1 today", planner.submission_summary(s))

    def test_digest_has_a_superalpha_line(self):
        txt = drafts.digest(self.j, self.st, planner.iso_week())
        self.assertIn("superalphas: locked", txt)


class TestKnowledgePackNamesWhatChanged(_Home):
    def test_second_rebuild_changes_nothing(self):
        out = config.HOME / "pack"
        first = knowledge_pack.build(out)
        self.assertEqual(len(first.changed), 10)
        before = (out / "02_concepts.md").stat().st_mtime_ns
        second = knowledge_pack.build(out)
        self.assertEqual(second.changed, [])
        self.assertEqual((out / "02_concepts.md").stat().st_mtime_ns, before)
        self.assertIn("Last rebuilt", (out / "INDEX.md").read_text())
        self.assertIn("1 a day", knowledge_pack.goals_and_rules())


class TestCockpitText(unittest.TestCase):
    def test_no_dead_lab_sync_button_and_a_current_routine(self):
        src = (ROOT / "apps" / "cockpit.py").read_text()
        self.assertNotIn("sync_btn", src)
        self.assertIn("Ideas app, **Week** page", src)
        self.assertIn("leads, cards and drafts", src)
        self.assertNotIn("Data tab's concept list", (ROOT / "ideaengine" / "drafts.py").read_text())

    def test_project_instructions_name_the_same_files_as_the_pack(self):
        # every Claude Project file lists exactly the knowledge files INDEX.md sends it
        # 1.10.3 (agent pack v3): three projects; the BRAIN Library merged into Scout & Writer
        names = {"1_scout_writer.md": "Scout & Writer", "2_critic.md": "Critic",
                 "3_weekly_reviewer.md": "Weekly Reviewer"}
        for fname, project in names.items():
            head = (ROOT / "claude_projects" / fname).read_text().split("--- paste from here ---")[0]
            want = {n for n, used in knowledge_pack.USED_BY.items() if project in used}
            have = {n for n in knowledge_pack.USED_BY if n in head}
            self.assertEqual(have, want, fname)
            row = next(ln for ln in (ROOT / "claude_projects" / "README.md").read_text().splitlines()
                       if ln.startswith(f"| HYPOLAB - {project} |"))
            nums = {n for n in knowledge_pack.USED_BY if n[:2] in row.split("|")[4]}
            self.assertEqual(nums, want, f"README row for {project}")


@unittest.skipUnless(HAVE_WEB, "web dependencies not installed")
class TestWeekPage(_Home):
    def setUp(self):
        super().setUp()
        from starlette.testclient import TestClient
        from ideaweb import state as web_state
        from ideaweb.app import app
        config.save_settings(mode="sandbox", state_doc_url="https://claude.ai/code/artifact/my-own-doc")
        hyp._LIB_CACHE.clear()
        web_state.reset()
        self.c = TestClient(app)

    def tearDown(self):
        from ideaweb import state as web_state
        web_state.reset()
        super().tearDown()

    def test_state_doc_link_and_weekly_ceiling(self):
        r = self.c.get("/week")
        self.assertEqual(r.status_code, 200)
        self.assertIn("my-own-doc", r.text)
        self.assertIn('max="20" name="submit_target"', r.text)
        week = planner.iso_week()
        self.c.post("/week/plan", data={"week": week, "region": "USA", "categories": ["analyst"],
                                        "card_target": "5", "submit_target": "99"})
        from ideaweb import state as web_state
        self.assertEqual(web_state.state().store.plan(week)["submit_target"], 20)


if __name__ == "__main__":
    unittest.main()
