"""討論存活層（SPEC.md §7.1）：讓同一個討論跨請求存活。

只保管別人給的 discussion 物件並對它呼叫 status()，不做任何狀態機判斷。
只在記憶體，不落檔；伺服器一停，討論就沒了。
"""

import copy
import secrets
import threading


class Session:
    """一份存活中的討論：執行權、快照與可重放的事件流。"""

    def __init__(self, session_id: str, discussion):
        self.id = session_id
        self.discussion = discussion
        self._exec_lock = threading.Lock()
        self._events_lock = threading.Lock()
        self._claimed = False
        self._events = []
        self._next_seq = 0
        self._snapshot = copy.deepcopy(discussion.status())

    def try_claim(self) -> bool:
        """非阻塞取得執行權；已被佔用立刻回 False，絕不等待。"""
        if not self._exec_lock.acquire(blocking=False):
            return False
        self._claimed = True
        return True

    # threading.Lock 沒有擁有者概念：任何執行緒都能放掉別人取得的執行權。
    # 本層刻意不做擁有者追蹤，代價是呼叫端必須自己 try / finally 配對。
    def release(self) -> None:
        """釋放執行權。刷新快照必須發生在鎖還握著的時候。"""
        if not self._exec_lock.locked():
            raise RuntimeError("release() 在未持有執行權時被呼叫")
        self._snapshot = copy.deepcopy(self.discussion.status())
        self._claimed = False
        self._exec_lock.release()

    @property
    def is_busy(self) -> bool:
        return self._claimed

    @property
    def snapshot(self) -> dict:
        return copy.deepcopy(self._snapshot)

    def refresh(self) -> dict:
        """重新呼叫 discussion.status() 更新快照，回傳新快照的深拷貝。"""
        self._snapshot = copy.deepcopy(self.discussion.status())
        return copy.deepcopy(self._snapshot)

    def append_event(self, kind: str, data) -> int:
        with self._events_lock:
            self._next_seq += 1
            self._events.append(
                {"seq": self._next_seq, "kind": kind, "data": data})
            return self._next_seq

    def events_since(self, cursor: int) -> list:
        with self._events_lock:
            return copy.deepcopy(
                [e for e in self._events if e["seq"] > cursor])


class SessionStore:
    """Session 的容器；多執行緒存取，id 一律不可猜。"""

    def __init__(self):
        self._sessions = {}
        self._order = []
        self._lock = threading.Lock()

    def create(self, discussion) -> Session:
        session_id = secrets.token_urlsafe(16)
        session = Session(session_id, discussion)
        with self._lock:
            self._sessions[session_id] = session
            self._order.append(session_id)
        return session

    def get(self, session_id: str):
        with self._lock:
            return self._sessions.get(session_id)

    def list_ids(self) -> list:
        with self._lock:
            return list(self._order)

    def remove(self, session_id: str) -> bool:
        with self._lock:
            if session_id not in self._sessions:
                return False
            del self._sessions[session_id]
            self._order.remove(session_id)
            return True
