from . import claude, codex, gemini, opencode

ADAPTERS = {
    "claude": claude,
    "codex": codex,
    "gemini": gemini,
    "opencode": opencode,
}


def detect_all() -> list:
    """依 ADAPTERS 順序回傳每個 detect() 的結果。"""
    results = []
    for cli_id in ADAPTERS:
        results.append(ADAPTERS[cli_id].detect())
    return results
