"""討論狀態機與停止邊界（SPEC.md §5）。純狀態，不認識 CLI、不啟動子行程。"""

import copy
import re

DEFAULT_MAX_ROUNDS = 5
ADVISOR = "advisor"
ARBITER = "arbiter"

PHASE_READY = "ready"
PHASE_IN_ROUND = "in_round"
PHASE_AWAITING_USER = "awaiting_user"


class BoundaryError(Exception):
    """狀態機拒絕了一個會越過停止邊界的操作。"""


def _is_num(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def parse_marker(text: str) -> dict:
    """依 SPEC.md §5 邊界 5 解析最後一個非空白行的立場標記。"""
    last_line = ""
    for line in text.splitlines():
        if line.strip():
            last_line = line.strip()
    if not last_line:
        return {"stance": None, "more": True, "violation": True}
    pattern = (
        r"^\[立場\s*[:：]\s*(同意|保留|反對)\s*\]"
        r"\s*\[補充\s*[:：]\s*(有|無)\s*\]$"
    )
    m = re.match(pattern, last_line)
    if m is None:
        return {"stance": None, "more": True, "violation": True}
    return {
        "stance": m.group(1),
        "more": m.group(2) == "有",
        "violation": False,
    }


def _deep_copy_if_dict(value):
    return copy.deepcopy(value) if isinstance(value, dict) else value


def merge_usage(total: dict, usage) -> dict:
    """把一次呼叫的 usage 併進累計，回傳新 dict，不就地修改任何輸入。"""
    out = copy.deepcopy(total)
    if usage is None:
        return out
    for key, value in usage.items():
        if key not in out:
            out[key] = _deep_copy_if_dict(value)
            continue
        existing = out[key]
        if isinstance(existing, dict) and isinstance(value, dict):
            out[key] = merge_usage(existing, value)
        elif _is_num(existing) and _is_num(value):
            out[key] = existing + value
    return out


class Discussion:
    def __init__(self, question: str, seats: list,
                 max_rounds: int = DEFAULT_MAX_ROUNDS, context: str = ""):
        if not isinstance(question, str) or not question.strip():
            raise ValueError("question 不得為空")
        if not isinstance(seats, list) or not (2 <= len(seats) <= 4):
            raise ValueError("seats 長度須為 2～4")
        seen_ids = set()
        arbiter_count = 0
        advisor_count = 0
        copies = []
        for seat in seats:
            if not isinstance(seat, dict):
                raise ValueError("每個席次必須是 dict")
            required = ("seat_id", "cli", "model", "role")
            if set(seat.keys()) != set(required):
                raise ValueError("席次必須恰好含 seat_id/cli/model/role 四鍵")
            seat_id = seat["seat_id"]
            cli = seat["cli"]
            model = seat["model"]
            role = seat["role"]
            if not isinstance(seat_id, str) or not seat_id:
                raise ValueError("seat_id 須為非空字串")
            if not isinstance(cli, str) or not cli:
                raise ValueError("cli 須為非空字串")
            if model is not None and (not isinstance(model, str) or not model):
                raise ValueError("model 須為 None 或非空字串")
            if role not in (ADVISOR, ARBITER):
                raise ValueError("role 須為 advisor 或 arbiter")
            if seat_id in seen_ids:
                raise ValueError(f"seat_id 重複: {seat_id}")
            seen_ids.add(seat_id)
            if role == ARBITER:
                arbiter_count += 1
            else:
                advisor_count += 1
            copies.append({
                "seat_id": seat_id,
                "cli": cli,
                "model": model,
                "role": role,
            })
        if arbiter_count != 1:
            raise ValueError("必須恰好一個 arbiter")
        if advisor_count < 1:
            raise ValueError("必須至少一個 advisor")
        if isinstance(max_rounds, bool) or not isinstance(max_rounds, int) or max_rounds < 1:
            raise ValueError("max_rounds 須為 >= 1 的 int")
        if not isinstance(context, str):
            raise ValueError("context 須為 str")
        self.question = question
        self.max_rounds = max_rounds
        self.context = context
        self.seats = copies
        self.advisors = [s for s in copies if s["role"] == ADVISOR]
        self.arbiter = next(s for s in copies if s["role"] == ARBITER)
        self.arbitrations = []
        self.phase = PHASE_READY
        self.rounds = []
        self._usage_by_seat = {}
        self._calls_total = 0
        self._calls_by_seat = {}

    def begin_round(self) -> int:
        if self.phase != PHASE_READY:
            raise BoundaryError("必須在使用者確認後才能開始新的一輪")
        self.rounds.append([])
        self.phase = PHASE_IN_ROUND
        return len(self.rounds) - 1

    def _resolve_advisor(self, seat_id: str) -> dict:
        for seat in self.advisors:
            if seat["seat_id"] == seat_id:
                return seat
        raise ValueError(f"未知或非顧問席次: {seat_id}")

    def record_speech(self, seat_id: str, result: dict) -> dict:
        if self.phase != PHASE_IN_ROUND:
            raise BoundaryError("現在不在進行中的一輪")
        self._resolve_advisor(seat_id)
        current = self.rounds[-1]
        if any(rec["seat_id"] == seat_id for rec in current):
            raise ValueError(f"{seat_id} 本輪已發言")
        ok = bool(result["ok"])
        if ok:
            marker = parse_marker(result["text"])
            stance = marker["stance"]
            more = marker["more"]
            violation = marker["violation"]
        else:
            stance = None
            more = True
            violation = False
        record = {
            "seat_id": seat_id,
            "ok": ok,
            "text": result["text"],
            "truncated": result["truncated"],
            "error": result["error"],
            "elapsed_s": result["elapsed_s"],
            "model_used": result["model_used"],
            "usage": copy.deepcopy(result["usage"]),
            "stance": stance,
            "more": more,
            "violation": violation,
        }
        current.append(record)
        self._calls_total += 1
        self._calls_by_seat[seat_id] = self._calls_by_seat.get(seat_id, 0) + 1
        prev = self._usage_by_seat.get(seat_id, {})
        self._usage_by_seat[seat_id] = merge_usage(prev, result["usage"])
        return record

    def end_round(self) -> None:
        if self.phase != PHASE_IN_ROUND:
            raise BoundaryError("現在不在進行中的一輪")
        spoke = {rec["seat_id"] for rec in self.rounds[-1]}
        missing = [s["seat_id"] for s in self.advisors if s["seat_id"] not in spoke]
        if missing:
            raise ValueError(f"尚有顧問未發言: {', '.join(missing)}")
        self.phase = PHASE_AWAITING_USER

    def request_next_round(self, confirm_over_cap: bool = False) -> None:
        if self.phase != PHASE_AWAITING_USER:
            raise BoundaryError("使用者尚未要求下一輪")
        if self._rounds_completed() >= self.max_rounds and not confirm_over_cap:
            raise BoundaryError("已達輪數上限，需明確確認才能再開一輪")
        self.phase = PHASE_READY

    def can_arbitrate(self) -> bool:
        """SPEC.md §6.1 的三條前提全部成立才可仲裁。純查詢：不改狀態、不丟例外。"""
        if self.phase == PHASE_IN_ROUND:
            return False
        if self._rounds_completed() < 1:
            return False
        return any(rec["ok"] for r in self.rounds for rec in r)

    def record_arbitration(self, result: dict) -> dict:
        """記錄一次仲裁者呼叫（SPEC.md §6.1）。

        仲裁者不是第四位顧問：不進 rounds、不解析立場標記、不影響收斂或格式違規。
        """
        if self.phase == PHASE_IN_ROUND:
            raise BoundaryError("目前正在進行中的一輪，無法仲裁")
        if self._rounds_completed() < 1:
            raise BoundaryError("尚未完成任何一輪，無法仲裁")
        if not any(rec["ok"] for r in self.rounds for rec in r):
            raise BoundaryError("逐字稿中沒有任何成功的發言，無法仲裁")
        seat_id = self.arbiter["seat_id"]
        record = {
            "seat_id": seat_id,
            "ok": bool(result["ok"]),
            "text": result["text"],
            "truncated": result["truncated"],
            "error": result["error"],
            "elapsed_s": result["elapsed_s"],
            "model_used": result["model_used"],
            "usage": copy.deepcopy(result["usage"]),
        }
        self.arbitrations.append(record)
        self._calls_total += 1
        self._calls_by_seat[seat_id] = self._calls_by_seat.get(seat_id, 0) + 1
        prev = self._usage_by_seat.get(seat_id, {})
        self._usage_by_seat[seat_id] = merge_usage(prev, result["usage"])
        return record

    def _rounds_completed(self) -> int:
        n = len(self.rounds)
        if n and self.phase == PHASE_IN_ROUND:
            return n - 1
        return n

    def converged(self) -> bool:
        if self.phase != PHASE_AWAITING_USER:
            return False
        return all(rec["more"] is False for rec in self.rounds[-1])

    def status(self) -> dict:
        rounds_completed = self._rounds_completed()
        return {
            "phase": self.phase,
            "rounds_completed": rounds_completed,
            "max_rounds": self.max_rounds,
            "at_cap": rounds_completed >= self.max_rounds,
            "can_start_round": self.phase == PHASE_READY,
            "converged": self.converged(),
            "format_violations": sum(
                rec["violation"]
                for r in self.rounds
                for rec in r
            ),
            "usage": {
                "calls": self._calls_total,
                "by_seat": {
                    seat_id: {
                        "calls": self._calls_by_seat[seat_id],
                        "usage": copy.deepcopy(self._usage_by_seat[seat_id]),
                    }
                    for seat_id in self._calls_by_seat
                },
            },
        }
