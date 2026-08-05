# 工作包 016：序列輪替的討論引擎（一輪的編排）

**動手前先整段讀完 `SPEC.md` §6（討論流程）**，另讀 §3.1（逐字稿由 council 自己管）、
§4（`ask()` 的回傳結構）、§5 邊界 1／2／4／5。

本包新增 `src/engine/orchestrator.py` 與 `tests/test_engine_orchestrator.py`，
**不動任何既有檔案**——`src/engine/state.py` 一個字都不要改。

狀態機（014／015）已經做好「邊界掛在哪」，本包做的是**編排**：誰在什麼時候發言、
每個人看得到什麼、回覆怎麼交回狀態機。**一輪就停**。

---

## 🔴 本包的紅線：不准打到真實 CLI（結構層，不是拜託）

014 那包靠「禁止 import `adapters`」在結構上保證不可能燒到額度。本包**必須真的呼叫
`ask()`**，沒辦法用同一招，所以改用另一個結構性做法：

> **`orchestrator.py` 自己不認識任何 adapter。呼叫哪個 CLI 是由呼叫端傳進來的
> `ask_fn` 決定的，而 `ask_fn` 是 `run_round()` 的必填參數、沒有預設值。**

- ⚠️ **`ask_fn` 不得有預設值，不得 fallback 到 `adapters.ADAPTERS`，不得在
  `ask_fn is None` 時自己去找真的 adapter。** 忘了傳的後果必須是 `TypeError`
  當場失敗，**不可以是「安靜地打到真的 CLI」**。
  這條的由來：010 那包的紅線寫在文字裡，交付的腳本是 `bin="${PROBE_X_BIN:-claude}"`
  ——預設值就是真 binary，漏設一個環境變數就打到真的。**預設值 fail-open 是本專案
  最貴的一種 bug（它花的是 Frank 的錢）。**
- ⚠️ **`src/engine/orchestrator.py` 不得 import `subprocess`、`os`、`sys`，
  也不得 import `adapters`。** 測試檔同樣不得 import `subprocess` 與 `adapters`，
  **一律用純 Python 的假函式當 `ask_fn`**（不要用 `unittest.mock` 去 patch 真模組，
  也不要啟動任何子行程，連假的執行檔都不要）。
- 「真的接上四家 CLI」是**下一包**（進入點／UI）的事。本包交付後引擎還不能端到端跑，
  **這是刻意的**，不要順手補一個接線函式進來。

---

## 檔案

- `src/engine/orchestrator.py`——本包全部的實作。
- `tests/test_engine_orchestrator.py`——本包全部的測試。

測試的匯入方式沿用既有慣例（見 `tests/test_engine_state.py` 開頭）：把 `src/` 加進
`sys.path` 後 `from engine import orchestrator`。

---

## 介面契約（請照字面實作，不要擴充公開介面）

### 模組層常數

```python
DEFAULT_MAX_CHARS = 8000     # SPEC.md §5 邊界 2
DEFAULT_TIMEOUT_S = 180      # SPEC.md §5 邊界 4（180 不是 120，理由見 SPEC 該條）
```

⚠️ 這兩個值**只能在這裡出現一次**。不要在 `run_round()` 的函式簽章以外的地方
再寫一次數字，也不要在 `build_prompt()` 或測試以外的任何位置寫死 `8000` / `180`。
`SPEC.md` §5 的參數散落成各處的預設值，正是本包要避免的事。

### 1. `ADVISOR_INSTRUCTION`（模組層常數，字串）

給顧問的任務指示，**逐字照抄下面這段，不要改寫、不要潤飾、不要翻譯**
（它會被測試逐字比對；要改措辭是 SPEC 層的決定，不是實作層的）：

```
【你的任務】
你是本次討論的顧問「{seat_id}」。請針對上面的原始問題提出你的看法。
若上面已經有其他顧問的發言，請一併回應他們的論點——同意哪裡、補充什麼、反對什麼。

回覆的最後一行必須是下面這個格式，前後不要有任何其他文字：
[立場: 同意] [補充: 無]

其中「立場」三選一：同意 / 保留 / 反對；「補充」二選一：有 / 無。
「補充: 無」代表你認為自己已經沒有新的論點可以加。
```

