import json
import os
import shutil
import tempfile

from .base import MAX_ARG_CHARS, check_arg_injection
from .base import detect as _detect
from .base import run as _run
from .base import truncate as _truncate

ID = "opencode"
CMD = "opencode"

AGENT_NAME = "advisor"
AGENT_DEF = """\
---
description: Read-only council advisor.
mode: primary
permission:
  bash: deny
  edit: deny
  webfetch: deny
  task: deny
  todowrite: deny
  websearch: deny
  lsp: deny
  skill: deny
---

You are a council advisor. Answer the question directly.
"""

# `--agent` 指向不存在的 agent 時 opencode 不報錯，只印這行 stderr
# 後退回完全可寫的預設 agent，exit code 仍為 0。
FALLBACK_MSG = "Falling back to default agent"


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
        agents_dir = os.path.join(workdir, ".opencode", "agents")
        os.makedirs(agents_dir)
        with open(os.path.join(agents_dir, AGENT_NAME + ".md"), "w",
                  encoding="utf-8") as f:
            f.write(AGENT_DEF)

        argv = [path, "run", "--dir", workdir, "--format", "json",
                "--agent", AGENT_NAME]
        if model is not None:
            argv += ["-m", model]
        argv += ["--", prompt]
        result = _run(argv, timeout_s)

    if not result["ok"]:
        result.pop("stderr", None)
        return result

    if FALLBACK_MSG in result["stderr"]:
        return {"ok": False, "text": "", "truncated": False,
                "error": "opencode read-only agent not in effect "
                         "(fell back to default agent); result discarded",
                "elapsed_s": result["elapsed_s"]}

    text = _extract_text(result["text"])
    if not text.strip():
        return {"ok": False, "text": "", "truncated": False,
                "error": "no assistant text found in opencode event stream",
                "elapsed_s": result["elapsed_s"]}

    text, truncated = _truncate(text, max_chars)
    return {"ok": True, "text": text, "truncated": truncated,
            "error": None, "elapsed_s": result["elapsed_s"]}
