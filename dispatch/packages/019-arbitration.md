# 工作包 019：仲裁流程

**動手前先整段讀完 `SPEC.md` §6 與 §6.1（§6.1 是本包的規格，剛新增）**，
另讀 §5 邊界 5／6、§3.1、§3.3。

顧問輪替與六道邊界都已完成，缺的是最後一個角色：**仲裁者**。目前 `--arbiter`
指定的席次從頭到尾不會被呼叫。本包讓使用者可以在一輪結束後叫它出來整合結論。

⚠️ **本包會修改三個已經穩定、已被 181 個測試覆蓋的檔案**（`state.py`、
`orchestrator.py`、`cli.py`）。**只准做下面明列的增修，不准順手改任何其他東西**，
既有測試一個都不得變紅。

---

## 檔案

| 檔案 | 動作 |
|---|---|
| `src/engine/state.py` | **增修**：新增 `self.arbiter`／`self.arbitrations`／`can_arbitrate()`／`record_arbitration()` |
| `src/engine/orchestrator.py` | **增修**：抽出共用的 prompt 前綴、新增 `ARBITER_INSTRUCTION`／`build_arbiter_prompt()`／`run_arbitration()` |
| `src/cli.py` | **增修**：新增 `--arbitrate` 旗標與仲裁區段輸出 |
| `run.sh` | **只改註解**（見第 5 節，不得改行為） |
| `tests/test_engine_state.py` | 增加測試 |
| `tests/test_engine_orchestrator.py` | 增加測試 |

⚠️ **不新增任何檔案**，包含 `tests/test_cli.py`——測試檔不得 import `cli`／`adapters`
（既有紅線），所以 `cli.py` 的部分靠驗收條件的真實輸出來證明，不寫測試。

⚠️ **既有的隔離規定全部延續**：`state.py`／`orchestrator.py`／`wiring.py`
**不得 import `subprocess`／`os`／`sys`／`adapters`**；`src/cli.py` 仍是唯一
允許 import `adapters` 的檔案；測試檔不得 import `adapters`／`cli`／`subprocess`。

✅ **本包唯一放寬的一條**：`orchestrator.py` **可以**
`from engine.state import BoundaryError`。理由見第 2 節第 4 點——它必須在花錢之前
自己丟出邊界錯誤。除此之外 `orchestrator.py` 仍不得 import 任何其他東西。

---

## 介面契約（照字面實作，不要擴充公開介面）

### 1. `state.Discussion` 新增兩個屬性

在 `__init__` 既有驗證通過之後設定（席次驗證保證恰好一個 arbiter，不必重複檢查）：

- `self.arbiter`：那唯一一個 `role == ARBITER` 的席次 dict（**就是 `self.seats` 裡
  的那一個物件本身，不要另外複製一份**）。
- `self.arbitrations`：`[]`，之後每次仲裁 append 一筆 record。

⚠️ **`self.seats` 與 `self.advisors` 的既有語意一字不改**：`seats` 仍含仲裁者，
`advisors` 仍不含。既有測試守著這件事。

### 2. `state.Discussion.can_arbitrate() -> bool`

`SPEC.md` §6.1 的三條前提，**全部成立才回 `True`**：

```python
不在進行中的一輪        self.phase != PHASE_IN_ROUND
至少完成一輪            self._rounds_completed() >= 1
至少有一則成功的發言    任何一輪裡有 rec["ok"] 為真
```

- ⚠️ 第三條要掃**所有輪次**，不是只看最後一輪。第一輪大家有講話、第二輪全部逾時，
  仲裁者仍有東西可讀。
- 這是一個**純查詢**：不改任何狀態、不丟例外。

### 3. `state.Discussion.record_arbitration(result: dict) -> dict`

參數是 `SPEC.md` §4 的七鍵 dict（與 `record_speech` 收的同一種）。
**不收 `seat_id`**——仲裁者只有一個，由 `self.arbiter["seat_id"]` 決定，
少一個參數就少一種傳錯的方式。

1. `can_arbitrate()` 為 `False` ⇒ 丟 `BoundaryError`，訊息要**說得出是哪一條前提
   沒過**（三種情況三種訊息）。
