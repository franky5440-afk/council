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
    只挑固定的行萃取，絕不回傳整坨 stderr。
    model_used：只認 header 區塊——第一與第二條分隔線之間的第一筆
    `model: <名稱>`。分隔線 = 去除頭尾空白後只由 `-` 組成且長度 ≥ 3 的行。
    找不到分隔線、header 不完整（缺第二條分隔線）、或區塊內沒有 `model:` 行，
    一律回 None。**取不到就回 None 是刻意設計**：stderr 會原樣回顯 stdin
    （逐字稿，屬不可信輸入），若退而求其次去區塊外找，prompt 內容就能覆寫
    真值、消音 SPEC.md §2.2(3) 的警示；回 None 由 UI 顯示為未經確認，
    遠比回一個可被偽造的值好。
    usage：`tokens used` 那一行的**下一行**數字（含千分位逗號，如 `4,739`）。
    掃全文、後者勝——注入的假值在 stdin 回顯內、真值印在更後面 ⇒ 真值勝出。
    `tokens used` 若是最後一行（逾時截斷）則回 None，不拋例外。
    """
    lines = (stderr or "").splitlines()

    def is_separator(line: str) -> bool:
        stripped = line.strip()
        return len(stripped) >= 3 and all(c == "-" for c in stripped)

    model_used = None
    seps = [i for i, line in enumerate(lines) if is_separator(line)]
    if len(seps) >= 2:
        for line in lines[seps[0] + 1:seps[1]]:
            stripped = line.strip()
            if stripped.startswith("model: "):
                model_used = stripped[len("model: "):].strip()
                break

    tokens_used = None
    for i, line in enumerate(lines):
        if line.strip() == "tokens used" and i + 1 < len(lines):
            for nxt in lines[i + 1].split():
                cleaned = nxt.replace(",", "").strip()
                if cleaned.isdigit():
                    tokens_used = int(cleaned)
                    break
    usage = None
    if tokens_used is not None:
        usage = {"tokens_used": tokens_used}
    return model_used, usage
