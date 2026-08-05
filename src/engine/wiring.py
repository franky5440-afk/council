"""接線層（工作包 017）：把命令列的席次字串轉成 state.Discussion 吃的 dict，
並產生符合 orchestrator.run_round() 契約的 ask_fn。

本模組不認識任何 CLI：registry 一律由呼叫端注入（SPEC.md §4），
不在這裡 import 任何 adapter。
"""


def parse_seat_spec(spec: str, seat_id: str, role: str) -> dict:
    """把一個席次字串轉成 seat dict。只從左邊第一個 ':' 切一次。

    "claude" ⇒ {"seat_id": seat_id, "cli": "claude", "model": None, "role": role}
    "gemini:gemini-2.5-pro" ⇒ model 為 "gemini-2.5-pro"
    "opencode:provider/model:x" ⇒ model 為 "provider/model:x"（只切第一刀）
    """
    stripped = spec.strip()
    if not stripped:
        raise ValueError("席次規格為空白")
    parts = stripped.split(":", 1)
    if len(parts) == 1:
        cli, model = parts[0], None
    else:
        cli, model = parts
        if not cli:
            raise ValueError("席次規格缺少 CLI 名稱（『:』左邊為空）")
        if not model:
            raise ValueError("席次規格缺少模型名稱（『:』右邊為空）")
    return {"seat_id": seat_id, "cli": cli, "model": model, "role": role}


def format_context(files) -> str:
    """把 [(檔名, 內容), ...] 排成送進 prompt 的脈絡文字（SPEC.md §3.3）。

    純排版，不開檔、不碰檔案系統——讀檔是 cli.py 的事。
    空 list 回 ""；否則每檔一段，段與段之間以一個空行連接。
    """
    blocks = [f"【檔案：{name}】\n{content}" for name, content in files]
    return "\n\n".join(blocks)


def make_ask_fn(registry):
    """產生符合 orchestrator.run_round() 契約的 ask_fn。

    registry: {cli_id: 具有 .ask() 的物件}，必填，沒有預設值，不得 fallback。
    本層只做轉接：一律以關鍵字呼叫 adapter 的 ask()，原樣回傳。
    不 retry、不記 log、不計時——逾時截斷是 adapter 的事，失敗記錄是 orchestrator 的事。
    """
    def ask_fn(cli, prompt, model, timeout_s, max_chars) -> dict:
        if cli not in registry:
            available = ", ".join(sorted(registry))
            raise ValueError(f"未知的 CLI: {cli}（可用: {available}）")
        return registry[cli].ask(prompt=prompt, model=model,
                                 timeout_s=timeout_s, max_chars=max_chars)
    return ask_fn


def dry_run_ask_fn(cli, prompt, model, timeout_s, max_chars) -> dict:
    """不呼叫任何東西的假回覆，供未指定 --live 時使用。"""
    return {
        "ok": True,
        "text": f"【DRY RUN】{cli} 未被實際呼叫。收到 prompt {len(prompt)} 字元、"
                f"model={model}、timeout_s={timeout_s}、max_chars={max_chars}。\n"
                "[立場: 保留] [補充: 有]",
        "truncated": False,
        "error": None,
        "elapsed_s": 0.0,
        "model_used": None,
        "usage": None,
    }
