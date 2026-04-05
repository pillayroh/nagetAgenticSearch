"""Bounded in-memory store for run documents when MongoDB is disabled."""

from __future__ import annotations

from collections import OrderedDict
from threading import Lock

_lock = Lock()
_store: OrderedDict[str, dict] = OrderedDict()
_MAX_RUNS = 256


def save_run(run_id: str, doc: dict) -> None:
    with _lock:
        _store[run_id] = doc
        _store.move_to_end(run_id)
        while len(_store) > _MAX_RUNS:
            _store.popitem(last=False)


def get_run(run_id: str) -> dict | None:
    with _lock:
        doc = _store.get(run_id)
        if doc is not None:
            _store.move_to_end(run_id)
        return dict(doc) if doc is not None else None
