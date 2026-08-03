# 工作包 014：討論狀態模型 ＋ 停止邊界 1／3／5／6

**動手前先整段讀完 `SPEC.md` §5**，另讀 §6（討論流程）與 §4 的 `ask()` 回傳結構。

本包新增 `src/engine/` 與 `tests/test_engine_state.py`，**不動任何既有檔案**。

⚠️ **本包不實作輪替編排**（誰在什麼時候發言、怎麼組 prompt、呼叫 `ask()`）——那是下一包。
本包做的是「讓那些邊界有東西可以掛」的狀態模型，以及四道純狀態的邊界。
邊界 2（`max_chars`）與邊界 4（`timeout_s`）已在 adapter 層做完，**不要重做、不要碰**。

---

## 檔案

- `src/engine/__init__.py`——**空檔**。不要在裡面 re-export 或放邏輯。
- `src/engine/state.py`——本包全部的實作。
- `tests/test_engine_state.py`——本包全部的測試。

測試的匯入方式沿用既有慣例（見 `tests/test_adapters_ask.py` 開頭）：把 `src/` 加進
`sys.path` 後 `from engine import state`。

⚠️ **`src/engine/state.py` 不得 import `subprocess`、`os`、`sys`，也不得 import `adapters`。**
它是純狀態機，不認識 CLI，也不認識子行程。這不只是分層潔癖——**結構上不可能呼叫到
真實 CLI，就不可能燒掉 Frank 的額度**。測試檔同樣不得 import 這幾個模組。

---

## 介面契約（請照字面實作，不要擴充公開介面）

### 模組層常數與例外

```python
DEFAULT_MAX_ROUNDS = 5          # SPEC.md §5 邊界 3
ADVISOR = "advisor"
ARBITER = "arbiter"

PHASE_READY = "ready"                    # 可以開新的一輪
PHASE_IN_ROUND = "in_round"              # 一輪進行中
PHASE_AWAITING_USER = "awaiting_user"    # 一輪已結束，等使用者（邊界 1）

class BoundaryError(Exception):
    """狀態機拒絕了一個會越過停止邊界的操作。"""
```

**`ValueError` 與 `BoundaryError` 的分工，不要混用**：
呼叫端把參數寫錯（不存在的席次、重複發言、席次設定不合法）用 `ValueError`；
參數都對、但**這個動作會越過某道停止邊界**用 `BoundaryError`。
UI 之後要靠這個區分決定「顯示錯誤」還是「顯示一顆需要使用者按的按鈕」。

### 1. `parse_marker(text: str) -> dict`（邊界 5）

依 `SPEC.md` §5 邊界 5 的「解析規則」實作，回傳：

```python
{"stance": "同意"|"保留"|"反對"|None, "more": bool, "violation": bool}
```

- 取 `text` 的**最後一個非空白行**，`strip()` 後必須**整行完全符合**：
  左右方括號為半形，冒號接受 `:` 或 `：`，冒號後與括號內允許任意空白。
  例：`[立場: 同意] [補充: 無]`、`[立場：保留] [補充：有]` 都算命中。
- 命中 ⇒ `stance` 為該值、`more = (補充 == "有")`、`violation = False`。
- **任何不命中的情形**（沒有這行、格式壞掉、標記出現在中間但最後一行是別的內容、
  `text` 是空字串或全空白）⇒ `{"stance": None, "more": True, "violation": True}`。
- ⚠️ **不要 fallback 去掃前面幾行找標記。** 那正是本規則要擋的東西
  （逐字稿裡有別人的標記）。保守回「補充: 有」永遠是安全的，猜錯立場不是。

### 2. `merge_usage(total: dict, usage: dict | None) -> dict`（邊界 6）

把一次呼叫的 `usage` 併進累計，**回傳新的 dict，不得就地修改 `total`**。

- `usage is None` ⇒ 回 `total` 的**深複製**。
- 逐鍵合併：
  - 兩邊都是數字 ⇒ 相加。
  - 兩邊都是 dict ⇒ 遞迴合併（`opencode` 的 `usage["tokens"]` 是巢狀 dict）。
  - 只有一邊有該鍵 ⇒ 直接帶入；**若值是 dict 必須深複製**，不得與輸入共用參考
    （共用會讓下一次累計偷偷改到呼叫端手上的 dict）。
  - 型別衝突（一邊數字一邊 dict）或值是字串／`None`／其他型別 ⇒ **忽略新值、保留舊值，
    不拋例外**。CLI 的輸出格式隨時會變，讓 UI 因為多了一個字串欄位就整個炸掉是錯的。
