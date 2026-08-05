import copy
import sys
import unittest
from pathlib import Path

SRC_DIR = Path(__file__).resolve().parent.parent / "src"
sys.path.insert(0, str(SRC_DIR))

from engine import state  # noqa: E402


def make_seats(advisor_ids=("a1", "a2"), arbiter_id="arb") -> list:
    seats = [{"seat_id": sid, "cli": "claude", "model": None, "role": "advisor"}
             for sid in advisor_ids]
    seats.append({"seat_id": arbiter_id, "cli": "codex", "model": "m",
                  "role": "arbiter"})
    return seats


def ok_result(text="答覆\n[立場: 同意] [補充: 無]", usage=None) -> dict:
    return {"ok": True, "text": text, "truncated": False, "error": None,
            "elapsed_s": 1.0, "model_used": "model-x", "usage": usage}


def fail_result(usage=None) -> dict:
    return {"ok": False, "text": "", "truncated": False, "error": "timeout",
            "elapsed_s": 180.0, "model_used": None, "usage": usage}


class ParseMarkerTest(unittest.TestCase):
    def test_basic_hit(self):
        r = state.parse_marker("內容\n[立場: 同意] [補充: 無]")
        self.assertEqual(r, {"stance": "同意", "more": False, "violation": False})

    def test_fullwidth_colon(self):
        r = state.parse_marker("內容\n[立場：保留] [補充：有]")
        self.assertEqual(r, {"stance": "保留", "more": True, "violation": False})

    def test_marker_in_middle_only(self):
        r = state.parse_marker(
            "[立場: 同意] [補充: 無]\n後面還有別的文字"
        )
        self.assertEqual(r, {"stance": None, "more": True, "violation": True})

    def test_no_marker(self):
        r = state.parse_marker("就是一段普通文字")
        self.assertEqual(r, {"stance": None, "more": True, "violation": True})

    def test_trailing_blank_lines(self):
        r = state.parse_marker("內容\n[立場: 同意] [補充: 無]\n\n\n")
        self.assertEqual(r, {"stance": "同意", "more": False, "violation": False})

    def test_truncated_marker(self):
        r = state.parse_marker("內容\n[立場: 同意] [補充: ")
        self.assertEqual(r, {"stance": None, "more": True, "violation": True})


class MergeUsageTest(unittest.TestCase):
    def test_claude_shape_doubles(self):
        total = {"input_tokens": 10, "output_tokens": 5, "total_cost_usd": 1.0}
        for _ in range(2):
            total = state.merge_usage(total, {
                "input_tokens": 10, "output_tokens": 5, "total_cost_usd": 1.0})
        self.assertEqual(total, {
            "input_tokens": 30, "output_tokens": 15, "total_cost_usd": 3.0})

    def test_opencode_shape_nested(self):
        total = {"tokens": {"input": 3, "output": 4}, "cost": 0}
        total = state.merge_usage(total, {"tokens": {"input": 2, "output": 1},
                                          "cost": 0})
        self.assertEqual(total, {"tokens": {"input": 5, "output": 5}, "cost": 0})

    def test_conflict_and_non_numeric_ignored(self):
        total = {"input_tokens": 10, "str_field": "keep me", "flag": True}
        merged = state.merge_usage(total, {
            "input_tokens": 5,
            "str_field": "replace?",
            "flag": 3,
            "new_str": "ignored",
        })
        self.assertEqual(merged["input_tokens"], 15)
        self.assertEqual(merged["str_field"], "keep me")
        self.assertEqual(merged["flag"], True)
        self.assertEqual(merged["new_str"], "ignored")

    def test_no_mutation(self):
        total = {"tokens": {"input": 1}, "cost": 0.5}
        usage = {"tokens": {"input": 2, "output": 3}, "cost": 0.5}
        merged = state.merge_usage(total, usage)
        self.assertEqual(total, {"tokens": {"input": 1}, "cost": 0.5})
        self.assertEqual(usage, {"tokens": {"input": 2, "output": 3},
                                 "cost": 0.5})
        merged["tokens"]["input"] = 999
        merged["cost"] = 999
        self.assertEqual(total["tokens"]["input"], 1)
        self.assertEqual(total["cost"], 0.5)


