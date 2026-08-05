import copy
import sys
import unittest
from pathlib import Path

SRC_DIR = Path(__file__).resolve().parent.parent / "src"
sys.path.insert(0, str(SRC_DIR))

from engine import orchestrator  # noqa: E402
from engine import state  # noqa: E402

EXPECTED_INSTRUCTION = """【你的任務】
你是本次討論的顧問「{seat_id}」。請針對上面的原始問題提出你的看法。
若上面已經有其他顧問的發言，請一併回應他們的論點——同意哪裡、補充什麼、反對什麼。

回覆的最後一行必須是下面這個格式，前後不要有任何其他文字：
[立場: 同意] [補充: 無]

其中「立場」三選一：同意 / 保留 / 反對；「補充」二選一：有 / 無。
「補充: 無」代表你認為自己已經沒有新的論點可以加。"""


def make_seats(advisor_specs=None) -> list:
    if advisor_specs is None:
        advisor_specs = [
            ("a1", "claude", None),
            ("a2", "codex", None),
            ("a3", "opencode", None),
        ]
    seats = [{"seat_id": sid, "cli": cli, "model": model, "role": "advisor"}
             for (sid, cli, model) in advisor_specs]
    seats.append({"seat_id": "arb", "cli": "gemini", "model": "m",
                  "role": "arbiter"})
    return seats


def ok_result(text="答覆\n[立場: 同意] [補充: 無]", usage=None,
              truncated=False) -> dict:
    return {"ok": True, "text": text, "truncated": truncated, "error": None,
            "elapsed_s": 1.0, "model_used": "model-x", "usage": usage}


def fail_result(error="timeout", text="") -> dict:
    return {"ok": False, "text": text, "truncated": False, "error": error,
            "elapsed_s": 180.0, "model_used": None, "usage": None}


class FakeAsk:
    """純 Python 假 ask_fn：記錄收到的關鍵字參數，依 behaviors 決定每次回傳。

    behaviors 的第 i 個元素（i 由 0 起算）決定第 i 次呼叫的行為：
      - None          ：回傳標準成功結果 ok_result()
      - Exception 實例：拋出該例外
      - dict          ：原樣回傳
      - callable      ：以該次收到的參數 dict 呼叫，取其回傳值
    行為清單用完之後一律回傳 ok_result()。
    """

    def __init__(self, behaviors=None):
        self.behaviors = behaviors if behaviors is not None else []
        self.calls = []

    def __call__(self, cli, prompt, model, timeout_s, max_chars):
        call = {
            "cli": cli,
            "prompt": prompt,
            "model": model,
            "timeout_s": timeout_s,
            "max_chars": max_chars,
        }
        self.calls.append(call)
        idx = len(self.calls) - 1
        if idx < len(self.behaviors):
            behavior = self.behaviors[idx]
        else:
            behavior = None
        if isinstance(behavior, Exception):
            raise behavior
        if behavior is None:
            return ok_result()
        if isinstance(behavior, dict):
            return behavior
        return behavior(call)


class AdvisorInstructionTest(unittest.TestCase):
    def test_verbatim(self):
        self.assertEqual(orchestrator.ADVISOR_INSTRUCTION, EXPECTED_INSTRUCTION)

    def test_substitutes_seat_id_only(self):
        rendered = orchestrator.ADVISOR_INSTRUCTION.format(seat_id="a1")
        self.assertIn("顧問「a1」", rendered)
        self.assertNotIn("{seat_id}", rendered)


