# 工作包 017：接線層 ＋ 最小命令列進入點

**動手前先整段讀完 `SPEC.md` §4（Adapter 介面契約）、§2.2（席次必須揭露實際回答者）、
§5（六道邊界）、§6（討論流程）、§8（v1 範圍）。**

016 交付的 `orchestrator.run_round()` 的 `ask_fn` 是必填、沒有預設值，
所以引擎**目前碰不到任何真實 CLI，也就跑不起來**。本包把那條線接上，並給它一個
最小的命令列外殼，讓 council 第一次能端到端執行。

⚠️ **本包新增 `src/engine/wiring.py` 與 `src/cli.py` 與 `tests/test_engine_wiring.py`，
不動任何既有檔案**——`state.py`、`orchestrator.py`、`src/adapters/` 底下全部、
既有三個測試檔，一個字都不要改。

---

## 🔴 本包的紅線：你（builder）不准讓它打到真實 CLI

**接上真實 adapter 就等於接上 Frank 的付費訂閱。**`SPEC.md` §5 記錄的實測是
`claude` 光固定系統提示就約 **1.5 萬 token／次**，與問題長短無關。
本包的驗證由三段組成，**你只負責第一段**：

| 階段 | 由誰做 | 允許打到真實 CLI |
|---|---|---|
| ① 單元測試 ＋ dry-run 實跑 | **你（builder）** | ❌ **絕對不可以** |
| ② 假執行檔 PATH 下的端到端測試 | 主對話（reviewer） | ❌（假的執行檔） |
| ③ 第一次真實呼叫 | Frank 本人 | ✅ 由他親自決定時機 |

具體要求：

- ⚠️ **你不得以 `--live` 執行 `src/cli.py`，一次都不行。** 你只能跑不加 `--live` 的
  dry-run，以及 `python3 -m unittest`。
- ⚠️ **`--live` 必須是「明確加上去才會花錢」的旗標**（`action="store_true"`，預設
  `False`）。**不准反過來做成 `--dry-run` 旗標**——那樣預設值就是花錢，忘記加旗標
  的代價由 Frank 的帳單承擔。010 那包的 `bin="${PROBE_X_BIN:-claude}"`
  就是這個錯誤，**本專案最貴的一種 bug**。
- ⚠️ **`src/engine/wiring.py` 不得 import `adapters`。** 它只接受一個
  `registry`（dict）當參數，不自己去找真的 adapter。
- ⚠️ **`src/cli.py` 是整個 repo 唯一允許 import `adapters` 的檔案。**
- ⚠️ **測試檔不得 import `adapters`、不得 import `cli`、不得 import `subprocess`**，
  一律用測試檔內自己定義的假 registry。

---

## 檔案

- `src/engine/wiring.py`——接線層與可測的純函式。
- `src/cli.py`——命令列進入點。**放在 `src/` 底下**，這樣 `python3 src/cli.py`
  執行時 `src/` 自動在 `sys.path` 上，不需要任何 path 手腳。
- `tests/test_engine_wiring.py`——本包全部的測試（**只測 `wiring.py`**）。

---

## 介面契約（照字面實作，不要擴充公開介面）

### `src/engine/wiring.py`

#### 1. `parse_seat_spec(spec: str, seat_id: str, role: str) -> dict`

把命令列上的一個席次字串轉成 `state.Discussion` 吃的席次 dict。

- `"claude"` ⇒ `{"seat_id": seat_id, "cli": "claude", "model": None, "role": role}`
- `"gemini:gemini-2.5-pro"` ⇒ `model` 為 `"gemini-2.5-pro"`
- **只從左邊數第一個 `:` 切一次**（`str.split(":", 1)`）。
  ⚠️ `opencode` 的模型名長得像 `provider/model`，未來也可能含 `:`，
  切太多刀會把模型名切壞。
- `spec` 去空白後為空、或 `:` 左邊為空、或有 `:` 但右邊為空 ⇒ `ValueError`
  （訊息要講清楚是哪一種）。
- ⚠️ **不要驗證 `cli` 是不是四家之一**——那需要 import `adapters`，違反上面的隔離。
  未知的 CLI 由 `cli.py` 的 `detect()` 階段擋（見下）。

#### 2. `make_ask_fn(registry) -> callable`

`registry`：`{cli_id: 具有 .ask() 的物件}`。**必填，沒有預設值，不得 fallback。**

回傳一個符合 016 契約的 `ask_fn`：