class DiscussionInitTest(unittest.TestCase):
    def _base(self):
        return {"question": "q", "seats": make_seats(), "max_rounds": 3}

    def test_blank_question(self):
        for q in ("", "   "):
            with self.assertRaises(ValueError):
                state.Discussion(q, make_seats())

    def test_seats_count(self):
        for n in (0, 4, 5):
            seats = make_seats(advisor_ids=tuple(f"a{i}" for i in range(n)))
            with self.assertRaises(ValueError):
                state.Discussion("q", seats)

    def test_missing_or_extra_key(self):
        seats = make_seats()
        seats[0].pop("model")
        with self.assertRaises(ValueError):
            state.Discussion("q", seats)
        seats = make_seats()
        seats[0]["extra"] = 1
        with self.assertRaises(ValueError):
            state.Discussion("q", seats)

    def test_bad_field_types(self):
        arb = {"seat_id": "arb", "cli": "codex", "model": "m", "role": "arbiter"}
        cases = [
            {"seat_id": "", "cli": "claude", "model": None, "role": "advisor"},
            {"seat_id": "a", "cli": "", "model": None, "role": "advisor"},
            {"seat_id": "a", "cli": "claude", "model": 123, "role": "advisor"},
            {"seat_id": "a", "cli": "claude", "model": None, "role": "chaos"},
        ]
        for seat in cases:
            with self.assertRaises(ValueError):
                state.Discussion("q", [seat, arb])

    def test_duplicate_seat_id(self):
        seats = make_seats()
        seats[1]["seat_id"] = "a1"
        with self.assertRaises(ValueError):
            state.Discussion("q", seats)

    def test_arbiter_count(self):
        seats = make_seats()
        seats[0]["role"] = "arbiter"
        with self.assertRaises(ValueError):
            state.Discussion("q", seats)
        seats = make_seats()
        seats[1]["role"] = "arbiter"
        with self.assertRaises(ValueError):
            state.Discussion("q", seats)

    def test_no_advisor(self):
        seats = [{"seat_id": "arb", "cli": "c", "model": None,
                  "role": "arbiter"}]
        with self.assertRaises(ValueError):
            state.Discussion("q", seats)

    def test_bad_max_rounds(self):
        d = self._base()
        for mr in (0, True):
            with self.assertRaises(ValueError):
                state.Discussion(**{**d, "max_rounds": mr})

    def test_defaults_and_order(self):
        d = state.Discussion("q", make_seats(advisor_ids=("b1", "a1")))
        self.assertEqual([s["seat_id"] for s in d.advisors], ["b1", "a1"])
        self.assertEqual(d.max_rounds, state.DEFAULT_MAX_ROUNDS)
        self.assertEqual(d.phase, state.PHASE_READY)
        self.assertEqual(d.rounds, [])
        self.assertEqual([s["seat_id"] for s in d.seats], ["b1", "a1", "arb"])


class DiscussionContextTest(unittest.TestCase):
    def test_default_empty(self):
        d = state.Discussion("q", make_seats())
        self.assertEqual(d.context, "")

    def test_preserved_verbatim(self):
        ctx = "  帶前後空白與\n\t縮排  \n尾行  "
        d = state.Discussion("q", make_seats(), context=ctx)
        self.assertEqual(d.context, ctx)

    def test_non_str_raises(self):
        for bad in (None, 123, ["x"], {"a": 1}):
            with self.assertRaises(ValueError):
                state.Discussion("q", make_seats(), context=bad)

    def test_max_rounds_still_third_positional(self):
        d = state.Discussion("q", make_seats(), 2)
        self.assertEqual(d.max_rounds, 2)
        self.assertEqual(d.context, "")

    def test_context_not_in_status(self):
        d = state.Discussion("q", make_seats(), context="秘密脈絡")
        st = d.status()
        self.assertNotIn("context", st)

        def contains(obj):
            if isinstance(obj, dict):
                return any(contains(v) for v in obj.values())
            return obj == "秘密脈絡"

        self.assertFalse(contains(st))


