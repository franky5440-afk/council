import sys
import unittest
from pathlib import Path

SRC_DIR = Path(__file__).resolve().parent.parent / "src"
sys.path.insert(0, str(SRC_DIR))

from engine import orchestrator  # noqa: E402
from engine import state  # noqa: E402
from engine import wiring  # noqa: E402


def make_seats(advisor_specs=("claude", "gemini")) -> list:
    seats = []
    for i, cli in enumerate(advisor_specs):
        seats.append({"seat_id": f"{cli}-{i + 1}", "cli": cli,
                      "model": None, "role": state.ADVISOR})
    seats.append({"seat_id": "arb", "cli": "codex", "model": None,
                  "role": state.ARBITER})
    return seats


class FakeAdapter:
    """紀錄收到的關鍵字參數。ask 是 keyword-only：實作若改用位置參數會直接 TypeError。"""

    def __init__(self, reply=None):
        self.calls = []
        self.reply = reply

    def ask(self, *, prompt, model, timeout_s, max_chars):
        self.calls.append({
            "prompt": prompt,
            "model": model,
            "timeout_s": timeout_s,
            "max_chars": max_chars,
        })
        if self.reply is not None:
            return self.reply
        return {"ok": True, "text": "回覆\n[立場: 保留] [補充: 有]",
                "truncated": False, "error": None, "elapsed_s": 1.0,
                "model_used": None, "usage": None}


class ParseSeatSpecTest(unittest.TestCase):
    def test_plain_cli(self):
        seat = wiring.parse_seat_spec("claude", seat_id="s1", role="advisor")
        self.assertEqual(
            seat, {"seat_id": "s1", "cli": "claude", "model": None, "role": "advisor"})

    def test_cli_with_model(self):
        seat = wiring.parse_seat_spec("gemini:gemini-2.5-pro", seat_id="s2", role="arbiter")
        self.assertEqual(seat["cli"], "gemini")
        self.assertEqual(seat["model"], "gemini-2.5-pro")

    def test_colon_inside_model_kept(self):
        seat = wiring.parse_seat_spec("opencode:provider/model:x", seat_id="s3", role="advisor")
        self.assertEqual(seat["cli"], "opencode")
        self.assertEqual(seat["model"], "provider/model:x")

    def test_empty_raises(self):
        with self.assertRaises(ValueError):
            wiring.parse_seat_spec("", "s", "advisor")

    def test_left_empty_raises(self):
        with self.assertRaises(ValueError):
            wiring.parse_seat_spec(":model", "s", "advisor")

    def test_right_empty_raises(self):
        with self.assertRaises(ValueError):
            wiring.parse_seat_spec("claude:", "s", "advisor")

    def test_whitespace_raises(self):
        with self.assertRaises(ValueError):
            wiring.parse_seat_spec("   ", "s", "advisor")


class MakeAskFnTest(unittest.TestCase):
    def test_calls_correct_adapter(self):
        registry = {"claude": FakeAdapter(), "gemini": FakeAdapter()}
        ask_fn = wiring.make_ask_fn(registry)
        ask_fn(cli="gemini", prompt="p", model=None, timeout_s=1, max_chars=2)
        self.assertEqual(len(registry["claude"].calls), 0)
        self.assertEqual(len(registry["gemini"].calls), 1)

    def test_kwargs_passed_verbatim(self):
        registry = {"claude": FakeAdapter()}
        ask_fn = wiring.make_ask_fn(registry)
        ask_fn(cli="claude", prompt="問題", model="m-1", timeout_s=42, max_chars=123)
        call = registry["claude"].calls[0]
        self.assertEqual(call["prompt"], "問題")
        self.assertEqual(call["model"], "m-1")
        self.assertEqual(call["timeout_s"], 42)
        self.assertEqual(call["max_chars"], 123)

    def test_return_passthrough(self):
        reply = {"ok": True, "text": "x", "truncated": False, "error": None,
                 "elapsed_s": 0.5, "model_used": "m", "usage": {"a": 1}}

        class ReturnAdapter:
            def ask(self, *, prompt, model, timeout_s, max_chars):
                return reply

        ask_fn = wiring.make_ask_fn({"claude": ReturnAdapter()})
        got = ask_fn(cli="claude", prompt="p", model=None, timeout_s=1, max_chars=2)
        self.assertEqual(got, reply)
        self.assertIs(got, reply)

    def test_unknown_cli_raises(self):
        ask_fn = wiring.make_ask_fn({"claude": FakeAdapter()})
        with self.assertRaises(ValueError) as ctx:
            ask_fn(cli="nonexistent", prompt="p", model=None, timeout_s=1, max_chars=2)
        self.assertIn("nonexistent", str(ctx.exception))

    def test_adapter_exception_propagates(self):
        class BoomAdapter:
            def ask(self, *, prompt, model, timeout_s, max_chars):
                raise RuntimeError("boom")

        ask_fn = wiring.make_ask_fn({"claude": BoomAdapter()})
        with self.assertRaises(RuntimeError):
            ask_fn(cli="claude", prompt="p", model=None, timeout_s=1, max_chars=2)

    def test_registry_required(self):
        with self.assertRaises(TypeError):
            wiring.make_ask_fn()