```python
def ask_fn(cli, prompt, model, timeout_s, max_chars) -> dict
```

行為：

- `cli` 不在 `registry` ⇒ `ValueError`（訊息含該 `cli` 與可用的 id 清單）。
- 否則呼叫 `registry[cli].ask(prompt=prompt, model=model, timeout_s=timeout_s,
  max_chars=max_chars)` 並**原樣回傳**，不加工、不補欄位、不吞例外。
  ⚠️ **一律用關鍵字呼叫。** `adapters` 的 `ask()` 簽章是
  `(prompt, model, timeout_s, max_chars)`，與 `ask_fn` 的參數順序不同，
  用位置參數會無聲對錯位置。
- ⚠️ **不要在這裡 retry、不要記 log、不要計時。** 逾時與截斷是 adapter 的事
  （`SPEC.md` §4），失敗記錄是 `orchestrator` 的事（016）。這一層只做轉接。

#### 3. `dry_run_ask_fn(cli, prompt, model, timeout_s, max_chars) -> dict`

不呼叫任何東西的假回覆，供 `--live` 未指定時使用。回傳：

```python
{"ok": True,
 "text": f"【DRY RUN】{cli} 未被實際呼叫。收到 prompt {len(prompt)} 字元、"
         f"model={model}、timeout_s={timeout_s}、max_chars={max_chars}。\n"
         "[立場: 保留] [補充: 有]",
 "truncated": False, "error": None, "elapsed_s": 0.0,
 "model_used": None, "usage": None}
```

- ⚠️ **`text` 必須以 `【DRY RUN】` 開頭**，讓假輸出在畫面上一眼可辨，
  不可能被誤當成真實回覆。
- ⚠️ 最後一行的立場標記固定是 **`[立場: 保留] [補充: 有]`**——`補充: 有` 代表
  「不收斂」。dry-run **不可以**產生「看起來收斂了」的假訊號。

### `src/cli.py`

```
python3 src/cli.py "問題" --advisor claude --advisor gemini:某模型 --arbiter codex
```

參數（用標準庫 `argparse`，不要加第三方套件）：

| 參數 | 說明 |
|---|---|
| 位置參數 `question` | 必填，討論的原始問題 |
| `--advisor SPEC` | 可重複，**至少一個**。格式同 `parse_seat_spec` |
| `--arbiter SPEC` | **必填，恰好一個**（`state.Discussion` 要求恰好一個仲裁者） |
| `--live` | `action="store_true"`，**預設 `False`**。加了才會真的呼叫 CLI |
| `--timeout-s` | 預設 `orchestrator.DEFAULT_TIMEOUT_S` |
| `--max-chars` | 預設 `orchestrator.DEFAULT_MAX_CHARS` |

⚠️ **`--arbiter` 必填是刻意的**，即使仲裁流程還沒實作、它這一輪不會發言。
理由：狀態機要求恰好一個仲裁者，讓使用者現在就習慣指定，之後接上仲裁流程不必改介面。
**請在 `--arbiter` 的 help 文字裡註明「v1 尚未實作仲裁流程，本席次此輪不會發言」。**

`seat_id` 的產生規則（**不要讓使用者指定**）：

- 顧問依出現順序為 `f"{cli}-{i+1}"`（i 由 0 起算）。
  ⚠️ 這樣同一個 CLI 開兩個席次也不會撞 id（`SPEC.md` §2.1 允許）。
- 仲裁者固定為 `"arb"`。

執行流程：

1. 解析參數，用 `parse_seat_spec` 組出席次 list（顧問們在前、仲裁者在最後）。
2. **`--live` 時先跑 `detect()`**：對每個用到的 CLI id 呼叫
   `adapters.ADAPTERS[cli].detect()`，**任一個 `installed` 為假或 id 不存在
   ⇒ 印出錯誤並以非零退出碼結束，不進入討論**。
   ⚠️ `SPEC.md` §4 明訂 `detect()` 不消耗額度，所以這一步是免費的保險：
   打錯一個 CLI 名字就在燒錢前擋下來。
   ⚠️ **未指定 `--live` 時不要呼叫 `detect()`**——dry-run 應該在沒裝任何 CLI
   的機器上也能跑完。
3. 建立 `state.Discussion(question, seats)`。
4. `ask_fn = make_ask_fn(adapters.ADAPTERS) if args.live else dry_run_ask_fn`。
5. **`--live` 時**，在真正開始前印一行醒目的警告，例如
   `⚠️ LIVE 模式：即將對 N 個席次發出真實呼叫，會消耗訂閱額度。`
   ⚠️ **不要做互動確認（不要 `input()`）**——headless 執行會卡死。
   旗標本身就是那道確認。
