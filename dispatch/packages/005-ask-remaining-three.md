# 工作包 005：claude / codex / gemini 三家的 ask()

先讀 `SPEC.md` §4（介面契約）、§4.1（各 CLI 呼叫方式）、§4.2（顧問唯讀）、§5（停止邊界）。

形狀一律比照已完成的 `src/adapters/opencode.py`，那是本包的參考範本。

---

## 0. 前提：真實輸出樣本已經幫你抓好了

`tests/fixtures/` 下有三家 CLI 的**真實輸出樣本**，由主對話實機呼叫後擷取並去識別化。

**你要照著這些樣本寫解析，不要憑猜測，也不要自己去呼叫真實 CLI。**
呼叫真實 CLI 會消耗使用者的付費訂閱額度，這是本專案的硬禁令（`AGENTS.md`）。

樣本檔名與對應關係寫在 `tests/fixtures/README.md`。

---

## 1. 先改介面：`src/adapters/base.py` 的 `run()`

現簽章有兩個問題，本包一併修掉：

```python
# 現在
def run(argv: list, timeout_s: int, max_chars: int) -> dict

# 改成
def run(argv: list, timeout_s: int, cwd: str | None = None) -> dict
```

**移除 `max_chars`**：它被收下但函式內完全沒用到，截斷實際上是各 adapter 自己呼叫
`truncate()` 完成的。留著會讓下一個讀的人以為 `run()` 有做截斷。

**新增 `cwd`**：傳給 `subprocess.run(..., cwd=cwd)`。`cwd=None` 時維持現行行為。
理由見下一節——`claude` 與 `gemini` 沒有 opencode 那種 `--dir` 旗標，
要把顧問圈在空白暫存目錄裡**只能靠子行程的工作目錄**。

**另外一律加上 `stdin=subprocess.DEVNULL`**（不是參數，是寫死的行為）。
四家 CLI 都會試圖讀 stdin，不關掉會讓行程卡住（見 §2.1 的坑）。
這對 `opencode` 也是好事，順帶修掉。

所有呼叫點（含 `opencode.py` 與測試中直接呼叫 `base.run()` 的地方）一併更新。

## 2. 三個 adapter 的 `ask()`

簽章維持 `SPEC.md` §4 規定的 `ask(prompt, model, timeout_s, max_chars) -> dict`，不得更動。

**四家共通、逐字照 `opencode.py` 抄的部分**（不要重新發明）：

- prompt 超過 `MAX_ARG_CHARS` → 立刻回 `ok=False`，**不啟動子行程**
- `shutil.which()` 找不到執行檔 → `ok=False`，錯誤訊息說明是哪個 CLI 找不到
- 每次呼叫建一個**當次專用的空白暫存目錄**，用完刪除
- 萃取不到任何文字 → `ok=False` 並說明，**不得回傳空字串假裝成功**
- 最後才對萃取出的文字套 `truncate()`

### 2.1 指令形式（2026-08-03 **實機呼叫**驗證過，照抄即可）

⚠️ 這比 `SPEC.md` §4.1 記載的精確，因為 §4.1 寫於實作前、且**有兩處實測是錯的**。
以本節為準。`SPEC.md` 由主對話另行更新，**你不要改它**。

| id | argv | 唯讀機制 | 暫存目錄怎麼給 |
|---|---|---|---|
| `claude` | `claude -p <prompt> --output-format json --tools ""` | `--tools ""` 停用全部內建工具 | `cwd=` |
| `codex` | `codex exec --sandbox read-only --skip-git-repo-check --output-last-message <檔案> <prompt>` | `--sandbox read-only` | `-C <暫存目錄>` |
| `gemini` | `gemini -p <prompt> -o json --approval-mode plan --skip-trust` | `--approval-mode plan` | `cwd=` |

指定模型：`claude` 用 `--model`、`codex` 用 `-m`、`gemini` 用 `-m`。
`model` 為 `None` 時**完全不要加**該旗標，使用 CLI 預設模型。

