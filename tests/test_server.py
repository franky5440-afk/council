import http.client
import json
import socket
import sys
import threading
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path

SRC_DIR = Path(__file__).resolve().parent.parent / "src"
sys.path.insert(0, str(SRC_DIR))

import server  # noqa: E402
from engine import orchestrator  # noqa: E402
from engine import state  # noqa: E402
from engine import transcript  # noqa: E402

DEFAULT_ADVISORS = ["claude", "opencode"]


def make_ask_fn(text="意見。\n[立場: 保留] [補充: 有]", usage=None, delay=0.0):
    """回傳一個純 Python 的假 ask_fn，計數自己被呼叫幾次。"""
    calls = []

    def ask_fn(cli, prompt, model, timeout_s, max_chars):
        if delay:
            time.sleep(delay)
        calls.append(cli)
        return {
            "ok": True,
            "text": text,
            "truncated": False,
            "error": None,
            "elapsed_s": 0.1,
            "model_used": f"{cli}-model",
            "usage": usage,
        }

    ask_fn.calls = calls
    return ask_fn


def request(method, port, path, body=None, raw_body=None, headers=None):
    url = f"http://127.0.0.1:{port}{path}"
    data = None
    req_headers = {}
    if raw_body is not None:
        data = raw_body.encode("utf-8")
        req_headers["Content-Type"] = "application/json"
    elif body is not None:
        data = json.dumps(body).encode("utf-8")
        req_headers["Content-Type"] = "application/json"
    if headers:
        req_headers.update(headers)
    req = urllib.request.Request(url, data=data, headers=req_headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return resp.status, dict(resp.headers), resp.read()
    except urllib.error.HTTPError as exc:
        return exc.code, dict(exc.headers), exc.read()


def open_sse(port, path, headers=None):
    url = f"http://127.0.0.1:{port}{path}"
    req = urllib.request.Request(url, headers=headers or {})
    return urllib.request.urlopen(req, timeout=15)


def read_sse_events(resp, count, timeout=15):
    """從 SSE 回應讀取 count 則事件，回傳 [{seq, kind, data, data_count}, ...]。"""
    events = []
    current = None
    deadline = time.monotonic() + timeout
    while len(events) < count:
        if time.monotonic() > deadline:
            raise AssertionError(f"SSE 讀取逾時：只收到 {len(events)}/{count} 則")
        line = resp.readline()
        if not line:
            break
        text = line.decode("utf-8").rstrip("\r\n")
        if text == "":
            if current is not None:
                events.append(current)
                current = None
            continue
        if text.startswith(":"):
            continue
        if text.startswith("id: "):
            current = {"seq": int(text[4:]), "kind": None,
                       "data": None, "data_count": 0}
        elif text.startswith("event: ") and current is not None:
            current["kind"] = text[7:]
        elif text.startswith("data: ") and current is not None:
            current["data"] = json.loads(text[6:])
            current["data_count"] += 1
    return events


class ServerCase(unittest.TestCase):
    def start(self, ask_fn=None, **kwargs):
        if ask_fn is None:
            ask_fn = make_ask_fn()
        srv = server.build_server(ask_fn=ask_fn, live=False, port=0, **kwargs)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        self.addCleanup(srv.shutdown)
        self.addCleanup(srv.server_close)
        return srv, srv.server_address[1]

    def create_discussion(self, port, question="問題", advisors=None,
                          context=None):
        body = {"question": question,
                "advisors": advisors if advisors is not None else DEFAULT_ADVISORS,
                "arbiter": "gemini"}
        if context is not None:
            body["context"] = context
        status, _, resp_body = request("POST", port, "/api/discussions", body)
        self.assertEqual(status, 200, resp_body)
        return json.loads(resp_body)["id"]

    def run_rounds(self, port, did, n):
        for _ in range(n):
            status, _, resp_body = request(
                "POST", port, f"/api/discussions/{did}/rounds", {})
            self.assertEqual(status, 200, resp_body)


class CreateDiscussionTest(ServerCase):
    def test_legal_body_200_with_common_shape(self):
        srv, port = self.start()
        status, _, resp_body = request("POST", port, "/api/discussions", {
            "question": "我們該不該用 Rust？",
            "advisors": ["claude", "opencode:opencode/xxx-free"],
            "arbiter": "claude",
            "context": "脈絡",
        })
        self.assertEqual(status, 200, resp_body)
        data = json.loads(resp_body)
        for key in ("id", "question", "seats", "status", "live", "busy",
                    "context_chars"):
            self.assertIn(key, data)
        self.assertFalse(data["busy"])
        self.assertFalse(data["live"])
        self.assertEqual(data["question"], "我們該不該用 Rust？")

    def test_seat_ids_assigned_in_order(self):
        srv, port = self.start()
        status, _, resp_body = request("POST", port, "/api/discussions", {
            "question": "q",
            "advisors": ["claude", "opencode", "gemini"],
            "arbiter": "codex",
        })
        self.assertEqual(status, 200, resp_body)
        data = json.loads(resp_body)
        self.assertEqual([s["seat_id"] for s in data["seats"]],
                         ["claude-1", "opencode-2", "gemini-3", "arb"])
        self.assertEqual([s["role"] for s in data["seats"]],
                         ["advisor", "advisor", "advisor", "arbiter"])

    def test_response_omits_context_and_reports_chars(self):
        srv, port = self.start()
        context = "這是送給顧問的脈絡。\n第二行"
        status, _, resp_body = request("POST", port, "/api/discussions", {
            "question": "q",
            "advisors": ["claude"],
            "arbiter": "opencode",
            "context": context,
        })
        self.assertEqual(status, 200, resp_body)
        data = json.loads(resp_body)
        self.assertNotIn("context", data)
        self.assertEqual(data["context_chars"], len(context))

    def test_unknown_key_rejected_400(self):
        srv, port = self.start()
        status, _, resp_body = request("POST", port, "/api/discussions", {
            "question": "q", "advisors": ["claude"], "arbiter": "opencode",
            "extra": 1,
        })
        self.assertEqual(status, 400, resp_body)

    def test_bad_payloads_400(self):
        srv, port = self.start()
        cases = [
            {"question": "q", "advisors": [], "arbiter": "opencode"},
            {"question": "", "advisors": ["claude"], "arbiter": "opencode"},
            {"question": "q", "advisors": [":x"], "arbiter": "opencode"},
        ]
        for body in cases:
            with self.subTest(body=body):
                status, _, resp_body = request(
                    "POST", port, "/api/discussions", body)
                self.assertEqual(status, 400, resp_body)

    def test_invalid_json_body_400(self):
        srv, port = self.start()
        status, _, resp_body = request(
            "POST", port, "/api/discussions", raw_body="這不是 JSON")
        self.assertEqual(status, 400, resp_body)


class GateTest(ServerCase):
    def test_host_evil_403(self):
        srv, port = self.start()
        status, _, resp_body = request("POST", port, "/api/discussions", {
            "question": "q", "advisors": ["claude"], "arbiter": "opencode",
        }, headers={"Host": "evil.example.com"})
        self.assertEqual(status, 403, resp_body)

    def test_host_localhost_passes(self):
        srv, port = self.start()
        did = self.create_discussion(port)
        status, _, resp_body = request(
            "GET", port, f"/api/discussions/{did}",
            headers={"Host": f"localhost:{port}"})
        self.assertEqual(status, 200, resp_body)

    def test_origin_checks(self):
        srv, port = self.start()
        status, _, resp_body = request("POST", port, "/api/discussions", {
            "question": "q", "advisors": ["claude"], "arbiter": "opencode",
        }, headers={"Origin": "https://evil.example.com"})
        self.assertEqual(status, 403, resp_body)

        did = self.create_discussion(port)
        status, _, resp_body = request(
            "GET", port, f"/api/discussions/{did}",
            headers={"Origin": f"http://127.0.0.1:{port}"})
        self.assertEqual(status, 200, resp_body)

        status, _, resp_body = request(
            "GET", port, f"/api/discussions/{did}")
        self.assertEqual(status, 200, resp_body)

    def test_wrong_content_type_415(self):
        srv, port = self.start()
        status, _, resp_body = request("POST", port, "/api/discussions", {
            "question": "q", "advisors": ["claude"], "arbiter": "opencode",
        }, headers={"Content-Type": "text/plain"})
        self.assertEqual(status, 415, resp_body)

    def test_no_access_control_headers(self):
        srv, port = self.start()
        responses = [
            request("POST", port, "/api/discussions",
                    {"question": "q", "advisors": ["claude"],
                     "arbiter": "opencode"}),
            request("GET", port, "/no-such-path"),
            request("POST", port, "/api/discussions", {},
                    headers={"Origin": "https://evil.example.com"}),
        ]
        for status, headers, _ in responses:
            self.assertFalse(
                any(k.lower().startswith("access-control") for k in headers),
                f"回應含 Access-Control 標頭: {sorted(headers)}")

    def test_content_length_too_large_413(self):
        srv, port = self.start()
        status, _, resp_body = request("POST", port, "/api/discussions", {
            "question": "q", "advisors": ["claude"], "arbiter": "opencode",
        }, headers={"Content-Length": "5000001"})
        self.assertEqual(status, 413, resp_body)

    def test_post_without_content_type_415(self):
        ask_fn = make_ask_fn()
        srv, port = self.start(ask_fn=ask_fn)
        did = self.create_discussion(port)
        calls_before = len(ask_fn.calls)
        for headers in ({}, {"Content-Type": "text/plain"}):
            with self.subTest(headers=headers):
                conn = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
                conn.request("POST", f"/api/discussions/{did}/rounds",
                             body="", headers=headers)
                resp = conn.getresponse()
                resp.read()
                conn.close()
                self.assertEqual(resp.status, 415, resp.status)
        self.assertEqual(len(ask_fn.calls), calls_before)


class StatusTest(ServerCase):
    def test_get_existing_200(self):
        srv, port = self.start()
        did = self.create_discussion(port)
        status, _, resp_body = request(
            "GET", port, f"/api/discussions/{did}")
        self.assertEqual(status, 200, resp_body)
        data = json.loads(resp_body)
        self.assertEqual(data["id"], did)
        self.assertIn("status", data)
        self.assertIn("seats", data)

    def test_get_missing_and_unknown_paths_404(self):
        srv, port = self.start()
        status, _, _ = request("GET", port, "/api/discussions/no-such")
        self.assertEqual(status, 404)
        status, _, _ = request("GET", port, "/api/foo")
        self.assertEqual(status, 404)

    def test_delete_method_405(self):
        srv, port = self.start()
        did = self.create_discussion(port)
        status, _, resp_body = request(
            "DELETE", port, f"/api/discussions/{did}")
        self.assertEqual(status, 405, resp_body)


class RoundTest(ServerCase):
    def test_first_round_runs_all_advisors(self):
        ask_fn = make_ask_fn()
        srv, port = self.start(ask_fn=ask_fn)
        did = self.create_discussion(port)
        status, _, resp_body = request(
            "POST", port, f"/api/discussions/{did}/rounds", {})
        self.assertEqual(status, 200, resp_body)
        self.assertEqual(len(ask_fn.calls), len(DEFAULT_ADVISORS))
        data = json.loads(resp_body)
        self.assertEqual(data["status"]["rounds_completed"], 1)

    def test_second_round_allowed(self):
        ask_fn = make_ask_fn()
        srv, port = self.start(ask_fn=ask_fn)
        did = self.create_discussion(port)
        self.run_rounds(port, did, 2)
        self.assertEqual(len(ask_fn.calls), 2 * len(DEFAULT_ADVISORS))

    def test_max_rounds_boundary_then_confirm(self):
        ask_fn = make_ask_fn()
        srv, port = self.start(ask_fn=ask_fn)
        did = self.create_discussion(port)
        self.run_rounds(port, did, state.DEFAULT_MAX_ROUNDS)
        status, _, resp_body = request(
            "POST", port, f"/api/discussions/{did}/rounds", {})
        self.assertEqual(status, 409, resp_body)
        self.assertEqual(json.loads(resp_body)["code"], "boundary")
        status, _, resp_body = request(
            "POST", port, f"/api/discussions/{did}/rounds",
            {"confirm_over_cap": True})
        self.assertEqual(status, 200, resp_body)
        self.assertEqual(
            json.loads(resp_body)["status"]["rounds_completed"],
            state.DEFAULT_MAX_ROUNDS + 1)

    def test_concurrent_rounds_exactly_one_wins(self):
        ask_fn = make_ask_fn(delay=0.5)
        srv, port = self.start(ask_fn=ask_fn)
        did = self.create_discussion(port)
        barrier = threading.Barrier(2)
        results = []
        results_lock = threading.Lock()

        def worker():
            barrier.wait()
            result = request(
                "POST", port, f"/api/discussions/{did}/rounds", {})
            with results_lock:
                results.append(result)

        threads = [threading.Thread(target=worker) for _ in range(2)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        statuses = sorted(r[0] for r in results)
        self.assertEqual(statuses, [200, 409])
        loser = [json.loads(r[2]) for r in results if r[0] == 409][0]
        self.assertEqual(loser["code"], "busy")
        self.assertEqual(len(ask_fn.calls), len(DEFAULT_ADVISORS))

    def test_execution_right_released_after_boundary(self):
        ask_fn = make_ask_fn()
        srv, port = self.start(ask_fn=ask_fn)
        did = self.create_discussion(port)
        self.run_rounds(port, did, state.DEFAULT_MAX_ROUNDS)
        status, _, resp_body = request(
            "POST", port, f"/api/discussions/{did}/rounds", {})
        self.assertEqual(status, 409, resp_body)
        self.assertEqual(json.loads(resp_body)["code"], "boundary")
        status, _, resp_body = request(
            "POST", port, f"/api/discussions/{did}/rounds",
            {"confirm_over_cap": True})
        self.assertEqual(status, 200, resp_body)

    def test_round_unknown_body_key_400(self):
        srv, port = self.start()
        did = self.create_discussion(port)
        status, _, resp_body = request(
            "POST", port, f"/api/discussions/{did}/rounds", {"extra": 1})
        self.assertEqual(status, 400, resp_body)


class ArbitrationTest(ServerCase):
    def test_refused_before_any_round_no_call(self):
        ask_fn = make_ask_fn()
        srv, port = self.start(ask_fn=ask_fn)
        did = self.create_discussion(port)
        status, _, resp_body = request(
            "POST", port, f"/api/discussions/{did}/arbitration", {})
        self.assertEqual(status, 409, resp_body)
        self.assertEqual(json.loads(resp_body)["code"], "boundary")
        self.assertEqual(len(ask_fn.calls), 0)

    def test_after_round_counts_usage(self):
        ask_fn = make_ask_fn()
        srv, port = self.start(ask_fn=ask_fn)
        did = self.create_discussion(port)
        self.run_rounds(port, did, 1)
        before = json.loads(request(
            "GET", port, f"/api/discussions/{did}")[2])
        before_calls = before["status"]["usage"]["calls"]
        status, _, resp_body = request(
            "POST", port, f"/api/discussions/{did}/arbitration", {})
        self.assertEqual(status, 200, resp_body)
        data = json.loads(resp_body)
        self.assertEqual(data["status"]["usage"]["calls"], before_calls + 1)

    def test_does_not_affect_rounds(self):
        ask_fn = make_ask_fn()
        srv, port = self.start(ask_fn=ask_fn)
        did = self.create_discussion(port)
        self.run_rounds(port, did, 1)
        status, _, resp_body = request(
            "POST", port, f"/api/discussions/{did}/arbitration", {})
        self.assertEqual(status, 200, resp_body)
        self.assertEqual(
            json.loads(resp_body)["status"]["rounds_completed"], 1)
        status, _, resp_body = request(
            "POST", port, f"/api/discussions/{did}/rounds", {})
        self.assertEqual(status, 200, resp_body)
        self.assertEqual(
            json.loads(resp_body)["status"]["rounds_completed"], 2)

    def test_arbitration_boundary_emits_no_event(self):
        # 工作包 025 回歸：arbitration_started 必須在 can_arbitrate() 前提
        # 檢查「之後」才發（on_start 回呼），否則前提不成立時會發出一則
        # 沒有結局的事件，畫面的佔位永遠清不掉。
        ask_fn = make_ask_fn()
        srv, port = self.start(ask_fn=ask_fn)
        did = self.create_discussion(port)
        status, _, resp_body = request(
            "POST", port, f"/api/discussions/{did}/arbitration", {})
        self.assertEqual(status, 409, resp_body)
        self.assertEqual(json.loads(resp_body)["code"], "boundary")
        # SSE 不會自己結束：用短 timeout 一行一行讀，收集已送達的資料，
        # 斷言其中沒有 arbitration_started。
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=2)
        conn.request("GET", f"/api/discussions/{did}/events?cursor=0")
        resp = conn.getresponse()
        lines = []
        try:
            while True:
                line = resp.readline()
                if not line:
                    break
                lines.append(line)
        except socket.timeout:
            pass
        finally:
            conn.close()
        data = b"".join(lines)
        self.assertNotIn(b"arbitration_started", data)


class ExportTest(ServerCase):
    def test_export_headers(self):
        srv, port = self.start()
        did = self.create_discussion(port)
        self.run_rounds(port, did, 1)
        status, headers, _ = request(
            "GET", port, f"/api/discussions/{did}/export.md")
        self.assertEqual(status, 200)
        self.assertEqual(headers.get("Content-Type"),
                         "text/markdown; charset=utf-8")
        self.assertEqual(headers.get("Cache-Control"), "no-store")
        self.assertEqual(headers.get("X-Content-Type-Options"), "nosniff")
        self.assertEqual(
            headers.get("Content-Disposition"),
            f'attachment; filename="council-{did}.md"')

    def test_export_body_matches_render_markdown(self):
        srv, port = self.start()
        did = self.create_discussion(port)
        self.run_rounds(port, did, 1)
        status, _, body = request(
            "GET", port, f"/api/discussions/{did}/export.md")
        self.assertEqual(status, 200)
        session = srv.store.get(did)
        _, _, meta_body = request(
            "GET", port, f"/api/discussions/{did}")
        meta = json.loads(meta_body)
        expected = transcript.render_markdown(
            meta, session.events_since(0)).encode("utf-8")
        self.assertEqual(body, expected)

    def test_export_missing_id_404(self):
        srv, port = self.start()
        status, _, _ = request(
            "GET", port, "/api/discussions/no-such/export.md")
        self.assertEqual(status, 404)

    def test_export_post_404(self):
        srv, port = self.start()
        did = self.create_discussion(port)
        status, _, _ = request(
            "POST", port, f"/api/discussions/{did}/export.md", {})
        self.assertEqual(status, 404)

    def test_export_host_gate_403(self):
        srv, port = self.start()
        did = self.create_discussion(port)
        status, _, _ = request(
            "GET", port, f"/api/discussions/{did}/export.md",
            headers={"Host": "evil.example.com"})
        self.assertEqual(status, 403)

    def test_export_does_not_claim_execution_right(self):
        srv, port = self.start()
        did = self.create_discussion(port)
        self.run_rounds(port, did, 1)
        status, _, _ = request(
            "GET", port, f"/api/discussions/{did}/export.md")
        self.assertEqual(status, 200)
        session = srv.store.get(did)
        self.assertTrue(session.try_claim())
        session.release()


class SseTest(ServerCase):
    def test_event_order_and_monotonic_seqs(self):
        srv, port = self.start()
        did = self.create_discussion(port)
        self.run_rounds(port, did, 1)
        resp = open_sse(port, f"/api/discussions/{did}/events")
        self.addCleanup(resp.close)
        events = read_sse_events(resp, 4)
        self.assertEqual(
            [e["kind"] for e in events],
            ["round_started", "speech", "speech", "round_finished"])
        self.assertEqual([e["seq"] for e in events], [1, 2, 3, 4])

    def test_multiline_speech_single_data_line(self):
        text = "第一行\n第二行: 有冒號\n[立場: 保留] [補充: 有]"
        ask_fn = make_ask_fn(text=text)
        srv, port = self.start(ask_fn=ask_fn)
        did = self.create_discussion(port)
        self.run_rounds(port, did, 1)
        resp = open_sse(port, f"/api/discussions/{did}/events")
        self.addCleanup(resp.close)
        events = read_sse_events(resp, 4)
        for e in events:
            self.assertEqual(
                e["data_count"], 1, f"事件 {e['seq']} 的 data 不是單行")
        speeches = [e["data"] for e in events if e["kind"] == "speech"]
        self.assertEqual(len(speeches), 2)
        for rec in speeches:
            self.assertEqual(rec["text"], text)

    def test_cursor_query_resumes(self):
        srv, port = self.start()
        did = self.create_discussion(port)
        self.run_rounds(port, did, 1)
        resp = open_sse(port, f"/api/discussions/{did}/events?cursor=2")
        self.addCleanup(resp.close)
        events = read_sse_events(resp, 2)
        self.assertEqual([e["seq"] for e in events], [3, 4])

    def test_last_event_id_wins_over_query(self):
        srv, port = self.start()
        did = self.create_discussion(port)
        self.run_rounds(port, did, 1)
        resp = open_sse(
            port, f"/api/discussions/{did}/events?cursor=1",
            headers={"Last-Event-ID": "2"})
        self.addCleanup(resp.close)
        events = read_sse_events(resp, 2)
        self.assertEqual([e["seq"] for e in events], [3, 4])

    def test_bad_cursor_replays_all(self):
        srv, port = self.start()
        did = self.create_discussion(port)
        self.run_rounds(port, did, 1)
        resp = open_sse(port, f"/api/discussions/{did}/events?cursor=abc")
        self.addCleanup(resp.close)
        events = read_sse_events(resp, 4)
        self.assertEqual([e["seq"] for e in events], [1, 2, 3, 4])

    def test_sse_does_not_block_round(self):
        srv, port = self.start()
        did = self.create_discussion(port)
        resp = open_sse(port, f"/api/discussions/{did}/events")
        self.addCleanup(resp.close)
        status, _, resp_body = request(
            "POST", port, f"/api/discussions/{did}/rounds", {})
        self.assertEqual(status, 200, resp_body)
        events = read_sse_events(resp, 4)
        self.assertEqual(
            [e["kind"] for e in events],
            ["round_started", "speech", "speech", "round_finished"])


def make_seats():
    return [
        {"seat_id": "a1", "cli": "claude", "model": None, "role": "advisor"},
        {"seat_id": "a2", "cli": "opencode", "model": None, "role": "advisor"},
        {"seat_id": "arb", "cli": "gemini", "model": "m", "role": "arbiter"},
    ]


class OnRecordTest(unittest.TestCase):
    def test_on_record_called_per_advisor_in_order(self):
        d = state.Discussion("問題", make_seats())
        got = []
        fake = make_ask_fn()
        orchestrator.run_round(d, fake, on_record=got.append)
        self.assertEqual(len(got), 2)
        self.assertEqual([r["seat_id"] for r in got], ["a1", "a2"])

    def test_on_record_exception_does_not_break_round(self):
        d = state.Discussion("問題", make_seats())

        def boom(record):
            raise RuntimeError("boom")

        fake = make_ask_fn()
        status = orchestrator.run_round(d, fake, on_record=boom)
        self.assertEqual(status["rounds_completed"], 1)
        self.assertEqual(status["phase"], state.PHASE_AWAITING_USER)
        self.assertEqual(len(fake.calls), 2)

    def test_without_on_record_unchanged(self):
        d = state.Discussion("問題", make_seats())
        fake = make_ask_fn()
        status = orchestrator.run_round(d, fake)
        self.assertEqual(status, d.status())
        self.assertEqual(len(fake.calls), 2)


class OnStartTest(unittest.TestCase):
    def test_on_start_fires_before_ask_fn(self):
        d = state.Discussion("問題", make_seats())
        orchestrator.run_round(d, make_ask_fn())
        order = []

        def on_start():
            order.append("on_start")

        def ask_fn(cli, prompt, model, timeout_s, max_chars):
            order.append("ask_fn")
            return make_ask_fn()(cli, prompt, model, timeout_s, max_chars)

        orchestrator.run_arbitration(d, ask_fn, on_start=on_start)
        self.assertEqual(order, ["on_start", "ask_fn"])

    def test_on_start_not_called_when_boundary(self):
        d = state.Discussion("問題", make_seats())
        called = []
        fake = make_ask_fn()
        with self.assertRaises(state.BoundaryError):
            orchestrator.run_arbitration(
                d, fake, on_start=lambda: called.append(1))
        self.assertEqual(called, [])
        self.assertEqual(len(fake.calls), 0)

    def test_on_start_exception_does_not_break_arbitration(self):
        d = state.Discussion("問題", make_seats())
        orchestrator.run_round(d, make_ask_fn())

        def boom():
            raise RuntimeError("boom")

        record = orchestrator.run_arbitration(d, make_ask_fn(), on_start=boom)
        self.assertEqual(record["ok"], True)

    def test_without_on_start_unchanged(self):
        d = state.Discussion("問題", make_seats())
        orchestrator.run_round(d, make_ask_fn())
        fake = make_ask_fn()
        record = orchestrator.run_arbitration(d, fake)
        self.assertEqual(record, d.arbitrations[-1])
        self.assertEqual(len(fake.calls), 1)


class HostWhitelistTest(ServerCase):
    def test_rejects_non_loopback_hosts(self):
        for bad in ("0.0.0.0", "", "192.168.1.5", "example.com"):
            with self.subTest(host=bad):
                with self.assertRaises(ValueError):
                    server.build_server(
                        ask_fn=make_ask_fn(), live=False, host=bad)

    def test_accepts_localhost_host(self):
        srv, port = self.start(host="localhost")
        did = self.create_discussion(port)
        status, _, resp_body = request(
            "GET", port, f"/api/discussions/{did}")
        self.assertEqual(status, 200, resp_body)


if __name__ == "__main__":
    unittest.main()