class BuildPromptTest(unittest.TestCase):
    def test_first_round_first_speaker_no_round_block(self):
        d = state.Discussion("我們該不該用 Rust 重寫？", make_seats())
        d.begin_round()
        prompt = orchestrator.build_prompt(d, "a1")
        self.assertIn("【原始問題】", prompt)
        self.assertIn("我們該不該用 Rust 重寫？", prompt)
        self.assertIn("【你的任務】", prompt)
        self.assertNotIn("【第 1 輪】", prompt)

    def test_first_round_second_speaker_includes_first_verbatim(self):
        d = state.Discussion("問題", make_seats())
        d.begin_round()
        first_text = "第一位的看法\n[立場: 同意] [補充: 無]"
        d.record_speech("a1", ok_result(text=first_text))
        prompt = orchestrator.build_prompt(d, "a2")
        self.assertIn("【第 1 輪】", prompt)
        self.assertIn("── a1 ──", prompt)
        self.assertIn(first_text, prompt)

    def test_second_round_orders_blocks(self):
        d = state.Discussion("問題", make_seats(advisor_specs=[
            ("a1", "claude", None), ("a2", "codex", None)]))
        d.begin_round()
        d.record_speech("a1", ok_result(text="第一輪 a1\n[立場: 同意] [補充: 有]"))
        d.record_speech("a2", ok_result(text="第一輪 a2\n[立場: 保留] [補充: 無]"))
        d.end_round()
        d.request_next_round()
        d.begin_round()
        d.record_speech("a1", ok_result(text="第二輪 a1\n[立場: 同意] [補充: 無]"))
        prompt = orchestrator.build_prompt(d, "a2")
        i1 = prompt.index("【第 1 輪】")
        i2 = prompt.index("【第 2 輪】")
        it = prompt.index("【你的任務】")
        self.assertLess(i1, i2)
        self.assertLess(i2, it)
        self.assertIn("第一輪 a1", prompt)
        self.assertIn("第一輪 a2", prompt)
        self.assertIn("第二輪 a1", prompt)

    def test_failed_speech_shows_unanswered_with_error(self):
        d = state.Discussion("問題", make_seats())
        d.begin_round()
        d.record_speech("a1", fail_result(error="timeout", text="不該出現的內容"))
        prompt = orchestrator.build_prompt(d, "a2")
        self.assertIn("（未回應：timeout）", prompt)
        self.assertNotIn("不該出現的內容", prompt)

    def test_error_none_shows_plain_unanswered(self):
        d = state.Discussion("問題", make_seats())
        d.begin_round()
        d.record_speech("a1", fail_result(error=None))
        prompt = orchestrator.build_prompt(d, "a2")
        self.assertIn("（未回應）", prompt)
        self.assertNotIn("（未回應：", prompt)

    def test_truncated_marks_and_keeps_text(self):
        d = state.Discussion("問題", make_seats())
        d.begin_round()
        d.record_speech("a1", ok_result(
            text="長篇原文\n[立場: 同意] [補充: 有]", truncated=True))
        prompt = orchestrator.build_prompt(d, "a2")
        self.assertIn("（本則發言超過長度上限，已被截斷）", prompt)
        self.assertIn("長篇原文", prompt)

    def test_task_block_substitutes_seat_id(self):
        d = state.Discussion("問題", make_seats())
        d.begin_round()
        prompt = orchestrator.build_prompt(d, "a3")
        self.assertIn("顧問「a3」", prompt)
        self.assertNotIn("{seat_id}", prompt)

    def test_arbiter_never_in_transcript(self):
        d = state.Discussion("問題", make_seats())
        d.begin_round()
        d.record_speech("a1", ok_result())
        d.record_speech("a2", ok_result())
        d.record_speech("a3", ok_result())
        d.end_round()
        prompt = orchestrator.build_prompt(d, "a1")
        self.assertNotIn("── arb ──", prompt)
        self.assertNotIn("gemini", prompt)

    def test_no_side_effects(self):
        d = state.Discussion("問題", make_seats())
        d.begin_round()
        d.record_speech("a1", ok_result())
        d.record_speech("a2", ok_result())
        before = d.status()
        orchestrator.build_prompt(d, "a3")
        self.assertEqual(d.status(), before)

    def test_context_block_prepends_and_precedes_question(self):
        d = state.Discussion("問題", make_seats(), context="脈絡內容")
        d.begin_round()
        prompt = orchestrator.build_prompt(d, "a1")
        self.assertTrue(prompt.startswith("【專案脈絡】"))
        self.assertLess(prompt.index("【專案脈絡】"), prompt.index("【原始問題】"))

    def test_context_round_task_order(self):
        d = state.Discussion("問題", make_seats(), context="脈絡內容")
        d.begin_round()
        d.record_speech("a1", ok_result(text="第一則\n[立場: 同意] [補充: 無]"))
        prompt = orchestrator.build_prompt(d, "a2")
        i_c = prompt.index("【專案脈絡】")
        i_q = prompt.index("【原始問題】")
        i_r = prompt.index("【第 1 輪】")
        i_t = prompt.index("【你的任務】")
        self.assertLess(i_c, i_q)
        self.assertLess(i_q, i_r)
        self.assertLess(i_r, i_t)

    def test_blank_context_no_block(self):
        for ctx in ("", "   \n  "):
            d = state.Discussion("問題", make_seats(), context=ctx)
            d.begin_round()
            prompt = orchestrator.build_prompt(d, "a1")
            self.assertNotIn("【專案脈絡】", prompt)

    def test_context_verbatim_in_output(self):
        ctx = "第一行\n\n  帶縮排與空行\n尾行"
        d = state.Discussion("問題", make_seats(), context=ctx)
        d.begin_round()
        prompt = orchestrator.build_prompt(d, "a1")
        self.assertIn(f"【專案脈絡】\n{ctx}", prompt)
        self.assertIn(ctx, prompt)

    def test_run_round_sends_context_to_every_advisor(self):
        d = state.Discussion("問題", make_seats(), context="每個人都該看到的脈絡")
        fake = FakeAsk()
        orchestrator.run_round(d, fake)
        self.assertEqual(len(fake.calls), 3)
        for call in fake.calls:
            self.assertTrue(call["prompt"].startswith("【專案脈絡】"))
            self.assertIn("每個人都該看到的脈絡", call["prompt"])


