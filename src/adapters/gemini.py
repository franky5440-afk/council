import json
import shutil
import tempfile

from .base import PROMPT_INDICATOR, check_arg_injection
from .base import detect as _detect
from .base import run as _run
from .base import truncate as _truncate

ID = "gemini"
CMD = "gemini"


def detect() -> dict:
    return _detect(CMD, ID)


def _model_and_usage(data: dict) -> tuple:
    """從 stdout JSON 取實際模型與用量（SPEC.md §2.2 表格，2026-08-04 實測）。

    model_used：stats.models 的鍵名（實際回答的模型）。取不到回 None。
    usage：stats.models.<鍵>.tokens 物件。取不到回 None。
    """
    stats = data.get("stats")
    if not isinstance(stats, dict):
        return None, None
    models = stats.get("models")
    if not isinstance(models, dict) or not models:
        return None, None
    name = next(iter(models))
    entry = models[name]
    if not isinstance(entry, dict):
        return name, None
    tokens = entry.get("tokens")
    if not isinstance(tokens, dict):
        return name, None
    return name, tokens


def ask(prompt: str, model: str | None, timeout_s: int, max_chars: int) -> dict:
    path = shutil.which(CMD)
    if path is None:
        return {"ok": False, "text": "", "truncated": False,
                "error": "gemini not found in PATH", "elapsed_s": 0.0,
                "model_used": None, "usage": None}

    injection = check_arg_injection(PROMPT_INDICATOR, model)
    if injection is not None:
        return injection

    with tempfile.TemporaryDirectory() as workdir:
        argv = [path, "-p", PROMPT_INDICATOR, "-o", "json",
                "--approval-mode", "plan", "--skip-trust"]
        if model is not None:
            argv += ["-m", model]
        result = _run(argv, timeout_s, stdin_text=prompt, cwd=workdir)

    if not result["ok"]:
        result.pop("stderr", None)
        return result

    try:
        data = json.loads(result["text"])
    except json.JSONDecodeError as exc:
        return {"ok": False, "text": "", "truncated": False,
                "error": f"gemini returned invalid JSON: {exc}",
                "elapsed_s": result["elapsed_s"],
                "model_used": None, "usage": None}

    if not isinstance(data, dict):
        return {"ok": False, "text": "", "truncated": False,
                "error": "gemini returned non-object JSON",
                "elapsed_s": result["elapsed_s"],
                "model_used": None, "usage": None}

    text = data.get("response")
    if not isinstance(text, str) or not text.strip():
        return {"ok": False, "text": "", "truncated": False,
                "error": "no assistant text found in gemini output",
                "elapsed_s": result["elapsed_s"],
                "model_used": None, "usage": None}

    model_used, usage = _model_and_usage(data)
    text, truncated = _truncate(text, max_chars)
    return {"ok": True, "text": text, "truncated": truncated,
            "error": None, "elapsed_s": result["elapsed_s"],
            "model_used": model_used, "usage": usage}