class Boundary1Test(unittest.TestCase):
    def test_awaiting_user_blocks_begin(self):
        d = state.Discussion("q", make_seats())
        d.begin_round()
        d.record_speech("a1", ok_result())
        d.record_speech("a2", ok_result())
        d.end_round()
        self.assertEqual(d.phase, state.PHASE_AWAITING_USER)
        with self.assertRaises(state.BoundaryError):
            d.begin_round()
        d.request_next_round()
        self.assertEqual(d.phase, state.PHASE_READY)
        self.assertEqual(d.begin_round(), 1)


class Boundary3Test(unittest.TestCase):
    def test_cap_blocks_and_confirm_overrides(self):
        d = state.Discussion("q", make_seats(), max_rounds=2)
        for i in range(2):
            d.begin_round()
            d.record_speech("a1", ok_result())
            d.record_speech("a2", ok_result())
            d.end_round()
            if i == 0:
                d.request_next_round()
        with self.assertRaises(state.BoundaryError):
            d.request_next_round()
        d.request_next_round(confirm_over_cap=True)
        self.assertEqual(d.begin_round(), 2)

    def test_at_cap_flag(self):
        d = state.Discussion("q", make_seats(), max_rounds=1)
        self.assertFalse(d.status()["at_cap"])
        d.begin_round()
        d.record_speech("a1", ok_result())
        d.record_speech("a2", ok_result())
        d.end_round()
        self.assertTrue(d.status()["at_cap"])


class Boundary5Test(unittest.TestCase):
    def _run_round(self, d, more_a1, more_a2):
        d.begin_round()
        d.record_speech("a1", ok_result(text=f"[立場: 同意] [補充: {more_a1}]"))
        d.record_speech("a2", ok_result(text=f"[立場: 反對] [補充: {more_a2}]"))
        d.end_round()

    def test_converged_when_all_done(self):
        d = state.Discussion("q", make_seats())
        self._run_round(d, "無", "無")
        self.assertTrue(d.converged())

    def test_not_converged_when_one_more(self):
        d = state.Discussion("q", make_seats())
        self._run_round(d, "有", "無")
        self.assertFalse(d.converged())

    def test_timeout_not_converged_no_violation(self):
        d = state.Discussion("q", make_seats())
        d.begin_round()
        d.record_speech("a1", fail_result())
        d.record_speech("a2", ok_result())
        d.end_round()
        self.assertFalse(d.converged())
        rec = d.rounds[-1][0]
        self.assertFalse(rec["violation"])
        self.assertTrue(rec["more"])
        self.assertIsNone(rec["stance"])

    def test_not_converged_while_in_round(self):
        d = state.Discussion("q", make_seats())
        d.begin_round()
        d.record_speech("a1", ok_result(text="[立場: 同意] [補充: 無]"))
        d.record_speech("a2", ok_result(text="[立場: 同意] [補充: 無]"))
        self.assertFalse(d.converged())