class RunRoundNormalTest(unittest.TestCase):
    def test_three_advisor_calls_in_order(self):
        d = state.Discussion("問題", make_seats())
        fake = FakeAsk()
        orchestrator.run_round(d, fake)
        self.assertEqual(len(fake.calls), 3)
        self.assertEqual([c["cli"] for c in fake.calls],
                         ["claude", "codex", "opencode"])
        self.assertNotIn("gemini", [c["cli"] for c in fake.calls])

    def test_model_passed_per_seat(self):
        seats = make_seats(advisor_specs=[
            ("a1", "claude", None),
            ("a2", "codex", "gpt-5"),
            ("a3", "opencode", None),
        ])
        d = state.Discussion("問題", seats)
        fake = FakeAsk()
        orchestrator.run_round(d, fake)
        self.assertEqual([c["model"] for c in fake.calls],
                         [None, "gpt-5", None])

    def test_timeout_and_max_chars_defaults(self):
        d = state.Discussion("問題", make_seats())
        fake = FakeAsk()
        orchestrator.run_round(d, fake)
        for c in fake.calls:
            self.assertEqual(c["timeout_s"], orchestrator.DEFAULT_TIMEOUT_S)
            self.assertEqual(c["max_chars"], orchestrator.DEFAULT_MAX_CHARS)

    def test_timeout_and_max_chars_overrides(self):
        d = state.Discussion("問題", make_seats())
        fake = FakeAsk()
        orchestrator.run_round(d, fake, timeout_s=42, max_chars=1234)
        for c in fake.calls:
            self.assertEqual(c["timeout_s"], 42)
            self.assertEqual(c["max_chars"], 1234)

    def test_prompt_rebuilt_per_speaker(self):
        d = state.Discussion("問題", make_seats())
        fake = FakeAsk([
            lambda c: ok_result(text="a1 回覆\n[立場: 同意] [補充: 無]"),
            lambda c: ok_result(text="a2 回覆\n[立場: 同意] [補充: 無]"),
            lambda c: ok_result(text="a3 回覆\n[立場: 同意] [補充: 無]"),
        ])
        orchestrator.run_round(d, fake)
        self.assertIn("a1 回覆\n[立場: 同意] [補充: 無]",
                      fake.calls[1]["prompt"])
        self.assertIn("a2 回覆\n[立場: 同意] [補充: 無]",
                      fake.calls[2]["prompt"])
        self.assertFalse(
            state.parse_marker("a2 回覆\n[立場: 同意] [補充: 無]")["violation"])

    def test_phase_and_can_start_after_round(self):
        d = state.Discussion("問題", make_seats())
        orchestrator.run_round(d, FakeAsk())
        self.assertEqual(d.phase, state.PHASE_AWAITING_USER)
        self.assertFalse(d.status()["can_start_round"])

    def test_returned_status_fields(self):
        d = state.Discussion("問題", make_seats())
        status = orchestrator.run_round(d, FakeAsk())
        self.assertEqual(status, d.status())
        self.assertEqual(status["phase"], state.PHASE_AWAITING_USER)
        self.assertEqual(status["rounds_completed"], 1)
        self.assertEqual(status["max_rounds"], state.DEFAULT_MAX_ROUNDS)
        self.assertFalse(status["at_cap"])
        self.assertFalse(status["can_start_round"])
        self.assertTrue(status["converged"])
        self.assertEqual(status["format_violations"], 0)
        self.assertEqual(status["usage"]["calls"], 3)
        self.assertEqual(status["usage"]["total"], {})
        self.assertEqual(set(status["usage"]["by_seat"]), {"a1", "a2", "a3"})


