import os
import shutil
import tempfile

from .base import PROMPT_INDICATOR, check_arg_injection
from .base import detect as _detect
from .base import run as _run
from .base import truncate as _truncate

ID = "codex"
CMD = "codex"


def detect() -> dict:
    return _detect(CMD, ID)


def ask(prompt: str, model: str | None, timeout_s: int, max_chars: int) -> dict:
    path = shutil.which(CMD)
    if path is None:
        return {"ok": False, "text": "", "truncated": False,
                "error": "codex not found in PATH", "elapsed_s": 0.0,
                "model_used": None, "usage": None}

    injection = check_arg_injection(PROMPT_INDICATOR, model)
    if injection is not None:
        return injection

    with tempfile.TemporaryDirectory() as workdir:
        out_file = os.path.join(workdir, "reply.txt")
        argv = [path, "exec", "--sandbox", "read-only", "--skip-git-repo-check",
                "--output-last-message", out_file, "-C", workdir]
        if model is not None:
            argv += ["-m", model]
        argv += ["--", PROMPT_INDICATOR]
        result = _run(argv, timeout_s, stdin_text=prompt, cwd=workdir)

        raw = None
        if result["ok"]:
            if os.path.exists(out_file):
                with open(out_file, "r", encoding="utf-8") as f:
                    raw = f.read()

    stderr = result.get("stderr", "") or ""
    if not result["ok"]:
        result.pop("stderr", None)
        return result

    if raw is None:
        return {"ok": False, "text": "", "truncated": False,
                "error": "codex did not write output file",
                "elapsed_s": result["elapsed_s"],
                "model_used": None, "usage": None}

    if not raw.strip():
        return {"ok": False, "text": "", "truncated": False,
                "error": "codex output file is empty",
                "elapsed_s": result["elapsed_s"],
                "model_used": None, "usage": None}

    model_used, usage = _parse_metadata(stderr)
    text, truncated = _truncate(raw, max_chars)
    return {"ok": True, "text": text, "truncated": truncated,
            "error": None, "elapsed_s": result["elapsed_s"],
            "model_used": model_used, "usage": usage}


def _parse_metadata(stderr: str) -> tuple:
    """從 stderr 取實際模型與用量（SPEC.md §2.2 表格，2026-08-04 實測）。

    codex 只在 stderr 回報，且 stderr 會含本機路徑與提示回顯——因此這裡
    只挑固定的行萃取，絕不回傳整坨 stderr（紅線二）。
    model_used：`model: <名稱>`。usage：`tokens used` 那一行的**下一行**
    數字（含千分位逗號，如 `4,739`）。取不到任何值就回 None。
    """
    lines = (stderr or "").splitlines()
    model_used = None
    tokens_used = None
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("model: "):
            model_used = stripped[len("model: "):].strip()
        elif stripped == "tokens used":
            for nxt in lines[i + 1].split():
                cleaned = nxt.replace(",", "").strip()
                if cleaned.isdigit():
                    tokens_used = int(cleaned)
                    break
    usage = None
    if tokens_used is not None:
        usage = {"tokens_used": tokens_used}
    return model_used, usage
