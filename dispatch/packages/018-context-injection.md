# 工作包 018：專案脈絡注入

**動手前先整段讀完 `SPEC.md` §3.3（本包的規格，剛新增）**，另讀 §3.1、§6、§5 邊界 6。

顧問看不到使用者的專案（§3.3 說明了為什麼），所以「關於這個專案」的問題目前只能得到
通用答案。本包讓使用者可以顯式把脈絡送進去。

⚠️ **本包會修改兩個已經穩定、已被 167 個測試覆蓋的檔案**（`state.py`、
`orchestrator.py`）。**只准做下面明列的增修，不准順手改任何其他東西**，
既有測試一個都不得變紅。

---

## 檔案

| 檔案 | 動作 |
|---|---|
| `src/engine/state.py` | **增修**：`Discussion` 多一個選用參數 `context` |
| `src/engine/orchestrator.py` | **增修**：`build_prompt` 在最前面加一個脈絡區塊 |
| `src/engine/wiring.py` | **增修**：新增純函式 `format_context()` |
| `src/cli.py` | **增修**：新增 `--context` 參數 |
| `tests/test_engine_state.py` | 增加測試 |
| `tests/test_engine_orchestrator.py` | 增加測試 |
| `tests/test_engine_wiring.py` | 增加測試 |

⚠️ **不新增任何檔案。** 也不要動 `run.sh`——它已經會把多餘參數原樣轉給 `cli.py`。

⚠️ **既有的隔離規定全部延續**：`state.py` 與 `orchestrator.py` 與 `wiring.py`
**不得 import `subprocess`／`os`／`sys`／`adapters`**；`src/cli.py` 仍是唯一
允許 import `adapters` 的檔案；測試檔不得 import `adapters`／`cli`／`subprocess`。

---

## 介面契約（照字面實作，不要擴充公開介面）

### 1. `state.Discussion` 多一個選用參數

```python
def __init__(self, question: str, seats: list,
             max_rounds: int = DEFAULT_MAX_ROUNDS, context: str = "")
```

- `context` **必須是 `str`**，否則 `ValueError`（`None` 也不接受——空脈絡就用 `""`）。
  不做 `strip()`、不做長度上限、不做任何內容檢查。
- 存成屬性 `self.context`。
- ⚠️ **`context` 不得影響狀態機的任何其他行為**：不進 `status()`、不影響邊界判定、
  不影響 `record_speech` / `converged` / 用量累計。它只是一段被保管的字串。
- ⚠️ **`max_rounds` 仍是第三個位置參數，`context` 排第四。**
  既有呼叫端（`cli.py`、既有測試）用的是位置或關鍵字傳 `max_rounds`，
  順序改掉會靜默壞掉。

### 2. `orchestrator.build_prompt` 在最前面加脈絡區塊

`SPEC.md` §3.3：**脈絡在最前、問題其次、逐字稿再次、任務最後。**

- `discussion.context` **去空白後非空**時，在所有區塊之前插入：
  ```
  【專案脈絡】
  {discussion.context}
  ```
  （原文照送，**不要 strip、不要重排、不要加工**——`strip()` 只用於「判斷是不是空的」。）
- 去空白後為空 ⇒ **完全不輸出這個區塊**，輸出與現在完全相同（既有測試會守這件事）。
- 其餘組成規則一字不改（區塊之間仍以一個空行 `"\n\n"` 連接）。

### 3. `wiring.format_context(files) -> str`（純函式）

`files`：`[(檔名, 內容), ...]` 的 list。**本函式不開檔、不碰檔案系統**——
讀檔是 `cli.py` 的事，這裡只負責排版，這樣它才測得動。

- 空 list ⇒ 回 `""`。
- 否則每個檔案一段，段與段之間以一個空行連接：
  ```
  【檔案：{檔名}】
  {內容}
  ```
- ⚠️ **標頭用 `【檔案：…】`，不要用 `── … ──`。** 後者是逐字稿裡發言者的分隔符
  （`orchestrator.build_prompt`），兩者長一樣會讓顧問把檔案誤認成別人的發言。

### 4. `cli.py` 新增 `--context`

| 參數 | 說明 |
|---|---|
| `--context PATH` | **可重複**，選用。要送給顧問的脈絡檔案 |

- 依出現順序讀取每個檔案，**UTF-8**，讀進來後以 `format_context()` 排版，
  結果傳給 `state.Discussion(..., context=...)`。
- **讀不到檔案時**（不存在、沒權限、不是 UTF-8）⇒ 印出**可讀的錯誤訊息到 stderr
  並以退出碼 1 結束**，不要讓 Python traceback 噴到使用者臉上，
  也**不要**默默跳過那個檔案繼續跑（脈絡少一塊而使用者不知道，比直接失敗更糟）。
- 有指定 `--context` 時，在開始討論前印一行規模提示，例如：
  ```
  脈絡：2 個檔案、48,213 字元（每席次、每輪都會重送）
  ```
  ⚠️ **這行不是裝飾**。`SPEC.md` §3.3 明載脈絡會被重複計費，使用者必須在燒之前
  看得到規模。字元數用 `format_context()` 的結果去算（那才是真正送出去的東西）。
- ⚠️ **不要做自動摘要、不要自動掃描專案目錄、不要猜哪些檔案相關、不要設大小上限、
  不要截斷。** `SPEC.md` §3.3 明文禁止——送什麼由使用者指定。

---

## 測試

