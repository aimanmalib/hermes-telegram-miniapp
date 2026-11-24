"""Session reads through ``hermes_compat``: the storage interface when Hermes has it, ``SessionDB`` otherwise.

The fakes copy the shapes of Hermes v0.23.4's ``persistence_assembly`` and ``persistence.conversation`` that the
plugin uses; the real modules are exercised by the contract tests and were checked against seeded stores on v0.23.0
and v0.23.4.
"""

from __future__ import annotations

import importlib.util
import sys
import types
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

import pytest

COMPAT = Path(__file__).resolve().parents[1] / "plugin" / "dashboard" / "hermes_compat.py"


@pytest.fixture
def compat():
    spec = importlib.util.spec_from_file_location("tma_compat_storage_test", COMPAT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class Order(Enum):
    STARTED_AT = "started_at"
    LAST_ACTIVE = "last_active"


@dataclass(frozen=True)
class Query:
    sources: tuple | None = None
    order: Order = Order.STARTED_AT


@dataclass(frozen=True)
class Window:
    limit: int | None
    offset: int = 0


@dataclass(frozen=True)
class Read:
    limit: int | None = None
    latest: bool = False


class Row:
    def __init__(self, d):
        self.d = d

    def as_list_row(self):
        return dict(self.d)

    def as_wire_row(self):
        return dict(self.d)


class Store:
    def __init__(self, calls):
        self.calls = calls
        self.sessions = types.SimpleNamespace(list_sessions=self.list_sessions, count_sessions=lambda: 7)
        self.messages = types.SimpleNamespace(read_transcript=self.read_transcript)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.calls.append("closed")

    def list_sessions(self, query, window):
        self.calls.append(("list", query, window))
        return [Row({"id": "a", "source": "telegram"})]

    def read_transcript(self, session_id, request):
        self.calls.append(("read", session_id, request))
        return [Row({"content": "hi"})]


def install_storage(monkeypatch, tmp_path, store_exists=True):
    calls: list = []
    db = tmp_path / "state.db"
    if store_exists:
        db.write_text("")
    scope = types.SimpleNamespace(profile_dir=tmp_path)
    pa = types.ModuleType("persistence_assembly")
    pa.profile_scope = lambda: scope
    pa.store_location = lambda s: db
    pa.open_persistence_reader = lambda target: (calls.append(("open", target)), Store(calls))[1]
    sess = types.ModuleType("persistence.conversation.sessions")
    sess.SessionQuery, sess.SessionWindow, sess.SessionOrder = Query, Window, Order
    msgs = types.ModuleType("persistence.conversation.messages")
    msgs.TranscriptRead = Read
    conv = types.ModuleType("persistence.conversation")
    conv.sessions, conv.messages = sess, msgs
    root = types.ModuleType("persistence")
    root.conversation = conv
    for name, mod in {"persistence_assembly": pa, "persistence": root, "persistence.conversation": conv,
                      "persistence.conversation.sessions": sess, "persistence.conversation.messages": msgs}.items():
        monkeypatch.setitem(sys.modules, name, mod)
    monkeypatch.delitem(sys.modules, "hermes_state", raising=False)
    return calls


def test_storage_interface_lists_newest_active_first_and_closes(compat, monkeypatch, tmp_path):
    calls = install_storage(monkeypatch, tmp_path)
    assert compat.list_sessions(limit=5, source="telegram") == [{"id": "a", "source": "telegram"}]
    _, query, window = calls[1]
    assert calls[0] == ("open", tmp_path)
    assert query == Query(sources=("telegram",), order=Order.LAST_ACTIVE)
    assert window == Window(limit=5)
    assert calls[-1] == "closed"


def test_storage_interface_count_and_latest_messages(compat, monkeypatch, tmp_path):
    calls = install_storage(monkeypatch, tmp_path)
    assert compat.count_sessions() == 7
    assert compat.session_messages("s1", 20) == [{"content": "hi"}]
    assert ("read", "s1", Read(limit=20, latest=True)) in calls
    compat.session_messages("s1", 0)
    assert ("read", "s1", Read()) in calls


def test_missing_store_reads_as_empty_without_opening(compat, monkeypatch, tmp_path):
    calls = install_storage(monkeypatch, tmp_path, store_exists=False)
    assert compat.list_sessions(limit=5) == []
    assert compat.count_sessions() == 0
    assert compat.session_messages("s1", 5) == []
    assert calls == []


def test_older_hermes_uses_session_db_and_closes_it(compat, monkeypatch):
    for name in ("persistence_assembly", "persistence", "persistence.conversation"):
        monkeypatch.setitem(sys.modules, name, None)   # import raises ImportError
    closed = []

    class FakeDB:
        def list_sessions_rich(self, **kw):
            assert kw in ({"source": None, "limit": 3, "order_by_last_active": True}, {"limit": 1000})
            return [{"id": "old"}]

        def get_messages(self, session_id):
            return [{"n": i} for i in range(5)]

        def close(self):
            closed.append(True)

    hs = types.ModuleType("hermes_state")
    hs.SessionDB = FakeDB
    monkeypatch.setitem(sys.modules, "hermes_state", hs)
    assert compat.list_sessions(limit=3) == [{"id": "old"}]
    assert compat.session_messages("x", 2) == [{"n": 3}, {"n": 4}]
    assert compat.count_sessions() == 1      # no session_count: falls back to the listing
    assert len(closed) == 3 + 1              # one per call, the count fallback opens twice