- `{seat_id}` 是**唯一**的代入位置，用 `str.format(seat_id=...)` 或等效方式代入。
- ⚠️ 這段文字裡的 `[立場: 同意] [補充: 無]` 是**給模型看的範例**。它與
  `state.parse_marker()` 的解析規則必須一致（半形方括號、半形冒號、格式完全相同），
  **但不要 import `state` 去組出這行**——那會讓解析規則與示範文字互相耦合，
  將來改一邊會無聲影響另一邊。兩邊各自寫死，靠測試守住它們一致（見測試 12）。

### 2. `build_prompt(discussion, seat_id) -> str`

依 `SPEC.md` §6 第 3 點組出要送給某位顧問的完整 prompt。

⚠️ **`SPEC.md` 那句「原始問題 + 本輪前 N-1 位的發言 + 先前各輪完整逐字稿」是在列
「包含哪些內容」，不是在規定順序。** 實際順序**照下面寫死的來**，不要照 SPEC 的
字面順序把先前各輪放到本輪後面（那讀起來是時序錯亂的）。

輸出＝以下區塊依序以**一個空行**（`"\n\n"`）連接：

1. **問題區塊**：
   ```
   【原始問題】
   {discussion.question}
   ```
2. **每一輪一個區塊**，依輪次由舊到新。第 k 輪（k 從 **1** 起算，不是 0）：
   ```
   【第 k 輪】
   ```
   後面接該輪**已有紀錄的每一筆**，依紀錄順序，每筆之前加一個空行：
   ```
   ── {seat_id} ──
   {發言內容}
   ```
   - `ok` 為真 ⇒ `{發言內容}` 就是 `record["text"]` 的**原文**（含它自己那行立場標記，
     不要清掉——`SPEC.md` §5 已經把「逐字稿裡會出現別人的標記」納入解析規則了）。
   - `ok` 為真且 `truncated` 為真 ⇒ 在 `text` 之後另起一行加上
     `（本則發言超過長度上限，已被截斷）`。
   - `ok` 為**假** ⇒ `{發言內容}` 一律是 `（未回應：{record["error"]}）`；
     `record["error"]` 為 `None` 或空字串時用 `（未回應）`。
     ⚠️ **絕對不可以把 `error` 的內容當成該顧問的發言直接放進逐字稿。**
     那會讓下一位顧問去回應一段 stderr。
   - **沒有任何紀錄的輪不輸出整個區塊**（進行中的那一輪若還沒人發言，就整段略過，
     不要留一個空的 `【第 k 輪】`）。
   - ⚠️ **進行中的那一輪也要輸出**（那就是「本輪前 N-1 位的發言」的來源）。
     `discussion.rounds` 本來就含進行中的那一輪，照順序走即可，不要特別排除它。
3. **任務區塊**：`ADVISOR_INSTRUCTION` 代入 `seat_id` 之後的字串。

其他規定：

- `build_prompt` 是**純函式**：不得修改 `discussion`、不得呼叫 `ask_fn`、
  不得呼叫任何會改狀態的方法。
- `seat_id` 只用在任務區塊的代入，**不做任何驗證**（是不是顧問、有沒有發過言，
  都由 `run_round()` 與狀態機負責）。本函式不拋例外。
- ⚠️ **不要對逐字稿做任何長度裁切、摘要或去重。** 長度風險已經在 `SPEC.md` §3.2
  處理掉了（prompt 走 stdin，沒有 argv 上限），在這裡再切一刀等於讓那次改造失效。
  總量的節制是 §5 邊界 3（輪數上限）的工作。

### 3. `run_round(discussion, ask_fn, *, max_chars=DEFAULT_MAX_CHARS, timeout_s=DEFAULT_TIMEOUT_S) -> dict`

跑**完整的一輪**：所有顧問依序各發言一次，然後結束這一輪。

`ask_fn` 的契約（由呼叫端提供，本模組只負責照這個形狀呼叫）：

```python
ask_fn(cli=str, prompt=str, model=str|None, timeout_s=int, max_chars=int) -> dict
# 回傳與 SPEC.md §4 的 ask() 完全相同的七個鍵：
# ok / text / truncated / error / elapsed_s / model_used / usage
```