2. 組出 record，鍵**恰好這八個**：
   `seat_id`／`ok`／`text`／`truncated`／`error`／`elapsed_s`／`model_used`／`usage`。
   - `seat_id` ＝ 仲裁者的 seat_id。`ok` 用 `bool(result["ok"])`。
     `usage` 要 `copy.deepcopy`（與 `record_speech` 同做法）。
   - 🔴 **絕對不得含 `stance`／`more`／`violation` 三鍵。** 這不是省略，是紅線：
     仲裁者不參與收斂偵測（§6.1），少了這三鍵，將來若有人不小心把仲裁記錄餵進
     `converged()` 會當場 `KeyError` 炸掉，而不是安靜地汙染收斂訊號。
   - ⚠️ **不要對 `result["text"]` 呼叫 `parse_marker()`。** 一次都不要。
3. append 進 `self.arbitrations`。
   🔴 **不得 append 進 `self.rounds` 的任何一輪**——仲裁者不是第四個發言者。
4. 記帳（§6.1）：`_calls_total` +1、`_calls_by_seat[仲裁者]` +1、
   `_usage_total` 與 `_usage_by_seat[仲裁者]` 各以 `merge_usage()` 併入。
   **`ok` 為 `False` 時次數一樣 +1**（呼叫發生了就是發生了，`record_speech` 也是這樣算）。
5. **不改 `self.phase`**、不改 `self.rounds`。
6. 回傳那筆 record。

### 4. `status()` 不新增任何欄位

仲裁者的用量會經由 `usage.calls`／`usage.total`／`usage.by_seat` 自然出現，
那正是 §5 邊界 6 要的東西。**不要加 `arbitrations` 計數欄位**，也不要讓
`converged`／`format_violations`／`rounds_completed`／`at_cap` 有任何行為變化。

### 5. `orchestrator.py`：抽出共用前綴

現在 `build_prompt()` 組的是「脈絡 → 原始問題 → 各輪逐字稿 → 顧問任務」。
仲裁者要的是**同樣的前三塊，換掉最後一塊**。

⇒ 把前三塊抽成一個私有函式，兩邊共用：

```python
def _prefix_blocks(discussion) -> list:
    """脈絡（若非空白）＋原始問題＋各輪逐字稿，依序回傳區塊 list。"""
```

- `build_prompt(discussion, seat_id)` ＝ `_prefix_blocks(...)` ＋ 顧問任務區塊，
  以 `"\n\n"` 連接。
- ⚠️ **`build_prompt` 的輸出必須與現在一字不差**（既有測試會守，包含
  `ADVISOR_INSTRUCTION` 的完整字面）。這一步是純重構，不是行為變更。
- ⚠️ **`ADVISOR_INSTRUCTION` 一個字都不准改。** 既有測試硬編了它的全文。

### 6. `orchestrator.ARBITER_INSTRUCTION`

新增一段模組層常數，含 `{seat_id}` 佔位符，由 `build_arbiter_prompt` 以
`.format(seat_id=...)` 填入。內容照抄下面這段，不要自由發揮：

```
【你的任務】
你是本次討論的仲裁者「{seat_id}」。你沒有參與上面的任何一輪發言，
現在第一次讀到這份逐字稿。請針對最上面的原始問題輸出一份整合結論，包含：

1. 各方的共識是什麼。
2. 分歧在哪裡，以及分歧的真正原因是什麼（是前提不同，還是結論不同）。
3. 你的最終建議，以及採納它的前提與風險。

請直接下判斷，不要只複述各方說過的話。若逐字稿裡的資訊不足以下判斷，
明說缺什麼，不要用推測填補。
```

🔴 **這段文字裡不得出現 `[立場` 這個字串。** 仲裁者不參與收斂偵測（§6.1），
要求它輸出標記行只會製造一行沒人解析的雜訊。有測試守這件事。

### 7. `orchestrator.build_arbiter_prompt(discussion) -> str`

`_prefix_blocks(discussion)` ＋ `ARBITER_INSTRUCTION.format(seat_id=discussion.arbiter["seat_id"])`，
以 `"\n\n"` 連接。**純函式**：不修改 `discussion`、不呼叫 `ask_fn`。

### 8. `orchestrator.run_arbitration(discussion, ask_fn, *, max_chars=DEFAULT_MAX_CHARS, timeout_s=DEFAULT_TIMEOUT_S) -> dict`

`ask_fn` 的契約與 `run_round()` 完全相同，**同樣是必填、沒有預設值**。

執行順序**必須是這個順序**：

1. 🔴 **第一件事**：`if not discussion.can_arbitrate(): raise BoundaryError(...)`。
   **在任何 `ask_fn` 呼叫之前**。順序反過來就是「先花錢、再發現不該花」，
   而仲裁者拿的是最長的逐字稿、通常也是最貴的一席。有測試用絆線函式守這件事。
