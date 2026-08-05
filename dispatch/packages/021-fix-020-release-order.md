# 工作包 021：修正 020 的 `release()` 順序（接續同一 session）

**這是 020 的修正包，範圍極小。** 020 的交付品質沒問題——五項突變我自己重做過全部翻紅、
隔離檢查全過、備份也照指示放在 `dispatch/tmp/020-backup/`。**問題出在我的契約寫錯了順序**，
你是照字面實作的。

---

## 問題（已可重現，不是推測）

`Session.release()` 目前是這個順序：

```python
self._exec_lock.release()          # ← 先放掉執行權
self._claimed = False
self._snapshot = copy.deepcopy(self.discussion.status())   # ← 才去讀討論
```

我用探針實測過：**在 `release()` 呼叫 `discussion.status()` 的那一刻，鎖已經放掉了，
而且別的執行緒此刻真的搶得到執行權**。實測輸出：

```
release() 內 status() 被呼叫時的觀察：
  [{'鎖仍被持有': False, '此刻別的執行緒能否搶到執行權': True}]
```

兩個後果，都打在 `SPEC.md` §7.1 這一層存在的理由上：

1. **快照可能是撕裂的。** A 放掉鎖之後才去讀 `status()`，此時 B 可能已經搶到執行權並
   開始跑下一輪。真的 `status()` 會走訪各席次的累計字典（`state.py` 的
   `_calls_by_seat`），**邊走訪邊被另一條執行緒新增鍵，會直接 `RuntimeError:
   dictionary changed size during iteration`**——而快照的整個存在目的就是避免讀到
   半更新的用量統計。
2. **`is_busy` 會說謊。** A 在 B 搶到之後才執行 `self._claimed = False`，
   於是 B 明明正在跑，`is_busy` 卻回 `False`。

⚠️ **這不是理論問題**：`ThreadingHTTPServer` 是多執行緒的，而使用者連點兩下
「再一輪」正好會製造這個時序。

---

## 檔案

| 檔案 | 動作 |
|---|---|
| `src/engine/sessions.py` | **增修**：只改 `release()`，並補 `refresh()` 的說明 |
| `tests/test_engine_sessions.py` | **增加**兩個測試，既有 21 個**一個都不准改** |

⚠️ **不准動任何其他檔案。** 不要「順手」改 `try_claim`、`append_event`、
`SessionStore`、或既有測試。既有 227 個測試必須全過。

---

## 介面契約

### 1. `release()` 改成這個順序

```python
def release(self) -> None:
    """釋放執行權。刷新快照必須發生在鎖還握著的時候。"""
    if not self._exec_lock.locked():
        raise RuntimeError("release() 在未持有執行權時被呼叫")
    self._snapshot = copy.deepcopy(self.discussion.status())
    self._claimed = False
    self._exec_lock.release()
```

- **順序是本包的全部重點**：檢查 → 刷新快照 → 清 `_claimed` → **最後才放鎖**。
- 未持有執行權時仍要丟 `RuntimeError`（既有測試守著），但改用
  `self._exec_lock.locked()` 判斷，**不要**再用 `try/except RuntimeError` 包
  `release()`——那個寫法必須先真的把鎖放掉才知道有沒有錯，順序就修不回來了。
- ⚠️ **不要改成 `RLock`**、不要引入新的鎖、不要動 `try_claim()`。

### 2. 在 `release()` 上方補一行註解，寫明本層不防的事

`threading.Lock` **沒有擁有者概念**：任何執行緒都能放掉別人取得的執行權。
本層刻意不做擁有者追蹤（會多一組要維護的狀態），代價是**呼叫端必須自己
`try` / `finally` 配對**。請用一行註解把這件事寫在程式碼裡，讓下一包（HTTP 伺服器）
的人看得到。**只寫註解，不要實作擁有者檢查。**

### 3. `refresh()` 補一句 docstring

寫明它**只該由持有執行權的人呼叫**——沒有執行權時呼叫它，讀到的可能是別人跑到一半的
狀態。**行為不變，只加 docstring。**

---

## 測試（新增兩個，放進既有檔案）

**22. `release()` 刷新快照時執行權必須還在手上。**

用一個探針討論：它的 `status()` 被呼叫時，回頭觀察 session 的公開狀態。

```python
class ProbeDiscussion:
    """status() 被呼叫的當下，回頭觀察 session 的公開狀態。"""

    def __init__(self):
        self.session = None
        self.busy_during_status = []
        self.stolen_during_status = []

    def status(self):
        if self.session is not None:
            self.busy_during_status.append(self.session.is_busy)
            self.stolen_during_status.append(self.session.try_claim())
        return {"phase": "ready", "usage": {"calls": 0, "by_seat": {}}}
```

測試流程：

1. `probe = ProbeDiscussion()`；`session = SessionStore().create(probe)`。
2. **建立之後**才 `probe.session = session`（避開 `__init__` 那次 `status()`）。
3. `session.try_claim()` ⇒ `True`。
4. `session.release()`。
5. 斷言 `probe.busy_during_status == [True]`
   （刷新快照的那一刻，執行權還在手上）。
6. 斷言 `probe.stolen_during_status == [False]`
   （那一刻**別人搶不到**執行權）。

⚠️ **只用公開介面**（`is_busy`／`try_claim`），不要去讀 `_exec_lock` 之類的私有屬性
——測試要守的是對外的保證，不是實作細節。

**23. 修正後 `release()` 仍然完成它該做的事。**

`try_claim()` → 改掉 `FakeDiscussion` 的狀態 → `release()` ⇒
`snapshot` 是新的、`is_busy` 為 `False`、且能再次 `try_claim()`。
（既有測試分別涵蓋了其中幾項，這條是把「修完之後整條路徑仍然通」綁成一個。）

---

## 驗收條件（貼真實輸出）

1. `python3 -m unittest discover tests` **全過**，貼出最後三行。
   既有 227 個一個都不得減少或變紅，新增後應為 **229**。
   ⚠️ 請自己實際跑完再回報。
2. 貼出 `git diff src/engine/sessions.py`，證明**只有 `release()` 與兩處說明文字**
   被改動，`try_claim`／`append_event`／`events_since`／`SessionStore` 一行未動。
3. **突變驗證一項**：把 `release()` 改回**原本的順序**（先 `release()` 再刷新快照）
   ⇒ **測試 22 必須翻紅**。貼出失敗輸出，還原後貼全過結果。
   - 🔴 只准動 `src/engine/sessions.py`，不准動測試。
   - 🔴 備份放 `dispatch/tmp/021-backup/`，**不要放 `/tmp`**。還原後 `cmp` 驗位元組相同。
4. 貼出 `git status --short`，證明只有 `src/engine/sessions.py` 與
   `tests/test_engine_sessions.py` 兩個檔案有變動（`sessions.py` 這時已是
   `?? ` 未追蹤或 ` M`，兩者皆可，重點是沒有別的檔案被碰）。

---

## 不要做的事

- **不要重寫 020 的其他部分。** 它是對的，我驗過了。
- **不要加擁有者追蹤、不要換 `RLock`、不要加新的鎖。**
- **不要寫 HTTP／SSE／HTML。** 那是下一包。
- 不要碰版控、不要新增檔案、不要新增第三方套件。