⚠️ **一律以關鍵字呼叫**（`ask_fn(cli=..., prompt=..., ...)`），不要用位置參數。
`adapters` 的 `ask()` 簽章是 `(prompt, model, timeout_s, max_chars)`、順序與這裡不同，
用位置參數會在接線那一包無聲地把參數對錯位置。

執行流程，**照這個順序，不要加迴圈**：

1. `discussion.begin_round()`——**不要自己檢查 `phase`**，狀態機會擋（邊界 1）。
   它拋出的 `BoundaryError` 直接往外傳，不要捕捉、不要包裝。
2. 依 `discussion.advisors` 的順序，對每一位顧問：
   1. `prompt = build_prompt(discussion, seat["seat_id"])`
      ——⚠️ **每一位都要在輪到他的當下重新組**，不可以在迴圈外組一次共用，
      否則第 2 位看不到第 1 位剛剛講的話。
   2. 呼叫 `ask_fn(cli=seat["cli"], prompt=prompt, model=seat["model"],
      timeout_s=timeout_s, max_chars=max_chars)`。
   3. 從回傳取出那七個鍵，組成要交給狀態機的 `result`。
   4. `discussion.record_speech(seat["seat_id"], result)`。
3. `discussion.end_round()`。
4. 回傳 `discussion.status()`。

**失敗處理（這是「不整場卡死」的實作，`SPEC.md` §5 邊界 4 的精神）**：

- 上面 2-2 與 2-3（呼叫 `ask_fn` 以及從其回傳取那七個鍵）**若拋出任何 `Exception`**
  ——包含逾時、子行程炸掉、回傳形狀不對造成的 `KeyError`／`TypeError`——
  一律轉成下面這筆「未回應」紀錄，然後**繼續下一位顧問**：

  ```python
  {"ok": False, "text": "", "truncated": False,
   "error": f"{type(exc).__name__}: {exc}",
   "elapsed_s": 0.0, "model_used": None, "usage": None}
  ```

- ⚠️ **捕捉範圍只能包住 2-2 與 2-3。`discussion.record_speech()` 與
  `begin_round()`／`end_round()` 拋出的例外絕對不可以被吞掉**——那是狀態機在
  執行停止邊界，吞掉它等於把邊界關掉。寫成一個包住兩三行的 `try`，
  不要圖方便把整個迴圈主體包起來。
- ⚠️ 不要 retry、不要退避、不要「換一家問問看」。失敗就是本輪未回應，
  由使用者在下一輪決定要不要繼續。

**絕對不可以做的事**：

- ⚠️ **不得呼叫 `discussion.request_next_round()`。** 那是使用者的動作，
  是邊界 1 的全部意義。本模組出現這個字串就是錯的。
- ⚠️ **不得在 `run_round()` 內迴圈跑多輪**，不得提供 `run_discussion()`／
  `run_until_converged()` 之類的東西。
- ⚠️ **不得呼叫仲裁者。** 只走 `discussion.advisors`；仲裁流程是獨立的一包。
  （`discussion.advisors` 本來就已排除仲裁者，照它走就對了——不要自己再從
  `discussion.seats` 過濾一次。）

---

## 測試（`tests/test_engine_orchestrator.py`）

⚠️ **不得 import `subprocess` 與 `adapters`，不得啟動任何子行程。**
`ask_fn` 一律用測試檔內自己定義的純 Python 函式（可以記錄自己被呼叫時收到的參數）。
收尾請貼出證明沒有這些 import 的 `grep` 輸出。

以下每一項都要有測試，**全部必要**：

**`build_prompt`**

1. 第一輪第一位：輸出含原始問題與任務區塊，**不含任何 `【第 k 輪】` 區塊**。
2. 第一輪第二位：輸出含 `【第 1 輪】` 與第一位的發言原文（含其立場標記行）。
3. 第二輪第一位：輸出含 `【第 1 輪】` 完整內容，且 `【第 1 輪】` 出現在
   `【第 2 輪】`（若有）之前、兩者都出現在任務區塊之前——**順序要驗，不只驗有沒有**。
