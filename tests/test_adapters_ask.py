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


class OpenCodeAskTest(unittest.TestCase):
    def test_normal_stream_extracts_text(self):
        with tempdir() as tmp:
            stream = " ".join(
                shq(x)
                for x in [event("step_start"), event("text", "hello from fake model"),
                          event("step_finish")]
            )
            make_exec(tmp, "opencode", f"printf '%s\\n' {stream}")
            with patched_path(str(tmp)):
                result = opencode.ask("hello", None, 5, 100)
        self.assertTrue(result["ok"])
        self.assertEqual(result["text"], "hello from fake model")
        self.assertFalse(result["truncated"])
        self.assertIsNone(result["error"])

    def test_long_text_truncated(self):
        long_text = "x" * 500
        with tempdir() as tmp:
            make_exec(tmp, "opencode", f"printf '%s\\n' {shq(event('text', long_text))}")
            with patched_path(str(tmp)):
                result = opencode.ask("hello", None, 5, 100)
        self.assertTrue(result["ok"])
        self.assertTrue(result["truncated"])
        self.assertEqual(result["text"], "x" * 100)
        self.assertEqual(len(result["text"]), 100)

    def test_hung_subprocess_times_out(self):
        with tempdir() as tmp:
            make_exec(tmp, "opencode", "exec /bin/sleep 60")
            with patched_path(str(tmp)):
                result = opencode.ask("hello", None, 0.3, 100)
        self.assertFalse(result["ok"])
        self.assertIn("timed out", result["error"])
        self.assertEqual(result["text"], "")

    def test_nonzero_exit_is_readable(self):
        with tempdir() as tmp:
            make_exec(tmp, "opencode",
                      f"printf '%s\\n' {shq(event('text', 'hi'))}; exit 3")
            with patched_path(str(tmp)):
                result = opencode.ask("hello", None, 5, 100)
        self.assertFalse(result["ok"])
        self.assertIn("command exited with code 3", result["error"])
        self.assertEqual(result["text"], "")

    def test_stream_without_text_is_failure(self):
        with tempdir() as tmp:
            stream = " ".join(shq(x) for x in [event("step_start"), event("step_finish")])
            make_exec(tmp, "opencode", f"printf '%s\\n' {stream}")
            with patched_path(str(tmp)):
                result = opencode.ask("hello", None, 5, 100)
        self.assertFalse(result["ok"])
        self.assertIn("no assistant text", result["error"])

    def test_oversized_prompt_never_spawns_subprocess(self):
        with tempdir() as tmp:
            marker = tmp / "spawned"
            make_exec(tmp, "opencode", f"touch {shq(str(marker))}")
            prompt = "x" * (base.MAX_ARG_CHARS + 1)
            with patched_path(str(tmp)):
                result = opencode.ask(prompt, None, 5, 100)
        self.assertFalse(result["ok"])
        self.assertIn("prompt too long", result["error"])
        self.assertFalse(marker.exists())

    def test_model_none_omits_m_flag(self):
        with tempdir() as tmp:
            arglog = tmp / "args.log"
            body = (
                f"printf '%s\\n' \"$@\" > {shq(str(arglog))}\n"
                f"printf '%s\\n' {shq(event('text', 'ok'))}"
            )
            make_exec(tmp, "opencode", body)
            with patched_path(str(tmp)):
                result = opencode.ask("hello", None, 5, 100)
            self.assertTrue(result["ok"])
            args = arglog.read_text().splitlines()
            self.assertEqual(args[0], "run")
            self.assertNotIn("-m", args)
            self.assertEqual(args[-1], "hello")

    def test_model_passed_as_m_flag(self):
        with tempdir() as tmp:
            arglog = tmp / "args.log"
            body = (
                f"printf '%s\\n' \"$@\" > {shq(str(arglog))}\n"
                f"printf '%s\\n' {shq(event('text', 'ok'))}"
            )
            make_exec(tmp, "opencode", body)
            with patched_path(str(tmp)):
                result = opencode.ask("hello", "opencode/some-model", 5, 100)
            self.assertTrue(result["ok"])
            args = arglog.read_text().splitlines()
            self.assertEqual(args[0], "run")
            self.assertIn("--dir", args)
            m_i = args.index("-m")
            self.assertEqual(args[m_i + 1], "opencode/some-model")
            self.assertEqual(args[-1], "hello")

    def test_dash_prompt_injection_rejected(self):
        with tempdir() as tmp:
            marker = tmp / "spawned"
            make_exec(tmp, "opencode", f"touch {shq(str(marker))}")
            with patched_path(str(tmp)):
                result = opencode.ask("--dangerously-bypass-approvals-and-sandbox",
                                      None, 5, 100)
        self.assertFalse(result["ok"])
        self.assertIn("starts with '-'", result["error"])
        self.assertFalse(marker.exists())

    def test_dash_model_rejected(self):
        with tempdir() as tmp:
            marker = tmp / "spawned"
            make_exec(tmp, "opencode", f"touch {shq(str(marker))}")
            with patched_path(str(tmp)):
                result = opencode.ask("hello", "-model-thing", 5, 100)
        self.assertFalse(result["ok"])
        self.assertIn("starts with '-'", result["error"])
        self.assertFalse(marker.exists())

    def test_double_separator_right_before_prompt(self):
        with tempdir() as tmp:
            arglog = tmp / "args.log"
            make_exec(tmp, "opencode",
                      f"printf '%s\\n' \"$@\" > {shq(str(arglog))}; "
                      f"printf '%s\\n' {shq(event('text', 'ok'))}")
            with patched_path(str(tmp)):
                result = opencode.ask("hello", None, 5, 100)
            self.assertTrue(result["ok"])
            args = arglog.read_text().splitlines()
            self.assertEqual(args[-2], "--")
            self.assertEqual(args[-1], "hello")

    def test_agent_flag_pair_present(self):
        with tempdir() as tmp:
            arglog = tmp / "args.log"
            make_exec(tmp, "opencode",
                      f"printf '%s\\n' \"$@\" > {shq(str(arglog))}; "
                      f"printf '%s\\n' {shq(event('text', 'ok'))}")
            with patched_path(str(tmp)):
                result = opencode.ask("hello", None, 5, 100)
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
                result = opencode.ask("hello", None, 5, 100)
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
                result = opencode.ask("hello", None, 5, 100)
        self.assertFalse(result["ok"])
        self.assertEqual(result["text"], "")
        self.assertIn("not in effect", result["error"])

    def test_no_fallback_message_succeeds(self):
        with tempdir() as tmp:
            make_exec(tmp, "opencode", f"printf '%s\\n' {shq(event('text', 'ok'))}")
            with patched_path(str(tmp)):
                result = opencode.ask("hello", None, 5, 100)
        self.assertTrue(result["ok"])
        self.assertEqual(result["text"], "ok")


