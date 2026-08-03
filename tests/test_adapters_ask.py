import json
import os
import stat
import subprocess
import sys
import unittest
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

SRC_DIR = Path(__file__).resolve().parent.parent / "src"
sys.path.insert(0, str(SRC_DIR))

from adapters import opencode  # noqa: E402
from adapters import claude  # noqa: E402
from adapters import codex  # noqa: E402
from adapters import gemini  # noqa: E402
from adapters import base  # noqa: E402
from adapters.base import PROMPT_INDICATOR  # noqa: E402

FIXTURES = Path(__file__).parent / "fixtures"


def fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def shq(s: str) -> str:
    return "'" + s.replace("'", "'\\''") + "'"


def event(kind: str, text: str | None = None) -> str:
    if text is None:
        return json.dumps({"type": kind, "part": {"type": kind}})
    return json.dumps({"type": kind, "part": {"type": kind, "text": text}})


@contextmanager
def patched_path(path: str):
    old = os.environ.get("PATH")
    os.environ["PATH"] = path
    try:
        yield
    finally:
        if old is None:
            os.environ.pop("PATH", None)
        else:
            os.environ["PATH"] = old


def make_exec(dirpath: Path, name: str, body: str) -> str:
    script = dirpath / name
    script.write_text("#!/bin/sh\n" + body)
    script.chmod(stat.S_IRWXU)
    return str(script)


def tempdir():
    import tempfile

    @contextmanager
    def _inner():
        with tempfile.TemporaryDirectory() as d:
            yield Path(d)

    return _inner()


def stdin_argv_body(arg_log: str, stdin_log: str, payload: str) -> str:
    """把 argv 逐行寫進 arg_log、stdin 原樣寫進 stdin_log，再把 payload 印到 stdout。"""
    return (
        f"printf '%s\\n' \"$@\" > {shq(arg_log)}\n"
        f"/bin/cat > {shq(stdin_log)}\n"
        f"printf '%s\\n' {shq(payload)}"
    )


def opencode_body(arg_log: str, stdin_log: str, events) -> str:
    """opencode 用：epoch 本身已是空格分隔的單引號 JSON token（如既有用例），
    直接原樣放進 printf（不再包 shq，否則會變成單一行、解析失敗）。"""
    stream = " ".join(shq(x) for x in events)
    return (
        f"printf '%s\\n' \"$@\" > {shq(arg_log)}\n"
        f"/bin/cat > {shq(stdin_log)}\n"
        f"printf '%s\\n' {stream}"
    )


def codex_body(arg_log: str, stdin_log: str, reply: str, stderr: str = "") -> str:
    """codex 用的 stub：記錄 argv／stdin、寫出 --output-last-message 目標、選擇性印 stderr。"""
    return (
        f"printf '%s\\n' \"$@\" > {shq(arg_log)}\n"
        f"/bin/cat > {shq(stdin_log)}\n"
        "prev=''\n"
        "for a in \"$@\"; do\n"
        f"  [ \"$prev\" = '--output-last-message' ] && printf '%s' {shq(reply)} > \"$a\"\n"
        "  prev=\"$a\"\n"
        "done\n"
        + (f"printf '%s\\n' {shq(stderr)} >&2\n" if stderr else "")
    )


def opencode_stream(texts=("ok",), tokens=None, cost=None) -> str:
    events = [event("step_start")]
    for t in texts:
        events.append(event("text", t))
    if tokens is not None:
        part = {"type": "step-finish", "tokens": tokens}
        if cost is not None:
            part["cost"] = cost
        events.append(json.dumps({"type": "step_finish", "part": part}))
    else:
        events.append(event("step_finish"))
    return " ".join(shq(x) for x in events)


