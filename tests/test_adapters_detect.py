import os
import stat
import sys
import unittest
from contextlib import contextmanager
from pathlib import Path

SRC_DIR = Path(__file__).resolve().parent.parent / "src"
sys.path.insert(0, str(SRC_DIR))

from adapters import ADAPTERS, detect_all  # noqa: E402
from adapters import base  # noqa: E402


class FakeAdapter:
    def __init__(self, cli_id):
        self._id = cli_id

    def detect(self):
        return {"id": self._id, "installed": True, "path": "/bin/fake",
                "version": "1.0.0", "error": None}

    def ask(self, prompt, timeout_s, max_chars):
        raise NotImplementedError


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


class DetectNotInstalledTest(unittest.TestCase):
    def test_missing_executable(self):
        with tempdir() as tmp:
            with patched_path(str(tmp)):
                result = base.detect("no-such-cli-xyz", "fake")
        self.assertFalse(result["installed"])
        self.assertIsNone(result["path"])
        self.assertIsNone(result["version"])
        self.assertTrue(result["error"])


class DetectInstalledTest(unittest.TestCase):
    def test_version_first_line_stripped(self):
        with tempdir() as tmp:
            make_exec(tmp, "fakecli", "printf '  v1.2.3  \\nsecond line\\n'")
            with patched_path(str(tmp)):
                result = base.detect("fakecli", "fake")
        self.assertTrue(result["installed"])
        self.assertEqual(result["version"], "v1.2.3")
        self.assertIsNone(result["error"])
        self.assertEqual(result["id"], "fake")

    def test_nonzero_exit(self):
        with tempdir() as tmp:
            make_exec(tmp, "fakecli", "exit 3")
            with patched_path(str(tmp)):
                result = base.detect("fakecli", "fake")
        self.assertTrue(result["installed"])
        self.assertIsNone(result["version"])
        self.assertTrue(result["error"])

    def test_empty_output(self):
        with tempdir() as tmp:
            make_exec(tmp, "fakecli", "true")
            with patched_path(str(tmp)):
                result = base.detect("fakecli", "fake")
        self.assertTrue(result["installed"])
        self.assertIsNone(result["version"])
        self.assertTrue(result["error"])

    def test_timeout_kills_hung_process(self):
        with tempdir() as tmp:
            make_exec(tmp, "fakecli", "exec /bin/sleep 60")
            with patched_path(str(tmp)):
                result = base.detect("fakecli", "fake", timeout_s=0.3)
        self.assertTrue(result["installed"])
        self.assertIsNone(result["version"])
        self.assertTrue(result["error"])
        self.assertIn("timed out", result["error"])


class RegistryTest(unittest.TestCase):
    def setUp(self):
        self._original = dict(ADAPTERS)
        ADAPTERS.clear()
        for key in ["alpha", "beta", "gamma"]:
            ADAPTERS[key] = FakeAdapter(key)

    def tearDown(self):
        ADAPTERS.clear()
        ADAPTERS.update(self._original)

    def test_detect_all_returns_one_result_per_adapter(self):
        results = detect_all()
        self.assertEqual(len(results), len(ADAPTERS))
        self.assertGreater(len(ADAPTERS), 0)

    def test_detect_all_ids_match_adapter_keys_in_order(self):
        results = detect_all()
        self.assertEqual([r["id"] for r in results], list(ADAPTERS.keys()))


class AskNotImplementedTest(unittest.TestCase):
    def test_ask_raises_not_implemented(self):
        for cli_id in ADAPTERS:
            with self.assertRaises(NotImplementedError):
                ADAPTERS[cli_id].ask("prompt", 10, 100)


def tempdir():
    import tempfile

    @contextmanager
    def _inner():
        with tempfile.TemporaryDirectory() as d:
            yield Path(d)

    return _inner()


if __name__ == "__main__":
    unittest.main()