class RunRoundFailureTest(unittest.TestCase):
    def test_middle_raises_continues(self):
        d = state.Discussion("問題", make_seats())
        fake = FakeAsk([None, RuntimeError("boom"), None])
        status = orchestrator.run_round(d, fake)
        self.assertEqual(len(fake.calls), 3)
        rec = d.rounds[-1][1]
        self.assertFalse(rec["ok"])
        self.assertIn("RuntimeError", rec["error"])
        self.assertIn("boom", rec["error"])
        self.assertEqual(rec["text"], "")
        self.assertFalse(rec["truncated"])
        self.assertEqual(rec["elapsed_s"], 0.0)
        self.assertIsNone(rec["model_used"])
        self.assertIsNone(rec["usage"])
        self.assertEqual(status["phase"], state.PHASE_AWAITING_USER)

    def test_missing_key_recorded_as_failure(self):
        d = state.Discussion("問題", make_seats())
        bad = {"ok": True, "text": "x", "truncated": False, "error": None,
               "elapsed_s": 1.0, "model_used": None}
        fake = FakeAsk([None, bad, None])
        status = orchestrator.run_round(d, fake)
        self.assertEqual(len(fake.calls), 3)
        rec = d.rounds[-1][1]
        self.assertFalse(rec["ok"])
        self.assertIn("KeyError", rec["error"])
        self.assertEqual(status["phase"], state.PHASE_AWAITING_USER)

    def test_all_fail_round_still_ends(self):
        d = state.Discussion("問題", make_seats())
        fake = FakeAsk([RuntimeError("x"), RuntimeError("y"), RuntimeError("z")])
        status = orchestrator.run_round(d, fake)
        self.assertEqual(status["usage"]["calls"], 3)
        self.assertEqual(status["phase"], state.PHASE_AWAITING_USER)
        self.assertTrue(all(not r["ok"] for r in d.rounds[-1]))


class RunRoundBoundaryTest(unittest.TestCase):
    def test_boundary1_blocks_immediate_rerun(self):
        d = state.Discussion("問題", make_seats())
        orchestrator.run_round(d, FakeAsk())
        with self.assertRaises(state.BoundaryError):
            orchestrator.run_round(d, FakeAsk())
        d.request_next_round()
        orchestrator.run_round(d, FakeAsk())
        self.assertEqual(d.status()["rounds_completed"], 2)

    def test_boundary3_not_bypassed(self):
        d = state.Discussion("問題", make_seats(), max_rounds=1)
        orchestrator.run_round(d, FakeAsk())
        with self.assertRaises(state.BoundaryError):
            d.request_next_round()
        with self.assertRaises(state.BoundaryError):
            orchestrator.run_round(d, FakeAsk())

    def test_run_round_never_advances_phase(self):
        d = state.Discussion("問題", make_seats())
        orchestrator.run_round(d, FakeAsk())
        self.assertEqual(d.status()["phase"], state.PHASE_AWAITING_USER)

    def test_ask_fn_required_no_default(self):
        d = state.Discussion("問題", make_seats())
        with self.assertRaises(TypeError):
            orchestrator.run_round(d)