class OpenCodeAskTest(unittest.TestCase):
    MODEL = "opencode/deepseek-v4-flash-free"

    def test_normal_stream_extracts_text(self):
        with tempdir() as tmp:
            make_exec(tmp, "opencode", f"printf '%s\\n' {opencode_stream(('hello from fake model',))}")
            with patched_path(str(tmp)):
                result = opencode.ask("hello", self.MODEL, 5, 100)
        self.assertTrue(result["ok"])
        self.assertEqual(result["text"], "hello from fake model")
        self.assertFalse(result["truncated"])
        self.assertIsNone(result["error"])

    def test_prompt_sent_via_stdin_not_argv(self):
        with tempdir() as tmp:
            arglog = tmp / "args.log"
            stdinlog = tmp / "stdin.txt"
            body = opencode_body(str(arglog), str(stdinlog),
                                 [event("step_start"), event("text", "ok"),
                                  event("step_finish")])
            make_exec(tmp, "opencode", body)
            with patched_path(str(tmp)):
                result = opencode.ask("hello from user", self.MODEL, 5, 100)
            self.assertTrue(result["ok"])
            args = arglog.read_text().splitlines()
            self.assertNotIn("hello from user", args)
            self.assertEqual(args[-1], PROMPT_INDICATOR)
            self.assertEqual(stdinlog.read_text().strip(), "hello from user")

    def test_long_text_truncated(self):
        long_text = "x" * 500
        with tempdir() as tmp:
            make_exec(tmp, "opencode",
                      f"printf '%s\\n' {shq(event('text', long_text))}")
            with patched_path(str(tmp)):
                result = opencode.ask("hello", self.MODEL, 5, 100)
        self.assertTrue(result["ok"])
        self.assertTrue(result["truncated"])
        self.assertEqual(result["text"], "x" * 100)

    def test_hung_subprocess_times_out(self):
        with tempdir() as tmp:
            make_exec(tmp, "opencode", "exec /bin/sleep 60")
            with patched_path(str(tmp)):
                result = opencode.ask("hello", self.MODEL, 0.3, 100)
        self.assertFalse(result["ok"])
        self.assertIn("timed out", result["error"])
        self.assertEqual(result["text"], "")

    def test_nonzero_exit_is_readable(self):
        with tempdir() as tmp:
            make_exec(tmp, "opencode",
                      f"printf '%s\\n' {shq(event('text', 'hi'))}; exit 3")
            with patched_path(str(tmp)):
                result = opencode.ask("hello", self.MODEL, 5, 100)
        self.assertFalse(result["ok"])
        self.assertIn("command exited with code 3", result["error"])
        self.assertEqual(result["text"], "")

    def test_stream_without_text_is_failure(self):
        with tempdir() as tmp:
            stream = " ".join(shq(x) for x in [event("step_start"), event("step_finish")])
            make_exec(tmp, "opencode", f"printf '%s\\n' {stream}")
            with patched_path(str(tmp)):
                result = opencode.ask("hello", self.MODEL, 5, 100)
        self.assertFalse(result["ok"])
        self.assertIn("no assistant text", result["error"])

    def test_large_chinese_prompt_accepted_via_stdin(self):
        big = "中" * 60000
        self.assertEqual(len(big.encode("utf-8")), 180000)
        with tempdir() as tmp:
            stdinlog = tmp / "stdin.txt"
            body = opencode_body(str(tmp / "args.log"), str(stdinlog),
                                 [event("step_start"), event("text", "ok"),
                                  event("step_finish")])
            make_exec(tmp, "opencode", body)
            with patched_path(str(tmp)):
                result = opencode.ask(big, self.MODEL, 5, 100)
            self.assertTrue(result["ok"])
            self.assertNotIn("prompt too long", result["error"] or "")
            self.assertEqual(stdinlog.read_text().strip(), big)

    def test_model_none_omits_m_flag(self):
        with tempdir() as tmp:
            arglog = tmp / "args.log"
            body = opencode_body(str(arglog), str(tmp / "stdin.txt"),
                                 [event("step_start"), event("text", "ok"),
                                  event("step_finish")])
            make_exec(tmp, "opencode", body)
            with patched_path(str(tmp)):
                result = opencode.ask("hello", None, 5, 100)
            self.assertTrue(result["ok"])
            args = arglog.read_text().splitlines()
            self.assertNotIn("-m", args)
            self.assertEqual(args[-1], PROMPT_INDICATOR)

    def test_model_passed_as_m_flag(self):
        with tempdir() as tmp:
            arglog = tmp / "args.log"
            body = opencode_body(str(arglog), str(tmp / "stdin.txt"),
                                 [event("step_start"), event("text", "ok"),
                                  event("step_finish")])
            make_exec(tmp, "opencode", body)
            with patched_path(str(tmp)):
                result = opencode.ask("hello", self.MODEL, 5, 100)
            self.assertTrue(result["ok"])
            args = arglog.read_text().splitlines()
            self.assertEqual(args[0], "run")
            self.assertIn("--dir", args)
            m_i = args.index("-m")
            self.assertEqual(args[m_i + 1], self.MODEL)

    def test_agent_flag_pair_present(self):
        with tempdir() as tmp:
            arglog = tmp / "args.log"
            make_exec(tmp, "opencode",
                      opencode_body(str(arglog), str(tmp / "stdin.txt"),
                                    [event("step_start"), event("text", "ok"),
                                     event("step_finish")]))
            with patched_path(str(tmp)):
                result = opencode.ask("hello", self.MODEL, 5, 100)
            self.assertTrue(result["ok"])
            args = arglog.read_text().splitlines()
            i = args.index("--agent")
            self.assertEqual(args[i + 1], opencode.AGENT_NAME)

    def test_agent_file_created_with_deny(self):
        with tempdir() as tmp:
            copy = tmp / "agent_copy.md"
            agent_sub = f".opencode/agents/{opencode.AGENT_NAME}.md"
            body = (
                "prev=''\n"
                "for a in \"$@\"; do\n"
                "  if [ \"$prev\" = '--dir' ]; then\n"
                f"    while IFS= read -r line; do printf '%s\\n' \"$line\"; done "
                f"< \"$a/{agent_sub}\" > {shq(str(copy))}\n"
                "  fi\n"
                '  prev="$a"\n'
                "done\n"
                f"printf '%s\\n' {shq(event('text', 'ok'))}"
            )
            make_exec(tmp, "opencode", body)
            with patched_path(str(tmp)):
                result = opencode.ask("hello", self.MODEL, 5, 100)
            self.assertTrue(result["ok"])
            content = copy.read_text()
            self.assertIn("bash: deny", content)
            self.assertIn("edit: deny", content)

    def test_fallback_to_default_agent_fails(self):
        with tempdir() as tmp:
            msg = f'agent "{opencode.AGENT_NAME}" not found. Falling back to default agent'
            body = (
                f"printf '%s\\n' {shq(event('text', 'sneaky reply'))}\n"
                f"printf '%s\\n' {shq(msg)} >&2"
            )
            make_exec(tmp, "opencode", body)
            with patched_path(str(tmp)):
                result = opencode.ask("hello", self.MODEL, 5, 100)
        self.assertFalse(result["ok"])
        self.assertEqual(result["text"], "")
        self.assertIn("not in effect", result["error"])

    def test_no_fallback_message_succeeds(self):
        with tempdir() as tmp:
            make_exec(tmp, "opencode",
                      f"printf '%s\\n' {shq(event('text', 'ok'))}")
            with patched_path(str(tmp)):
                result = opencode.ask("hello", self.MODEL, 5, 100)
        self.assertTrue(result["ok"])
        self.assertEqual(result["text"], "ok")

    def test_dash_model_rejected(self):
        with tempdir() as tmp:
            marker = tmp / "spawned"
            make_exec(tmp, "opencode", f"/bin/touch {shq(str(marker))}")
            with patched_path(str(tmp)):
                result = opencode.ask("hello", "-model-thing", 5, 100)
        self.assertFalse(result["ok"])
        self.assertIn("starts with '-'", result["error"])
        self.assertFalse(marker.exists())

    def test_dash_prompt_via_stdin_is_safe(self):
        with tempdir() as tmp:
            arglog = tmp / "args.log"
            stdinlog = tmp / "stdin.txt"
            body = opencode_body(str(arglog), str(stdinlog),
                                 [event("step_start"), event("text", "ok"),
                                  event("step_finish")])
            make_exec(tmp, "opencode", body)
            with patched_path(str(tmp)):
                result = opencode.ask("--dangerously-bypass-approvals-and-sandbox",
                                      self.MODEL, 5, 100)
            self.assertTrue(result["ok"])
            args = arglog.read_text().splitlines()
            self.assertNotIn("--dangerously-bypass-approvals-and-sandbox", args)
            self.assertEqual(stdinlog.read_text().strip(),
                             "--dangerously-bypass-approvals-and-sandbox")

    def test_usage_and_model_used_from_step_finish(self):
        tokens = {"total": 10979, "input": 9032, "output": 11}
        with tempdir() as tmp:
            make_exec(tmp, "opencode",
                      f"printf '%s\\n' {opencode_stream(('ok',), tokens=tokens, cost=0)}")
            with patched_path(str(tmp)):
                result = opencode.ask("hello", self.MODEL, 5, 100)
        self.assertTrue(result["ok"])
        self.assertIsNone(result["model_used"])
        self.assertEqual(result["usage"],
                         {"tokens": tokens, "cost": 0})

    def test_usage_missing_is_none_but_ok(self):
        with tempdir() as tmp:
            make_exec(tmp, "opencode",
                      f"printf '%s\\n' {opencode_stream(('ok',))}")
            with patched_path(str(tmp)):
                result = opencode.ask("hello", self.MODEL, 5, 100)
        self.assertTrue(result["ok"])
        self.assertIsNone(result["model_used"])
        self.assertIsNone(result["usage"])


