"""Phase 5 (HYPOLAB 1.7.0): the learning loop - journal facts, inbox, drafts from evidence, source quality,
the learning digest, and what the journal changes in the card ranking."""
import json
import os
import tempfile
import time
import unittest

_HOME = tempfile.mkdtemp()
os.environ["HYPOLAB_HOME"] = _HOME

import pandas as pd  # noqa: E402

from hypolab import learning  # noqa: E402
from hypolab.ideas import _dataset_info, _score  # noqa: E402
from hypolab.journal import Journal  # noqa: E402
from hypolab.research import Researcher  # noqa: E402
from ideaengine import drafts, knowledge_pack, learn, planner  # noqa: E402
from ideaengine.store import IdeaStore  # noqa: E402


def idea(j, idea_id, family, region="USA", cats="analyst", hyp=None):
    j.db.execute("INSERT OR IGNORE INTO ideas (id, hypothesis_id, region, family, title, categories, created) "
                 "VALUES (?,?,?,?,?,?,?)", (idea_id, hyp or idea_id.split("@")[0], region, family, idea_id, cats, 0))
    j.db.commit()


def res(j, idea_id, verdict, sharpe, region="USA", purpose="explore", expr=None, failed=(), rung="r", backend="brain",
        universe="TOP3000"):
    res.n += 1
    j.record(idea_id, rung, purpose, expr or f"rank(x{res.n})", {"region": region, "delay": 1, "universe": universe},
             {"alpha_id": f"A{res.n}", "is_sharpe": sharpe, "is_fitness": sharpe / 2 if sharpe else None,
              "status": "COMPLETE", "failed": list(failed)}, verdict, backend=backend)
    time.sleep(0.001)


res.n = 0