4. 前一位 `ok=False` 且 `error="timeout"` ⇒ 逐字稿含 `（未回應：timeout）`，
   且**不含**該筆的 `text` 內容。另驗 `error=None` 時輸出 `（未回應）`。
5. 前一位 `truncated=True` ⇒ 逐字稿含 `（本則發言超過長度上限，已被截斷）`，
   且 `text` 原文仍在。
6. 任務區塊確實代入了正確的 `seat_id`。
7. **仲裁者的席次不會出現在逐字稿裡**（狀態機不接受仲裁者發言，所以構造上就不會有；
   本測試驗的是 `build_prompt` 沒有自己去翻 `discussion.seats` 撈仲裁者）。
8. `build_prompt` 呼叫前後 `discussion.status()` 完全相同（純函式，沒有副作用）。

**`run_round` 正常流程**

9. 三位顧問（其中一席是仲裁者，共四個席次）跑一輪：`ask_fn` **恰好被呼叫 3 次**，
   `cli` 依 `advisors` 的順序出現，**仲裁者的 `cli` 一次都沒被呼叫**。
10. 每次呼叫收到的 `model` 是該席次的 `model`（含 `model=None` 的席次要驗到）。
11. 收到的 `timeout_s` / `max_chars` 預設為 `DEFAULT_TIMEOUT_S` / `DEFAULT_MAX_CHARS`；
    明確傳入其他值時，**每一次呼叫**都收到傳入的值。
12. **第 N 位收到的 prompt 含第 N-1 位剛剛的回覆內容**（證明 prompt 是逐位重組的）。
    ⚠️ 這個測試裡讓假 `ask_fn` 回傳的 `text` 以 `ADVISOR_INSTRUCTION` 示範的那行標記
    （`[立場: 同意] [補充: 無]`）結尾，並斷言 `state.parse_marker()` 對它
    `violation` 為 `False`——**這就是守住「示範文字與解析規則一致」的那個測試**。
13. 跑完後 `phase == state.PHASE_AWAITING_USER`（`end_round()` 有被呼叫），
    且 `status()["can_start_round"]` 為 `False`。
14. 回傳值就是 `discussion.status()`：驗 `rounds_completed == 1`、
    `usage["calls"] == 3`、`usage["by_seat"]` 有三位顧問。

**`run_round` 失敗與邊界**

15. 中間那位的 `ask_fn` 拋 `RuntimeError("boom")` ⇒ 該筆記為 `ok=False`、
    `error` 含 `RuntimeError` 與 `boom`、`text` 為 `""`、`usage` 為 `None`、
    `elapsed_s == 0.0`、`model_used` 為 `None`、`truncated` 為 `False`
    （**七個欄位逐一驗**），**且第三位仍然被呼叫、`end_round()` 仍然成功**。
16. `ask_fn` 回傳缺鍵的 dict（例如少了 `usage`）⇒ 同樣記為 `ok=False`，整輪不中斷。
17. 全部三位都拋例外 ⇒ 一輪照樣正常結束，`usage["calls"] == 3`
    （失敗也算呼叫次數，`SPEC.md` §5 邊界 6）。
18. **邊界 1**：`run_round()` 跑完後**直接再呼叫一次 `run_round()` ⇒ `BoundaryError`**；
    先 `discussion.request_next_round()` 之後才成功。
    **⚠️ 這是本包最重要的一個測試。**
19. **邊界 3**：`max_rounds=1` 時跑完第一輪，`request_next_round()` 仍照狀態機規則
    擋下（驗 `run_round` 沒有繞過它）。
20. `run_round()` 內部**沒有**呼叫 `request_next_round()`：跑完一輪後
    `phase` 是 `awaiting_user` 而不是 `ready`（與測試 13 同一件事，
    但這裡要用 `status()["phase"]` 明確斷言，因為它是 UI 讀的欄位）。
21. 忘記傳 `ask_fn` ⇒ `TypeError`（證明沒有預設值可以 fail-open 到真實 CLI）。

---

## 驗收條件（貼真實輸出，不要只描述）