- ⚠️ **`bool` 不算數字。** `isinstance(True, int)` 在 Python 是 `True`，
  不特判會把旗標當數字加起來。
- ⚠️ **不做任何跨 CLI 的鍵名正規化。** `codex` 的 `tokens_used` 與 `claude` 的
  `input_tokens` 就是不同的東西，硬合會做出一個看起來很權威的假數字。
  `SPEC.md` §4 已明文「不要自行估算 token」，這裡是同一條。

### 3. `class Discussion`

```python
def __init__(self, question: str, seats: list, max_rounds: int = DEFAULT_MAX_ROUNDS)
```

`seats` 是 dict 的 list，每個席次：

```python
{"seat_id": str, "cli": str, "model": str | None, "role": ADVISOR | ARBITER}
```

建構時驗證，任一不符一律 `ValueError`（訊息要講清楚是哪一條）：

- `question` 去空白後不得為空。
- `seats` 長度為 **2～4**（`SPEC.md` §6）。
- 每個席次是 dict，且恰好含上面四個鍵；`seat_id`、`cli` 為非空字串；
  `model` 為 `None` 或非空字串；`role` 為 `ADVISOR` 或 `ARBITER`。
- `seat_id` 不得重複。
- **恰好一個 `ARBITER`**，且**至少一個 `ADVISOR`**（`SPEC.md` §6：仲裁者不列入輪替）。
- `max_rounds` 為 `>= 1` 的 `int`（`bool` 不算）。

⚠️ **不要驗證 `cli` 是不是四家之一**——那需要 import `adapters`，違反上面的隔離規定；
接線是引擎的事，不是狀態機的事。

建構後的屬性（**唯讀使用，不要提供 setter**）：

- `question`、`max_rounds`
- `seats`：原 list 的複本（每個席次也複製，不與呼叫端共用參考）
- `advisors`：`role == ADVISOR` 的席次，**維持傳入順序**（`SPEC.md` §6「固定順序」）
- `phase`：初始為 `PHASE_READY`。
  **第一輪不需要使用者再按一次**——使用者提問本身就是那個動作。
- `rounds`：`list[list[record]]`，初始 `[]`。**進行中的那一輪也在裡面**。

#### `begin_round(self) -> int`

`phase` 不是 `PHASE_READY` ⇒ `BoundaryError`。
否則附加一個空的新輪、`phase = PHASE_IN_ROUND`、回傳這一輪的索引（0 起算）。

#### `record_speech(self, seat_id: str, result: dict) -> dict`

`result` 就是 `ask()` 的回傳 dict（`SPEC.md` §4）。

- `phase` 不是 `PHASE_IN_ROUND` ⇒ `BoundaryError`。
- `seat_id` 不是**顧問**席次（不存在、或它是仲裁者）⇒ `ValueError`。
- 這一輪已經有該 `seat_id` 的紀錄 ⇒ `ValueError`（一輪一人只發言一次）。
- ⚠️ **不要檢查發言順序。** 順序由下一包的輪替編排負責，本包不管。

建立並附加到目前這一輪的紀錄：

```python
{"seat_id": str, "ok": bool, "text": str, "truncated": bool, "error": str | None,
 "elapsed_s": float, "model_used": str | None, "usage": dict | None,
 "stance": str | None, "more": bool, "violation": bool}
```

- `result["ok"]` 為真 ⇒ `stance` / `more` / `violation` 取自 `parse_marker(result["text"])`。
- `result["ok"]` 為假（逾時、呼叫失敗）⇒ `stance = None`、`more = True`、
  **`violation = False`**。理由見 `SPEC.md` §5 邊界 5 最後一條：沒發言不是格式違規。
- 用量累計（邊界 6）：本席次與總計的 `calls` **各 +1**，
  `usage` 以 `merge_usage()` 併入本席次與總計。
  ⚠️ **`ok=False` 的呼叫一樣 `calls +1`**——它照樣燒了額度，不計入等於謊報。
- 回傳這筆紀錄。

#### `end_round(self) -> None`

- `phase` 不是 `PHASE_IN_ROUND` ⇒ `BoundaryError`。
- **仍有顧問尚未留下紀錄** ⇒ `ValueError`（訊息列出缺哪些 `seat_id`）。
- `phase = PHASE_AWAITING_USER`。