class TestJournalFacts(unittest.TestCase):
    def setUp(self):
        self.j = Journal(":memory:")

    def test_near_miss_and_budget(self):
        idea(self.j, "ANL_EPS_REVISION@USA", "eps_revision")
        res(self.j, "ANL_EPS_REVISION@USA", "WEAK", 0.6)
        res(self.j, "ANL_EPS_REVISION@USA", "NEAR", 1.4, failed=["LOW_FITNESS"])
        nm = learning.near_misses(self.j, budget=10)
        self.assertEqual(nm["idea_id"].tolist(), ["ANL_EPS_REVISION@USA"])
        self.assertFalse(bool(nm["at_budget"].iloc[0]))
        self.assertEqual(int(nm["tries_left"].iloc[0]), 8)
        nm2 = learning.near_misses(self.j, budget=2)
        self.assertTrue(bool(nm2["at_budget"].iloc[0]))
        # planner keeps its old shape (tries left only)
        self.assertEqual(planner.near_misses(self.j, budget=2).shape[0], 0)
        self.assertEqual(planner.near_misses(self.j, budget=10)["tries_left"].tolist(), [8])

    def test_file_journal_ignores_sandbox_rows(self):
        path = os.path.join(tempfile.mkdtemp(), "j.sqlite")
        j = Journal(path)
        idea(j, "X@SBX", "fam_x", region="SBX")
        res(j, "X@SBX", "NEAR", 1.5, region="SBX", backend="sandbox")
        self.assertTrue(learning.near_misses(j).empty)
        self.assertEqual(len(learning.live_experiments(self.j)), 0)

    def test_inverted_until_flipped(self):
        idea(self.j, "SNT_NEWS_DRIFT@USA", "news_drift")
        res(self.j, "SNT_NEWS_DRIFT@USA", "INVERTED", -1.6)
        self.assertEqual(learning.inverted(self.j)["idea_id"].tolist(), ["SNT_NEWS_DRIFT@USA"])
        res(self.j, "SNT_NEWS_DRIFT@USA", "WEAK", 0.9, expr="reverse(rank(x))")
        self.assertTrue(learning.inverted(self.j).empty)

    def test_dead_end_families(self):
        idea(self.j, "A@USA", "fam_dead")
        for _ in range(5):
            res(self.j, "A@USA", "NOISE", 0.1)
        idea(self.j, "B@USA", "fam_alive")
        for v in ("NOISE", "NOISE", "NOISE", "NOISE", "WEAK"):
            res(self.j, "B@USA", v, 0.7)
        de = learning.dead_end_families(self.j)
        self.assertEqual(de["family"].tolist(), ["fam_dead"])
        self.assertEqual(planner.dead_end_families(self.j), ["fam_dead"])

    def test_scan_candidates_use_the_noise_bar_and_skip_used_fields(self):
        sharpes = [0.1, -0.2, 0.15, 0.05, -0.1, 0.2, 0.0, 0.12, -0.05, 0.08, 3.5, -3.2]
        for k, sh in enumerate(sharpes):
            f = f"fld{k}"
            idea(self.j, f"LENS_{f}@USA", "lens_model77", cats="model", hyp=f"LENS_{f}")
            res(self.j, f"LENS_{f}@USA", "NOISE", sh, purpose="scan", expr=f"rank(ts_rank({f}, 63))")
        sc = learning.scan_candidates(self.j)
        self.assertEqual(set(sc["field"]), {"fld10", "fld11"})
        self.assertTrue((sc["noise_bar"] < 3.2).all())
        self.assertEqual(sc["dataset"].iloc[0], "model77")
        # a card that later used fld10 removes it from the candidates
        idea(self.j, "IE_X@USA", "x")
        res(self.j, "IE_X@USA", "WEAK", 0.8, expr="rank(fld10) + rank(close)")
        self.assertEqual(learning.scan_candidates(self.j)["field"].tolist(), ["fld11"])

    def test_check_failures_and_card_warnings(self):
        idea(self.j, "C@EUR", "fam_c", region="EUR", cats="analyst")
        for _ in range(4):
            res(self.j, "C@EUR", "WEAK", 0.8, region="EUR", failed=["LOW_SUB_UNIVERSE_SHARPE"])
        cf = learning.check_failures(self.j)
        self.assertEqual(cf.iloc[0]["check"], "LOW_SUB_UNIVERSE_SHARPE")
        self.assertEqual(int(cf.iloc[0]["failed"]), 4)
        w = learning.card_warnings(self.j, "EUR", ["analyst"])
        self.assertTrue(w and "LOW_SUB_UNIVERSE_SHARPE" in w[0])
        self.assertEqual(learning.card_warnings(self.j, "USA", ["analyst"]), [])

    def test_transfers_and_adjustments(self):
        idea(self.j, "ERN_PEAD@USA", "pead")
        res(self.j, "ERN_PEAD@USA", "PASS", 2.1)
        idea(self.j, "ERN_PEAD@SBX", "pead", region="SBX")
        res(self.j, "ERN_PEAD@SBX", "PASS", 2.6, region="SBX")
        tr = learning.transfers(self.j, ["USA", "EUR", "SBX"])
        self.assertEqual(tr[["hypothesis_id", "from_region", "to_region"]].values.tolist(),
                         [["ERN_PEAD", "USA", "EUR"]])                  # never from or to the practice market
        adj = learning.card_adjustments(self.j, "EUR")
        self.assertIn("ERN_PEAD", adj)
        self.assertGreater(adj["ERN_PEAD"][0], 0)
        self.assertNotIn("ERN_PEAD", learning.card_adjustments(self.j, "USA"))


