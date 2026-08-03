import shutil
import subprocess

FALLBACK_TIMEOUT_S = 10


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