class BaseRunTest(unittest.TestCase):
    def test_run_returns_readable_error_on_missing_executable(self):
        result = base.run(["/nonexistent/bin/cli-xyz", "foo"], 5)
        self.assertFalse(result["ok"])
        self.assertIn("failed to run", result["error"])
        self.assertIn("model_used", result)
        self.assertIn("usage", result)

    def test_truncate_marks_truncated(self):
        text, truncated = base.truncate("abcde", 3)
        self.assertTrue(truncated)
        self.assertEqual(text, "abc")
        text, truncated = base.truncate("abc", 5)
        self.assertFalse(truncated)
        self.assertEqual(text, "abc")

    def test_run_no_stdin_text_uses_devnull(self):
        with mock.patch("adapters.base.subprocess.run") as mocked:
            mocked.return_value = SimpleNamespace(returncode=0, stdout="", stderr="")
            result = base.run(["fake-cli"], 5)
        self.assertTrue(result["ok"])
        self.assertIs(mocked.call_args.kwargs["stdin"], subprocess.DEVNULL)
        self.assertNotIn("input", mocked.call_args.kwargs)

    def test_run_stdin_text_written_then_closed(self):
        with mock.patch("adapters.base.subprocess.run") as mocked:
            mocked.return_value = SimpleNamespace(returncode=0, stdout="", stderr="")
            result = base.run(["fake-cli"], 5, stdin_text="hello")
        self.assertTrue(result["ok"])
        self.assertEqual(mocked.call_args.kwargs["input"], "hello")
        self.assertNotIn("stdin", mocked.call_args.kwargs)

    def test_run_stdin_text_reaches_child(self):
        with tempdir() as tmp:
            capture = tmp / "captured.txt"
            make_exec(tmp, "fakecli", f"/bin/cat > {shq(str(capture))}")
            with patched_path(str(tmp)):
                result = base.run(["fakecli"], 5, stdin_text="payload\nsecond")
            self.assertTrue(result["ok"])
            self.assertEqual(capture.read_text(), "payload\nsecond")

    def test_stderr_warning_first_error_last(self):
        with tempdir() as tmp:
            body = (
                "printf '%s\\n' 'Ripgrep is not available. Falling back to GrepTool.' >&2\n"
                "printf '%s\\n' 'Unable to reach the model server.' >&2\n"
                "exit 3"
            )
            make_exec(tmp, "fakecli", body)
            with patched_path(str(tmp)):
                result = base.run(["fakecli"], 5)
        self.assertIn("Unable to reach the model server.", result["error"])
        self.assertNotIn("Ripgrep", result["error"])
        self.assertIn("command exited with code 3", result["error"])

    def test_stderr_stack_trace_lines_skipped(self):
        with tempdir() as tmp:
            body = (
                "printf '%s\\n' 'Ripgrep is not available. Falling back to GrepTool.' >&2\n"
                "printf '%s\\n' 'Attempt 1 failed with status 503. Retrying with backoff... _ApiError: {\"error\":{\"code\":503}}' >&2\n"
                "printf '%s\\n' '    at throwErrorIfNotOK (file:///usr/local/lib/node_modules/@google/gemini-cli/bundle/chunk.js:267191:24)' >&2\n"
                "printf '%s\\n' '    at process.processTicksAndRejections (node:internal/process/task_queues:104:5)' >&2\n"
                "exit 3"
            )
            make_exec(tmp, "fakecli", body)
            with patched_path(str(tmp)):
                result = base.run(["fakecli"], 5)
        self.assertIn("Attempt 1 failed with status 503", result["error"])
        self.assertNotIn("throwErrorIfNotOK", result["error"])
        self.assertNotIn("processTicksAndRejections", result["error"])

    def test_stderr_overlong_line_truncated(self):
        with tempdir() as tmp:
            body = f"printf '%s\\n' {'x' * 350} >&2; exit 3"
            make_exec(tmp, "fakecli", body)
            with patched_path(str(tmp)):
                result = base.run(["fakecli"], 5)
        self.assertTrue(result["error"].endswith("x" * base.MAX_ERROR_CHARS + "…"))
        self.assertEqual(len(result["error"]), len("command exited with code 3: ") + base.MAX_ERROR_CHARS + 1)

    def test_stderr_empty_omits_detail(self):
        with tempdir() as tmp:
            make_exec(tmp, "fakecli", "exit 3")
            with patched_path(str(tmp)):
                result = base.run(["fakecli"], 5)
        self.assertEqual(result["error"], "command exited with code 3")

    def test_run_success_carries_stderr(self):
        with tempdir() as tmp:
            make_exec(tmp, "fakecli",
                      "printf '%s' 'warn text' >&2; printf '%s' 'out text'")
            with patched_path(str(tmp)):
                result = base.run(["fakecli"], 5)
        self.assertTrue(result["ok"])
        self.assertEqual(result["stderr"], "warn text")

    def test_run_nonzero_carries_stderr(self):
        with tempdir() as tmp:
            make_exec(tmp, "fakecli", "printf '%s' 'boom' >&2; exit 3")
            with patched_path(str(tmp)):
                result = base.run(["fakecli"], 5)
        self.assertFalse(result["ok"])
        self.assertEqual(result["stderr"], "boom")

    def test_run_timeout_has_stderr_key(self):
        with tempdir() as tmp:
            make_exec(tmp, "fakecli", "exec /bin/sleep 60")
            with patched_path(str(tmp)):
                result = base.run(["fakecli"], 0.2)
        self.assertFalse(result["ok"])
        self.assertIn("timed out", result["error"])
        self.assertIn("stderr", result)
        self.assertEqual(result["stderr"], "")

    def test_run_missing_exec_has_stderr_key(self):
        result = base.run(["/nonexistent/bin/nope-xyz"], 5)
        self.assertFalse(result["ok"])
        self.assertIn("stderr", result)
        self.assertEqual(result["stderr"], "")


