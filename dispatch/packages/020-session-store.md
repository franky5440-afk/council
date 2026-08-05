# 工作包 020：討論的存活層（web UI 的前置）

**動手前先整段讀完 `SPEC.md` §7.1（本包的規格，剛新增）**，另讀 §7、§5 邊界 1、§8。

命令列一次執行＝一輪，狀態隨行程結束消失，所以**第二輪目前做不到**。web UI 要多輪，
就得有一層讓同一個討論跨請求存活。本包只做那一層，**不做 HTTP、不做 SSE、不做 HTML**
（那是 021／022）。

✅ **本包是純新增：只新增兩個檔案，一個既有檔案都不改。** 沒有回歸風險，
既有 206 個測試必須原封不動全過。

---

## 檔案

| 檔案 | 動作 |
|---|---|
| `src/engine/sessions.py` | **新增**：`Session` 與 `SessionStore` |
| `tests/test_engine_sessions.py` | **新增**：本包的測試 |

⚠️ **不准修改任何既有檔案**——包含 `state.py`、`orchestrator.py`、`wiring.py`、
`cli.py`、`run.sh`、`SPEC.md`、既有測試檔。一行都不要動。

### 🔴 本包的結構性紅線：`sessions.py` 不准 import 本專案的任何東西

`sessions.py` 的模組層 import **只准有這三個標準函式庫**：

```python
import copy
import secrets
import threading
```

**不得** import `state`／`orchestrator`／`wiring`／`adapters`／`cli`，
也不得 import `subprocess`／`os`／`sys`／`json`／`time`／`http`／任何第三方套件。

⚠️ **這不是潔癖，是本包的驗收核心**：存活層若認識狀態機，它就會開始替狀態機做決定
（例如「幫忙判斷能不能開下一輪」），而那些判斷 `SPEC.md` §5 已經有唯一的家了。
它只保管一個**別人給它的物件**，只對那個物件呼叫 `status()`。
測試會用一個假的 stub 物件證明這件事——**測試檔同樣不准 import `state`**。

---

## 介面契約（照字面實作，不要擴充公開介面）

### 1. `Session`

```python
class Session:
    def __init__(self, session_id: str, discussion):
```

- `self.id = session_id`、`self.discussion = discussion`（**原物件，不要複製**）。
- 內部持有兩把 `threading.Lock`：一把是**執行權**，一把保護事件清單。
  ⚠️ **兩把要分開。** 事件的讀寫必須在輪次進行中也能發生（那正是即時進度的來源），
  拿執行權那把來保護事件，等於讓讀者被整輪擋住。
- 建立時立刻把 `discussion.status()` 存成初始快照。

#### 執行權（`SPEC.md` §7.1 的邊界 1 保護）

| 方法 | 行為 |
|---|---|
| `try_claim() -> bool` | **非阻塞**取得執行權。已被佔用⇒**立刻**回 `False`，**絕不等待** |
| `release() -> None` | 釋放執行權，並**順手刷新快照**（見下） |
| `is_busy` (property) | 目前是否被佔用 |

- 🔴 **`try_claim()` 絕對不可以阻塞。** 用 `Lock.acquire(blocking=False)`。
  寫成會等的版本，第二個分頁就要等完整整一輪（可能 180 秒 ×N 席）才被告知
  輪次早被開走——`SPEC.md` §7.1 明文禁止。
- `release()` 在**未持有執行權**時呼叫 ⇒ 丟 `RuntimeError`，訊息要看得懂。
  不要默默忽略：那代表呼叫端的 `try`／`finally` 寫錯了，安靜吞掉會變成
  「討論永遠卡在忙碌」這種極難查的狀態。
- ⚠️ 執行權**不重入**：同一個執行緒連續 `try_claim()` 兩次，第二次回 `False`。
  用 `Lock`，**不要用 `RLock`**。

#### 快照（讀者路徑）

| 方法 | 行為 |
|---|---|
| `snapshot` (property) | 回傳**最後一次刷新**的 `status()` 內容的**深拷貝** |
| `refresh() -> dict` | 重新呼叫 `discussion.status()` 更新快照，回傳新快照的深拷貝 |

- ⚠️ **快照不會自己更新。** 討論狀態變了但沒 `refresh()`／`release()` ⇒
  `snapshot` 仍是舊的。**這是刻意的**（§7.1）：輪次進行中直接讀狀態機會讀到
  半更新的用量統計，即時進度應該走事件流。有測試守這件事，不要「修好」它。
- 🔴 **`snapshot` 必須回深拷貝。** 回內部物件的話，任何一個讀者改到它，
  之後所有讀者都會看到被改過的內容——而這是使用者用來看自己燒了多少錢的數字。

#### 事件流（`SPEC.md` §7.1 的可重放）

| 方法 | 行為 |
|---|---|
| `append_event(kind: str, data) -> int` | 追加一個事件，回傳它的序號 |
| `events_since(cursor: int) -> list` | 回傳所有**序號大於 `cursor`** 的事件（深拷貝） |