class BaseRunTest(unittest.TestCase):
    def test_run_returns_readable_error_on_missing_executable(self):
        result = base.run(["/nonexistent/bin/cli-xyz", "foo"], 5)
        self.assertFalse(result["ok"])
        self.assertIn("failed to run", result["error"])

    def test_truncate_marks_truncated(self):
        text, truncated = base.truncate("abcde", 3)
        self.assertTrue(truncated)
        self.assertEqual(text, "abc")
        text, truncated = base.truncate("abc", 5)
        self.assertFalse(truncated)
        self.assertEqual(text, "abc")

    def test_run_always_closes_stdin(self):
        with mock.patch("adapters.base.subprocess.run") as mocked:
            mocked.return_value = SimpleNamespace(returncode=0, stdout="", stderr="")
            result = base.run(["fake-cli"], 5)
        self.assertTrue(result["ok"])
        self.assertIs(mocked.call_args.kwargs["stdin"], subprocess.DEVNULL)

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


def log_args_body(out_log: str, payload: str) -> str:
    return (
        f"printf '%s\\n' \"$@\" > {shq(out_log)}\n"
        f"printf '%s\\n' {shq(payload)}"
    )


class ClaudeAskTest(unittest.TestCase):
    def test_success_extracts_result(self):
        with tempdir() as tmp:
            payload = fixture("claude_success.json")
            make_exec(tmp, "claude", f"printf '%s\\n' {shq(payload)}")
            with patched_path(str(tmp)):
                result = claude.ask("hello", None, 5, 100)
        self.assertTrue(result["ok"])
        self.assertEqual(result["text"], json.loads(fixture("claude_success.json"))["result"])
        self.assertFalse(result["truncated"])
        self.assertIsNone(result["error"])

    def test_is_error_reports_readable_error(self):
        with tempdir() as tmp:
            payload = fixture("claude_error.json")
            make_exec(tmp, "claude", f"printf '%s\\n' {shq(payload)}")
            with patched_path(str(tmp)):
                result = claude.ask("hello", None, 5, 100)
        self.assertFalse(result["ok"])
        self.assertIn("is_error", result["error"])
        self.assertEqual(result["text"], "")

    def test_long_text_truncated(self):
        long_text = "x" * 500
        payload = json.dumps({"is_error": False, "result": long_text})
        with tempdir() as tmp:
            make_exec(tmp, "claude", f"printf '%s\\n' {shq(payload)}")
            with patched_path(str(tmp)):
                result = claude.ask("hello", None, 5, 100)
        self.assertTrue(result["ok"])
        self.assertTrue(result["truncated"])
        self.assertEqual(result["text"], "x" * 100)

    def test_invalid_json_is_failure(self):
        with tempdir() as tmp:
            make_exec(tmp, "claude", "printf '%s\\n' 'not json'")
            with patched_path(str(tmp)):
                result = claude.ask("hello", None, 5, 100)
        self.assertFalse(result["ok"])
        self.assertIn("invalid JSON", result["error"])
        self.assertEqual(result["text"], "")

    def test_hung_subprocess_times_out(self):
        with tempdir() as tmp:
            make_exec(tmp, "claude", "exec /bin/sleep 60")
            with patched_path(str(tmp)):
                result = claude.ask("hello", None, 0.3, 100)
        self.assertFalse(result["ok"])
        self.assertIn("timed out", result["error"])
        self.assertEqual(result["text"], "")

    def test_nonzero_exit_is_readable(self):
        with tempdir() as tmp:
            make_exec(tmp, "claude", "printf '%s\\n' hi; exit 3")
            with patched_path(str(tmp)):
                result = claude.ask("hello", None, 5, 100)
        self.assertFalse(result["ok"])
        self.assertIn("command exited with code 3", result["error"])
        self.assertEqual(result["text"], "")
        self.assertNotIn("stderr", result)

    def test_oversized_prompt_never_spawns_subprocess(self):
        with tempdir() as tmp:
            marker = tmp / "spawned"
            make_exec(tmp, "claude", f"touch {shq(str(marker))}")
            prompt = "x" * (base.MAX_ARG_CHARS + 1)
            with patched_path(str(tmp)):
                result = claude.ask(prompt, None, 5, 100)
        self.assertFalse(result["ok"])
        self.assertIn("prompt too long", result["error"])
        self.assertFalse(marker.exists())

    def test_model_flag_presence(self):
        payload = json.dumps({"is_error": False, "result": "ok"})
        with tempdir() as tmp:
            none_log = tmp / "none.log"
            model_log = tmp / "model.log"
            make_exec(tmp, "claude", log_args_body(str(none_log), payload))
            with patched_path(str(tmp)):
                none_result = claude.ask("hello", None, 5, 100)
            make_exec(tmp, "claude", log_args_body(str(model_log), payload))
            with patched_path(str(tmp)):
                model_result = claude.ask("hello", "claude-opus-5", 5, 100)
            self.assertTrue(none_result["ok"])
            self.assertTrue(model_result["ok"])
            none_args = none_log.read_text().splitlines()
            model_args = model_log.read_text().splitlines()
            self.assertNotIn("--model", none_args)
            self.assertIn("--model", model_args)
            self.assertIn("claude-opus-5", model_args)

    def test_readonly_flags_present(self):
        payload = json.dumps({"is_error": False, "result": "ok"})
        with tempdir() as tmp:
            arglog = tmp / "args.log"
            make_exec(tmp, "claude", log_args_body(str(arglog), payload))
            with patched_path(str(tmp)):
                result = claude.ask("hello", None, 5, 100)
            self.assertTrue(result["ok"])
            args = arglog.read_text().splitlines()
            tools_i = args.index("--tools")
            self.assertEqual(args[tools_i + 1], "")

    def test_dash_prompt_injection_rejected(self):
        with tempdir() as tmp:
            marker = tmp / "spawned"
            make_exec(tmp, "claude", f"touch {shq(str(marker))}")
            with patched_path(str(tmp)):
                result = claude.ask("--dangerously-bypass-approvals-and-sandbox",
                                    None, 5, 100)
        self.assertFalse(result["ok"])
        self.assertIn("starts with '-'", result["error"])
        self.assertFalse(marker.exists())

    def test_dash_model_rejected(self):
        with tempdir() as tmp:
            marker = tmp / "spawned"
            make_exec(tmp, "claude", f"touch {shq(str(marker))}")
            with patched_path(str(tmp)):
                result = claude.ask("hello", "-model-thing", 5, 100)
        self.assertFalse(result["ok"])
        self.assertIn("starts with '-'", result["error"])
        self.assertFalse(marker.exists())

    def test_double_separator_right_before_prompt(self):
        payload = json.dumps({"is_error": False, "result": "x"})
        with tempdir() as tmp:
            arglog = tmp / "args.log"
            make_exec(tmp, "claude", log_args_body(str(arglog), payload))
            with patched_path(str(tmp)):
                result = claude.ask("hello", None, 5, 100)
            self.assertTrue(result["ok"])
            args = arglog.read_text().splitlines()
            self.assertEqual(args[-2], "--")
            self.assertEqual(args[-1], "hello")