⚠️ **`end_round()` 絕對不可以把 `phase` 設回 `PHASE_READY`。** 這一行就是邊界 1 的全部。

#### `request_next_round(self, confirm_over_cap: bool = False) -> None`

**這是唯一能讓 `phase` 回到 `PHASE_READY` 的方法**，代表「使用者按了再一輪」。

- `phase` 不是 `PHASE_AWAITING_USER` ⇒ `BoundaryError`。
- 已完成輪數 `>= max_rounds` 且 `confirm_over_cap` 不為真 ⇒ `BoundaryError`
  （邊界 3；`SPEC.md` §5 允許「明確確認再開一輪」，`confirm_over_cap=True` 就是那個確認）。
- 否則 `phase = PHASE_READY`。

#### `converged(self) -> bool`（邊界 5）

`phase` 不是 `PHASE_AWAITING_USER` ⇒ 回 `False`（一輪還沒結束，談不上收斂）。
否則：**最後一輪的每一筆紀錄 `more` 都是 `False`** ⇒ `True`，否則 `False`。

#### `status(self) -> dict`（邊界 6 的 UI 單一資料來源）

```python
{"phase": str,
 "rounds_completed": int,       # 進行中的那一輪不算
 "max_rounds": int,
 "at_cap": bool,                # rounds_completed >= max_rounds
 "can_start_round": bool,       # phase == PHASE_READY
 "converged": bool,
 "format_violations": int,      # 累計 violation 為真的紀錄數
 "usage": {"calls": int,
           "total": dict,
           "by_seat": {seat_id: {"calls": int, "usage": dict}}}}
```

- `rounds_completed` **用推導的**（`len(self.rounds)` 扣掉進行中的那一輪），
  不要另外維護一個計數器——兩個來源會對不起來。
- `by_seat` 只放**已經發過言的**顧問，不要為沒發言過的席次先塞零。
- ⚠️ 回傳的 `usage` dict 要是**複製**，呼叫端拿去改不得影響內部累計。

---

## 測試（`tests/test_engine_state.py`）

⚠️ **不得 import `subprocess` / `adapters`，不得啟動任何子行程（連假的都不用）。**
本包全部是純函式與純狀態機測試。收尾請貼出證明沒有這些 import 的 `grep` 輸出。

以下每一項都要有測試，**全部必要**：

**`parse_marker`**

1. `[立場: 同意] [補充: 無]` ⇒ `同意` / `more False` / `violation False`。
2. 全形冒號 `[立場：保留] [補充：有]` ⇒ 解析成功、`more True`、`violation False`。
3. **標記出現在中間、最後一行是別的文字**（模擬逐字稿引用了別人的標記）
   ⇒ `stance None`、`more True`、`violation True`。**這是本包最重要的一個測試。**
4. 完全沒有標記 ⇒ `more True`、`violation True`。
5. 標記後面還有空白行／換行 ⇒ 仍然命中（取的是最後一個**非空白**行）。
6. 被截斷的標記（如 `[立場: 同意] [補充: ` 斷在這裡）⇒ `violation True`、`more True`。

**`merge_usage`**

7. `claude` 形狀（`input_tokens` / `output_tokens` / `total_cost_usd`）連加兩次 ⇒ 各鍵為兩倍。
8. `opencode` 形狀（`{"tokens": {巢狀}, "cost": 0}`）⇒ 巢狀鍵正確相加。
9. 型別衝突與非數字值被忽略、不拋例外；`bool` 不被當數字加。
10. **不就地修改**：呼叫後傳進去的 `total` 與 `usage`（含其巢狀 dict）內容不變；
    修改回傳值不會反過來改到輸入。

**`Discussion` 建構驗證**（每項各自 `ValueError`）

11. 空 `question`；席次少於 2 或多於 4；缺鍵／型別錯；`seat_id` 重複；
    零個或兩個仲裁者；沒有顧問；`max_rounds` 為 0 或 `True`。

**邊界 1（最關鍵）**

12. `end_round()` 之後 `phase == PHASE_AWAITING_USER`，
    **直接呼叫 `begin_round()` ⇒ `BoundaryError`**；
    先 `request_next_round()` 之後才能成功 `begin_round()`。

**邊界 3**

