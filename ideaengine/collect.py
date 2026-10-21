"""Run the collectors from a terminal (phase 7, 1.9.0).

    python -m ideaengine.collect osap                  # the bundled Open Source Asset Pricing list (offline)
    python -m ideaengine.collect osap --download       # the latest list from OSAP's GitHub
    python -m ideaengine.collect arxiv                 # newest q-fin papers (arXiv API)
    python -m ideaengine.collect news                  # the RSS feeds in settings.json (collector_feeds)
    python -m ideaengine.collect datasets              # under-used datasets in your downloaded field lists
    python -m ideaengine.collect all                   # all of the above (osap from the bundled list)
    python -m ideaengine.collect arxiv --file saved.xml   # a page you saved yourself (any collector but datasets)
    python -m ideaengine.collect list                  # what is in the inbox

Same as Leads > From outside in the Ideas app (python -m hypolab collect ... works too). Cadence that fits the
design: news daily, arXiv twice a week, OSAP once (then browse), datasets after each field-list download.
"""
from __future__ import annotations

import sys
from typing import List, Optional

from ideaengine import collectors as C
from ideaengine import sources as S


def _catalog():
    from hypolab import config
    from hypolab.catalog import Catalog
    if config.sandbox_mode():
        print("(sandbox mode: the practice market has no value scores - nothing to collect from datasets)")
    return Catalog()


def run(kind: str, store, file: Optional[str] = None, download: bool = False) -> dict:
    text = C.load_file(file, binary=kind in ("arxiv", "news")) if file else None      # 1.9.1: XML decodes itself
    if kind == "datasets":
        from hypolab.journal import Journal
        return S.collect(store, "datasets", catalog=_catalog(), journal=Journal.open_readonly())
    return S.collect(store, kind, text=text, origin="download" if download else ("file " + file if file else ""))


def main(argv: Optional[List[str]] = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] in ("-h", "--help", "help"):
        print(__doc__)
        return 0
    from ideaengine.store import IdeaStore
    store = IdeaStore()
    kind = argv[0]
    file = argv[argv.index("--file") + 1] if "--file" in argv and argv.index("--file") + 1 < len(argv) else None
    download = "--download" in argv
    if kind == "list":
        S.refresh_covered(store)
        df = S.items(store, show="new", limit=30)
        if df.empty:
            print("The inbox is empty. Run: python -m ideaengine.collect all")
            return 0
        for r in df.itertuples(index=False):
            cov = f"  (same paper as {', '.join(r.covered_by)})" if r.covered_by else ""
            print(f"{r.relevance:5.2f}  {S.KIND_SHORT.get(r.kind, r.kind):8} {r.tag:34} {r.title[:60]}{cov}")
        print(f"... {df.attrs.get('total', len(df))} new item(s) in all; open Leads > From outside in the Ideas app.")
        return 0
    kinds = list(S.COLLECTORS) if kind == "all" else [kind]
    if any(k not in S.COLLECTORS for k in kinds):
        print(f"unknown collector {kind!r}; one of {', '.join(S.COLLECTORS)}, all, list")
        return 1
    code = 0
    for k in kinds:
        try:
            res = run(k, store, file if kind != "all" else None, download)
            extra = f" ({len(res['errors'])} feed(s) failed: {'; '.join(res['errors'])})" if res.get("errors") else ""
            ret = f", {res['retired']} used dataset(s) retired" if res.get("retired") else ""
            print(f"{k}: {res['found']} item(s) read, {res['added']} new{ret}{extra}")
        except Exception as e:  # noqa: BLE001
            code = 1
            hint = (" - save the page in a browser and run it again with --file <saved file>"
                    if k in ("arxiv", "news", "osap") else "")
            print(f"{k}: failed ({type(e).__name__}: {e}){hint}")
    return code


if __name__ == "__main__":
    sys.exit(main())
