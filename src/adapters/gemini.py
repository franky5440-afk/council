import json
import shutil
import tempfile

from .base import MAX_ARG_CHARS, check_arg_injection
from .base import detect as _detect
from .base import run as _run
from .base import truncate as _truncate

ID = "gemini"
CMD = "gemini"


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
                "error": "gemini not found in PATH", "elapsed_s": 0.0}

    injection = check_arg_injection(prompt, model)
    if injection is not None:
        return injection

    with tempfile.TemporaryDirectory() as workdir:
        argv = [path, "-p", prompt, "-o", "json",
                "--approval-mode", "plan", "--skip-trust"]
        if model is not None:
            argv += ["-m", model]
        result = _run(argv, timeout_s, cwd=workdir)

    if not result["ok"]:
        result.pop("stderr", None)
        return result

    try:
        data = json.loads(result["text"])
    except json.JSONDecodeError as exc:
        return {"ok": False, "text": "", "truncated": False,
                "error": f"gemini returned invalid JSON: {exc}",
                "elapsed_s": result["elapsed_s"]}

    if not isinstance(data, dict):
        return {"ok": False, "text": "", "truncated": False,
                "error": "gemini returned non-object JSON",
                "elapsed_s": result["elapsed_s"]}

    text = data.get("response")
    if not isinstance(text, str) or not text.strip():
        return {"ok": False, "text": "", "truncated": False,
                "error": "no assistant text found in gemini output",
                "elapsed_s": result["elapsed_s"]}

    text, truncated = _truncate(text, max_chars)
    return {"ok": True, "text": text, "truncated": truncated,
            "error": None, "elapsed_s": result["elapsed_s"]}