class ClaudeAskTest(unittest.TestCase):
    def test_success_extracts_result_and_metadata(self):
        payload = fixture("claude_success.json")
        with tempdir() as tmp:
            make_exec(tmp, "claude", f"printf '%s\\n' {shq(payload)}")
            with patched_path(str(tmp)):
                result = claude.ask("hello", "claude-opus-5", 5, 100)
        self.assertTrue(result["ok"])
        self.assertEqual(result["text"],
                         json.loads(fixture("claude_success.json"))["result"])
        self.assertFalse(result["truncated"])
        self.assertIsNone(result["error"])
        self.assertEqual(result["model_used"], "claude-opus-5")
        self.assertEqual(result["usage"]["total_cost_usd"], 0.0929975)
        self.assertEqual(result["usage"]["input_tokens"], 2)

    def test_prompt_sent_via_stdin_not_argv(self):
        payload = json.dumps({"is_error": False, "result": "ok"})
        with tempdir() as tmp:
            arglog = tmp / "args.log"
            stdinlog = tmp / "stdin.txt"
            body = stdin_argv_body(str(arglog), str(stdinlog), payload)
            make_exec(tmp, "claude", body)
            with patched_path(str(tmp)):
                result = claude.ask("hello from user", "claude-opus-5", 5, 100)
            self.assertTrue(result["ok"])
            args = arglog.read_text().splitlines()
            self.assertNotIn("hello from user", args)
            self.assertIn(PROMPT_INDICATOR, args)
            self.assertEqual(stdinlog.read_text().strip(), "hello from user")

    def test_long_text_truncated(self):
        long_text = "x" * 500
        payload = json.dumps({"is_error": False, "result": long_text})
        with tempdir() as tmp:
            make_exec(tmp, "claude", f"printf '%s\\n' {shq(payload)}")
            with patched_path(str(tmp)):
                result = claude.ask("hello", "claude-opus-5", 5, 100)
        self.assertTrue(result["ok"])
        self.assertTrue(result["truncated"])
        self.assertEqual(result["text"], "x" * 100)

    def test_invalid_json_is_failure(self):
        with tempdir() as tmp:
            make_exec(tmp, "claude", "printf '%s\\n' 'not json'")
            with patched_path(str(tmp)):
                result = claude.ask("hello", "claude-opus-5", 5, 100)
        self.assertFalse(result["ok"])
        self.assertIn("invalid JSON", result["error"])
        self.assertEqual(result["text"], "")

    def test_hung_subprocess_times_out(self):
        with tempdir() as tmp:
            make_exec(tmp, "claude", "exec /bin/sleep 60")
            with patched_path(str(tmp)):
                result = claude.ask("hello", "claude-opus-5", 0.3, 100)
        self.assertFalse(result["ok"])
        self.assertIn("timed out", result["error"])
        self.assertEqual(result["text"], "")

    def test_nonzero_exit_is_readable(self):
        with tempdir() as tmp:
            make_exec(tmp, "claude", "printf '%s\\n' hi; exit 3")
            with patched_path(str(tmp)):
                result = claude.ask("hello", "claude-opus-5", 5, 100)
        self.assertFalse(result["ok"])
        self.assertIn("command exited with code 3", result["error"])
        self.assertEqual(result["text"], "")
        self.assertNotIn("stderr", result)

    def test_large_chinese_prompt_accepted_via_stdin(self):
        payload = json.dumps({"is_error": False, "result": "ok"})
        big = "中" * 60000
        self.assertEqual(len(big.encode("utf-8")), 180000)
        with tempdir() as tmp:
            stdinlog = tmp / "stdin.txt"
            body = stdin_argv_body(str(tmp / "args.log"), str(stdinlog), payload)
            make_exec(tmp, "claude", body)
            with patched_path(str(tmp)):
                result = claude.ask(big, "claude-opus-5", 5, 100)
            self.assertTrue(result["ok"])
            self.assertNotIn("prompt too long", result["error"] or "")
            self.assertEqual(stdinlog.read_text().strip(), big)

    def test_model_none_omits_model_flag(self):
        payload = json.dumps({"is_error": False, "result": "ok"})
        with tempdir() as tmp:
            arglog = tmp / "args.log"
            make_exec(tmp, "claude", stdin_argv_body(str(arglog), str(tmp / "stdin.txt"), payload))
            with patched_path(str(tmp)):
                result = claude.ask("hello", None, 5, 100)
            self.assertTrue(result["ok"])
            args = arglog.read_text().splitlines()
            self.assertNotIn("--model", args)
            self.assertIn(PROMPT_INDICATOR, args)

    def test_model_flag_presence(self):
        payload = json.dumps({"is_error": False, "result": "ok"})
        with tempdir() as tmp:
            arglog = tmp / "args.log"
            make_exec(tmp, "claude", stdin_argv_body(str(arglog), str(tmp / "stdin.txt"), payload))
            with patched_path(str(tmp)):
                result = claude.ask("hello", "claude-opus-5", 5, 100)
            self.assertTrue(result["ok"])
            args = arglog.read_text().splitlines()
            m_i = args.index("--model")
            self.assertEqual(args[m_i + 1], "claude-opus-5")

    def test_readonly_flags_present(self):
        payload = json.dumps({"is_error": False, "result": "ok"})
        with tempdir() as tmp:
            arglog = tmp / "args.log"
            make_exec(tmp, "claude", stdin_argv_body(str(arglog), str(tmp / "stdin.txt"), payload))
            with patched_path(str(tmp)):
                result = claude.ask("hello", "claude-opus-5", 5, 100)
            self.assertTrue(result["ok"])
            args = arglog.read_text().splitlines()
            tools_i = args.index("--tools")
            self.assertEqual(args[tools_i + 1], "")
            p_i = args.index("-p")
            self.assertEqual(args[p_i + 1], PROMPT_INDICATOR)

    def test_dash_model_rejected(self):
        with tempdir() as tmp:
            marker = tmp / "spawned"
            make_exec(tmp, "claude", f"/bin/touch {shq(str(marker))}")
            with patched_path(str(tmp)):
                result = claude.ask("hello", "-model-thing", 5, 100)
        self.assertFalse(result["ok"])
        self.assertIn("starts with '-'", result["error"])
        self.assertFalse(marker.exists())

    def test_dash_prompt_via_stdin_is_safe(self):
        with tempdir() as tmp:
            arglog = tmp / "args.log"
            stdinlog = tmp / "stdin.txt"
            body = stdin_argv_body(str(arglog), str(stdinlog),
                                   json.dumps({"is_error": False, "result": "ok"}))
            make_exec(tmp, "claude", body)
            with patched_path(str(tmp)):
                result = claude.ask("--dangerously-bypass-approvals-and-sandbox",
                                    "claude-opus-5", 5, 100)
            self.assertTrue(result["ok"])
            args = arglog.read_text().splitlines()
            self.assertNotIn("--dangerously-bypass-approvals-and-sandbox", args)
            self.assertEqual(stdinlog.read_text().strip(),
                             "--dangerously-bypass-approvals-and-sandbox")

    def test_metadata_missing_is_none_but_ok(self):
        payload = json.dumps({"is_error": False, "result": "ok"})
        with tempdir() as tmp:
            make_exec(tmp, "claude", f"printf '%s\\n' {shq(payload)}")
            with patched_path(str(tmp)):
                result = claude.ask("hello", "claude-opus-5", 5, 100)
        self.assertTrue(result["ok"])
        self.assertIsNone(result["model_used"])
        self.assertIsNone(result["usage"])