class Boundary6Test(unittest.TestCase):
    def test_by_seat_and_total(self):
        d = state.Discussion("q", make_seats())
        d.begin_round()
        d.record_speech("a1", ok_result(usage={
            "input_tokens": 10, "output_tokens": 5, "total_cost_usd": 1.0}))
        d.record_speech("a2", ok_result(usage={
            "tokens": {"input": 3, "output": 4}, "cost": 0}))
        d.end_round()
        st = d.status()
        self.assertEqual(st["usage"]["calls"], 2)
        self.assertEqual(
            st["usage"]["by_seat"]["a1"]["usage"]["input_tokens"], 10)
        self.assertEqual(st["usage"]["by_seat"]["a2"]["usage"]["tokens"]["input"], 3)
        self.assertEqual(st["usage"]["total"]["input_tokens"], 10)
        self.assertEqual(st["usage"]["total"]["tokens"]["input"], 3)

    def test_failed_call_counts(self):
        d = state.Discussion("q", make_seats())
        d.begin_round()
        d.record_speech("a1", fail_result(usage=None))
        d.record_speech("a2", ok_result())
        d.end_round()
        st = d.status()
        self.assertEqual(st["usage"]["calls"], 2)
        self.assertEqual(st["usage"]["total"], {})

    def test_status_usage_is_copy(self):
        d = state.Discussion("q", make_seats())
        d.begin_round()
        d.record_speech("a1", ok_result(usage={"input_tokens": 10}))
        d.record_speech("a2", ok_result())
        d.end_round()
        first = d.status()
        first["usage"]["total"]["input_tokens"] = 999
        first["usage"]["by_seat"]["a1"]["usage"]["input_tokens"] = 999
        second = d.status()
        self.assertEqual(second["usage"]["total"]["input_tokens"], 10)
        self.assertEqual(second["usage"]["by_seat"]["a1"]["usage"]["input_tokens"], 10)


class StateMachineRulesTest(unittest.TestCase):
    def test_record_invalid_seat(self):
        d = state.Discussion("q", make_seats())
        d.begin_round()
        with self.assertRaises(ValueError):
            d.record_speech("arb", ok_result())
        with self.assertRaises(ValueError):
            d.record_speech("nope", ok_result())

    def test_record_out_of_round(self):
        d = state.Discussion("q", make_seats())
        with self.assertRaises(state.BoundaryError):
            d.record_speech("a1", ok_result())

    def test_duplicate_speech(self):
        d = state.Discussion("q", make_seats())
        d.begin_round()
        d.record_speech("a1", ok_result())
        with self.assertRaises(ValueError):
            d.record_speech("a1", ok_result())

    def test_end_round_with_missing_advisor(self):
        d = state.Discussion("q", make_seats())
        d.begin_round()
        d.record_speech("a1", ok_result())
        with self.assertRaises(ValueError):
            d.end_round()

    def test_end_round_out_of_round(self):
        d = state.Discussion("q", make_seats())
        with self.assertRaises(state.BoundaryError):
            d.end_round()

    def test_request_next_round_out_of_awaiting(self):
        d = state.Discussion("q", make_seats())
        with self.assertRaises(state.BoundaryError):
            d.request_next_round()

    def test_rounds_completed(self):
        d = state.Discussion("q", make_seats())
        d.begin_round()
        d.record_speech("a1", ok_result())
        d.record_speech("a2", ok_result())
        self.assertEqual(d.status()["rounds_completed"], 0)
        d.end_round()
        self.assertEqual(d.status()["rounds_completed"], 1)


class StatusFieldsTest(unittest.TestCase):
    def _run_round(self, d, a1_text, a2_text):
        d.begin_round()
        d.record_speech("a1", ok_result(text=a1_text))
        d.record_speech("a2", ok_result(text=a2_text))
        d.end_round()

    def test_format_violations_accumulate_across_rounds(self):
        d = state.Discussion("q", make_seats())
        self._run_round(d, "沒有結尾標記", "[立場: 同意] [補充: 無]")
        self.assertEqual(d.status()["format_violations"], 1)
        d.request_next_round()
        self._run_round(d, "又是沒有結尾標記", "[立場: 同意] [補充: 無]")
        self.assertEqual(d.status()["format_violations"], 2)

    def test_format_violations_ignores_timeout(self):
        d = state.Discussion("q", make_seats())
        d.begin_round()
        d.record_speech("a1", fail_result())
        d.record_speech("a2", ok_result(text="[立場: 同意] [補充: 無]"))
        d.end_round()
        self.assertEqual(d.status()["format_violations"], 0)

    def test_can_start_round_follows_phase(self):
        d = state.Discussion("q", make_seats())
        self.assertTrue(d.status()["can_start_round"])
        d.begin_round()
        self.assertFalse(d.status()["can_start_round"])
        d.record_speech("a1", ok_result())
        d.record_speech("a2", ok_result())
        d.end_round()
        self.assertFalse(d.status()["can_start_round"])
        d.request_next_round()
        self.assertTrue(d.status()["can_start_round"])

    def test_status_converged_matches_converged_all_done(self):
        d = state.Discussion("q", make_seats())
        self._run_round(d, "[立場: 同意] [補充: 無]", "[立場: 同意] [補充: 無]")
        self.assertTrue(d.converged())
        self.assertTrue(d.status()["converged"])

    def test_status_converged_matches_converged_some_more(self):
        d = state.Discussion("q", make_seats())
        self._run_round(d, "[立場: 同意] [補充: 有]", "[立場: 同意] [補充: 無]")
        self.assertFalse(d.converged())
        self.assertFalse(d.status()["converged"])