**唯讀是硬要求**（`SPEC.md` §4.2）。上表的機制層手段不得省略、不得改成
「在 prompt 裡請模型不要動檔案」。

#### ⚠️ 兩個實測踩到的坑，必做

- **stdin 一定要導向 `/dev/null`**（三家皆是）。也就是 `subprocess` 呼叫時傳
  `stdin=subprocess.DEVNULL`。不這樣做，`claude` 會卡住整個行程——實測從 9.9 秒
  暴增到 176 秒後才被強制終止。這要加在 `base.run()` 裡，四家共用。
- **`gemini` 少了 `--skip-trust` 會直接失敗**（exit 55），而且會把
  `--approval-mode plan` 無聲改回 `default`。兩個旗標要一起給。

細節與證據見 `tests/fixtures/README.md`，動手前先讀那份。

### 2.2 三家的輸出各不相同

- **`claude`**：回**單一 JSON 物件**（不是事件流）。文字在 `result`。
  ⚠️ **必須先檢查 `is_error`**：失敗時仍是合法 JSON，但**沒有 `result` 欄位**，
  直接取會變成 `KeyError` 而不是可讀錯誤。兩種情況的樣本都在 fixtures 裡。
- **`gemini`**：回**單一 JSON 物件**，文字在 `response`。
- **`codex`**：`--output-last-message` 把最終回覆**以純文字寫進你指定的檔案**，
  這家**完全不需要解析 JSON**——讀那個檔案即可。檔案開在該次的暫存目錄內。
  ⚠️ 該檔案**結尾沒有換行符**，不要假設有。
  ⚠️ 檔案不存在或內容空白 → `ok=False`，不要回空字串假裝成功。

`claude` 與 `gemini` 都要處理「stdout 不是合法 JSON」的情況 → `ok=False` 加可讀錯誤，
不得讓 `json.JSONDecodeError` 直接往外拋。

## 3. 測試（延伸 `tests/test_adapters_ask.py`）

標準庫 `unittest`。**不得呼叫真實 CLI**，沿用該檔現有的「假可執行腳本 + 改 PATH」手法。

三家各自至少涵蓋：

- 正常輸出（**假腳本吐的內容請取自 `tests/fixtures/`**）→ 正確萃取文字、`ok=True`
- 超過 `max_chars` → `truncated=True` 且文字確實被截斷
- 逾時 → `ok=False`，錯誤訊息含逾時字樣（用很短的 timeout，別讓測試跑很久）
- 非零退出 → `ok=False` 且錯誤可讀
- 輸出解析不出文字（含 `codex` 的檔案沒被寫出來這個情況）→ `ok=False`
- prompt 超過長度上限 → `ok=False`，且**根本沒有啟動子行程**（實際驗證這點）

另補一項共通測試：**`model=None` 時 argv 裡不含模型旗標，給了 `model` 時才有。**
（設法讓假腳本把收到的 argv 記下來供斷言。）

⚠️ 上一輪你被抓到寫過一個**恆真的斷言**。本輪請自己反向檢查：
每個斷言都要能因為程式碼壞掉而失敗。做不到的斷言不要寫。

## 4. 自我驗證

1. `python3 -m unittest discover tests -v` 全數通過，貼出**真實輸出與耗時**。
2. 說明每家的解析各對應 fixture 的哪個欄位／哪種形狀。
3. 沒跑過的不要說它會動；沒驗證的部分明確標「未驗證」。

## 5. 界線

- 不改 `SPEC.md`、`AGENTS.md`、`dispatch.sh`、`README.md`、`LICENSE`
- 不改 `tests/fixtures/` 下的樣本檔（那是證據，不是素材）
- 不動 `detect()` 既有邏輯，不動 `opencode.py` 的 `ask()` 解析邏輯
  （只有 `base.run()` 簽章變更連帶的那一行要改）
- 不呼叫任何真實 CLI
- 不 `git add` / `git commit`
- 不引入第三方套件
- 不新增沒被要求的功能、抽象層、設定項