2. `seat = discussion.arbiter`，以 `ask_fn(cli=seat["cli"], prompt=build_arbiter_prompt(discussion), model=seat["model"], timeout_s=..., max_chars=...)` 呼叫。
3. `try` **只包住 `ask_fn` 呼叫與取值**（與 `run_round` 同做法）。丟例外時記為
   `ok=False`、`error=f"{type(exc).__name__}: {exc}"`、其餘欄位比照 `run_round`
   的失敗分支。⚠️ **不要把 `record_arbitration` 放進 `try`**——狀態機自己的拒絕
   不得被吞掉。
4. `return discussion.record_arbitration(result)`。

🔴 **本函式不得呼叫** `run_round`／`begin_round`／`end_round`／`request_next_round`，
也不得自己重試。仲裁跑完就結束，下一步永遠由使用者決定（§5 邊界 1）。

### 9. `cli.py` 新增 `--arbitrate`

| 參數 | 說明 |
|---|---|
| `--arbitrate` | 選用旗標。該輪跑完後**追加一次仲裁者呼叫**，輸出整合結論 |

- ⚠️ **預設關閉。** 不加就跟現在完全一樣：仲裁者一次都不會被呼叫。
  這與 `--live` 是同一個原則——**會花錢的事必須明確打開**。
- `--arbiter` 的既有 help 文字 `"v1 尚未實作仲裁流程，本席次此輪不會發言"`
  **已經過期，改掉**：改成說明它只在加上 `--arbitrate` 時才會被呼叫。
- LIVE 模式的警告行目前是
  `⚠️ LIVE 模式：即將對 N 個顧問席次發出真實呼叫，會消耗訂閱額度。`
  加了 `--arbitrate` 時要**一併講出仲裁者那一次**（例如追加一句
  「並在該輪結束後追加 1 次仲裁者呼叫」）。⚠️ 這行是使用者燒錢前唯一看得到的
  預告，少報一次呼叫就是報錯數字。
- 一輪跑完、逐字稿印完之後：
  - `discussion.can_arbitrate()` 為 `True` ⇒ 呼叫 `orchestrator.run_arbitration()`，
    然後印出仲裁區段（標題自訂，需含席次 id；成功印 `text`，
    截斷比照顧問加註，失敗印 `（未回應：...）`）。
  - 為 `False` ⇒ **不呼叫**，印一行可讀訊息到 **stderr**，說明為什麼跳過
    以及「未消耗額度」，然後**照常印狀態、退出碼 0**。
    退出碼 0 是刻意的：那一輪本身完整跑完也印出來了，跳過仲裁是設計內的省錢行為，
    不是執行失敗。
- 🔴 **印出的狀態必須是仲裁之後重新取得的 `discussion.status()`。**
  現在的寫法是 `status = orchestrator.run_round(...)` 拿到一份快照就拿去印；
  仲裁發生在那之後，**沿用舊快照會讓用量少算仲裁那一次**（§5 邊界 6 漏報）。
  請改成在印狀態前重新呼叫 `discussion.status()`。

### 10. `run.sh` 只改註解

`ARBITER="claude"` 上方那兩行註解寫著「仲裁流程尚未實作，這一席這輪不會發言」，
本包之後就是錯的。改成說明：**要仲裁請自己加 `--arbitrate`**（多餘參數會原樣轉給
`cli.py`），並提醒**這一席是 `claude`，一次仲裁會消耗付費額度**。

🔴 **不得把 `--arbitrate` 加進 `ARGS`**，不得改任何一行程式邏輯。只動註解文字。

---

## 測試

⚠️ 新增的測試**放進既有的兩個測試檔**，不要新增檔案。既有測試一個都不得修改。

### `tests/test_engine_state.py`

1. `discussion.arbiter` 就是那個仲裁席次（`seat_id`／`role` 相符），且它**不在**
   `discussion.advisors` 裡、**有在** `discussion.seats` 裡。
2. 新建的討論（尚未跑任何一輪）⇒ `can_arbitrate()` 為 `False`，
   且 `record_arbitration(...)` 丟 `BoundaryError`。
3. `begin_round()` 之後、輪還沒結束 ⇒ `can_arbitrate()` 為 `False`、
   `record_arbitration` 丟 `BoundaryError`。