class ArbiterAccessTest(unittest.TestCase):
    def _finished_round(self, d):
        d.begin_round()
        d.record_speech("a1", ok_result())
        d.record_speech("a2", ok_result())
        d.end_round()

    def test_arbiter_is_the_seat_object(self):
        d = state.Discussion("q", make_seats())
        self.assertEqual(d.arbiter["seat_id"], "arb")
        self.assertEqual(d.arbiter["role"], state.ARBITER)
        arb_from_seats = next(s for s in d.seats if s["role"] == state.ARBITER)
        self.assertIs(d.arbiter, arb_from_seats)
        self.assertNotIn(d.arbiter, d.advisors)


class CanArbitrateTest(unittest.TestCase):
    def _finished_round(self, d, a1_result=None, a2_result=None):
        d.begin_round()
        d.record_speech("a1", a1_result or ok_result())
        d.record_speech("a2", a2_result or ok_result())
        d.end_round()

    def test_new_discussion_cannot_arbitrate(self):
        d = state.Discussion("q", make_seats())
        self.assertFalse(d.can_arbitrate())
        with self.assertRaises(state.BoundaryError):
            d.record_arbitration(ok_result())

    def test_in_round_cannot_arbitrate(self):
        d = state.Discussion("q", make_seats())
        d.begin_round()
        self.assertFalse(d.can_arbitrate())
        with self.assertRaises(state.BoundaryError):
            d.record_arbitration(ok_result())

    def test_after_full_round_can_arbitrate(self):
        d = state.Discussion("q", make_seats())
        self._finished_round(d)
        self.assertTrue(d.can_arbitrate())

    def test_all_failed_round_cannot_arbitrate(self):
        d = state.Discussion("q", make_seats())
        self._finished_round(d, fail_result(), fail_result())
        self.assertFalse(d.can_arbitrate())
        with self.assertRaises(state.BoundaryError):
            d.record_arbitration(ok_result())

    def test_success_in_earlier_round_still_allows(self):
        d = state.Discussion("q", make_seats())
        self._finished_round(d)
        d.request_next_round()
        self._finished_round(d, fail_result(), fail_result())
        self.assertTrue(d.can_arbitrate())

    def test_ready_phase_still_allows(self):
        d = state.Discussion("q", make_seats())
        self._finished_round(d)
        d.request_next_round()
        self.assertEqual(d.phase, state.PHASE_READY)
        self.assertTrue(d.can_arbitrate())