- 序號從 **1** 開始、單調遞增、**不重複也不跳號**。
  序號的產生與追加必須在同一把鎖內完成——先算號碼再放進清單，中間被另一個執行緒
  插隊就會發出兩個相同的號碼，而客戶端正是靠它決定「我漏了哪些」。
- 每個事件是一個 dict：`{"seq": int, "kind": kind, "data": data}`，**恰好三鍵**。
- `events_since(0)` ⇒ 全部。`events_since(超過最大序號)` ⇒ 空 list（**不是例外**）。
- 🔴 **`>` 不是 `>=`。** 客戶端送來的是「我已經收到的最後一號」，
  用 `>=` 會把那一則重送一次，畫面上就會出現重複的發言。
- 回傳值必須是深拷貝（理由同快照）。
- **不設事件數量上限、不做清理。** 一場討論的事件量受 `max_rounds` × 席次數封頂
  （`SPEC.md` §5 邊界 3），沒有無限成長的路徑。不要加 ring buffer 或 TTL。

### 2. `SessionStore`

```python
class SessionStore:
    def __init__(self):
```

| 方法 | 行為 |
|---|---|
| `create(discussion) -> Session` | 產生不可猜的 id、建立 `Session`、存起來、回傳它 |
| `get(session_id) -> Session\|None` | 找不到回 **`None`**，不丟例外 |
| `list_ids() -> list` | 依**建立順序**回傳 id |
| `remove(session_id) -> bool` | 移除成功回 `True`，本來就不存在回 `False` |

- 🔴 **id 一律 `secrets.token_urlsafe(16)`。不得用流水號、不得用 `id()`、
  不得用計數器。** `SPEC.md` §7.1：id 會出現在 URL 裡，而本機任何程序都打得到
  這個伺服器——猜得到 id 就能替使用者開新一輪、花他的額度。有測試守這件事。
- 內部 dict 的所有讀寫都要在 store 自己的鎖內（`ThreadingHTTPServer` 是多執行緒的）。
  ⚠️ 這把鎖與 `Session` 的兩把**無關**，不要共用。
- **不設 session 數量上限、不做逾時清理。** 本機單人使用，加了只是多一組要維護的
  規則。要收掉討論就呼叫 `remove()`。

---

## 測試

⚠️ **新增檔案 `tests/test_engine_sessions.py`**，比照既有測試檔的開頭寫法
（把 `src` 加進 `sys.path`，然後 `from engine import sessions`）。

🔴 **測試檔不得 import `state`／`orchestrator`／`wiring`／`adapters`／`cli`／
`subprocess`／`unittest.mock`。** 一律自己寫一個 stub 當討論：

```python
class FakeDiscussion:
    """只有 status() 的假討論——證明 sessions.py 不依賴真的狀態機。"""
    def __init__(self):
        self.calls = 0
        self.state = {"phase": "ready", "usage": {"calls": 0, "by_seat": {}}}
    def status(self):
        self.calls += 1
        return copy.deepcopy(self.state)
```

（測試檔可以 import `copy`、`threading`、`unittest`、`sys`、`pathlib`。）

**`SessionStore`**

1. `create()` 回傳的 `Session`，其 `.discussion` **就是傳進去的那個物件**（`assertIs`）。
2. 連續 `create()` 三次，三個 id **各不相同**，且每個 id 長度 **≥ 20**、
   `id.isdigit()` 為 `False`（守「不得用流水號」）。
3. `get()` 回傳的是**同一個 `Session` 物件**（`assertIs`）；不存在的 id 回 `None`。
4. `remove()` 成功回 `True`、之後 `get()` 回 `None`；再 `remove()` 同一個回 `False`。
5. `list_ids()` 的順序**等於建立順序**。

**執行權**

6. 第一次 `try_claim()` 為 `True`；未 release 時第二次為 `False`；
   `release()` 之後再 `try_claim()` 又是 `True`。
7. `is_busy` 在 claim 前後正確反映。
8. 未持有執行權時 `release()` 丟 `RuntimeError`。
9. **多執行緒搶執行權：** 開 8 條執行緒、以 `threading.Barrier` 對齊後同時
   `try_claim()`，**恰好 1 條成功**。重複跑 20 次都一樣。
   ⚠️ 這條測的是 §7.1 那條紅線（兩個分頁同時按「再一輪」會花兩倍的錢）。
10. **`try_claim()` 不會阻塞**：主執行緒持有執行權，另一條執行緒呼叫 `try_claim()`
    後**必須立刻回來**。用 `threading.Event`＋`event.wait(timeout=2)` 驗證它在
    兩秒內就回傳了（正確實作是微秒級；設 2 秒是給老機器留餘裕）。
    ⚠️ **不要用 sleep 來「等它應該好了」**，要斷言它自己回來了。

**快照**

11. 剛 `create()` 出來的 `Session`，其 `snapshot` 內容等於 `discussion.status()`。
12. 改掉 `FakeDiscussion` 的內部狀態、**不呼叫 refresh** ⇒ `snapshot` **仍是舊的**。
13. `refresh()` 之後 `snapshot` 變成新的。
14. `try_claim()` → 改狀態 → `release()` ⇒ `snapshot` 是新的（release 會刷新）。
15. **深拷貝**：把 `snapshot` 回傳的 dict 就地改掉（含巢狀的 `usage.by_seat`），
    再讀一次 `snapshot`，內容**不受影響**。