class CodexAskTest(unittest.TestCase):
    CODX_LAST = "我是基於 GPT-5 的 Codex 模型。"

    def test_success_reads_output_file(self):
        with tempdir() as tmp:
            body = (
                "prev=''\n"
                "for a in \"$@\"; do\n"
                f"  [ \"$prev\" = '--output-last-message' ] && printf '%s' "
                f"{shq(self.CODX_LAST)} > \"$a\"\n"
                "  prev=\"$a\"\n"
                "done\n"
            )
            make_exec(tmp, "codex", body)
            with patched_path(str(tmp)):
                result = codex.ask("hello", None, 5, 100)
        self.assertTrue(result["ok"])
        self.assertEqual(result["text"], self.CODX_LAST)
        self.assertFalse(result["truncated"])
        self.assertIsNone(result["error"])

    def test_output_file_never_written_is_failure(self):
        with tempdir() as tmp:
            make_exec(tmp, "codex", "true")
            with patched_path(str(tmp)):
                result = codex.ask("hello", None, 5, 100)
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
                result = codex.ask("hello", None, 5, 100)
        self.assertFalse(result["ok"])
        self.assertIn("empty", result["error"])
        self.assertEqual(result["text"], "")

    def test_long_text_truncated(self):
        long_text = "x" * 500
        with tempdir() as tmp:
            body = (
                "prev=''\n"
                "for a in \"$@\"; do\n"
                f"  [ \"$prev\" = '--output-last-message' ] && printf '%s' "
                f"{shq(long_text)} > \"$a\"\n"
                "  prev=\"$a\"\n"
                "done\n"
            )
            make_exec(tmp, "codex", body)
            with patched_path(str(tmp)):
                result = codex.ask("hello", None, 5, 100)
        self.assertTrue(result["ok"])
        self.assertTrue(result["truncated"])
        self.assertEqual(result["text"], "x" * 100)

    def test_hung_subprocess_times_out(self):
        with tempdir() as tmp:
            make_exec(tmp, "codex", "exec /bin/sleep 60")
            with patched_path(str(tmp)):
                result = codex.ask("hello", None, 0.3, 100)
        self.assertFalse(result["ok"])
        self.assertIn("timed out", result["error"])
        self.assertEqual(result["text"], "")

    def test_nonzero_exit_is_readable(self):
        with tempdir() as tmp:
            make_exec(tmp, "codex", "exit 3")
            with patched_path(str(tmp)):
                result = codex.ask("hello", None, 5, 100)
        self.assertFalse(result["ok"])
        self.assertIn("command exited with code 3", result["error"])
        self.assertEqual(result["text"], "")
        self.assertNotIn("stderr", result)

    def test_oversized_prompt_never_spawns_subprocess(self):
        with tempdir() as tmp:
            marker = tmp / "spawned"
            make_exec(tmp, "codex", f"touch {shq(str(marker))}")
            prompt = "x" * (base.MAX_ARG_CHARS + 1)
            with patched_path(str(tmp)):
                result = codex.ask(prompt, None, 5, 100)
        self.assertFalse(result["ok"])
        self.assertIn("prompt too long", result["error"])
        self.assertFalse(marker.exists())

    def test_model_flag_presence(self):
        with tempdir() as tmp:
            none_log = tmp / "none.log"
            model_log = tmp / "model.log"
            body = (
                f"printf '%s\\n' \"$@\" > {shq(str(none_log))}\n"
                "prev=''\n"
                "for a in \"$@\"; do\n"
                f"  [ \"$prev\" = '--output-last-message' ] && printf '%s' "
                f"{shq(self.CODX_LAST)} > \"$a\"\n"
                "  prev=\"$a\"\n"
                "done\n"
            )
            make_exec(tmp, "codex", body)
            with patched_path(str(tmp)):
                none_result = codex.ask("hello", None, 5, 100)
            body = (
                f"printf '%s\\n' \"$@\" > {shq(str(model_log))}\n"
                "prev=''\n"
                "for a in \"$@\"; do\n"
                f"  [ \"$prev\" = '--output-last-message' ] && printf '%s' "
                f"{shq(self.CODX_LAST)} > \"$a\"\n"
                "  prev=\"$a\"\n"
                "done\n"
            )
            make_exec(tmp, "codex", body)
            with patched_path(str(tmp)):
                model_result = codex.ask("hello", "gpt-5-codex", 5, 100)
            self.assertTrue(none_result["ok"])
            self.assertTrue(model_result["ok"])
            none_args = none_log.read_text().splitlines()
            model_args = model_log.read_text().splitlines()
            self.assertNotIn("-m", none_args)
            self.assertIn("-m", model_args)
            self.assertIn("gpt-5-codex", model_args)

    def test_readonly_flags_present(self):
        with tempdir() as tmp:
            arglog = tmp / "args.log"
            body = (
                f"printf '%s\\n' \"$@\" > {shq(str(arglog))}\n"
                "prev=''\n"
                "for a in \"$@\"; do\n"
                f"  [ \"$prev\" = '--output-last-message' ] && printf '%s' "
                f"{shq(self.CODX_LAST)} > \"$a\"\n"
                "  prev=\"$a\"\n"
                "done\n"
            )
            make_exec(tmp, "codex", body)
            with patched_path(str(tmp)):
                result = codex.ask("hello", None, 5, 100)
            self.assertTrue(result["ok"])
            args = arglog.read_text().splitlines()
            sandbox_i = args.index("--sandbox")
            self.assertEqual(args[sandbox_i + 1], "read-only")

    def test_dash_prompt_injection_rejected(self):
        with tempdir() as tmp:
            marker = tmp / "spawned"
            make_exec(tmp, "codex", f"touch {shq(str(marker))}")
            with patched_path(str(tmp)):
                result = codex.ask("--dangerously-bypass-approvals-and-sandbox",
                                   None, 5, 100)
        self.assertFalse(result["ok"])
        self.assertIn("starts with '-'", result["error"])
        self.assertFalse(marker.exists())

    def test_dash_model_rejected(self):
        with tempdir() as tmp:
            marker = tmp / "spawned"
            make_exec(tmp, "codex", f"touch {shq(str(marker))}")
            with patched_path(str(tmp)):
                result = codex.ask("hello", "-model-thing", 5, 100)
        self.assertFalse(result["ok"])
        self.assertIn("starts with '-'", result["error"])
        self.assertFalse(marker.exists())

    def test_double_separator_right_before_prompt(self):
        with tempdir() as tmp:
            arglog = tmp / "args.log"
            body = (
                f"printf '%s\\n' \"$@\" > {shq(str(arglog))}\n"
                "prev=''\n"
                "for a in \"$@\"; do\n"
                f"  [ \"$prev\" = '--output-last-message' ] && printf '%s' "
                f"{shq(self.CODX_LAST)} > \"$a\"\n"
                "  prev=\"$a\"\n"
                "done\n"
            )
            make_exec(tmp, "codex", body)
            with patched_path(str(tmp)):
                result = codex.ask("hello", None, 5, 100)
            self.assertTrue(result["ok"])
            args = arglog.read_text().splitlines()
            self.assertEqual(args[-2], "--")
            self.assertEqual(args[-1], "hello")


