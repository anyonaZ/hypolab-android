"""The `analyst_skill` concept (B-20261022-1234, anl93 analyst track-record fields): it binds forecasters' track
records, not forecasts; anl93's fields are numbers even when they mention the "horizon date"; target_price no longer
binds a track-record field; nothing in the bundled 27k-field GLB catalog changes nature or matches by accident."""
import gzip
import json
import unittest
from pathlib import Path

from hypolab import concepts as C
from ideaengine import knowledge_pack

ROOT = Path(__file__).resolve().parent.parent
ANL93 = {   # wording from the brief; the real descriptions may differ - check the dry run on the live EUR list
    "anl93_analyst_accuracy1": "Share of the analyst's price targets that the stock price touched at least once",
    "anl93_analyst_accuracy2": "Share of price targets where the price was at the target on the horizon date",
    "anl93_analyst_consistency": "Negative standard deviation of the difference between target price and close price "
                                 "on the horizon day",
    "anl93_estimator_consistency": "",
}


def best(fid, desc):
    m = C.match_concepts(fid, desc, C.classify_nature(fid, desc))
    return m[0].concept if m else None


class TestAnalystSkill(unittest.TestCase):
    def test_track_record_fields_bind_and_are_numbers(self):
        for fid, desc in ANL93.items():
            self.assertNotIn(C.classify_nature(fid, desc), C.NON_NUMERIC, fid)
            self.assertEqual(best(fid, desc), "analyst_skill", fid)
        # consistency (scaled by price in the card) ranks first; raw hit rates are a past-return proxy
        s = {f: C.CONCEPTS["analyst_skill"].match(f, d)[0] for f, d in ANL93.items()}
        self.assertGreater(s["anl93_analyst_consistency"], s["anl93_analyst_accuracy1"])

    def test_what_it_must_not_take(self):
        self.assertIsNone(best("anl93_estimator_analyst", "Identifier of the analyst"))
        self.assertNotEqual(best("anl93_relative_accuracy1", "Rank of the analyst's accuracy among analysts covering "
                                 "the same stock"), "analyst_skill")        # averages to a constant per stock
        self.assertEqual(C.CONCEPTS["analyst_skill"].match("rtk_ptg_stddev", "Standard Deviation of Price Target")[0], 0)
        self.assertEqual(C.CONCEPTS["target_price"].match("anl93_analyst_consistency",
                                                          ANL93["anl93_analyst_consistency"])[0], 0)
        self.assertGreater(C.CONCEPTS["target_price"].match("anl93_target_price", "Analyst price target, 12 months")[0], 0)

    def test_bundled_catalog_unchanged(self):
        d = json.loads(gzip.open(ROOT / "data" / "catalog_GLB_MINVOL1M_D1.json.gz").read())
        skill = C.CONCEPTS["analyst_skill"]
        hits = [f["id"] for f in d["fields"] if skill.match(f["id"], f.get("description") or "")[0] > 0]
        self.assertEqual(hits, [])          # GLB has no track-record fields; profitability "consistency" is not one

    def test_knowledge_file_lists_it(self):
        self.assertIn("`analyst_skill`", knowledge_pack.concepts())
        self.assertIn("`analyst_skill`", (ROOT / "claude_projects" / "knowledge" / "02_concepts.md").read_text())


if __name__ == "__main__":
    unittest.main()