class RecordArbitrationTest(unittest.TestCase):
    def _finished_round(self, d, a1_result=None, a2_result=None):
        d.begin_round()
        d.record_speech("a1", a1_result or ok_result())
        d.record_speech("a2", a2_result or ok_result())
        d.end_round()

    def test_record_keys_exact_eight(self):
        d = state.Discussion("q", make_seats())
        self._finished_round(d)
        record = d.record_arbitration(ok_result(text="結論"))
        self.assertEqual(set(record.keys()),
                         {"seat_id", "ok", "text", "truncated", "error",
                          "elapsed_s", "model_used", "usage"})
        self.assertEqual(record["seat_id"], "arb")
        self.assertNotIn("stance", record)
        self.assertNotIn("more", record)
        self.assertNotIn("violation", record)

    def test_rounds_untouched(self):
        d = state.Discussion("q", make_seats())
        self._finished_round(d)
        before = copy.deepcopy(d.rounds)
        d.record_arbitration(ok_result(text="結論"))
        self.assertEqual(len(d.arbitrations), 1)
        self.assertEqual(d.rounds, before)

    def test_usage_accounted(self):
        d = state.Discussion("q", make_seats())
        self._finished_round(d)
        before = d.status()
        d.record_arbitration(ok_result(
            usage={"input_tokens": 100, "output_tokens": 50}))
        st = d.status()
        self.assertEqual(st["usage"]["calls"], before["usage"]["calls"] + 1)
        self.assertEqual(st["usage"]["total"]["input_tokens"], 100)
        self.assertEqual(st["usage"]["total"]["output_tokens"], 50)
        self.assertIn("arb", st["usage"]["by_seat"])
        self.assertEqual(st["usage"]["by_seat"]["arb"]["calls"], 1)

    def test_failed_arbitration_still_counts(self):
        d = state.Discussion("q", make_seats())
        self._finished_round(d)
        before_total = d.status()["usage"]["total"]
        record = d.record_arbitration(fail_result())
        self.assertFalse(record["ok"])
        self.assertEqual(len(d.arbitrations), 1)
        st = d.status()
        self.assertEqual(st["usage"]["calls"], 3)
        self.assertEqual(st["usage"]["total"], before_total)

    def test_arbitration_does_not_pollute_convergence(self):
        d = state.Discussion("q", make_seats())
        self._finished_round(d,
                             ok_result(text="[立場: 同意] [補充: 無]"),
                             ok_result(text="[立場: 同意] [補充: 無]"))
        before = d.status()
        d.record_arbitration(ok_result(text="結論\n[立場: 同意] [補充: 無]"))
        after = d.status()
        self.assertEqual(after["converged"], before["converged"])
        self.assertEqual(after["format_violations"], before["format_violations"])

    def test_arbitration_no_marker_no_violation(self):
        d = state.Discussion("q", make_seats())
        self._finished_round(d)
        before = d.status()["format_violations"]
        d.record_arbitration(ok_result(text="純文字結論，沒有任何標記行"))
        self.assertEqual(d.status()["format_violations"], before)

    def test_phase_unchanged(self):
        d = state.Discussion("q", make_seats())
        self._finished_round(d)
        self.assertEqual(d.phase, state.PHASE_AWAITING_USER)
        d.record_arbitration(ok_result(text="結論"))
        self.assertEqual(d.phase, state.PHASE_AWAITING_USER)

    def test_double_arbitration(self):
        d = state.Discussion("q", make_seats())
        self._finished_round(d)
        before = d.status()["usage"]["calls"]
        d.record_arbitration(ok_result(text="第一次"))
        d.record_arbitration(ok_result(text="第二次"))
        self.assertEqual(len(d.arbitrations), 2)
        self.assertEqual(d.status()["usage"]["calls"], before + 2)
        self.assertEqual(d.status()["usage"]["by_seat"]["arb"]["calls"], 2)

    def test_usage_deep_copied(self):
        d = state.Discussion("q", make_seats())
        self._finished_round(d)
        usage = {"input_tokens": 100}
        d.record_arbitration(ok_result(usage=usage))
        usage["input_tokens"] = 999
        st = d.status()
        self.assertEqual(st["usage"]["total"]["input_tokens"], 100)
        self.assertEqual(
            st["usage"]["by_seat"]["arb"]["usage"]["input_tokens"], 100)


if __name__ == "__main__":
    unittest.main()
