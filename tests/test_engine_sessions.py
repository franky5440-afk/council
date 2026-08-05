import copy
import sys
import threading
import unittest
from pathlib import Path

SRC_DIR = Path(__file__).resolve().parent.parent / "src"
sys.path.insert(0, str(SRC_DIR))

from engine import sessions  # noqa: E402


class FakeDiscussion:
    """只有 status() 的假討論——證明 sessions.py 不依賴真的狀態機。"""

    def __init__(self):
        self.calls = 0
        self.state = {"phase": "ready", "usage": {"calls": 0, "by_seat": {}}}

    def status(self):
        self.calls += 1
        return copy.deepcopy(self.state)


class ProbeDiscussion:
    """status() 被呼叫的當下，回頭觀察 session 的公開狀態。"""

    def __init__(self):
        self.session = None
        self.busy_during_status = []
        self.stolen_during_status = []

    def status(self):
        if self.session is not None:
            self.busy_during_status.append(self.session.is_busy)
            self.stolen_during_status.append(self.session.try_claim())
        return {"phase": "ready", "usage": {"calls": 0, "by_seat": {}}}


def new_session():
    store = sessions.SessionStore()
    return store, store.create(FakeDiscussion())


class SessionStoreTest(unittest.TestCase):
    def test_create_returns_session_with_same_discussion(self):
        fd = FakeDiscussion()
        store = sessions.SessionStore()
        session = store.create(fd)
        self.assertIs(session.discussion, fd)

    def test_ids_unique_and_not_sequential(self):
        store = sessions.SessionStore()
        ids = [store.create(FakeDiscussion()).id for _ in range(3)]
        self.assertEqual(len(set(ids)), 3)
        for sid in ids:
            self.assertGreaterEqual(len(sid), 20)
            self.assertFalse(sid.isdigit())

    def test_get_returns_same_object_and_none_for_missing(self):
        store = sessions.SessionStore()
        session = store.create(FakeDiscussion())
        self.assertIs(store.get(session.id), session)
        self.assertIsNone(store.get("no-such-id"))

    def test_remove_then_get_none_then_remove_false(self):
        store = sessions.SessionStore()
        session = store.create(FakeDiscussion())
        self.assertTrue(store.remove(session.id))
        self.assertIsNone(store.get(session.id))
        self.assertFalse(store.remove(session.id))

    def test_list_ids_in_creation_order(self):
        store = sessions.SessionStore()
        created = [store.create(FakeDiscussion()).id for _ in range(4)]
        self.assertEqual(store.list_ids(), created)