class GeminiAskTest(unittest.TestCase):
    def test_success_extracts_response(self):
        with tempdir() as tmp:
            payload = fixture("gemini_success.json")
            make_exec(tmp, "gemini", f"printf '%s\\n' {shq(payload)}")
            with patched_path(str(tmp)):
                result = gemini.ask("hello", None, 5, 100)
        self.assertTrue(result["ok"])
        self.assertEqual(result["text"], json.loads(fixture("gemini_success.json"))["response"])
        self.assertFalse(result["truncated"])
        self.assertIsNone(result["error"])

    def test_long_text_truncated(self):
        long_text = "x" * 500
        payload = json.dumps({"response": long_text})
        with tempdir() as tmp:
            make_exec(tmp, "gemini", f"printf '%s\\n' {shq(payload)}")
            with patched_path(str(tmp)):
                result = gemini.ask("hello", None, 5, 100)
        self.assertTrue(result["ok"])
        self.assertTrue(result["truncated"])
        self.assertEqual(result["text"], "x" * 100)

    def test_invalid_json_is_failure(self):
        with tempdir() as tmp:
            make_exec(tmp, "gemini", "printf '%s\\n' 'not json'")
            with patched_path(str(tmp)):
                result = gemini.ask("hello", None, 5, 100)
        self.assertFalse(result["ok"])
        self.assertIn("invalid JSON", result["error"])
        self.assertEqual(result["text"], "")

    def test_hung_subprocess_times_out(self):
        with tempdir() as tmp:
            make_exec(tmp, "gemini", "exec /bin/sleep 60")
            with patched_path(str(tmp)):
                result = gemini.ask("hello", None, 0.3, 100)
        self.assertFalse(result["ok"])
        self.assertIn("timed out", result["error"])
        self.assertEqual(result["text"], "")

    def test_nonzero_exit_is_readable(self):
        with tempdir() as tmp:
            make_exec(tmp, "gemini", "printf '%s\\n' hi; exit 3")
            with patched_path(str(tmp)):
                result = gemini.ask("hello", None, 5, 100)
        self.assertFalse(result["ok"])
        self.assertIn("command exited with code 3", result["error"])
        self.assertEqual(result["text"], "")
        self.assertNotIn("stderr", result)

    def test_oversized_prompt_never_spawns_subprocess(self):
        with tempdir() as tmp:
            marker = tmp / "spawned"
            make_exec(tmp, "gemini", f"touch {shq(str(marker))}")
            prompt = "x" * (base.MAX_ARG_CHARS + 1)
            with patched_path(str(tmp)):
                result = gemini.ask(prompt, None, 5, 100)
        self.assertFalse(result["ok"])
        self.assertIn("prompt too long", result["error"])
        self.assertFalse(marker.exists())

    def test_model_flag_presence(self):
        payload = json.dumps({"response": "ok"})
        with tempdir() as tmp:
            none_log = tmp / "none.log"
            model_log = tmp / "model.log"
            make_exec(tmp, "gemini", log_args_body(str(none_log), payload))
            with patched_path(str(tmp)):
                none_result = gemini.ask("hello", None, 5, 100)
            make_exec(tmp, "gemini", log_args_body(str(model_log), payload))
            with patched_path(str(tmp)):
                model_result = gemini.ask("hello", "gemini-2.5-flash", 5, 100)
            self.assertTrue(none_result["ok"])
            self.assertTrue(model_result["ok"])
            none_args = none_log.read_text().splitlines()
            model_args = model_log.read_text().splitlines()
            self.assertNotIn("-m", none_args)
            self.assertIn("-m", model_args)
            self.assertIn("gemini-2.5-flash", model_args)

    def test_readonly_flags_present(self):
        payload = json.dumps({"response": "ok"})
        with tempdir() as tmp:
            arglog = tmp / "args.log"
            make_exec(tmp, "gemini", log_args_body(str(arglog), payload))
            with patched_path(str(tmp)):
                result = gemini.ask("hello", None, 5, 100)
            self.assertTrue(result["ok"])
            args = arglog.read_text().splitlines()
            mode_i = args.index("--approval-mode")
            self.assertEqual(args[mode_i + 1], "plan")
            self.assertIn("--skip-trust", args)

    def test_dash_prompt_injection_rejected(self):
        with tempdir() as tmp:
            marker = tmp / "spawned"
            make_exec(tmp, "gemini", f"touch {shq(str(marker))}")
            with patched_path(str(tmp)):
                result = gemini.ask("--dangerously-bypass-approvals-and-sandbox",
                                    None, 5, 100)
        self.assertFalse(result["ok"])
        self.assertIn("starts with '-'", result["error"])
        self.assertFalse(marker.exists())

    def test_dash_model_rejected(self):
        with tempdir() as tmp:
            marker = tmp / "spawned"
            make_exec(tmp, "gemini", f"touch {shq(str(marker))}")
            with patched_path(str(tmp)):
                result = gemini.ask("hello", "-model-thing", 5, 100)
        self.assertFalse(result["ok"])
        self.assertIn("starts with '-'", result["error"])
        self.assertFalse(marker.exists())

    def test_double_separator_absent(self):
        payload = json.dumps({"response": "ok"})
        with tempdir() as tmp:
            arglog = tmp / "args.log"
            make_exec(tmp, "gemini", log_args_body(str(arglog), payload))
            with patched_path(str(tmp)):
                result = gemini.ask("hello", None, 5, 100)
            self.assertTrue(result["ok"])
            args = arglog.read_text().splitlines()
            self.assertNotIn("--", args)


if __name__ == "__main__":
    unittest.main()