class DryRunAskFnTest(unittest.TestCase):
    def test_returns_seven_keys(self):
        reply = wiring.dry_run_ask_fn("claude", "問題", "m", 5, 100)
        self.assertTrue(reply["ok"])
        self.assertTrue(reply["text"].startswith("【DRY RUN】"))
        self.assertFalse(reply["truncated"])
        self.assertIsNone(reply["error"])
        self.assertEqual(reply["elapsed_s"], 0.0)
        self.assertIsNone(reply["model_used"])
        self.assertIsNone(reply["usage"])

    def test_text_reports_params(self):
        reply = wiring.dry_run_ask_fn("gemini", "問題內容", "gemini-2.5-pro", 42, 123)
        self.assertIn("gemini", reply["text"])
        self.assertIn("收到 prompt 4 字元", reply["text"])
        self.assertIn("model=gemini-2.5-pro", reply["text"])
        self.assertIn("timeout_s=42", reply["text"])
        self.assertIn("max_chars=123", reply["text"])

    def test_marker_not_converged(self):
        reply = wiring.dry_run_ask_fn("claude", "問題", None, 5, 100)
        marker = state.parse_marker(reply["text"])
        self.assertFalse(marker["violation"])
        self.assertTrue(marker["more"])


class FormatContextTest(unittest.TestCase):
    def test_empty_list(self):
        self.assertEqual(wiring.format_context([]), "")

    def test_single_file(self):
        out = wiring.format_context([("SPEC.md", "內容一\n內容二")])
        self.assertEqual(out, "【檔案：SPEC.md】\n內容一\n內容二")

    def test_two_files_order_and_separator(self):
        out = wiring.format_context([
            ("a.md", "A內容"),
            ("b.md", "B內容"),
        ])
        self.assertEqual(
            out,
            "【檔案：a.md】\nA內容\n\n【檔案：b.md】\nB內容")

    def test_header_not_dash_form(self):
        out = wiring.format_context([("SPEC.md", "x")])
        self.assertIn("【檔案：SPEC.md】", out)
        self.assertNotIn("── SPEC.md ──", out)


class WiringRoundIntegrationTest(unittest.TestCase):
    def test_full_round_with_fake_registry(self):
        claude = FakeAdapter()
        gemini = FakeAdapter()
        codex = FakeAdapter()
        registry = {"claude": claude, "gemini": gemini, "codex": codex}
        d = state.Discussion("問題", make_seats())
        status = orchestrator.run_round(d, wiring.make_ask_fn(registry))
        self.assertEqual(len(claude.calls), 1)
        self.assertEqual(len(gemini.calls), 1)
        self.assertEqual(len(codex.calls), 0)
        self.assertEqual(status["usage"]["calls"], 2)
        self.assertEqual(status["phase"], state.PHASE_AWAITING_USER)

    def test_full_round_dry_run(self):
        d = state.Discussion("問題", make_seats())
        status = orchestrator.run_round(d, wiring.dry_run_ask_fn)
        self.assertEqual(status["usage"]["calls"], 2)
        self.assertEqual(status["phase"], state.PHASE_AWAITING_USER)
        self.assertFalse(status["converged"])


if __name__ == "__main__":
    unittest.main()