**事件流**

16. 第一個 `append_event` 回傳 `1`，接著是 `2`、`3`。
17. 事件 dict 的鍵**恰好**是 `{"seq", "kind", "data"}`。
18. `events_since(0)` 回全部；`events_since(2)` 只回 seq 3 以後的
    （**不含 seq 2 本身**）；`events_since(999)` 回**空 list**。
19. **深拷貝**：改動 `events_since()` 回傳的內容，不影響下一次讀到的結果。
20. **多執行緒追加**：8 條執行緒各 `append_event` 25 次，最後
    `events_since(0)` 有 **200 筆**，且 `seq` 的集合**恰好是 1..200**（不重不漏）。
21. **事件不被執行權擋住**：主執行緒持有執行權時，另一條執行緒仍能成功
    `append_event()` 與 `events_since()`（證明兩把鎖是分開的）。

---

## 驗收條件（貼真實輸出，不要只描述）

1. `python3 -m unittest discover tests` **全過**，貼出最後三行。
   **既有 206 個測試一個都不得減少或變紅**（本包不改任何既有檔案，理應如此）。
   ⚠️ 011 那次回報「交付完成」但實跑是 `FAILED (errors=1)`。**請自己實際跑完再回報。**
2. 貼出 `python3 -m unittest discover tests -v 2>&1 | grep -c 'ok$'` 之類的數字，
   說明新增了幾個測試。
3. 貼出 `head -20 src/engine/sessions.py`，證明模組層 import 只有那三個標準函式庫。
4. **突變驗證五項**，每項：改壞 → 貼失敗輸出（含翻紅的測試名）→ 還原 →
   最後貼還原後全過的結果。
   - (a) `try_claim()` 改成永遠回 `True`（不真的取鎖）⇒ 測試 6／9 翻紅。
   - (b) `release()` 拿掉刷新快照 ⇒ 測試 14 翻紅。
   - (c) `snapshot` 改成回內部物件（不深拷貝）⇒ 測試 15 翻紅。
   - (d) `events_since` 的 `>` 改成 `>=` ⇒ 測試 18 翻紅。
   - (e) `create()` 的 id 改成流水號字串（`"1"`、`"2"`…）⇒ 測試 2 翻紅。
   - 🔴 **突變只准動 `src/engine/sessions.py`**，不准動測試檔、不准動測試裡的樣本值。
   - 🔴 **備份請放 `dispatch/tmp/020-backup/`，不要放 `/tmp`。**
     （`AGENTS.md` 已有這條規定，019 那輪的備份跑到 `/tmp/opencode/` 去了。）
   - 還原後請 `cmp` 確認與備份**位元組相同**，並貼出結果。
5. 貼出 `git status --short`，證明**只有兩個新檔案**（`?? src/engine/sessions.py`、
   `?? tests/test_engine_sessions.py`），**沒有任何 ` M`**。
   ⚠️ `dispatch/tmp/` 已被 `.gitignore` 排除，備份不會出現在這裡，這是正常的。
6. 貼出隔離檢查：
   - `grep -nE '^(import|from)' src/engine/sessions.py` ——應**只有**那三行 stdlib。
   - `grep -nE 'state|orchestrator|wiring|adapters|cli|subprocess' src/engine/sessions.py` ——**應為空**。
   - `grep -nE 'from engine import (state|orchestrator|wiring)|adapters|import cli|subprocess|mock' tests/test_engine_sessions.py` ——**應為空**。
   - `grep -n 'RLock' src/engine/sessions.py` ——**應為空**（執行權不重入）。

---

## 不要做的事

- ⚠️ **不要寫任何 HTTP／SSE／HTML／JS。** 那是 021／022。本包交付後沒有任何東西
  會用到 `sessions.py`，**這是刻意的**（016 也是這樣，接線留給下一包）。
- ⚠️ **不要 import 狀態機、不要替它做判斷。** 存活層不判斷「能不能開下一輪」、
  不判斷「收斂了沒」、不碰用量計算——那些 `SPEC.md` §5 已經有唯一的家。
- ⚠️ **不要落檔。** 不寫 JSON、不寫 pickle、不寫任何持久化。`SPEC.md` §7.1 明講
  這一層只在記憶體，§8 明列存檔延後。
- **不要加逾時清理、TTL、session 數量上限、事件數量上限、ring buffer。**
  本機單人使用，這些是沒被要求的彈性。
- **不要加 logging。** 不要 `print`、不要 `logging`。
- **不要用 `RLock`、不要用 `queue`、不要用 `asyncio`、不要用 `dataclasses`／`enum`。**
  既有程式碼一律純 dict ＋ `threading.Lock`，照做。
- 不要碰版控（`git add` / `commit` / `push` 一律不執行）。
- 不要新增環境變數、設定檔、第三方套件。
