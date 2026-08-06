import json
import sys
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path

SRC_DIR = Path(__file__).resolve().parent.parent / "src"
sys.path.insert(0, str(SRC_DIR))

import server  # noqa: E402
import ui  # noqa: E402

STATIC_DIR = SRC_DIR / "static"
INDEX_PATH = STATIC_DIR / "index.html"

CSP_EXACT = ("default-src 'none'; script-src 'unsafe-inline'; "
             "style-src 'unsafe-inline'; connect-src 'self'; img-src 'none'; "
             "form-action 'none'; base-uri 'none'")

EVENT_KINDS = ("round_started", "speech", "round_finished",
               "arbitration_started", "arbitration_finished", "error")


def request(method, port, path, body=None, headers=None):
    url = f"http://127.0.0.1:{port}{path}"
    data = None
    req_headers = {}
    if body is not None:
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


class UiRouteTest(unittest.TestCase):
    def start(self):
        srv = server.build_server(ask_fn=lambda *a, **k: None, live=False, port=0)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        self.addCleanup(srv.shutdown)
        self.addCleanup(srv.server_close)
        return srv, srv.server_address[1]

    def test_index_served_at_root(self):
        srv, port = self.start()
        status, headers, body = request("GET", port, "/")
        self.assertEqual(status, 200)
        self.assertEqual(headers.get("Content-Type"), "text/html; charset=utf-8")
        self.assertEqual(headers.get("Cache-Control"), "no-store")
        self.assertIn("Content-Length", headers)
        self.assertEqual(body, ui.INDEX_HTML)

    def test_index_no_access_control_headers(self):
        srv, port = self.start()
        _, headers, _ = request("GET", port, "/")
        for name in headers:
            self.assertFalse(name.lower().startswith("access-control-"),
                             f"回應帶了 CORS 標頭：{name}")

    def test_index_refuses_to_be_framed(self):
        """SPEC.md §7.2 第 5 道：內嵌 iframe 會讓前四道全部通過（Host 正確、
        Origin 同源、Content-Type 由頁面自己設、同源不需要 CORS），所以拒絕被
        內嵌必須靠回應標頭。frame-ancestors 寫在 <meta> 裡無效。"""
        srv, port = self.start()
        _, headers, _ = request("GET", port, "/")
        lowered = {name.lower(): value for name, value in headers.items()}
        self.assertEqual(lowered.get("x-frame-options"), "DENY")
        self.assertEqual(lowered.get("content-security-policy"),
                         "frame-ancestors 'none'")

    def test_index_ignores_query_string(self):
        srv, port = self.start()
        status, _, _ = request("GET", port, "/?x=1")
        self.assertEqual(status, 200)

    def test_index_only_exact_root_path(self):
        srv, port = self.start()
        for path in ("/index.html", "/static/index.html", "/../src/server.py"):
            status, _, _ = request("GET", port, path)
            self.assertEqual(status, 404, f"{path} 應回 404")

    def test_double_slash_normalized_by_stdlib(self):
        """http.server 的 parse_request() 內建 gh-87389 的 open redirect 防護，
        在進入 handler 之前就把開頭的多個 / 併成一個 ⇒ // 到我們手上時
        self.path 已經是 /。這不是我們的路由放寬：唯一的靜態路由仍然是
        == "/"，沒有任何「路徑→檔案」的對映。此測試釘住 stdlib 的這個行為，
        哪天它改了要有人看一眼。"""
        srv, port = self.start()
        for path in ("//", "///"):
            status, _, _ = request("GET", port, path)
            self.assertEqual(status, 200, f"{path} 應回 200")

    def test_index_still_gated_by_host(self):
        srv, port = self.start()
        status, _, _ = request(
            "GET", port, "/", headers={"Host": "evil.example.com"})
        self.assertEqual(status, 403)

    def test_post_to_root_404(self):
        srv, port = self.start()
        status, _, _ = request("POST", port, "/", {})
        self.assertEqual(status, 404)

    def test_discussion_api_not_shadowed(self):
        srv, port = self.start()
        status, _, _ = request("GET", port, "/api/discussions/no-such")
        self.assertEqual(status, 404)


