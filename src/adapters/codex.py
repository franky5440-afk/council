import os
import shutil
import tempfile

from .base import MAX_ARG_CHARS, check_arg_injection
from .base import detect as _detect
from .base import run as _run
from .base import truncate as _truncate

ID = "codex"
CMD = "codex"


def detect() -> dict:
    return _detect(CMD, ID)


def ask(prompt: str, model: str | None, timeout_s: int, max_chars: int) -> dict:
    if len(prompt) > MAX_ARG_CHARS:
        return {"ok": False, "text": "", "truncated": False,
                "error": f"prompt too long ({len(prompt)} chars, "
                         f"max {MAX_ARG_CHARS})",
                "elapsed_s": 0.0}

    path = shutil.which(CMD)
    if path is None:
        return {"ok": False, "text": "", "truncated": False,
                "error": "codex not found in PATH", "elapsed_s": 0.0}

    injection = check_arg_injection(prompt, model)
    if injection is not None:
        return injection

    with tempfile.TemporaryDirectory() as workdir:
        out_file = os.path.join(workdir, "reply.txt")
        argv = [path, "exec", "--sandbox", "read-only", "--skip-git-repo-check",
                "--output-last-message", out_file, "-C", workdir]
        if model is not None:
            argv += ["-m", model]
        argv += ["--", prompt]
        result = _run(argv, timeout_s, cwd=workdir)

        raw = None
        if result["ok"]:
            if os.path.exists(out_file):
                with open(out_file, "r", encoding="utf-8") as f:
                    raw = f.read()

    if not result["ok"]:
        result.pop("stderr", None)
        return result

    if raw is None:
        return {"ok": False, "text": "", "truncated": False,
                "error": "codex did not write output file",
                "elapsed_s": result["elapsed_s"]}

    if not raw.strip():
        return {"ok": False, "text": "", "truncated": False,
                "error": "codex output file is empty",
                "elapsed_s": result["elapsed_s"]}

    text, truncated = _truncate(raw, max_chars)
    return {"ok": True, "text": text, "truncated": truncated,
            "error": None, "elapsed_s": result["elapsed_s"]}