class CodexAskTest(unittest.TestCase):
    CODX_LAST = "我是基於 GPT-5 的 Codex 模型。"
    CODEX_STDERR = (
        "Reading additional input from stdin...\n"
        "OpenAI Codex v0.145.0\n"
        "--------\n"
        "workdir: /home/<user>/council\n"
        "model: gpt-5.4-mini\n"
        "provider: openai\n"
        "user\n"
        f"{PROMPT_INDICATOR}\n"
        "<stdin>\n"
        "this is the transcript echo\n"
        "</stdin>\n"
        "codex\n"
        "STDIN-OK\n"
        "tokens used\n"
        "4,739"
    )

    def test_success_reads_output_file_and_metadata(self):
        with tempdir() as tmp:
            body = codex_body(str(tmp / "args.log"), str(tmp / "stdin.txt"),
                              self.CODX_LAST, self.CODEX_STDERR)
            make_exec(tmp, "codex", body)
            with patched_path(str(tmp)):
                result = codex.ask("hello", "gpt-5.4-mini", 5, 100)
        self.assertTrue(result["ok"])
        self.assertEqual(result["text"], self.CODX_LAST)
        self.assertFalse(result["truncated"])
        self.assertIsNone(result["error"])
        self.assertEqual(result["model_used"], "gpt-5.4-mini")
        self.assertEqual(result["usage"], {"tokens_used": 4739})

    def test_prompt_sent_via_stdin_not_argv(self):
        with tempdir() as tmp:
            arglog = tmp / "args.log"
            stdinlog = tmp / "stdin.txt"
            body = codex_body(str(arglog), str(stdinlog), self.CODX_LAST)
            make_exec(tmp, "codex", body)
            with patched_path(str(tmp)):
                result = codex.ask("hello from user", "gpt-5.4-mini", 5, 100)
            self.assertTrue(result["ok"])
            args = arglog.read_text().splitlines()
            self.assertNotIn("hello from user", args)
            self.assertEqual(args[-2], "--")
            self.assertEqual(args[-1], PROMPT_INDICATOR)
            self.assertEqual(stdinlog.read_text().strip(), "hello from user")

    def test_output_file_never_written_is_failure(self):
        with tempdir() as tmp:
            make_exec(tmp, "codex", "true")
            with patched_path(str(tmp)):
                result = codex.ask("hello", "gpt-5.4-mini", 5, 100)
        self.assertFalse(result["ok"])
        self.assertIn("did not write output file", result["error"])
        self.assertEqual(result["text"], "")

    def test_empty_output_file_is_failure(self):
        with tempdir() as tmp:
            body = (
                "prev=''\n"
                "for a in \"$@\"; do\n"
                "  [ \"$prev\" = '--output-last-message' ] && : > \"$a\"\n"
                "  prev=\"$a\"\n"
                "done\n"
            )
            make_exec(tmp, "codex", body)
            with patched_path(str(tmp)):
                result = codex.ask("hello", "gpt-5.4-mini", 5, 100)
        self.assertFalse(result["ok"])
        self.assertIn("empty", result["error"])
        self.assertEqual(result["text"], "")

    def test_long_text_truncated(self):
        long_text = "x" * 500
        with tempdir() as tmp:
            body = codex_body(str(tmp / "args.log"), str(tmp / "stdin.txt"), long_text)
            make_exec(tmp, "codex", body)
            with patched_path(str(tmp)):
                result = codex.ask("hello", "gpt-5.4-mini", 5, 100)
        self.assertTrue(result["ok"])
        self.assertTrue(result["truncated"])
        self.assertEqual(result["text"], "x" * 100)

    def test_hung_subprocess_times_out(self):
        with tempdir() as tmp:
            make_exec(tmp, "codex", "exec /bin/sleep 60")
            with patched_path(str(tmp)):
                result = codex.ask("hello", "gpt-5.4-mini", 0.3, 100)
        self.assertFalse(result["ok"])
        self.assertIn("timed out", result["error"])
        self.assertEqual(result["text"], "")

    def test_nonzero_exit_is_readable(self):
        with tempdir() as tmp:
            make_exec(tmp, "codex", "exit 3")
            with patched_path(str(tmp)):
                result = codex.ask("hello", "gpt-5.4-mini", 5, 100)
        self.assertFalse(result["ok"])
        self.assertIn("command exited with code 3", result["error"])
        self.assertEqual(result["text"], "")
        self.assertNotIn("stderr", result)

    def test_large_chinese_prompt_accepted_via_stdin(self):
        big = "中" * 60000
        self.assertEqual(len(big.encode("utf-8")), 180000)
        with tempdir() as tmp:
            stdinlog = tmp / "stdin.txt"
            body = codex_body(str(tmp / "args.log"), str(stdinlog), self.CODX_LAST)
            make_exec(tmp, "codex", body)
            with patched_path(str(tmp)):
                result = codex.ask(big, "gpt-5.4-mini", 5, 100)
            self.assertTrue(result["ok"])
            self.assertNotIn("prompt too long", result["error"] or "")
            self.assertEqual(stdinlog.read_text().strip(), big)

    def test_model_none_omits_m_flag(self):
        with tempdir() as tmp:
            arglog = tmp / "args.log"
            body = codex_body(str(arglog), str(tmp / "stdin.txt"), self.CODX_LAST)
            make_exec(tmp, "codex", body)
            with patched_path(str(tmp)):
                result = codex.ask("hello", None, 5, 100)
            self.assertTrue(result["ok"])
            args = arglog.read_text().splitlines()
            self.assertNotIn("-m", args)
            self.assertEqual(args[-1], PROMPT_INDICATOR)

    def test_model_flag_presence(self):
        with tempdir() as tmp:
            arglog = tmp / "args.log"
            body = codex_body(str(arglog), str(tmp / "stdin.txt"), self.CODX_LAST)
            make_exec(tmp, "codex", body)
            with patched_path(str(tmp)):
                result = codex.ask("hello", "gpt-5.4-mini", 5, 100)
            self.assertTrue(result["ok"])
            args = arglog.read_text().splitlines()
            m_i = args.index("-m")
            self.assertEqual(args[m_i + 1], "gpt-5.4-mini")

    def test_readonly_flags_present(self):
        with tempdir() as tmp:
            arglog = tmp / "args.log"
            body = codex_body(str(arglog), str(tmp / "stdin.txt"), self.CODX_LAST)
            make_exec(tmp, "codex", body)
            with patched_path(str(tmp)):
                result = codex.ask("hello", "gpt-5.4-mini", 5, 100)
            self.assertTrue(result["ok"])
            args = arglog.read_text().splitlines()
            sandbox_i = args.index("--sandbox")
            self.assertEqual(args[sandbox_i + 1], "read-only")

    def test_dash_model_rejected(self):
        with tempdir() as tmp:
            marker = tmp / "spawned"
            make_exec(tmp, "codex", f"/bin/touch {shq(str(marker))}")
            with patched_path(str(tmp)):
                result = codex.ask("hello", "-model-thing", 5, 100)
        self.assertFalse(result["ok"])
        self.assertIn("starts with '-'", result["error"])
        self.assertFalse(marker.exists())

    def test_dash_prompt_via_stdin_is_safe(self):
        with tempdir() as tmp:
            arglog = tmp / "args.log"
            stdinlog = tmp / "stdin.txt"
            body = codex_body(str(arglog), str(stdinlog), self.CODX_LAST)
            make_exec(tmp, "codex", body)
            with patched_path(str(tmp)):
                result = codex.ask("--dangerously-bypass-approvals-and-sandbox",
                                   "gpt-5.4-mini", 5, 100)
            self.assertTrue(result["ok"])
            args = arglog.read_text().splitlines()
            self.assertNotIn("--dangerously-bypass-approvals-and-sandbox", args)
            self.assertEqual(stdinlog.read_text().strip(),
                             "--dangerously-bypass-approvals-and-sandbox")

    def test_metadata_missing_is_none_but_ok(self):
        with tempdir() as tmp:
            body = codex_body(str(tmp / "args.log"), str(tmp / "stdin.txt"),
                              self.CODX_LAST, "Reading additional input from stdin...\n")
            make_exec(tmp, "codex", body)
            with patched_path(str(tmp)):
                result = codex.ask("hello", "gpt-5.4-mini", 5, 100)
        self.assertTrue(result["ok"])
        self.assertIsNone(result["model_used"])
        self.assertIsNone(result["usage"])