13. `max_rounds=2`：跑完兩輪後 `request_next_round()` ⇒ `BoundaryError`；
    改以 `confirm_over_cap=True` 呼叫 ⇒ 成功，且能再開一輪。
14. `status()["at_cap"]` 在達上限時為真、未達時為假。

**邊界 5**

15. 一輪內全員「補充: 無」⇒ `converged()` 為真；其中一位「有」⇒ 為假。
16. 其中一位 `ok=False`（逾時）⇒ `converged()` 為假，且該筆 `violation` 為 **False**。
17. 一輪進行中（尚未 `end_round()`）⇒ `converged()` 為假。

**邊界 6**

18. 兩位顧問各發言一次（一位 `claude` 形狀、一位 `opencode` 形狀）
    ⇒ `by_seat` 分計正確、`total` 為兩者合併、`calls` 為 2。
19. 一位顧問 `ok=False` 且 `usage` 為 `None` ⇒ **`calls` 仍 +1**、`total` 不變。
20. `status()` 回傳的 usage 被呼叫端修改後，再次呼叫 `status()` 的值不受影響。

**其他狀態機規則**

21. `record_speech()` 用仲裁者的 `seat_id` ⇒ `ValueError`；
    同一輪重複同一顧問 ⇒ `ValueError`；`phase` 不是 `in_round` 時呼叫 ⇒ `BoundaryError`。
22. 還有顧問沒發言就 `end_round()` ⇒ `ValueError`。
23. `rounds_completed` 在一輪進行中不把該輪算進去，`end_round()` 後才 +1。

---

## 驗收條件（貼真實輸出，不要只描述）

1. `python3 -m unittest discover tests` **全過**，貼出最後三行。
   既有 83 個測試**一個都不得減少或變紅**。
   ⚠️ 011 那次回報「交付完成」但實跑是 `FAILED (errors=1)`。**請自己實際跑完再回報。**
2. 貼出只跑 `tests/test_engine_state.py` 的輸出。
3. **突變驗證三項**，每項：改壞 → 貼出失敗輸出 → 還原 → 最後貼還原後全過的結果。
   - (a) 拿掉 `request_next_round()` 的 `phase` 檢查 ⇒ 邊界 1 的測試必須翻紅。
   - (b) 把邊界 3 的 `>=` 改成 `>` ⇒ 邊界 3 的測試必須翻紅。
   - (c) 把 `parse_marker` 改成「掃全文取第一個命中」⇒ 測試 3 必須翻紅。
   - 改之前先斷言「檔案內容確實變了」（修改前後字串不同），否則沒套用會看起來像有覆蓋。
   - ⚠️ **突變只准動 `src/engine/state.py` 這一側，不准動測試檔裡的樣本字串。**
     樣本同時餵給多個測試，改它會讓對照組跟著變、判定不會翻轉（010 與 013 都踩過）。
4. 貼出 `grep -nE 'import (subprocess|os|sys)|adapters' src/engine/state.py` 的輸出
   （應為空），以及測試檔對 `subprocess` / `adapters` 的同樣檢查
   （測試檔會 import `sys` 來加 `sys.path`，那是允許的）。

---

## 不要做的事

- **不要實作輪替編排**：不要組 prompt、不要決定誰先發言、不要呼叫 `ask()`。下一包做。
- **不要為仲裁者加任何狀態或方法**（`record_arbitration` 之類一律不要）。
  仲裁流程是獨立的一包，先做會做錯。仲裁者在本包只是一個被驗證存在的席次。
- **不要加任何會自己往前走的東西**：迴圈、`run()`、排程、`threading`、
  「自動開下一輪」的旗標。邊界 1 是本專案存在的理由。
- 不要做持久化／存檔／JSON 匯出（`SPEC.md` §8 明列延後）。
- 不要動 `src/adapters/` 底下任何檔案、`tests/` 既有的兩個測試檔、
  `SPEC.md`、`AGENTS.md`、`CLAUDE.md`、`dispatch.sh`、`dispatch/` 底下任何檔案。
- 不要碰版控（`git add` / `commit` / `push` 一律不執行），改動留在工作區即可。
- 不要新增設定項、環境變數、命令列參數。
- 不要用 `dataclasses` / `enum` / 第三方套件把這幾個 dict 包起來
  （`SPEC.md` §7：標準函式庫優先、不加沒要求的抽象）。既有程式碼一律用純 dict，照做。
