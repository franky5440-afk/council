"""038b 契約測試：現在會紅，交付後要綠。

失敗次數不能只有 web UI 看得見——命令列與匯出的逐字稿也要說。
"""
import io
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path

SRC_DIR = Path(__file__).resolve().parent.parent / "src"
sys.path.insert(0, str(SRC_DIR))

import cli  # noqa: E402
from engine import transcript  # noqa: E402


def make_status(by_seat) -> dict:
    return {
        "phase": "awaiting_user",
        "rounds_completed": 1,
        "max_rounds": 5,
        "at_cap": False,
        "can_start_round": False,
        "converged": False,
        "format_violations": 0,
        "usage": {"calls": sum(p["calls"] for p in by_seat.values()),
                  "by_seat": by_seat},
    }


def make_meta(by_seat) -> dict:
    return {
        "id": "sess-test-038b",
        "live": True,
        "busy": False,
        "question": "q",
        "context_chars": 0,
        "seats": [
            {"seat_id": "a1", "cli": "opencode", "model": None,
             "role": "advisor"},
            {"seat_id": "a2", "cli": "opencode", "model": None,
             "role": "advisor"},
            {"seat_id": "arb", "cli": "claude", "model": None,
             "role": "arbiter"},
        ],
        "status": make_status(by_seat),
    }


class CliShowsFailuresTest(unittest.TestCase):
    def test_failed_seat_is_printed(self):
        # 現在會紅：cli.py 只印 calls ⇒ 命令列使用者看不出是哪一席在失敗，
        # 只能從逐字稿正文的「（未回應：<錯誤>）」自己推。
        buf = io.StringIO()
        with redirect_stdout(buf):
            cli._print_status(make_status({
                "a1": {"calls": 2, "failed": 2, "usage": {}},
                "a2": {"calls": 2, "failed": 0, "usage": {}},
            }))
        out = buf.getvalue()
        self.assertIn("failed=2", out)

    def test_healthy_seat_shows_no_failed(self):
        # 護欄：failed 為 0 的席次不得掛一個 0 出來（每席都掛 0 就是噪音，
        # 與 web UI 的規則一致）。
        buf = io.StringIO()
        with redirect_stdout(buf):
            cli._print_status(make_status({
                "a2": {"calls": 2, "failed": 0, "usage": {}},
            }))
        self.assertNotIn("failed", buf.getvalue())

    def test_status_without_failed_key_does_not_explode(self):
        # 🔴 護欄：舊格式的 status（by_seat 沒有 failed 鍵）不得炸。
        # 既有測試就是這樣傳的（tests/test_transcript.py 的 by_seat 只有
        # calls 與 usage）⇒ 實作必須用 .get("failed", 0)，不能用 per["failed"]。
        buf = io.StringIO()
        with redirect_stdout(buf):
            cli._print_status(make_status({"a1": {"calls": 1, "usage": {}}}))
        self.assertNotIn("failed", buf.getvalue())

    def test_failed_and_usage_stay_on_one_line(self):
        # 我補的：契約六條的失敗席次樣本全是 usage={} ⇒ 「失敗與用量同時存在」
        # 沒有測試。若實作把 failed 接到 usage 之後、或寫成另一行，六條仍全綠。
        # 這條釘住「failed 在 calls 與 usage 之間、同一行」。
        buf = io.StringIO()
        with redirect_stdout(buf):
            cli._print_status(make_status({
                "a1": {"calls": 2, "failed": 2,
                       "usage": {"tokens": {"input": 1}}},
            }))
        out = buf.getvalue()
        self.assertIn("calls=2，failed=2，usage=", out)


class TranscriptShowsFailuresTest(unittest.TestCase):
    def test_failed_seat_is_exported(self):
        # 現在會紅：匯出的 md 只有 calls ⇒ 存檔之後就再也看不出哪一席壞過。
        out = transcript.render_markdown(make_meta({
            "a1": {"calls": 2, "failed": 2, "usage": {}},
            "a2": {"calls": 2, "failed": 0, "usage": {}},
        }), [])
        self.assertIn("failed=2", out)

    def test_healthy_seat_shows_no_failed(self):
        # 護欄：這條同時保護既有的 test_transcript.py:228
        # （它斷言 "- a1：calls=1\n- a2：calls=1"）——failed 若做成永遠顯示，
        # 那條會壞，而它不該壞。
        out = transcript.render_markdown(make_meta({
            "a2": {"calls": 1, "failed": 0, "usage": {}},
        }), [])
        self.assertNotIn("failed", out)

    def test_status_without_failed_key_does_not_explode(self):
        # 🔴 護欄：同上，舊格式不得炸。
        out = transcript.render_markdown(make_meta({
            "a1": {"calls": 1, "usage": {}},
        }), [])
        self.assertNotIn("failed", out)

    def test_failed_stays_on_calls_line_above_usage_rows(self):
        # 我補的：契約六條的失敗席次樣本全是 usage={} ⇒ 「失敗與用量同時存在」
        # 沒有測試。逐字稿的用量是 calls 行底下的縮排子行；若 failed 被接到
        # 子行之後、或寫成獨立行，六條仍全綠。這條釘住 failed 必須留在 calls
        # 行、子行仍跟在它後面。
        out = transcript.render_markdown(make_meta({
            "a1": {"calls": 2, "failed": 2,
                   "usage": {"tokens": {"input": 1}}},
        }), [])
        self.assertIn("- a1：calls=2，failed=2\n  - tokens.input：1", out)


if __name__ == "__main__":
    unittest.main()
