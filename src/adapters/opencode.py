import json
import shutil
import tempfile

from .base import MAX_ARG_CHARS, check_arg_injection
from .base import detect as _detect
from .base import run as _run
from .base import truncate as _truncate

ID = "opencode"
CMD = "opencode"


def detect() -> dict:
    return _detect(CMD, ID)


def _extract_text(stdout: str) -> str:
    """從 `--format json` 的事件流中萃取出模型的文字回覆。

    欄位形狀以 dispatch/sessions/*.jsonl 的真實樣本為準：模型的文字
    出現在 type == "text" 的事件，其 part.type == "text"、文字在 part.text。
    """
    texts = []
    for line in stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if event.get("type") != "text":
            continue
        part = event.get("part")
        if not isinstance(part, dict) or part.get("type") != "text":
            continue
        text = part.get("text")
        if isinstance(text, str) and text:
            texts.append(text)
    return "\n".join(texts)


def ask(prompt: str, model: str | None, timeout_s: int, max_chars: int) -> dict:
    if len(prompt) > MAX_ARG_CHARS:
        return {"ok": False, "text": "", "truncated": False,
                "error": f"prompt too long ({len(prompt)} chars, "
                         f"max {MAX_ARG_CHARS})",
                "elapsed_s": 0.0}

    path = shutil.which(CMD)
    if path is None:
        return {"ok": False, "text": "", "truncated": False,
                "error": "opencode not found in PATH", "elapsed_s": 0.0}

    injection = check_arg_injection(prompt, model)
    if injection is not None:
        return injection

    with tempfile.TemporaryDirectory() as workdir:
        argv = [path, "run", "--dir", workdir, "--format", "json"]
        if model is not None:
            argv += ["-m", model]
        argv += ["--", prompt]
        result = _run(argv, timeout_s)

    if not result["ok"]:
        return result

    text = _extract_text(result["text"])
    if not text.strip():
        return {"ok": False, "text": "", "truncated": False,
                "error": "no assistant text found in opencode event stream",
                "elapsed_s": result["elapsed_s"]}

    text, truncated = _truncate(text, max_chars)
    return {"ok": True, "text": text, "truncated": truncated,
            "error": None, "elapsed_s": result["elapsed_s"]}
