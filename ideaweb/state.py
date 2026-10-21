"""Shared, lazily built objects for the Ideas app (one per process)."""
from __future__ import annotations

import threading
from typing import Optional

from hypolab import config
from hypolab.catalog import Catalog
from hypolab.journal import Journal
from ideaengine import planner
from ideaengine.drafts import Drafts
from ideaengine.store import IdeaStore


class State:
    """Opened on first use. The catalog (field list) is the heavy part: built only when a page needs it."""

    def __init__(self):
        self._lock = threading.Lock()
        self._store = self._drafts = self._journal = None
        self._catalog = None
        self._sandbox_catalog = None

    @property
    def sandbox(self) -> bool:
        return config.sandbox_mode()

    @property
    def store(self) -> IdeaStore:
        if self._store is None:
            self._store = IdeaStore()
        return self._store

    @property
    def drafts(self) -> Drafts:
        if self._drafts is None:
            self._drafts = Drafts(self.store)
        return self._drafts

    @property
    def journal(self) -> Journal:
        """The real journal file. The Ideas app writes only bins and lessons; simulations stay in the cockpit."""
        if self._journal is None:
            self._journal = Journal()
        return self._journal

    def catalog(self) -> Catalog:
        with self._lock:
            if self.sandbox:
                if self._sandbox_catalog is None:
                    from hypolab.mock import MockBrain, sandbox_catalog_payload
                    cat = Catalog(":memory:")
                    cat.ingest_payload(sandbox_catalog_payload(MockBrain(seed=7).data))
                    self._sandbox_catalog = cat
                return self._sandbox_catalog
            if self._catalog is None:
                self._catalog = Catalog()
            return self._catalog

    def regions(self):
        return ["SBX"] if self.sandbox else config.account_regions()

    def default_region(self) -> str:
        if self.sandbox:
            return "SBX"
        w = planner.iso_week()
        # 1.10.3: the week's plan even when it was never saved (the starting plan), not the live region (USA) -
        # so a card for an EUR week is dry-run in EUR by default
        try:
            p = planner.propose(w, None, self.store.plan(w)) or {}
        except Exception:  # noqa: BLE001
            p = self.store.plan(w) or {}
        r = p.get("region") or config.live_region()
        return r if r in self.regions() else self.regions()[0]

    def tracker(self):
        """Pyramid counts without BRAIN: this quarter's downloaded submissions, else the journal."""
        from hypolab import account as acct
        from hypolab.pyramids import PyramidTracker, multiplier_table
        k = int(config.settings().get("alphas_per_pyramid", 3))
        try:
            if acct.last_sync(self.journal):
                qc, _ = acct.quarter_pyramids(self.journal, None if self.sandbox else self.catalog(),
                                              *acct.current_quarter())
                base = PyramidTracker(qc)
            else:
                base = PyramidTracker.from_journal(self.journal)
            return PyramidTracker(base.counts, alphas_per_pyramid=k, regions=base.regions,
                                  multipliers=multiplier_table())
        except Exception:  # noqa: BLE001
            return None


STATE: Optional[State] = None


def state() -> State:
    global STATE
    if STATE is None:
        STATE = State()
    return STATE


def reset() -> None:
    """Tests: forget everything (e.g. after changing HYPOLAB_HOME)."""
    global STATE
    STATE = None
