"""本機 HTTP 伺服器（SPEC.md §7）：建立討論、開輪、叫仲裁者、SSE 事件流。

本模組不認識任何 CLI adapter：真實呼叫由 serve.py 以 ask_fn 注入（與
orchestrator.py 同一個手法），因此不得 import adapters。伺服器也不開檔——
脈絡只接受請求裡的字串本文，狀態查詢不回傳脈絡原文（SPEC.md §7.2）。
"""

import json
import threading
import time
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

import ui

from engine import orchestrator
from engine import sessions
from engine import state
from engine import transcript
from engine.wiring import parse_seat_spec

EVENT_KINDS = (
    "round_started",
    "speech",
    "round_finished",
    "arbitration_started",
    "arbitration_finished",
    "error",
)

MAX_CONTENT_LENGTH = 5_000_000
HEARTBEAT_INTERVAL_S = 15
ALLOWED_HOSTS = ("127.0.0.1", "localhost")

DISCUSSION_KEYS = ("question", "advisors", "arbiter", "context")
ROUND_KEYS = ("confirm_over_cap",)


def _match(path: str):
    """把路徑切成 (路由名, session id)；不匹配任何路由回 (None, None)。"""
    parts = path.split("/")
    if len(parts) >= 3 and parts[1] == "api" and parts[2] == "discussions":
        rest = parts[3:]
        if len(rest) == 0:
            return ("discussions", None)
        if len(rest) == 1 and rest[0]:
            return ("discussion", rest[0])
        if len(rest) == 2 and rest[0] and rest[1] in (
                "rounds", "arbitration", "events", "export.md"):
            return (rest[1], rest[0])
    return (None, None)


def _parse_cursor(raw: str) -> int:
    """解析 SSE 游標；不是十進位非負整數一律當成 0（重播全部）。"""
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return 0
    if value < 0:
        return 0
    return value