4. 一輪完整跑完（至少一則 `ok=True`）⇒ `can_arbitrate()` 為 `True`。
5. 一輪完整跑完但**全員 `ok=False`** ⇒ `can_arbitrate()` 為 `False`、
   `record_arbitration` 丟 `BoundaryError`。**這條守的是額度**。
6. 第一輪有人成功、第二輪全員 `ok=False` ⇒ `can_arbitrate()` 仍為 `True`
   （前提三掃的是所有輪次，不是只看最後一輪）。
7. `request_next_round()` 之後（phase 回到 `ready`、已完成一輪且有成功發言）
   ⇒ `can_arbitrate()` 仍為 `True`。
8. 成功仲裁的回傳 record：`set(record.keys())` **恰好**等於那八個鍵，
   `seat_id` 是仲裁者，且 `"stance"`／`"more"`／`"violation"` **都不在**鍵裡。
9. 仲裁之後 `discussion.arbitrations` 長度為 1，且 `discussion.rounds`
   與仲裁前**逐輪逐筆完全相同**（先深拷貝一份再比對）。
10. 仲裁帶 `usage` ⇒ `status()["usage"]["calls"]` 比仲裁前多 1、`total` 已併入該
    usage、`by_seat` 出現仲裁者且其 `calls` 為 1。
11. 仲裁 `ok=False`、`usage=None` ⇒ 仍記錄、`calls` 仍 +1、`total` 與仲裁前相同。
12. 仲裁的 `text` **帶一行合法的 `[立場: 同意] [補充: 無]`** ⇒
    `status()["converged"]` 與 `status()["format_violations"]` 與仲裁前**完全相同**。
    ⚠️ 這條是本包最重要的一個測試：它證明仲裁者的發言汙染不到收斂訊號。
13. 仲裁的 `text` 完全沒有標記行 ⇒ `format_violations` 不增加。
14. 仲裁不改變 `phase`（`awaiting_user` 進、`awaiting_user` 出）。
15. 連續仲裁兩次 ⇒ `arbitrations` 長度 2、`calls` 累計 +2。
16. 深拷貝：把傳進 `record_arbitration` 的 `usage` dict 在事後就地改掉，
    `status()["usage"]["total"]` 不受影響。

### `tests/test_engine_orchestrator.py`

17. `build_arbiter_prompt` 同時含原始問題、**所有輪次**的逐字稿（不只最後一輪）、
    以及 `【你的任務】`。
18. 共用前綴：同一個 `discussion`，`build_prompt(d, 某顧問)` 與
    `build_arbiter_prompt(d)` 在各自第一個 `【你的任務】` 之前的文字**完全相同**。
    **這條守的是「兩份 prompt 的前綴不會各自漂移」**。
19. 有脈絡時 `build_arbiter_prompt` 的輸出以 `【專案脈絡】` 開頭。
20. `"[立場" not in ARBITER_INSTRUCTION`。
21. `can_arbitrate()` 為 `False` 時 `run_arbitration` 丟 `BoundaryError`，
    **且 `ask_fn` 完全沒有被呼叫**——`ask_fn` 請用一個「被呼叫就 `raise AssertionError`」
    的絆線函式。**這條守的是「不先花錢」**。
22. `run_arbitration` 傳給 `ask_fn` 的 `cli`／`model` 來自**仲裁者席次**
    （不是任何顧問），且 `timeout_s`／`max_chars` 原樣傳遞。
23. `run_arbitration` 的回傳值就是 `discussion.arbitrations[-1]`。
24. `ask_fn` 丟例外 ⇒ 記為 `ok=False`、`error` 含例外型別名、**例外不往外傳**，
    且 `status()["usage"]["calls"]` 仍 +1。
25. `run_arbitration` 之後 `discussion.phase` 不變、`status()["rounds_completed"]`
    不變、`discussion.rounds` 不變（不會偷偷觸發下一輪）。

⚠️ 測試一律用**純 Python 假函式**當 `ask_fn`，不要假子行程、不要 `unittest.mock`。

---

## 驗收條件（貼真實輸出，不要只描述）

1. `python3 -m unittest discover tests` **全過**，貼出最後三行。
   **既有 181 個測試一個都不得減少或變紅。**
   ⚠️ 011 那次回報「交付完成」但實跑是 `FAILED (errors=1)`。**請自己實際跑完再回報。**
2. 貼出 `python3 src/cli.py --help`，證明 `--arbitrate` 已加入、
   且 `--arbiter` 的說明已不再寫「尚未實作」。