1. `python3 -m unittest discover tests` **全過**，貼出最後三行。
   既有 **124** 個測試一個都不得減少或變紅。
   ⚠️ 011 那次回報「交付完成」但實跑是 `FAILED (errors=1)`。**請自己實際跑完再回報。**
2. 貼出只跑 `tests/test_engine_orchestrator.py` 的輸出。
3. **每一個對外可見的欄位都要有測試守住**——`run_round` 回傳的 `status()` 各欄位、
   失敗紀錄的七個欄位、`ask_fn` 收到的五個參數。收尾請自己逐項核對一次並列出對照表。
   ⚠️ 這條是因為 014 交付時 `status()` 的三個欄位沒有任何測試守住，把它們改成常數
   119 個測試照樣全過（015 才補掉）。**實作對不對與有沒有回歸防護是兩件事。**
4. **突變驗證四項**，每項：改壞 → 貼出失敗輸出 → 還原 → 最後貼還原後全過的結果。
   - (a) 把 `run_round()` 走訪的順序改成 `reversed(discussion.advisors)` ⇒ 順序測試翻紅。
   - (b) 把 `run_round()` 結尾的 `end_round()` 拿掉 ⇒ 測試 13／18 翻紅。
   - (c) 把 `build_prompt()` 改成只組本輪、不含先前各輪 ⇒ 測試 3 翻紅。
   - (d) 把 `run_round()` 的走訪對象從 `discussion.advisors` 改成 `discussion.seats`
     ⇒ 測試 9 翻紅（仲裁者被呼叫到）。
   - 改之前先斷言「檔案內容確實變了」（修改前後字串不同），否則沒套用會看起來像有覆蓋。
   - ⚠️ **突變只准動 `src/engine/orchestrator.py` 這一側，不准動測試檔、
     也不准動 `src/engine/state.py`。** 改到同時餵給對照組的東西，判定不會翻轉
     （010 與 013 都踩過）。
5. 貼出這兩個檢查的輸出：
   - `grep -nE 'import (subprocess|os|sys)|adapters|request_next_round' src/engine/orchestrator.py`
     ——**應為空**。
   - 測試檔對 `subprocess` / `adapters` 的同樣檢查（測試檔會 import `sys` 來加
     `sys.path`、會 import `state` 來取常數與 `parse_marker`，那兩個是允許的）。
6. 貼出 `git diff --stat` 與 `git status --short`，證明**只**新增了那兩個檔案、
   `src/engine/state.py` 與其他既有檔案都沒被動到。

---

## 不要做的事

- **不要接上真實的 adapter**：不要 import `adapters`、不要建立 `ask_fn` 的預設值、
  不要寫「接線」函式或 `__main__`。下一包做。
- **不要實作仲裁流程**（`SPEC.md` §6 第 6 點）。仲裁者在本包只是一個**不該被呼叫到**
  的席次。它的用量之後要自己併進累計，那是那一包的事。
- **不要加任何會自己往前走的東西**：多輪迴圈、`threading`、`asyncio`、排程、
  「自動開下一輪」的旗標、「全部人都說補充: 無 就自動再開一輪」。
  討論是序列的（`SPEC.md` §7），顧問**一個接一個**呼叫，不要平行化。
  邊界 1 是本專案存在的理由。
- **不要改 `src/engine/state.py`**。若你認為狀態機缺了什麼才能完成本包，
  **停手、寫進 `dispatch/BLOCKED.md`**，不要自己加方法。
- 不要做持久化／存檔／JSON 匯出（`SPEC.md` §8 明列延後）。
- 不要動 `src/adapters/` 底下任何檔案、`tests/` 既有的三個測試檔、
  `SPEC.md`、`AGENTS.md`、`CLAUDE.md`、`dispatch.sh`、`dispatch/` 底下任何檔案。
- 不要碰版控（`git add` / `commit` / `push` 一律不執行），改動留在工作區即可。
- 不要新增設定項、環境變數、命令列參數。
- 不要用 `dataclasses` / `enum` / 第三方套件把這幾個 dict 包起來
  （`SPEC.md` §7：標準函式庫優先、不加沒要求的抽象）。既有程式碼一律用純 dict，照做。