class _Server(ThreadingHTTPServer):
    daemon_threads = True  # SSE 連線長期佔住執行緒，不設會讓行程關不掉


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self._dispatch()

    def do_POST(self):
        self._dispatch()

    def do_DELETE(self):
        self._dispatch()

    def _dispatch(self):
        try:
            if not self._gate():
                return
            kind, arg = _match(urlparse(self.path).path)
            if self.command == "GET":
                if urlparse(self.path).path == "/":
                    self._get_index()
                elif kind == "discussion":
                    self._get_discussion(arg)
                elif kind == "events":
                    self._get_events(arg)
                elif kind == "export.md":
                    self._get_export(arg)
                else:
                    self._reply_error(404, "找不到該路徑")
            elif self.command == "POST":
                is_shutdown = urlparse(self.path).path == "/api/shutdown"
                if not is_shutdown and kind not in (
                        "discussions", "rounds", "arbitration"):
                    self._reply_error(404, "找不到該路徑")
                    return
                body = self._parse_json_body(self._read_body())
                if body is None:
                    self._reply_error(400, "請求 body 不是合法的 JSON 物件")
                    return
                if is_shutdown:
                    self._post_shutdown(body)
                elif kind == "discussions":
                    self._post_discussions(body)
                elif kind == "rounds":
                    self._post_rounds(arg, body)
                else:
                    self._post_arbitration(arg, body)
            else:
                if kind is None:
                    self._reply_error(404, "找不到該路徑")
                else:
                    self._reply_error(405, "該路徑不支援這個方法")
        except Exception:
            # body 會進到瀏覽器，絕不能放例外訊息或 traceback；
            # stderr 只在使用者自己的終端機，可以印。
            traceback.print_exc()
            try:
                self._reply_error(500, "內部錯誤")
            except Exception:
                pass

    def _gate(self) -> bool:
        """SPEC.md §7.2 的請求守門（第 1～3 道），順序即規格順序。"""
        port = self.server.server_address[1]
        host_header = self.headers.get("Host")
        if host_header not in (f"127.0.0.1:{port}", f"localhost:{port}"):
            self._reply_error(403, "Host 標頭不符：本伺服器只服務本機（SPEC.md §7.2）")
            return False

        origin = self.headers.get("Origin")
        if origin is not None and origin not in (
                f"http://127.0.0.1:{port}", f"http://localhost:{port}"):
            self._reply_error(403, "Origin 不符：拒絕跨來源存取")
            return False

        content_length = 0
        raw_length = self.headers.get("Content-Length")
        if raw_length is not None:
            try:
                content_length = int(raw_length)
            except ValueError:
                content_length = -1
        # 一律以「POST」判定，不是「有 body」：/rounds 與 /arbitration 都接受空 body，
        # 綁在 body 長度上等於讓 simple request 繞過 preflight（SPEC.md §7.2）。
        if self.command == "POST":
            content_type = self.headers.get("Content-Type", "")
            if not content_type.startswith("application/json"):
                self._reply_error(415, "Content-Type 必須是 application/json")
                return False
        if content_length < 0:
            self._reply_error(400, "Content-Length 必須是十進位整數")
            return False
        if content_length > MAX_CONTENT_LENGTH:
            self._reply_error(413, "請求內容過大")
            return False
        self._body_len = content_length
        return True

    def _read_body(self) -> bytes:
        # 恰好讀 Content-Length 那麼多位元組；read() 不給長度會一直
        # 等到連線關閉 ⇒ 伺服器卡死。
        length = getattr(self, "_body_len", 0)
        if length <= 0:
            return b""
        return self.rfile.read(length)

    @staticmethod
    def _parse_json_body(raw: bytes):
        if not raw.strip():
            return {}
        try:
            value = json.loads(raw)
        except ValueError:
            return None
        if not isinstance(value, dict):
            return None
        return value

    def _reply_json(self, status, payload) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _reply_error(self, status, message, code=None) -> None:
        payload = {"error": message}
        if code is not None:
            payload["code"] = code
        self._reply_json(status, payload)

    def _common_shape(self, session) -> dict:
        discussion = session.discussion
        return {
            "id": session.id,
            "live": self.server.live,
            "busy": session.is_busy,
            "question": discussion.question,
            "context_chars": len(discussion.context),
            "seats": discussion.seats,
            "status": session.snapshot,
        }

    def _get_index(self) -> None:
        # no-store：頁面內容在行程啟動時就固定了（ui.py 只讀一次），
        # 讓瀏覽器也不要留舊的，重啟伺服器就一定看到新版。
        body = ui.INDEX_HTML
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        # SPEC.md §7.2 第 5 道：前四道防的是跨來源 fetch()，內嵌 iframe 繞過的
        # 是整組——被框住的頁面自己發的請求，四道全部通過。frame-ancestors 只在
        # 回應標頭有效，寫在頁面的 <meta> 裡瀏覽器不認。
        self.send_header("Content-Security-Policy", "frame-ancestors 'none'")
        self.send_header("X-Frame-Options", "DENY")
        self.end_headers()
        self.wfile.write(body)

    def _get_discussion(self, session_id) -> None:
        session = self.server.store.get(session_id)
        if session is None:
            self._reply_error(404, "找不到該討論")
            return
        self._reply_json(200, self._common_shape(session))

    def _get_export(self, session_id) -> None:
        session = self.server.store.get(session_id)
        if session is None:
            self._reply_error(404, "找不到該討論")
            return
        # 讀者路徑：絕對不拿執行權（與 SSE 同一條規矩），否則「有人在匯出」
        # 會變成「沒有人能開下一輪」。逐字稿一律從事件流重播，不讀
        # discussion.rounds——那會被邊跑邊 append（SPEC.md §7.1）。
        body = transcript.render_markdown(
            self._common_shape(session), session.events_since(0)
        ).encode("utf-8")
        filename = "council-" + session.id + ".md"
        self.send_response(200)
        self.send_header("Content-Type", "text/markdown; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Disposition",
                         f'attachment; filename="{filename}"')
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def _post_discussions(self, body) -> None:
        unknown = set(body) - set(DISCUSSION_KEYS)
        if unknown:
            self._reply_error(400, f"不認識的鍵：{', '.join(sorted(unknown))}")
            return
        question = body.get("question")
        advisors = body.get("advisors")
        arbiter = body.get("arbiter")
        context = body.get("context", "")
        if not isinstance(question, str) or not question.strip():
            self._reply_error(400, "question 必須是非空的字串")
            return
        if not isinstance(advisors, list) or not advisors:
            self._reply_error(400, "advisors 必須是非空的字串 list")
            return
        if not all(isinstance(s, str) for s in advisors):
            self._reply_error(400, "advisors 必須全部是字串")
            return
        if not isinstance(arbiter, str):
            self._reply_error(400, "arbiter 必須是字串")
            return
        if not isinstance(context, str):
            self._reply_error(400, "context 必須是字串")
            return
        try:
            seats = []
            for i, spec in enumerate(advisors):
                seat = parse_seat_spec(spec, seat_id="", role=state.ADVISOR)
                seat["seat_id"] = f"{seat['cli']}-{i + 1}"
                seats.append(seat)
            seat = parse_seat_spec(arbiter, seat_id="", role=state.ARBITER)
            seat["seat_id"] = "arb"
            seats.append(seat)
            discussion = state.Discussion(question, seats, context=context)
        except ValueError as exc:
            self._reply_error(400, str(exc))
            return
        session = self.server.store.create(discussion)
        self._reply_json(200, self._common_shape(session))

    def _post_rounds(self, session_id, body) -> None:
        unknown = set(body) - set(ROUND_KEYS)
        if unknown:
            self._reply_error(400, f"不認識的鍵：{', '.join(sorted(unknown))}")
            return
        confirm = body.get("confirm_over_cap", False)
        if not isinstance(confirm, bool):
            self._reply_error(400, "confirm_over_cap 必須是布林值")
            return
        session = self.server.store.get(session_id)
        if session is None:
            self._reply_error(404, "找不到該討論")
            return
        # 執行權必須是最先拿的動作，在任何相位判斷之前——兩個分頁同時按
        # 「再一輪」，兩條執行緒會同時通過邊界 1 的相位檢查，跑出兩輪（§7.1）。
        if not session.try_claim():
            self._reply_json(409, {"error": "討論正在執行中", "code": "busy"})
            return
        try:
            try:
                discussion = session.discussion
                if discussion.phase == state.PHASE_AWAITING_USER:
                    discussion.request_next_round(confirm_over_cap=confirm)
                session.append_event(
                    "round_started", {"round": len(discussion.rounds) + 1})
                orchestrator.run_round(
                    discussion, self.server.ask_fn,
                    timeout_s=self.server.timeout_s,
                    max_chars=self.server.max_chars,
                    on_record=lambda rec: session.append_event("speech", rec))
                snapshot = session.refresh()
                session.append_event(
                    "round_finished",
                    {"round": len(discussion.rounds), "status": snapshot})
            except state.BoundaryError as exc:
                self._reply_error(409, str(exc), code="boundary")
                return
        finally:
            session.release()

        self._reply_json(200, self._common_shape(session))

    def _post_arbitration(self, session_id, body) -> None:
        if body:
            self._reply_error(400, "arbitration 不接受任何 body 鍵")
            return
        session = self.server.store.get(session_id)
        if session is None:
            self._reply_error(404, "找不到該討論")
            return
        if not session.try_claim():
            self._reply_json(409, {"error": "討論正在執行中", "code": "busy"})
            return
        try:
            try:
                discussion = session.discussion
                # arbitration_started 由 run_arbitration 的 on_start 回呼發出：
                # 仍在 ask_fn 之前（畫面先亮），但已在 can_arbitrate() 前提
                # 檢查之後 ⇒ 前提不成立時不會發出一則沒有結局的事件。
                record = orchestrator.run_arbitration(
                    discussion, self.server.ask_fn,
                    timeout_s=self.server.timeout_s,
                    max_chars=self.server.max_chars,
                    on_start=lambda: session.append_event(
                        "arbitration_started",
                        {"seat_id": discussion.arbiter["seat_id"]}))
                snapshot = session.refresh()
                session.append_event(
                    "arbitration_finished",
                    {"record": record, "status": snapshot})
            except state.BoundaryError as exc:
                self._reply_error(409, str(exc), code="boundary")
                return
        finally:
            session.release()

        self._reply_json(200, self._common_shape(session))

    def _post_shutdown(self, body) -> None:
        if body:
            self._reply_error(400, "shutdown 不接受任何 body 鍵")
            return
        # 🔴 順序就是規格，不可對調：回應必須先完整送出去，才能停迴圈。
        # 反過來（handler 裡同步 shutdown()）會讓瀏覽器看到連線被重置，
        # 使用者分不出「成功關閉」與「當掉了」。
        self._reply_json(200, {"stopping": True})
        self.wfile.flush()
        threading.Thread(target=self.server.shutdown, daemon=True).start()

    def _get_events(self, session_id) -> None:
        session = self.server.store.get(session_id)
        if session is None:
            self._reply_error(404, "找不到該討論")
            return
        # 讀者路徑：絕對不拿執行權，否則「有人在看畫面」會變成
        # 「沒有人能開下一輪」。
        cursor = self._parse_cursor_header_or_query()
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "close")
        self.end_headers()
        last_emit = time.monotonic()
        try:
            while True:
                events = session.events_since(cursor)
                for event in events:
                    self._write_sse_event(event)
                    cursor = event["seq"]
                    last_emit = time.monotonic()
                if time.monotonic() - last_emit >= HEARTBEAT_INTERVAL_S:
                    self.wfile.write(b": keep-alive\n\n")
                    self.wfile.flush()
                    last_emit = time.monotonic()
                time.sleep(0.25)
        except (BrokenPipeError, ConnectionResetError):
            # 客戶端斷線，直接收工，不要讓 traceback 淹沒終端機。
            return

    def _parse_cursor_header_or_query(self) -> int:
        last_event_id = self.headers.get("Last-Event-ID")
        if last_event_id is not None:
            return _parse_cursor(last_event_id)
        query = parse_qs(urlparse(self.path).query)
        return _parse_cursor(query.get("cursor", ["0"])[0])

    def _write_sse_event(self, event) -> None:
        # data 一律是 json.dumps 的結果：模型發言的多行文字會被編成 \n
        # 兩個字元，保證結果是單行，不會把 data: 欄位切成兩段。
        data_line = json.dumps(event["data"], ensure_ascii=False)
        chunk = (
            f"id: {event['seq']}\n"
            f"event: {event['kind']}\n"
            f"data: {data_line}\n\n"
        )
        self.wfile.write(chunk.encode("utf-8"))
        self.wfile.flush()


def build_server(*, ask_fn, live, host="127.0.0.1", port=8765,
                 timeout_s=orchestrator.DEFAULT_TIMEOUT_S,
                 max_chars=orchestrator.DEFAULT_MAX_CHARS):
    """建立並回傳一個已綁定但尚未 serve_forever() 的伺服器物件。"""
    if host not in ALLOWED_HOSTS:
        raise ValueError(
            f"host 只接受 loopback（{' / '.join(ALLOWED_HOSTS)}），不允許「{host}」："
            "綁到其他位址會讓本機以外的人（或被瀏覽器開到的惡意網頁）也能"
            "替使用者花訂閱額度（SPEC.md §7.2）")
    # host 通過白名單後一律綁 127.0.0.1：localhost 可能解析成 ::1，
    # 而 127.0.0.1 一定存在。
    httpd = _Server(("127.0.0.1", port), _Handler)
    httpd.ask_fn = ask_fn
    httpd.live = live
    httpd.timeout_s = timeout_s
    httpd.max_chars = max_chars
    httpd.store = sessions.SessionStore()
    return httpd
