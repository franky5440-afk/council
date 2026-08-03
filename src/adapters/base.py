import shutil
import subprocess
import time

FALLBACK_TIMEOUT_S = 10

# Linux 對單一 argv 字串有長度上限（MAX_ARG_STRLEN，典型 128 KiB）。
# 逐字稿隨輪次成長，送出前先檢查 prompt 長度，超過即回 ok=False。
MAX_ARG_CHARS = 100000


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
        stderr = (proc.stderr or "").strip()
        detail = ""
        if stderr:
            detail = ": " + stderr.splitlines()[0].strip()
        return {"id": cli_id, "installed": True, "path": path,
                "version": None,
                "error": f"command exited with code {proc.returncode}{detail}"}

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


def run(argv: list, timeout_s: int, max_chars: int) -> dict:
    """以子行程執行 argv，回傳 SPEC.md §4 的 ask() dict。

    負責與 CLI 無關的部分：以 list 形式 argv 呼叫（絕不經 shell）、
    逾時強制終止、量測 elapsed_s、非零退出回可讀錯誤。
    stdout 以原始內容原樣放進 text（可能包含 CLI 自己的格式，例如 JSON
    事件流），由各 adapter 解析萃取後再以 truncate() 套用 max_chars。
    """
    start = time.monotonic()
    try:
        proc = subprocess.run(argv, capture_output=True, text=True,
                              timeout=timeout_s)
    except subprocess.TimeoutExpired:
        return {"ok": False, "text": "", "truncated": False,
                "error": f"timed out after {timeout_s}s",
                "elapsed_s": _elapsed(start)}
    except OSError as exc:
        return {"ok": False, "text": "", "truncated": False,
                "error": f"failed to run: {exc}",
                "elapsed_s": _elapsed(start)}

    elapsed = _elapsed(start)
    if proc.returncode != 0:
        stderr = (proc.stderr or "").strip()
        detail = ""
        if stderr:
            detail = ": " + stderr.splitlines()[0].strip()
        return {"ok": False, "text": "", "truncated": False,
                "error": f"command exited with code {proc.returncode}{detail}",
                "elapsed_s": elapsed}

    return {"ok": True, "text": proc.stdout or "", "truncated": False,
            "error": None, "elapsed_s": elapsed}


def truncate(text: str, max_chars: int) -> tuple:
    """輸出超過 max_chars 時截斷並標記 truncated。

    回傳 (截斷後的文字, truncated: bool)。max_chars 限制的是「單次發言」
    （SPEC.md §5），必須在 adapter 萃取出發言文字後才套用。
    """
    if len(text) <= max_chars:
        return text, False
    return text[:max_chars], True
