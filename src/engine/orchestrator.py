"""一輪的序列編排（SPEC.md §6）：誰在什麼時候發言、看得到什麼、回覆怎麼交回狀態機。

本模組不認識任何 CLI adapter；實際呼叫由呼叫端以 ask_fn 注入，這裡只負責編排與組 prompt。
本模組唯一的 state import 是 BoundaryError：run_arbitration 必須在花錢之前自己丟出邊界錯誤。
"""

from engine.state import BoundaryError

DEFAULT_MAX_CHARS = 8000  # SPEC.md §5 邊界 2
DEFAULT_TIMEOUT_S = 180   # SPEC.md §5 邊界 4

ADVISOR_INSTRUCTION = """【你的任務】
你是本次討論的顧問「{seat_id}」。請針對上面的原始問題提出你的看法。
若上面已經有其他顧問的發言，請一併回應他們的論點——同意哪裡、補充什麼、反對什麼。

回覆的最後一行必須是下面這個格式，前後不要有任何其他文字：
[立場: 同意] [補充: 無]

其中「立場」三選一：同意 / 保留 / 反對；「補充」二選一：有 / 無。
「補充: 無」代表你認為自己已經沒有新的論點可以加。"""

ARBITER_INSTRUCTION = """【你的任務】
你是本次討論的仲裁者「{seat_id}」。你沒有參與上面的任何一輪發言，
現在第一次讀到這份逐字稿。請針對最上面的原始問題輸出一份整合結論，包含：

1. 各方的共識是什麼。
2. 分歧在哪裡，以及分歧的真正原因是什麼（是前提不同，還是結論不同）。
3. 你的最終建議，以及採納它的前提與風險。

請直接下判斷，不要只複述各方說過的話。若逐字稿裡的資訊不足以下判斷，
明說缺什麼，不要用推測填補。"""


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


def _prefix_blocks(discussion) -> list:
    """脈絡（若非空白）＋原始問題＋各輪逐字稿，依序回傳區塊 list。"""
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
    return blocks


def build_prompt(discussion, seat_id: str) -> str:
    """組出要送給某位顧問的完整 prompt。純函式：不修改 discussion、不呼叫 ask_fn。"""
    blocks = _prefix_blocks(discussion)
    blocks.append(ADVISOR_INSTRUCTION.format(seat_id=seat_id))
    return "\n\n".join(blocks)


def build_arbiter_prompt(discussion) -> str:
    """組出要送給仲裁者的完整 prompt。純函式：不修改 discussion、不呼叫 ask_fn。"""
    blocks = _prefix_blocks(discussion)
    blocks.append(ARBITER_INSTRUCTION.format(seat_id=discussion.arbiter["seat_id"]))
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


def run_arbitration(discussion, ask_fn, *, max_chars=DEFAULT_MAX_CHARS,
                    timeout_s=DEFAULT_TIMEOUT_S) -> dict:
    """執行一次仲裁者呼叫（SPEC.md §6.1）。

    ask_fn 契約與 run_round() 完全相同，必填、沒有預設值。
    第一件事是檢查 can_arbitrate()，在任何 ask_fn 呼叫之前——先花錢再發現
    不該花，錢就燒掉了。仲裁跑完就結束，不會自行開下一輪（§5 邊界 1）。
    """
    if not discussion.can_arbitrate():
        raise BoundaryError("目前不具備仲裁條件：需要不在進行中的一輪、"
                            "至少完成一輪、且逐字稿中有成功的發言")
    seat = discussion.arbiter
    prompt = build_arbiter_prompt(discussion)
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
    return discussion.record_arbitration(result)