class UiModuleTest(unittest.TestCase):
    def test_index_html_is_nonempty_bytes(self):
        self.assertIsInstance(ui.INDEX_HTML, bytes)
        self.assertGreater(len(ui.INDEX_HTML), 0)

    def test_ui_module_imports_nothing_forbidden(self):
        source = Path(ui.__file__).read_text(encoding="utf-8")
        for word in ("server", "engine", "adapters", "subprocess"):
            self.assertNotIn(word, source)


class IndexHtmlStructureTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = INDEX_PATH.read_text(encoding="utf-8")

    def test_no_html_injection_strings(self):
        for word in ("innerHTML", "outerHTML", "insertAdjacentHTML",
                     "document.write", "eval(", "new Function", "Function("):
            self.assertNotIn(word, self.source)

    def test_no_http_urls(self):
        for word in ("http://", "https://"):
            self.assertNotIn(word, self.source)

    def test_no_browser_storage(self):
        for word in ("localStorage", "sessionStorage", "indexedDB",
                     "document.cookie"):
            self.assertNotIn(word, self.source)

    def test_no_timers(self):
        for word in ("setInterval", "setTimeout"):
            self.assertNotIn(word, self.source)

    def test_uses_textcontent(self):
        self.assertIn("textContent", self.source)

    def test_csp_meta_exact(self):
        self.assertIn("Content-Security-Policy", self.source)
        self.assertIn(f'content="{CSP_EXACT}"', self.source)

    def test_single_inline_script_and_style(self):
        self.assertEqual(self.source.count("<script"), 1)
        self.assertEqual(self.source.count("<style"), 1)
        self.assertNotIn("<script src=", self.source)

    def test_confirm_over_cap_once_and_uses_confirm(self):
        self.assertEqual(self.source.count("confirm_over_cap"), 1)
        self.assertIn("confirm(", self.source)

    def test_first_round_button_label(self):
        """一輪都還沒跑過時按鈕不該寫「再一輪」——「再」預設前面有過一輪。
        ⚠️ 這是結構性斷言（只檢查原始碼字串），JS 的實際行為沒有自動化測試，
        本專案刻意不建 DOM 測試環境（SPEC.md §7：無建置步驟）。"""
        self.assertIn("開始討論（可延續數輪）", self.source)
        self.assertIn("再一輪（需確認）", self.source)
        self.assertIn("rounds_completed === 0", self.source)

    def test_usage_panel_shows_no_money(self):
        """Frank 實測回報：畫面出現金額會讓人以為 council 去打了 API 在收費。
        實際上 council 不呼叫任何模型 API，金額只是各家 CLI 依 API 定價換算的
        參考值 ⇒ 一律不顯示，只顯示 token 數。
        ⚠️ 這是結構性斷言（只檢查原始碼字串），JS 的實際行為沒有自動化測試，
        本專案刻意不建 DOM 測試環境（SPEC.md §7：無建置步驟）。"""
        self.assertNotIn("usage-cost", self.source)
        self.assertIn("isCostKey", self.source)

    def test_usage_total_is_labelled_as_not_a_sum(self):
        """merge_usage() 按鍵名相加，而 opencode 與 claude 的鍵名完全不同
        ⇒ total 區塊沒有任何欄位代表所有席次的真正總量，必須在畫面上講明白。"""
        self.assertIn("不是所有席次的總和", self.source)

    def test_advisor_order_is_documented(self):
        """席次順序就是發言順序，這件事只有實作知道，使用者看不出來。"""
        self.assertIn("由上到下就是發言順序", self.source)

    def test_all_event_kinds_listened(self):
        for kind in EVENT_KINDS:
            self.assertIn(kind, self.source)


if __name__ == "__main__":
    unittest.main()