⚠️ 新增的測試**放進既有的三個測試檔**，不要新增檔案。既有測試一個都不得修改。

**`tests/test_engine_state.py`**

1. 不傳 `context` ⇒ `discussion.context == ""`。
2. 傳字串 ⇒ 原樣保存（含前後空白、換行都不變）。
3. `context=None`、`context=123` ⇒ 各自 `ValueError`。
4. `max_rounds` 仍可用**第三個位置參數**傳入（`Discussion(q, seats, 2)`），
   且此時 `context` 為 `""`。**這個測試是防參數順序被改掉的。**
5. `context` 不出現在 `status()` 的任何欄位裡。

**`tests/test_engine_orchestrator.py`**

6. 有脈絡時，`build_prompt` 的輸出**以 `【專案脈絡】` 開頭**，
   且 `【專案脈絡】` 出現在 `【原始問題】` 之前。
7. 有脈絡且已有前一輪發言時，四者順序為
   **脈絡 → 原始問題 → 【第 1 輪】 → 【你的任務】**（用 `index()` 逐一比大小）。
8. `context=""` 與 `context="   \n  "` ⇒ 輸出**完全不含** `【專案脈絡】`。
9. 脈絡原文（含其中的空行與縮排）**原封不動**出現在輸出裡。
10. `run_round()` 跑一輪，**每一位顧問收到的 prompt 都含脈絡**
    （不是只有第一位）。

**`tests/test_engine_wiring.py`**

11. 空 list ⇒ `""`。
12. 單檔 ⇒ `【檔案：SPEC.md】` 標頭在前、內容在後。
13. 兩個檔 ⇒ 兩段都在、順序與傳入順序相同、以一個空行分隔。
14. 標頭**不是** `── … ──` 形式（斷言輸出不含 `── SPEC.md ──`）。

---

## 驗收條件（貼真實輸出，不要只描述）

1. `python3 -m unittest discover tests` **全過**，貼出最後三行。
   **既有 167 個測試一個都不得減少或變紅**——本包是增修既有模組，這條特別重要。
   ⚠️ 011 那次回報「交付完成」但實跑是 `FAILED (errors=1)`。**請自己實際跑完再回報。**
2. 貼出 `python3 src/cli.py --help`，證明 `--context` 已加入且可重複。
3. **貼出一次 dry-run 的完整輸出**，指令：
   ```
   python3 src/cli.py "這個專案接下來該做什麼？" --context SPEC.md --advisor claude --arbiter codex
   ```
   應該看到規模提示那一行，以及 dry-run 回覆裡的 prompt 字元數**明顯變大**
   （脈絡進去了）。⚠️ **不要加 `--live`，一次都不要。**
4. 貼出讀不到檔案時的行為：`--context 不存在的檔.md` ⇒ **可讀的錯誤訊息＋退出碼 1**，
   不是 traceback。請一併貼出 `echo $?`。
5. **突變驗證三項**，每項：改壞 → 貼失敗輸出 → 還原 → 最後貼還原後全過的結果。
   - (a) 把脈絡區塊改成加在**問題之後** ⇒ 測試 6／7 翻紅。
   - (b) 把「空脈絡不輸出區塊」的判斷拿掉（一律輸出）⇒ 測試 8 翻紅。
   - (c) 把 `format_context` 的標頭改成 `── {檔名} ──` ⇒ 測試 12／14 翻紅。
   - 改之前先斷言檔案內容確實變了。
   - ⚠️ **突變只准動實作那一側**（`orchestrator.py` / `wiring.py`），
     不准動測試檔、不准動測試裡的樣本字串。
6. 貼出 `git diff --stat`，證明**只**動了契約表列的那七個檔案，且
   `src/adapters/` 底下、`run.sh`、`SPEC.md` 全都沒被動到。
7. 貼出隔離檢查：
   - `grep -nE 'import (subprocess|os|sys)|adapters' src/engine/state.py src/engine/orchestrator.py src/engine/wiring.py` ——**應為空**。
   - `grep -nE 'adapters|import cli|from cli|subprocess' tests/test_engine_wiring.py tests/test_engine_orchestrator.py tests/test_engine_state.py` ——**應為空**。

---

## 不要做的事

- ⚠️ **不要以 `--live` 執行任何東西。** 本包的紅線與 017 相同：真實呼叫由 Frank 親自按。
- ⚠️ **不要改 `Discussion.__init__` 既有參數的順序或名稱**，不要把 `context` 塞進
  `status()`，不要讓它影響任何邊界判定。
- ⚠️ **不要自動讀取專案檔案**：不要預設帶入 `SPEC.md`、不要掃目錄、不要 glob、
  不要「找不到就找找看有沒有 README」。`SPEC.md` §3.3 明文禁止。
- **不要做摘要、壓縮、截斷、去重、快取**。脈絡原文照送。
- **不要實作仲裁流程、不要實作多輪、不要做存檔／匯出**（`SPEC.md` §8 明列延後）。
- 不要動 `src/adapters/` 底下任何檔案、`run.sh`、`SPEC.md`、`AGENTS.md`、
  `CLAUDE.md`、`dispatch.sh`、`dispatch/` 底下任何檔案。
- 不要碰版控（`git add` / `commit` / `push` 一律不執行）。
- 不要新增環境變數、設定檔、第三方套件。
- 不要用 `dataclasses` / `enum` 包任何東西。既有程式碼一律純 dict，照做。