class TestInbox(unittest.TestCase):
    def setUp(self):
        self.j = Journal(":memory:")
        self.s = IdeaStore(":memory:")
        idea(self.j, "ANL_EPS_REVISION@USA", "eps_revision")
        for v, sh in (("WEAK", 0.6), ("NEAR", 1.4)):
            res(self.j, "ANL_EPS_REVISION@USA", v, sh)
        idea(self.j, "SNT_NEWS_DRIFT@USA", "news_drift")
        res(self.j, "SNT_NEWS_DRIFT@USA", "INVERTED", -1.6)

    def test_items_skip_and_evidence_change(self):
        it = learn.items(self.j, self.s, regions=["USA", "EUR"])
        kinds = it["kind"].tolist()
        self.assertEqual(kinds[0], "near_miss")
        self.assertIn("inverted", kinds)
        self.assertIn("transfer", kinds)                    # NEAR in USA, untried in EUR
        first = it.iloc[0].to_dict()
        learn.skip(self.s, first, "not now")
        it2 = learn.items(self.j, self.s, regions=["USA", "EUR"])
        self.assertNotIn(first["key"], it2["key"].tolist())
        self.assertIn(first["key"], learn.items(self.j, self.s, regions=["USA", "EUR"], show="all")["key"].tolist())
        res(self.j, "ANL_EPS_REVISION@USA", "NEAR", 1.6)    # new evidence: the item comes back
        self.assertIn(first["key"], learn.items(self.j, self.s, regions=["USA", "EUR"])["key"].tolist())
        learn.reopen(self.s, first["key"])
        self.assertTrue(learn.decisions(self.s).empty)

    def test_sibling_draft_is_a_valid_new_card(self):
        c = learn.sibling_draft(self.j, "ANL_EPS_REVISION@USA", taken=[])
        self.assertTrue(c["id"].startswith("IE_ANL_EPS_REVISION_SIB"))
        self.assertIn("Sibling of ANL_EPS_REVISION", c["story"])
        rep = drafts.check_card(c)
        self.assertTrue(rep.ok, rep.summary())

    def test_scan_draft_is_a_valid_card(self):
        row = {"field": "fld11", "dataset": "model77", "region": "USA", "sharpe": -3.2, "noise_bar": 1.5,
               "n_probes": 12, "expression": "rank(ts_rank(fld11, 63))"}
        c = learn.scan_draft(row)
        self.assertEqual(c["ladder"][0]["expr"], "reverse(rank(ts_rank({x}, 63)))")
        self.assertEqual(c["sign"], "-1")
        rep = drafts.check_card(c)
        # the only thing missing is yours to write: why the edge persists
        self.assertEqual([(x.where, x.message) for x in rep.checks if x.level == "error"], [("why_persists", "empty")])
        row2 = dict(row, sharpe=2.0, expression="-rank(vec_avg(fld11))")
        self.assertEqual(learn.scan_draft(row2)["ladder"][0]["expr"], "-rank({x})")

    def test_source_quality_buckets(self):
        dr = drafts.Drafts(self.s)
        card = drafts.template()
        card.update({"id": "IE_1019_TEST", "title": "t", "family": "fam_t", "story": "s", "why_persists": "w",
                     "ladder": [{"name": "core", "expr": "rank(close)", "teaches": "t"}]})
        dr.save(card, "daily brief 2026-10-19")
        idea(self.j, "IE_1019_TEST@USA", "fam_t", hyp="IE_1019_TEST")
        res(self.j, "IE_1019_TEST@USA", "PASS", 2.2)
        sq = learn.source_quality(self.j, self.s).set_index("source")
        self.assertEqual(int(sq.loc["daily brief", "near_or_pass"]), 1)
        self.assertEqual(int(sq.loc["built-in cards", "ideas_tried"]), 2)

    def test_digest_json_is_small(self):
        for k in range(60):
            idea(self.j, f"IE_N{k}@USA", f"fam{k}", hyp=f"IE_N{k}")
            res(self.j, f"IE_N{k}@USA", "NEAR", 1.2 + k / 100)
        s = learn.digest_json(self.j, self.s, max_bytes=1500)
        self.assertLessEqual(len(s.encode()), 1500)
        d = json.loads(s)
        self.assertIn("near_misses", d)
        self.assertIn("source_quality", d)


