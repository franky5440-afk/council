"""038 契約測試：現在會紅，交付後要綠。

一席呼叫失敗不得讓整場討論永遠無法收斂，且失敗必須在對外狀態上看得見。
"""
import sys
import unittest
from pathlib import Path

SRC_DIR = Path(__file__).resolve().parent.parent / "src"
sys.path.insert(0, str(SRC_DIR))

from engine import state  # noqa: E402


def make_seats(advisor_ids=("a1", "a2"), arbiter_id="arb") -> list:
    seats = [{"seat_id": sid, "cli": "opencode", "model": None, "role": "advisor"}
             for sid in advisor_ids]
    seats.append({"seat_id": arbiter_id, "cli": "claude", "model": "m",
                  "role": "arbiter"})
    return seats


def done(text="答覆\n[立場: 同意] [補充: 無]") -> dict:
    """成功且表示沒有補充。"""
    return {"ok": True, "text": text, "truncated": False, "error": None,
            "elapsed_s": 1.0, "model_used": "model-x", "usage": None}


def more() -> dict:
    """成功且表示還有補充。"""
    return done("答覆\n[立場: 保留] [補充: 有]")


def failed() -> dict:
    """呼叫失敗（模型下架、401、逾時都長這樣）。"""
    return {"ok": False, "text": "", "truncated": False,
            "error": "command exited with code 1", "elapsed_s": 6.8,
            "model_used": None, "usage": None}


def one_round(d, results: dict) -> None:
    d.begin_round()
    for seat_id, result in results.items():
        d.record_speech(seat_id, result)
    d.end_round()


class FailedSeatMustNotBlockConvergenceTest(unittest.TestCase):
    def test_failed_seat_does_not_block_convergence(self):
        # 現在會紅：失敗席次被記成 more=True，而 converged() 要求全體 more is False
        # ⇒ 一席持續失敗的討論在數學上永遠不可能收斂，只能跑滿 max_rounds。
        d = state.Discussion("q", make_seats())
        one_round(d, {"a1": failed(), "a2": done()})
        self.assertTrue(d.converged())
        self.assertTrue(d.status()["converged"])

    def test_all_seats_failed_is_not_convergence(self):
        # 🔴 這條防的是修法本身的陷阱：若改成「只看成功的席次」而忘了處理空集合，
        # all([]) 回 True ⇒ 零份意見卻宣告收斂，比原本的 bug 更糟。
        d = state.Discussion("q", make_seats())
        one_round(d, {"a1": failed(), "a2": failed()})
        self.assertFalse(d.converged())
        self.assertFalse(d.status()["converged"])

    def test_successful_seat_wanting_more_still_blocks(self):
        # 護欄：成功且說「還有補充」的席次仍必須擋住收斂，這是邊界 5 的本體。
        d = state.Discussion("q", make_seats())
        one_round(d, {"a1": failed(), "a2": more()})
        self.assertFalse(d.converged())

    def test_unanimous_no_more_still_converges(self):
        # 護欄：沒有任何失敗時的原本行為不得被改動。
        d = state.Discussion("q", make_seats())
        one_round(d, {"a1": done(), "a2": done()})
        self.assertTrue(d.converged())


class FailuresMustBeVisibleTest(unittest.TestCase):
    def test_failed_count_is_reported_per_seat(self):
        # 現在會紅：by_seat 只有 calls，一次 401 與一次成功回答記成同一件事
        # ⇒ 使用者看不出是哪一席壞了，只看到「一直不收斂」。
        d = state.Discussion("q", make_seats())
        one_round(d, {"a1": failed(), "a2": done()})
        by_seat = d.status()["usage"]["by_seat"]
        self.assertEqual(by_seat["a1"]["calls"], 1)
        self.assertEqual(by_seat["a1"]["failed"], 1)
        self.assertEqual(by_seat["a2"]["calls"], 1)
        self.assertEqual(by_seat["a2"]["failed"], 0)

    def test_failed_count_accumulates_across_rounds(self):
        d = state.Discussion("q", make_seats())
        one_round(d, {"a1": failed(), "a2": done()})
        d.request_next_round()
        one_round(d, {"a1": failed(), "a2": done()})
        by_seat = d.status()["usage"]["by_seat"]
        self.assertEqual(by_seat["a1"]["failed"], 2)
        self.assertEqual(by_seat["a1"]["calls"], 2)
        self.assertEqual(by_seat["a2"]["failed"], 0)

    def test_arbitration_failure_also_counted(self):
        d = state.Discussion("q", make_seats())
        one_round(d, {"a1": done(), "a2": done()})
        d.record_arbitration(failed())
        by_seat = d.status()["usage"]["by_seat"]
        self.assertEqual(by_seat["arb"]["failed"], 1)


class SeatCountErrorMessageTest(unittest.TestCase):
    def test_message_speaks_in_advisor_units(self):
        # 現在會紅：訊息是「seats 長度須為 2～4」，它數的是總席次，
        # 但使用者數的是顧問 ⇒ 填 4 個顧問的人看到「須為 2～4」會以為自己合規。
        seats = [{"seat_id": f"a{i}", "cli": "opencode", "model": None,
                  "role": "advisor"} for i in range(1, 5)]
        seats.append({"seat_id": "arb", "cli": "claude", "model": None,
                      "role": "arbiter"})
        with self.assertRaises(ValueError) as cm:
            state.Discussion("q", seats)
        msg = str(cm.exception)
        self.assertIn("顧問", msg)
        self.assertIn("仲裁者", msg)
        self.assertIn("5", msg)          # 要說出實際收到幾席


class FailSafeFieldsMustSurviveTest(unittest.TestCase):
    def test_failed_record_keeps_fail_safe_fields(self):
        # 護欄（我補的）：第 1 節明文「不改記錄欄位」——失敗席次的 more 維持 True、
        # stance 維持 None、violation 維持 False。那個 more=True 是刻意的 fail-safe
        # （解析失敗時寧可不收斂、也不要提早結束討論），正是「收斂只看成功席次」
        # 這個修法得以成立的前提，不許有人為了省事把它改成 False。
        d = state.Discussion("q", make_seats())
        one_round(d, {"a1": failed(), "a2": done()})
        rec = d.rounds[-1][0]
        self.assertIsNone(rec["stance"])
        self.assertTrue(rec["more"])
        self.assertFalse(rec["violation"])

    def test_failed_count_does_not_leak_into_usage_or_violations(self):
        # 護欄（我補的）：失敗在對外狀態上看得到，但只透過 failed 欄位——不得汙染
        # format_violations（呼叫失敗不是格式違規，SPEC.md §5 邊界 5）也不得製造
        # 假的 usage。
        d = state.Discussion("q", make_seats())
        one_round(d, {"a1": failed(), "a2": done()})
        st = d.status()
        self.assertEqual(st["format_violations"], 0)
        self.assertEqual(st["usage"]["by_seat"]["a1"]["usage"], {})


if __name__ == "__main__":
    unittest.main()
