import shutil
import subprocess
import time

FALLBACK_TIMEOUT_S = 10

# Linux 對單一 argv 字串有長度上限（MAX_ARG_STRLEN，典型 128 KiB）。
# 逐字稿隨輪次成長，送出前先檢查 prompt 長度，超過即回 ok=False。
MAX_ARG_CHARS = 100000


def check_arg_injection(prompt: str, model: str | None) -> dict | None:
    """prompt 或 model 以 `-` 開頭時回 ok=False dict，否則回 None。

    以 `-` 開頭的字串會被 CLI 當成旗標解析（argument injection），
    攻擊者可藉此送出 `--dangerously-bypass-...` 這類解除沙箱的旗標，
    繞過 SPEC.md §4.2 的唯讀保證。四個 adapter 在啟動子行程前呼叫。
    model=None 時不檢查 model。
    """
    if prompt.startswith("-"):
        return {"ok": False, "text": "", "truncated": False,
                "error": "prompt starts with '-' and would be parsed as a CLI flag",
                "elapsed_s": 0.0}
    if model is not None and model.startswith("-"):
        return {"ok": False, "text": "", "truncated": False,
                "error": "model starts with '-' and would be parsed as a CLI flag",
                "elapsed_s": 0.0}
    return None


def detect(cmd: str, cli_id: str, timeout_s: int = FALLBACK_TIMEOUT_S) -> dict:
    """以 `<cmd> --version` 偵測 CLI 是否可用，回傳 SPEC.md §4 的 dict。

    只執行 --version，不發出任何會消耗額度的呼叫。
    """
    path = shutil.which(cmd)
    if path is None:
        return {"id": cli_id, "installed": False, "path": None,
                "version": None, "error": "not found in PATH"}

    try:
        proc = subprocess.run([path, "--version"], capture_output=True,
                              text=True, timeout=timeout_s)
    except subprocess.TimeoutExpired:
        return {"id": cli_id, "installed": True, "path": path,
                "version": None,
                "error": f"timed out after {timeout_s}s"}
    except OSError as exc:
        return {"id": cli_id, "installed": True, "path": path,
                "version": None, "error": f"failed to run: {exc}"}

    if proc.returncode != 0:
        detail = _pick_error_line(proc.stderr)
        error = f"command exited with code {proc.returncode}"
        if detail is not None:
            error += f": {detail}"
        return {"id": cli_id, "installed": True, "path": path,
                "version": None, "error": error}

    out = (proc.stdout or "").strip()
    if not out:
        return {"id": cli_id, "installed": True, "path": path,
                "version": None, "error": "no output from --version"}

    first_line = out.splitlines()[0].strip()
    if not first_line:
        return {"id": cli_id, "installed": True, "path": path,
                "version": None, "error": "no output from --version"}

    return {"id": cli_id, "installed": True, "path": path,
            "version": first_line, "error": None}


def _elapsed(start: float) -> float:
    return round(time.monotonic() - start, 3)


MAX_ERROR_CHARS = 300


def _pick_error_line(stderr: str) -> str | None:
    """從 stderr 挑出最可能是真正錯誤的一行，取不到回 None。

    規則（SPEC.md §4.1：回報可讀的錯誤，不要整坨 stderr）：
    1. 丟掉堆疊追蹤行（去開頭空白後以 `at ` 起始）
    2. 丟掉空白行
    3. 取剩下的最後一行——CLI 常在真正錯誤前先印無害警告
    4. 超過 MAX_ERROR_CHARS 截斷並以 … 結尾
    """
    candidates = []
    for line in (stderr or "").splitlines():
        stripped = line.lstrip()
        if not stripped:
            continue
        if stripped.startswith("at "):
            continue
        candidates.append(stripped)
    if not candidates:
        return None
    line = candidates[-1]
    if len(line) > MAX_ERROR_CHARS:
        line = line[:MAX_ERROR_CHARS] + "…"
    return line


def run(argv: list, timeout_s: int, cwd: str | None = None) -> dict:
    """以子行程執行 argv，回傳 SPEC.md §4 的 ask() dict。

    負責與 CLI 無關的部分：以 list 形式 argv 呼叫（絕不經 shell）、
    逾時強制終止、量測 elapsed_s、非零退出回可讀錯誤。
    stdout 以原始內容原樣放進 text（可能包含 CLI 自己的格式，例如 JSON
    事件流），由各 adapter 解析萃取後再以 truncate() 套用 max_chars。
    stderr 以原始內容原樣放進 stderr，供 adapter 檢查（例如 opencode 的
    fail-open 偵測）；此鍵只在 base.run() 與 adapter 之間流通。
    stdin 一律導向 /dev/null：四家 CLI 都會讀 stdin，不關掉會讓行程卡住。
    """
    start = time.monotonic()
    try:
        proc = subprocess.run(argv, capture_output=True, text=True,
                              timeout=timeout_s, stdin=subprocess.DEVNULL,
                              cwd=cwd)
    except subprocess.TimeoutExpired:
        return {"ok": False, "text": "", "truncated": False,
                "error": f"timed out after {timeout_s}s",
                "stderr": "", "elapsed_s": _elapsed(start)}
    except OSError as exc:
        return {"ok": False, "text": "", "truncated": False,
                "error": f"failed to run: {exc}",
                "stderr": "", "elapsed_s": _elapsed(start)}

    elapsed = _elapsed(start)
    if proc.returncode != 0:
        detail = _pick_error_line(proc.stderr)
        error = f"command exited with code {proc.returncode}"
        if detail is not None:
            error += f": {detail}"
        return {"ok": False, "text": "", "truncated": False,
                "error": error, "stderr": proc.stderr or "",
                "elapsed_s": elapsed}

    return {"ok": True, "text": proc.stdout or "", "truncated": False,
            "error": None, "stderr": proc.stderr or "",
            "elapsed_s": elapsed}


def truncate(text: str, max_chars: int) -> tuple:
    """輸出超過 max_chars 時截斷並標記 truncated。

    回傳 (截斷後的文字, truncated: bool)。max_chars 限制的是「單次發言」
    （SPEC.md §5），必須在 adapter 萃取出發言文字後才套用。
    """
    if len(text) <= max_chars:
        return text, False
    return text[:max_chars], True
