"""037c 契約測試：現在會紅，交付後要綠。

跨 CLI 的 usage 不得被扁平合併成一個看起來像總和的數字。
資料來自 2026-08-07 macOS 上的真實呼叫（gemini ＋ codex 同一輪）。
"""
import copy
import sys
import unittest
from pathlib import Path

SRC_DIR = Path(__file__).resolve().parent.parent / "src"
sys.path.insert(0, str(SRC_DIR))

from engine import state  # noqa: E402

STATIC_DIR = SRC_DIR / "static"
INDEX_PATH = STATIC_DIR / "index.html"


def make_seats(advisor_ids=("a1", "a2"), arbiter_id="arb") -> list:
    seats = [{"seat_id": sid, "cli": "claude", "model": None, "role": "advisor"}
             for sid in advisor_ids]
    seats.append({"seat_id": arbiter_id, "cli": "codex", "model": "m",
                  "role": "arbiter"})
    return seats


def ok_result(text="答覆\n[立場: 同意] [補充: 無]", usage=None) -> dict:
    return {"ok": True, "text": text, "truncated": False, "error": None,
            "elapsed_s": 1.0, "model_used": "model-x", "usage": usage}


GEMINI = {"input": 10324, "prompt": 10324, "candidates": 34,
          "total": 11283, "cached": 0, "thoughts": 925, "tool": 0}
CODEX = {"tokens_used": 3174}


class CrossCliUsageContractTest(unittest.TestCase):
    def _two_families(self) -> dict:
        d = state.Discussion("q", make_seats())
        d.begin_round()
        d.record_speech("a1", ok_result(usage=copy.deepcopy(GEMINI)))
        d.record_speech("a2", ok_result(usage=copy.deepcopy(CODEX)))
        d.end_round()
        return d.status()

    def test_no_outward_field_claims_to_be_a_total(self):
        # 現在會紅：status()["usage"]["total"]["total"] == 11283，
        # 看起來像兩席總和、實際只有 gemini 一家。
        st = self._two_families()
        self.assertNotIn("total", st["usage"])

    def test_per_seat_usage_stays_verbatim(self):
        st = self._two_families()
        self.assertEqual(st["usage"]["by_seat"]["a1"]["usage"], GEMINI)
        self.assertEqual(st["usage"]["by_seat"]["a2"]["usage"], CODEX)

    def test_calls_is_still_a_real_total(self):
        # calls 與 CLI 家別無關，它是真的總和，不得一起被拿掉。
        st = self._two_families()
        self.assertEqual(st["usage"]["calls"], 2)

    def test_same_seat_across_rounds_still_accumulates(self):
        # merge_usage 在同一席（＝同一家 CLI）內仍必須累加，不得整個砍掉。
        d = state.Discussion("q", make_seats())
        for _ in range(2):
            d.begin_round()
            d.record_speech("a1", ok_result(usage={"input_tokens": 10}))
            d.record_speech("a2", ok_result(usage={"input_tokens": 1}))
            d.end_round()
            d.request_next_round()
        st = d.status()
        self.assertEqual(st["usage"]["by_seat"]["a1"]["usage"]["input_tokens"], 20)
        self.assertEqual(st["usage"]["by_seat"]["a1"]["calls"], 2)

    def test_no_outward_total_after_arbitration(self):
        # record_arbitration 也曾累加 _usage_total（SPEC.md §6.1：仲裁用量必須
        # 併進本次討論）——那條路徑也不能把 total 復活，arb 的 usage 必須照原文
        # 留在 by_seat 側。
        d = state.Discussion("q", make_seats())
        d.begin_round()
        d.record_speech("a1", ok_result(usage=copy.deepcopy(GEMINI)))
        d.record_speech("a2", ok_result(usage=copy.deepcopy(CODEX)))
        d.end_round()
        d.record_arbitration(ok_result(usage=copy.deepcopy(CODEX)))
        st = d.status()
        self.assertNotIn("total", st["usage"])
        self.assertEqual(st["usage"]["by_seat"]["arb"]["usage"], CODEX)


class CliMustNotReadRemovedFieldTest(unittest.TestCase):
    def test_cli_py_does_not_reference_usage_total(self):
        # cli.py 的「累計 usage」直接 print usage['total']，是整個 bug 唯一裸奔的
        # 地方（第 4.2 節）。欄位移除後該行會變成 KeyError，而 cli.py 沒有任何
        # 既有測試 ⇒ 用結構守門擋復活。
        cli_source = (SRC_DIR / "cli.py").read_text(encoding="utf-8")
        self.assertNotIn("usage['total']", cli_source)


class UiMustNotReadRemovedFieldTest(unittest.TestCase):
    def test_index_html_does_not_reference_usage_total(self):
        # 現在會紅：index.html 有 `var total = usage.total;`。
        # 這條同時守住空狀態條件不得再掛在該欄位上。
        html = INDEX_PATH.read_text(encoding="utf-8")
        self.assertNotIn("usage.total", html)


if __name__ == "__main__":
    unittest.main()