class GeminiAskTest(unittest.TestCase):
    def test_success_extracts_response_and_metadata(self):
        payload = fixture("gemini_success.json")
        with tempdir() as tmp:
            make_exec(tmp, "gemini", f"printf '%s\\n' {shq(payload)}")
            with patched_path(str(tmp)):
                result = gemini.ask("hello", "gemini-3.1-pro", 5, 100)
        self.assertTrue(result["ok"])
        self.assertEqual(result["text"],
                         json.loads(fixture("gemini_success.json"))["response"])
        self.assertFalse(result["truncated"])
        self.assertIsNone(result["error"])
        self.assertEqual(result["model_used"], "gemini-3.1-pro-preview-customtools")
        self.assertEqual(result["usage"]["input"], 5484)

    def test_prompt_sent_via_stdin_not_argv(self):
        payload = json.dumps({"response": "ok"})
        with tempdir() as tmp:
            arglog = tmp / "args.log"
            stdinlog = tmp / "stdin.txt"
            body = stdin_argv_body(str(arglog), str(stdinlog), payload)
            make_exec(tmp, "gemini", body)
            with patched_path(str(tmp)):
                result = gemini.ask("hello from user", "gemini-3.1-pro", 5, 100)
            self.assertTrue(result["ok"])
            args = arglog.read_text().splitlines()
            self.assertNotIn("hello from user", args)
            self.assertIn(PROMPT_INDICATOR, args)
            self.assertEqual(stdinlog.read_text().strip(), "hello from user")

    def test_long_text_truncated(self):
        long_text = "x" * 500
        payload = json.dumps({"response": long_text})
        with tempdir() as tmp:
            make_exec(tmp, "gemini", f"printf '%s\\n' {shq(payload)}")
            with patched_path(str(tmp)):
                result = gemini.ask("hello", "gemini-3.1-pro", 5, 100)
        self.assertTrue(result["ok"])
        self.assertTrue(result["truncated"])
        self.assertEqual(result["text"], "x" * 100)

    def test_invalid_json_is_failure(self):
        with tempdir() as tmp:
            make_exec(tmp, "gemini", "printf '%s\\n' 'not json'")
            with patched_path(str(tmp)):
                result = gemini.ask("hello", "gemini-3.1-pro", 5, 100)
        self.assertFalse(result["ok"])
        self.assertIn("invalid JSON", result["error"])
        self.assertEqual(result["text"], "")

    def test_hung_subprocess_times_out(self):
        with tempdir() as tmp:
            make_exec(tmp, "gemini", "exec /bin/sleep 60")
            with patched_path(str(tmp)):
                result = gemini.ask("hello", "gemini-3.1-pro", 0.3, 100)
        self.assertFalse(result["ok"])
        self.assertIn("timed out", result["error"])
        self.assertEqual(result["text"], "")

    def test_nonzero_exit_is_readable(self):
        with tempdir() as tmp:
            make_exec(tmp, "gemini", "printf '%s\\n' hi; exit 3")
            with patched_path(str(tmp)):
                result = gemini.ask("hello", "gemini-3.1-pro", 5, 100)
        self.assertFalse(result["ok"])
        self.assertIn("command exited with code 3", result["error"])
        self.assertEqual(result["text"], "")
        self.assertNotIn("stderr", result)

    def test_large_chinese_prompt_accepted_via_stdin(self):
        payload = json.dumps({"response": "ok"})
        big = "中" * 60000
        self.assertEqual(len(big.encode("utf-8")), 180000)
        with tempdir() as tmp:
            stdinlog = tmp / "stdin.txt"
            body = stdin_argv_body(str(tmp / "args.log"), str(stdinlog), payload)
            make_exec(tmp, "gemini", body)
            with patched_path(str(tmp)):
                result = gemini.ask(big, "gemini-3.1-pro", 5, 100)
            self.assertTrue(result["ok"])
            self.assertNotIn("prompt too long", result["error"] or "")
            self.assertEqual(stdinlog.read_text().strip(), big)

    def test_model_none_omits_m_flag(self):
        payload = json.dumps({"response": "ok"})
        with tempdir() as tmp:
            arglog = tmp / "args.log"
            make_exec(tmp, "gemini", stdin_argv_body(str(arglog), str(tmp / "stdin.txt"), payload))
            with patched_path(str(tmp)):
                result = gemini.ask("hello", None, 5, 100)
            self.assertTrue(result["ok"])
            args = arglog.read_text().splitlines()
            self.assertNotIn("-m", args)
            self.assertIn(PROMPT_INDICATOR, args)

    def test_model_flag_presence(self):
        payload = json.dumps({"response": "ok"})
        with tempdir() as tmp:
            arglog = tmp / "args.log"
            make_exec(tmp, "gemini", stdin_argv_body(str(arglog), str(tmp / "stdin.txt"), payload))
            with patched_path(str(tmp)):
                result = gemini.ask("hello", "gemini-3.1-pro", 5, 100)
            self.assertTrue(result["ok"])
            args = arglog.read_text().splitlines()
            m_i = args.index("-m")
            self.assertEqual(args[m_i + 1], "gemini-3.1-pro")

    def test_readonly_flags_present(self):
        payload = json.dumps({"response": "ok"})
        with tempdir() as tmp:
            arglog = tmp / "args.log"
            make_exec(tmp, "gemini", stdin_argv_body(str(arglog), str(tmp / "stdin.txt"), payload))
            with patched_path(str(tmp)):
                result = gemini.ask("hello", "gemini-3.1-pro", 5, 100)
            self.assertTrue(result["ok"])
            args = arglog.read_text().splitlines()
            mode_i = args.index("--approval-mode")
            self.assertEqual(args[mode_i + 1], "plan")
            self.assertIn("--skip-trust", args)

    def test_no_double_separator(self):
        payload = json.dumps({"response": "ok"})
        with tempdir() as tmp:
            arglog = tmp / "args.log"
            make_exec(tmp, "gemini", stdin_argv_body(str(arglog), str(tmp / "stdin.txt"), payload))
            with patched_path(str(tmp)):
                result = gemini.ask("hello", "gemini-3.1-pro", 5, 100)
            self.assertTrue(result["ok"])
            args = arglog.read_text().splitlines()
            self.assertNotIn("--", args)

    def test_dash_model_rejected(self):
        with tempdir() as tmp:
            marker = tmp / "spawned"
            make_exec(tmp, "gemini", f"/bin/touch {shq(str(marker))}")
            with patched_path(str(tmp)):
                result = gemini.ask("hello", "-model-thing", 5, 100)
        self.assertFalse(result["ok"])
        self.assertIn("starts with '-'", result["error"])
        self.assertFalse(marker.exists())

    def test_dash_prompt_via_stdin_is_safe(self):
        with tempdir() as tmp:
            arglog = tmp / "args.log"
            stdinlog = tmp / "stdin.txt"
            body = stdin_argv_body(str(arglog), str(stdinlog),
                                   json.dumps({"response": "ok"}))
            make_exec(tmp, "gemini", body)
            with patched_path(str(tmp)):
                result = gemini.ask("--dangerously-bypass-approvals-and-sandbox",
                                    "gemini-3.1-pro", 5, 100)
            self.assertTrue(result["ok"])
            args = arglog.read_text().splitlines()
            self.assertNotIn("--dangerously-bypass-approvals-and-sandbox", args)
            self.assertEqual(stdinlog.read_text().strip(),
                             "--dangerously-bypass-approvals-and-sandbox")

    def test_metadata_missing_is_none_but_ok(self):
        payload = json.dumps({"response": "ok"})
        with tempdir() as tmp:
            make_exec(tmp, "gemini", f"printf '%s\\n' {shq(payload)}")
            with patched_path(str(tmp)):
                result = gemini.ask("hello", "gemini-3.1-pro", 5, 100)
        self.assertTrue(result["ok"])
        self.assertIsNone(result["model_used"])
        self.assertIsNone(result["usage"])


if __name__ == "__main__":
    unittest.main()
