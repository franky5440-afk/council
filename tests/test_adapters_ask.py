import json
import os
import stat
import sys
import unittest
from contextlib import contextmanager
from pathlib import Path

SRC_DIR = Path(__file__).resolve().parent.parent / "src"
sys.path.insert(0, str(SRC_DIR))

from adapters import opencode  # noqa: E402
from adapters import base  # noqa: E402


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
            self.assertEqual(args[5], "-m")
            self.assertEqual(args[6], "opencode/some-model")
            self.assertEqual(args[-1], "hello")


class BaseRunTest(unittest.TestCase):
    def test_run_returns_readable_error_on_missing_executable(self):
        result = base.run(["/nonexistent/bin/cli-xyz", "foo"], 5, 100)
        self.assertFalse(result["ok"])
        self.assertIn("failed to run", result["error"])

    def test_truncate_marks_truncated(self):
        text, truncated = base.truncate("abcde", 3)
        self.assertTrue(truncated)
        self.assertEqual(text, "abc")
        text, truncated = base.truncate("abc", 5)
        self.assertFalse(truncated)
        self.assertEqual(text, "abc")


if __name__ == "__main__":
    unittest.main()