class TestRankingAndHandoffs(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.R = Researcher.sandbox()

    def test_dead_end_family_ranks_lower_with_a_note(self):
        before = {c.hypothesis.id: c for c in self.R.ideas(n=60, one_per_family=False, use_pyramids=False)}
        target = next(iter(before.values()))
        for k in range(5):
            self.R.journal.record(target.id, "r", "explore", f"rank(dummy{k})", {"region": "SBX", "delay": 1},
                                  {"alpha_id": f"D{k}", "is_sharpe": 0.05, "status": "COMPLETE"}, "NOISE",
                                  backend="sandbox")
        self.R.journal.log_idea(target)
        after = {c.hypothesis.id: c for c in self.R.ideas(n=60, one_per_family=False, use_pyramids=False)}
        a = after.get(target.hypothesis.id)
        self.assertIsNotNone(a)
        self.assertLess(a.score, before[target.hypothesis.id].score - 1.5)
        self.assertTrue(any("dead end" in n for n in a.score_notes))

    def test_value_score_and_multiplier_raise_the_score(self):
        card = self.R.ideas(n=5, use_pyramids=False)[0]
        ds = {b.dataset for b in card.bindings.values()}
        _score(card, {}, None)
        base = card.score
        _score(card, {}, None, datasets={d: {"value_score": 5.0, "pyramid_multiplier": 1.4} for d in ds})
        if card.bindings:
            self.assertAlmostEqual(card.score - base, 0.9 + 0.3, places=5)
            self.assertTrue(any("value score 5" in n for n in card.score_notes))

    def test_dataset_info_reads_the_catalog(self):
        class Cat:
            def datasets(self, *a):
                return pd.DataFrame([{"id": "d1", "value_score": 4.0, "pyramid_multiplier": float("nan")}])
        self.assertEqual(_dataset_info(Cat(), "USA", "TOP3000", 1),
                         {"d1": {"value_score": 4.0, "pyramid_multiplier": None}})

    def test_digest_state_text_and_pack_carry_the_loop(self):
        j, s = Journal(":memory:"), IdeaStore(":memory:")
        idea(j, "ANL_EPS_REVISION@USA", "eps_revision")
        res(j, "ANL_EPS_REVISION@USA", "NEAR", 1.4)
        for k, sh in enumerate([0.1, -0.2, 0.15, 0.05, -0.1, 0.2, 0.0, 0.12, -0.05, 0.08, 3.5]):
            idea(j, f"LENS_g{k}@USA", "lens_ds9", cats="model", hyp=f"LENS_g{k}")
            res(j, f"LENS_g{k}@USA", "NOISE", sh, purpose="scan", expr=f"rank(g{k})")
        dg = drafts.digest(j, s, planner.iso_week())
        self.assertIn("learning loop (whole journal):", dg)
        self.assertIn("ds9.g10", dg)
        self.assertIn("```json", dg)
        st = drafts.state_text(j, s, planner.iso_week())
        self.assertIn("## Leads from the journal", st)
        self.assertIn("Scan candidate", st)
        txt = knowledge_pack.dead_ends(j)
        self.assertIn("## Leads", txt)
        self.assertIn("ds9.g10", txt)

    def test_check_card_carries_journal_warnings(self):
        j = Journal(":memory:")
        cards = self.R.ideas(n=3, use_pyramids=False)
        c = cards[0]
        for k in range(4):
            j.record(c.id, "r", "explore", f"rank(w{k})", {"region": "SBX", "delay": 1},
                     {"alpha_id": f"W{k}", "is_sharpe": 0.8, "status": "COMPLETE", "failed": ["LOW_TURNOVER"]},
                     "WEAK", backend="sandbox")
        j.log_idea(c)
        raw = drafts.library_raw()[c.hypothesis.id][0]
        rep = drafts.check_card(dict(raw, id="IE_TMP_COPY"), self.R.catalog, "SBX", journal=j)
        self.assertTrue(any("LOW_TURNOVER" in x.message for x in rep.checks), rep.summary())


if __name__ == "__main__":
    unittest.main()