6. 呼叫 `orchestrator.run_round(discussion, ask_fn, timeout_s=..., max_chars=...)`。
7. 印出本輪逐字稿與狀態（格式見下）。
8. **結束。一次執行 ＝ 一輪。**

⚠️ **不要做多輪迴圈、不要問「要不要再一輪」、不要存檔。**
「再一輪」需要保存討論狀態，而 `SPEC.md` §8 明列**討論存檔與匯出延後**。
多輪是 web UI（§7）的事。邊界 1 在這裡的體現就是：**程式跑完一輪就結束。**

輸出格式（純文字，不要加顏色碼、不要用第三方套件排版）：

```
每位顧問一段：
  ── {seat_id} ──
  {text}
  （回答者：{model_used}）        ← model_used 為 None 時印「（回答者：未經確認）」
  失敗時改印：（未回應：{error}）

最後印狀態摘要，至少含：
  已完成輪數 / 上限、是否達上限（at_cap）、是否收斂（converged）、
  格式違規次數（format_violations）、
  總呼叫次數與累計 usage、以及各席次分計（by_seat）
```

⚠️ **`model_used` 為 `None` 一定要印成「未經確認」，不可以拿我們送出的 `model`
頂替。** `SPEC.md` §2.2 的可見性要求就是為了偵測 CLI 偷換模型，回顯等於把這個
偵測關掉。

⚠️ **`usage` 的呈現直接印狀態機給的數字，不要自己換算、不要估算 token、
不要把不同 CLI 的鍵名合併。**`SPEC.md` §4：不要自行估算 token，估錯比沒有更糟。

---

## 測試（`tests/test_engine_wiring.py`，只測 `wiring.py`）

⚠️ **不得 import `adapters`、`cli`、`subprocess`，不得用 `unittest.mock` patch
真模組，不得啟動任何子行程。** 假 registry 用測試檔內自己定義的小類別即可。
收尾請貼出證明沒有這些 import 的 `grep` 輸出。

**`parse_seat_spec`**

1. `"claude"` ⇒ `cli` 正確、`model` 為 `None`、`seat_id` 與 `role` 照傳入值。
2. `"gemini:gemini-2.5-pro"` ⇒ `model` 正確。
3. `"opencode:provider/model:x"` ⇒ `cli` 為 `opencode`、
   **`model` 為 `"provider/model:x"`**（只切第一刀）。
4. 空字串、`":model"`、`"claude:"`、只有空白 ⇒ 各自 `ValueError`。

**`make_ask_fn`**

5. 回傳的 `ask_fn` 呼叫到正確的 adapter：兩個 id 的假 registry，
   指定其中一個 ⇒ 只有那一個的 `.ask` 被呼叫。
6. **參數是以關鍵字傳遞且對應正確**：假 adapter 記錄收到的 `prompt` / `model` /
   `timeout_s` / `max_chars`，逐項斷言。
   ⚠️ 假 adapter 的 `ask` 請定義成 `def ask(self, *, prompt, model, timeout_s,
   max_chars)`（**keyword-only**）——這樣萬一實作改用位置參數，測試會直接爆掉。
   **這是本包最重要的一個測試。**
7. adapter 的回傳被**原樣**回傳（同一個 dict 內容，未被加工）。
8. 未知的 `cli` ⇒ `ValueError`，且訊息含該 `cli` 名稱。
9. adapter 的 `ask` 拋例外時，`ask_fn` **不吞掉**（例外往外傳；失敗記錄是
   orchestrator 的責任，不是這一層的）。
10. `make_ask_fn` 少傳 `registry` ⇒ `TypeError`（無預設值）。

**`dry_run_ask_fn`**

11. 回傳 `ok=True`、`text` 以 `【DRY RUN】` 開頭、`usage` 為 `None`、
    `model_used` 為 `None`。
12. `text` 的最後一行餵進 `state.parse_marker()` ⇒
    `violation` 為 `False` **且 `more` 為 `True`**（dry-run 不得偽造收斂訊號）。

**接起來（仍然零真實 CLI）**

13. 用假 registry 組 `ask_fn`，餵進 `orchestrator.run_round()` 跑完一輪 ⇒
    每個假 adapter 各被呼叫一次、`status()["usage"]["calls"]` 正確、
    `phase` 為 `awaiting_user`。