class BuildArbiterPromptTest(unittest.TestCase):
    def _two_rounds(self):
        d = state.Discussion("問題", make_seats(advisor_specs=[
            ("a1", "claude", None), ("a2", "codex", None)]))
        d.begin_round()
        d.record_speech("a1", ok_result(text="第一輪 a1\n[立場: 同意] [補充: 無]"))
        d.record_speech("a2", ok_result(text="第一輪 a2\n[立場: 同意] [補充: 無]"))
        d.end_round()
        d.request_next_round()
        d.begin_round()
        d.record_speech("a1", ok_result(text="第二輪 a1\n[立場: 同意] [補充: 無]"))
        d.record_speech("a2", ok_result(text="第二輪 a2\n[立場: 同意] [補充: 無]"))
        d.end_round()
        return d

    def test_includes_question_all_rounds_and_task(self):
        d = self._two_rounds()
        prompt = orchestrator.build_arbiter_prompt(d)
        self.assertIn("問題", prompt)
        self.assertIn("【原始問題】", prompt)
        self.assertIn("【第 1 輪】", prompt)
        self.assertIn("【第 2 輪】", prompt)
        self.assertIn("第一輪 a1", prompt)
        self.assertIn("第二輪 a2", prompt)
        self.assertIn("【你的任務】", prompt)
        self.assertIn("仲裁者「arb」", prompt)

    def test_shared_prefix_before_task_block(self):
        d = self._two_rounds()
        advisor_prompt = orchestrator.build_prompt(d, "a1")
        arbiter_prompt = orchestrator.build_arbiter_prompt(d)
        cut_a = advisor_prompt.index("【你的任務】")
        cut_b = arbiter_prompt.index("【你的任務】")
        self.assertEqual(advisor_prompt[:cut_a], arbiter_prompt[:cut_b])

    def test_context_prepended(self):
        d = state.Discussion("問題", make_seats(), context="脈絡")
        prompt = orchestrator.build_arbiter_prompt(d)
        self.assertTrue(prompt.startswith("【專案脈絡】"))

    def test_no_stance_marker_required(self):
        self.assertNotIn("[立場", orchestrator.ARBITER_INSTRUCTION)


class RunArbitrationTest(unittest.TestCase):
    def _finished_discussion(self):
        d = state.Discussion("問題", make_seats(advisor_specs=[
            ("a1", "claude", None), ("a2", "codex", None)]))
        d.begin_round()
        d.record_speech("a1", ok_result())
        d.record_speech("a2", ok_result())
        d.end_round()
        return d

    def test_refuses_before_any_call(self):
        d = state.Discussion("問題", make_seats())
        calls = []

        def tripwire(cli, prompt, model, timeout_s, max_chars):
            calls.append(1)
            raise AssertionError("ask_fn 不該被呼叫")

        with self.assertRaises(state.BoundaryError):
            orchestrator.run_arbitration(d, tripwire)
        self.assertEqual(calls, [])

    def test_uses_arbiter_seat_and_passes_limits(self):
        d = self._finished_discussion()
        fake = FakeAsk()
        orchestrator.run_arbitration(d, fake, timeout_s=42, max_chars=1234)
        self.assertEqual(len(fake.calls), 1)
        call = fake.calls[0]
        self.assertEqual(call["cli"], "gemini")
        self.assertEqual(call["model"], "m")
        self.assertEqual(call["timeout_s"], 42)
        self.assertEqual(call["max_chars"], 1234)
        self.assertIn("仲裁者「arb」", call["prompt"])

    def test_returns_the_record(self):
        d = self._finished_discussion()
        record = orchestrator.run_arbitration(d, FakeAsk())
        self.assertIs(record, d.arbitrations[-1])

    def test_ask_fn_exception_recorded(self):
        d = self._finished_discussion()
        record = orchestrator.run_arbitration(d, FakeAsk([RuntimeError("boom")]))
        self.assertFalse(record["ok"])
        self.assertIn("RuntimeError", record["error"])
        self.assertIn("boom", record["error"])
        self.assertEqual(d.status()["usage"]["calls"], 3)

    def test_no_state_mutation(self):
        d = self._finished_discussion()
        before = d.status()
        rounds_before = copy.deepcopy(d.rounds)
        orchestrator.run_arbitration(d, FakeAsk())
        after = d.status()
        self.assertEqual(after["phase"], before["phase"])
        self.assertEqual(after["rounds_completed"], before["rounds_completed"])
        self.assertEqual(d.rounds, rounds_before)


if __name__ == "__main__":
    unittest.main()