3. **貼出一次 dry-run 的完整輸出**（⚠️ **不要加 `--live`，一次都不要**）：
   ```
   python3 src/cli.py "先做仲裁還是先做 web UI？" --advisor claude --advisor gemini --arbiter codex --arbitrate
   ```
   應看到仲裁區段，且狀態裡 **`總呼叫次數：3`**（兩位顧問＋一次仲裁）、
   `by_seat` 含仲裁者席次。
4. **回歸證明**：同一條指令**拿掉 `--arbitrate`** 再跑一次，貼出輸出，
   證明 `總呼叫次數：2`、`by_seat` **完全沒有**仲裁者席次
   （仲裁確實是 opt-in，沒被預設打開）。
5. **突變驗證五項**，每項：改壞 → 貼失敗輸出（含翻紅的測試名）→ 還原 →
   最後貼還原後全過的結果。
   - (a) `can_arbitrate()` 拿掉「至少一則成功發言」那條 ⇒ 測試 5 翻紅。
   - (b) `record_arbitration` 改成同時 append 進 `self.rounds[-1]` ⇒ 測試 9／12／13 翻紅。
   - (c) `record_arbitration` 拿掉用量併入與 `calls` +1 ⇒ 測試 10／11 翻紅。
   - (d) `run_arbitration` 把前置的 `can_arbitrate` 檢查**移到 `ask_fn` 呼叫之後**
     ⇒ 測試 21 翻紅。
   - (e) `build_arbiter_prompt` 改成不含逐字稿（只有問題＋任務）⇒ 測試 17／18 翻紅。
   - 改之前先確認檔案內容確實變了；還原後請確認與備份**位元組相同**。
   - 🔴 **突變只准動實作那一側**（`state.py`／`orchestrator.py`），
     **不准動測試檔、不准動測試裡的樣本字串**。
6. 貼出 `git diff --stat`，證明**只**動了契約表列的那六個檔案，且
   `src/adapters/` 底下、`src/engine/wiring.py`、`SPEC.md` 全都沒被動到。
7. 貼出隔離檢查：
   - `grep -nE 'import (subprocess|os|sys)|adapters' src/engine/state.py src/engine/orchestrator.py src/engine/wiring.py` ——**應為空**。
   - `grep -n 'request_next_round' src/engine/orchestrator.py` ——**應為空**。
   - `grep -nE 'parse_marker|stance|violation' src/engine/orchestrator.py` ——**應為空**
     （仲裁與收斂偵測在編排層完全不相干）。
   - `grep -nE 'adapters|import cli|from cli|subprocess|mock' tests/test_engine_state.py tests/test_engine_orchestrator.py` ——**應為空**。
8. 貼出 `git diff run.sh`，證明只改了註解文字、`ARGS` 與任何邏輯行都沒動。

---

## 不要做的事

- ⚠️ **不要以 `--live` 執行任何東西。** 真實呼叫由 Frank 親自按。
- ⚠️ **不要把仲裁者變成第四個發言者**：不進 `rounds`、不進 `advisors`、
  不套 `parse_marker`、不計入 `format_violations`、不影響 `converged`。
- ⚠️ **不要在 `status()` 新增欄位**，不要改既有欄位的算法。
- ⚠️ **不要改 `ADVISOR_INSTRUCTION`**（既有測試硬編了它的全文），
  不要改 `build_prompt` 的輸出內容。
- ⚠️ **不要讓仲裁自動發生**：沒有 `--arbitrate` 就一次都不呼叫；
  仲裁完也不得自動再開一輪（§5 邊界 1）。
- **不要實作多輪迴圈、互動確認、存檔／匯出、web UI**（`SPEC.md` §8 明列延後）。
- **不要為仲裁加重試、加摘要、加截斷特例。** 逾時與長度上限沿用既有的
  `timeout_s`／`max_chars`，不要另立一組。
- 不要新增檔案（含 `tests/test_cli.py`）、不要動 `src/adapters/` 底下任何檔案、
  `src/engine/wiring.py`、`SPEC.md`、`AGENTS.md`、`CLAUDE.md`、`dispatch.sh`、
  `dispatch/` 底下任何檔案。
- 不要碰版控（`git add` / `commit` / `push` 一律不執行）。
- 不要新增環境變數、設定檔、第三方套件。
- 不要用 `dataclasses` / `enum` 包任何東西。既有程式碼一律純 dict，照做。
