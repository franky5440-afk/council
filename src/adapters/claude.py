import json
import shutil
import tempfile

from .base import PROMPT_INDICATOR, check_arg_injection
from .base import detect as _detect
from .base import run as _run
from .base import truncate as _truncate

ID = "claude"
CMD = "claude"


def detect() -> dict:
    return _detect(CMD, ID)


def _model_and_usage(data: dict) -> tuple:
    """從 stdout JSON 取實際模型與用量（SPEC.md §2.2 表格，2026-08-04 實測）。

    model_used：modelUsage 的鍵名；鍵名含版次時取其 canonicalModel
    （例如 `claude-opus-5[1m]` → `claude-opus-5`）。多鍵時取成本最高者
    ——那是實際回答的模型。取不到回 None。
    usage：頂層 usage 物件，另併入頂層 total_cost_usd。取不到回 None。
    """
    usage = None
    mu = data.get("modelUsage")
    if isinstance(mu, dict) and mu:
        costed = sorted(mu.items(), key=lambda kv: _as_float(kv[1].get("costUSD")) if isinstance(kv[1], dict) else 0.0,
                        reverse=True)
        name = costed[0][0]
        entry = costed[0][1]
        if isinstance(entry, dict) and isinstance(entry.get("canonicalModel"), str):
            name = entry["canonicalModel"]
    else:
        name = None

    top_usage = data.get("usage")
    if isinstance(top_usage, dict):
        usage = dict(top_usage)
        if isinstance(data.get("total_cost_usd"), (int, float)):
            usage["total_cost_usd"] = data["total_cost_usd"]
    return name, usage


def _as_float(value) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def ask(prompt: str, model: str | None, timeout_s: int, max_chars: int) -> dict:
    path = shutil.which(CMD)
    if path is None:
        return {"ok": False, "text": "", "truncated": False,
                "error": "claude not found in PATH", "elapsed_s": 0.0,
                "model_used": None, "usage": None}

    injection = check_arg_injection(PROMPT_INDICATOR, model)
    if injection is not None:
        return injection

    with tempfile.TemporaryDirectory() as workdir:
        argv = [path, "-p", PROMPT_INDICATOR, "--output-format", "json",
                "--tools", ""]
        if model is not None:
            argv += ["--model", model]
        result = _run(argv, timeout_s, stdin_text=prompt, cwd=workdir)

    if not result["ok"]:
        result.pop("stderr", None)
        return result

    stdout = result["text"]
    try:
        data = json.loads(stdout)
    except json.JSONDecodeError as exc:
        return {"ok": False, "text": "", "truncated": False,
                "error": f"claude returned invalid JSON: {exc}",
                "elapsed_s": result["elapsed_s"],
                "model_used": None, "usage": None}

    if not isinstance(data, dict):
        return {"ok": False, "text": "", "truncated": False,
                "error": "claude returned non-object JSON",
                "elapsed_s": result["elapsed_s"],
                "model_used": None, "usage": None}

    if data.get("is_error"):
        detail = ""
        errors = data.get("errors")
        if isinstance(errors, list) and errors:
            detail = ": " + str(errors[0])
        return {"ok": False, "text": "", "truncated": False,
                "error": "claude reported is_error=True" + detail,
                "elapsed_s": result["elapsed_s"],
                "model_used": None, "usage": None}

    text = data.get("result")
    if not isinstance(text, str) or not text.strip():
        return {"ok": False, "text": "", "truncated": False,
                "error": "no assistant text found in claude output",
                "elapsed_s": result["elapsed_s"],
                "model_used": None, "usage": None}

    model_used, usage = _model_and_usage(data)
    text, truncated = _truncate(text, max_chars)
    return {"ok": True, "text": text, "truncated": truncated,
            "error": None, "elapsed_s": result["elapsed_s"],
            "model_used": model_used, "usage": usage}