14. 用 `dry_run_ask_fn` 跑完整一輪 ⇒ 一樣正常結束，且
    `status()["converged"]` 為 **`False`**（因為 dry-run 一律回「補充: 有」）。

---

## 驗收條件（貼真實輸出，不要只描述）

1. `python3 -m unittest discover tests` **全過**，貼出最後三行。
   既有 **149** 個測試一個都不得減少或變紅。
   ⚠️ 011 那次回報「交付完成」但實跑是 `FAILED (errors=1)`。**請自己實際跑完再回報。**
2. 貼出只跑 `tests/test_engine_wiring.py` 的輸出。
3. 貼出 `python3 src/cli.py --help` 的完整輸出，
   **證明 `--live` 是需要明確加上的旗標**（不是預設開啟、也不是 `--dry-run`）。
4. **貼出一次 dry-run 的完整實跑輸出**，指令用：
   ```
   python3 src/cli.py "測試問題" --advisor claude --advisor gemini --arbiter codex
   ```
   應該看到兩段 `【DRY RUN】` 的顧問發言、仲裁者沒有發言、以及狀態摘要。
   ⚠️ **不要加 `--live`。一次都不要。**
5. **每一個對外可見的欄位都要有測試守住**——`parse_seat_spec` 回傳的四個鍵、
   `ask_fn` 傳給 adapter 的四個參數、`dry_run_ask_fn` 回傳的七個鍵。
   收尾請自己逐項核對一次並列出對照表。
   （014 交付時 `status()` 三個欄位沒有測試守住，改成常數後測試照樣全過。）
6. **突變驗證三項**，每項：改壞 → 貼出失敗輸出 → 還原 → 最後貼還原後全過的結果。
   - (a) 把 `make_ask_fn` 改成不傳 `model`（寫死 `model=None`）⇒ 測試 6 翻紅。
   - (b) 把 `parse_seat_spec` 的 `split(":", 1)` 改成 `split(":")` ⇒ 測試 3 翻紅。
   - (c) 把 `dry_run_ask_fn` 的標記改成 `[立場: 同意] [補充: 無]` ⇒ 測試 12／14 翻紅。
   - 改之前先斷言「檔案內容確實變了」，否則沒套用會看起來像有覆蓋。
   - ⚠️ **突變只准動 `src/engine/wiring.py` 這一側**，不准動測試檔、
     不准動 `state.py` / `orchestrator.py`。
7. 貼出這三個檢查的輸出：
   - `grep -n adapters src/engine/wiring.py` ——**應為空**。
   - `grep -nE 'adapters|import cli|from cli|subprocess|unittest.mock' tests/test_engine_wiring.py`
     ——**應為空**。
   - `grep -rn "live" src/cli.py | head` ——用來人工確認預設值方向正確。
8. 貼出 `git diff --stat` 與 `git status --short`，證明**只**新增了那三個檔案。

---

## 不要做的事

- ⚠️ **不要以 `--live` 執行任何東西。** 這是本包的首要紅線。
- ⚠️ **不要為了「試試看能不能通」而直接呼叫 `adapters.*.ask()`**，
  也不要寫任何會呼叫它的臨時腳本。要驗證接線，用假 registry。
- **不要實作仲裁流程**（`SPEC.md` §6 第 6 點）。`--arbiter` 只是把席次建起來。
- **不要實作多輪**：不要迴圈、不要 `input()` 互動、不要「自動再開一輪」。
  一次執行一輪，跑完就結束。邊界 1 是本專案存在的理由。
- **不要做討論存檔／JSON 匯出／log 檔**（`SPEC.md` §8 明列延後）。
- **不要動 `src/adapters/` 底下任何檔案。** 若你認為某個 adapter 有 bug，
  **停手、寫進 `dispatch/BLOCKED.md`**，不要順手修——那是會真的打到 CLI 的程式碼，
  改它必須由 Frank 決定驗證方式。
- 不要動 `state.py`、`orchestrator.py`、`tests/` 既有的四個測試檔、
  `SPEC.md`、`AGENTS.md`、`CLAUDE.md`、`dispatch.sh`、`dispatch/` 底下任何檔案。
- 不要碰版控（`git add` / `commit` / `push` 一律不執行），改動留在工作區即可。
- 不要新增環境變數、設定檔、第三方套件（`SPEC.md` §7：標準函式庫優先）。
- 不要用 `dataclasses` / `enum` 把席次 dict 包起來。既有程式碼一律用純 dict，照做。
