"""一輪的序列編排（SPEC.md §6）：誰在什麼時候發言、看得到什麼、回覆怎麼交回狀態機。

本模組不認識任何 CLI adapter；實際呼叫由呼叫端以 ask_fn 注入，這裡只負責編排與組 prompt。
"""

DEFAULT_MAX_CHARS = 8000  # SPEC.md §5 邊界 2
DEFAULT_TIMEOUT_S = 180   # SPEC.md §5 邊界 4

ADVISOR_INSTRUCTION = """【你的任務】
你是本次討論的顧問「{seat_id}」。請針對上面的原始問題提出你的看法。
若上面已經有其他顧問的發言，請一併回應他們的論點——同意哪裡、補充什麼、反對什麼。

回覆的最後一行必須是下面這個格式，前後不要有任何其他文字：
[立場: 同意] [補充: 無]

其中「立場」三選一：同意 / 保留 / 反對；「補充」二選一：有 / 無。
「補充: 無」代表你認為自己已經沒有新的論點可以加。"""


def _render_speech(record: dict) -> str:
    if record["ok"]:
        text = record["text"]
        if record["truncated"]:
            text += "\n（本則發言超過長度上限，已被截斷）"
        return text
    error = record["error"]
    if error:
        return f"（未回應：{error}）"
    return "（未回應）"


def build_prompt(discussion, seat_id: str) -> str:
    """組出要送給某位顧問的完整 prompt。純函式：不修改 discussion、不呼叫 ask_fn。"""
    blocks = []
    if discussion.context.strip():
        blocks.append(f"【專案脈絡】\n{discussion.context}")
    blocks.append(f"【原始問題】\n{discussion.question}")
    for round_index, round_records in enumerate(discussion.rounds, start=1):
        if not round_records:
            continue
        parts = [f"【第 {round_index} 輪】"]
        for record in round_records:
            parts.append(f"── {record['seat_id']} ──\n{_render_speech(record)}")
        blocks.append("\n\n".join(parts))
    blocks.append(ADVISOR_INSTRUCTION.format(seat_id=seat_id))
    return "\n\n".join(blocks)


def run_round(discussion, ask_fn, *, max_chars=DEFAULT_MAX_CHARS,
              timeout_s=DEFAULT_TIMEOUT_S) -> dict:
    """跑完整的一輪：所有顧問依序各發言一次，然後結束這一輪，回傳 discussion.status()。

    ask_fn(cli=..., prompt=..., model=..., timeout_s=..., max_chars=...) 必須回傳
    與 SPEC.md §4 相同的七鍵 dict；是必填參數，不提供即 TypeError，不會 fail-open。
    """
    discussion.begin_round()
    for seat in discussion.advisors:
        prompt = build_prompt(discussion, seat["seat_id"])
        try:
            reply = ask_fn(cli=seat["cli"], prompt=prompt, model=seat["model"],
                           timeout_s=timeout_s, max_chars=max_chars)
            result = {
                "ok": reply["ok"],
                "text": reply["text"],
                "truncated": reply["truncated"],
                "error": reply["error"],
                "elapsed_s": reply["elapsed_s"],
                "model_used": reply["model_used"],
                "usage": reply["usage"],
            }
        except Exception as exc:
            result = {
                "ok": False,
                "text": "",
                "truncated": False,
                "error": f"{type(exc).__name__}: {exc}",
                "elapsed_s": 0.0,
                "model_used": None,
                "usage": None,
            }
        discussion.record_speech(seat["seat_id"], result)
    discussion.end_round()
    return discussion.status()