class ExecutionRightTest(unittest.TestCase):
    def test_claim_release_cycle(self):
        _, session = new_session()
        self.assertTrue(session.try_claim())
        self.assertFalse(session.try_claim())
        session.release()
        self.assertTrue(session.try_claim())

    def test_is_busy_reflects_claim(self):
        _, session = new_session()
        self.assertFalse(session.is_busy)
        session.try_claim()
        self.assertTrue(session.is_busy)
        session.release()
        self.assertFalse(session.is_busy)

    def test_release_without_claim_raises(self):
        _, session = new_session()
        with self.assertRaises(RuntimeError):
            session.release()

    def test_concurrent_claim_exactly_one(self):
        for _ in range(20):
            session = sessions.SessionStore().create(FakeDiscussion())
            n = 8
            barrier = threading.Barrier(n)
            results = []
            results_lock = threading.Lock()

            def worker():
                barrier.wait()
                won = session.try_claim()
                with results_lock:
                    results.append(won)

            threads = [threading.Thread(target=worker) for _ in range(n)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()
            self.assertEqual(results.count(True), 1)

    def test_try_claim_does_not_block(self):
        _, session = new_session()
        self.assertTrue(session.try_claim())
        returned = threading.Event()
        result = []

        def worker():
            result.append(session.try_claim())
            returned.set()

        t = threading.Thread(target=worker)
        t.start()
        self.assertTrue(returned.wait(timeout=2), "try_claim() 阻塞超過 2 秒")
        t.join()
        self.assertEqual(result, [False])


class SnapshotTest(unittest.TestCase):
    def test_initial_snapshot_matches_status(self):
        fd = FakeDiscussion()
        session = sessions.SessionStore().create(fd)
        self.assertEqual(session.snapshot, fd.state)

    def test_snapshot_stale_without_refresh(self):
        fd = FakeDiscussion()
        session = sessions.SessionStore().create(fd)
        before = session.snapshot
        fd.state["phase"] = "in_round"
        fd.state["usage"]["calls"] = 7
        self.assertEqual(session.snapshot, before)
        self.assertEqual(session.snapshot["phase"], "ready")
        self.assertEqual(session.snapshot["usage"]["calls"], 0)

    def test_refresh_updates_snapshot(self):
        fd = FakeDiscussion()
        session = sessions.SessionStore().create(fd)
        fd.state["phase"] = "in_round"
        fresh = session.refresh()
        self.assertEqual(fresh["phase"], "in_round")
        self.assertEqual(session.snapshot["phase"], "in_round")

    def test_release_refreshes_snapshot(self):
        fd = FakeDiscussion()
        session = sessions.SessionStore().create(fd)
        session.try_claim()
        fd.state["phase"] = "awaiting_user"
        session.release()
        self.assertEqual(session.snapshot["phase"], "awaiting_user")

    def test_snapshot_is_deep_copy(self):
        _, session = new_session()
        snap = session.snapshot
        snap["phase"] = "mutated"
        snap["usage"]["calls"] = 99
        snap["usage"]["by_seat"]["hack"] = {"calls": 1}
        fresh = session.snapshot
        self.assertEqual(fresh["phase"], "ready")
        self.assertEqual(fresh["usage"]["calls"], 0)
        self.assertNotIn("hack", fresh["usage"]["by_seat"])


class EventStreamTest(unittest.TestCase):
    def test_append_event_seq_1_2_3(self):
        _, session = new_session()
        self.assertEqual(session.append_event("speech", "a"), 1)
        self.assertEqual(session.append_event("speech", "b"), 2)
        self.assertEqual(session.append_event("speech", "c"), 3)

    def test_event_dict_keys_exact(self):
        _, session = new_session()
        session.append_event("speech", {"text": "x"})
        event = session.events_since(0)[0]
        self.assertEqual(set(event.keys()), {"seq", "kind", "data"})

    def test_events_since_cursor(self):
        _, session = new_session()
        session.append_event("speech", "a")
        session.append_event("speech", "b")
        session.append_event("speech", "c")
        self.assertEqual([e["seq"] for e in session.events_since(0)], [1, 2, 3])
        self.assertEqual([e["seq"] for e in session.events_since(2)], [3])
        self.assertEqual(session.events_since(999), [])

    def test_events_since_deep_copy(self):
        _, session = new_session()
        session.append_event("speech", {"text": "你好", "usage": {"calls": 1}})
        got = session.events_since(0)
        got[0]["seq"] = 999
        got[0]["kind"] = "mutated"
        got[0]["data"]["usage"]["calls"] = 999
        again = session.events_since(0)
        self.assertEqual(again[0]["seq"], 1)
        self.assertEqual(again[0]["kind"], "speech")
        self.assertEqual(again[0]["data"]["usage"]["calls"], 1)

    def test_concurrent_append_unique_seqs(self):
        _, session = new_session()
        n_threads = 8
        per_thread = 25
        barrier = threading.Barrier(n_threads)

        def worker():
            barrier.wait()
            for i in range(per_thread):
                session.append_event("speech", {"i": i})

        threads = [threading.Thread(target=worker) for _ in range(n_threads)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        events = session.events_since(0)
        self.assertEqual(len(events), 200)
        self.assertEqual({e["seq"] for e in events}, set(range(1, 201)))

    def test_events_not_blocked_by_execution(self):
        _, session = new_session()
        self.assertTrue(session.try_claim())
        done = threading.Event()

        def worker():
            session.append_event("speech", "ok")
            session.events_since(0)
            done.set()

        t = threading.Thread(target=worker)
        t.start()
        self.assertTrue(done.wait(timeout=2), "事件讀寫被執行權擋住")
        t.join()
        self.assertEqual(len(session.events_since(0)), 1)


class ReleaseOrderTest(unittest.TestCase):
    def test_release_holds_execution_while_refreshing_snapshot(self):
        probe = ProbeDiscussion()
        session = sessions.SessionStore().create(probe)
        probe.session = session
        self.assertTrue(session.try_claim())
        session.release()
        self.assertEqual(probe.busy_during_status, [True])
        self.assertEqual(probe.stolen_during_status, [False])

    def test_release_still_completes_path(self):
        fd = FakeDiscussion()
        session = sessions.SessionStore().create(fd)
        self.assertTrue(session.try_claim())
        fd.state["phase"] = "awaiting_user"
        session.release()
        self.assertEqual(session.snapshot["phase"], "awaiting_user")
        self.assertFalse(session.is_busy)
        self.assertTrue(session.try_claim())


if __name__ == "__main__":
    unittest.main()
