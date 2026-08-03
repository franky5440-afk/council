# council 規格

版本 v0.1（2026-08-03）。本檔是實作的**唯一契約來源**；工作包只引用本檔，不重述。

---

## 1. 這是什麼

一個本機執行的 orchestrator，讓使用者在**同一個對話框**裡同時徵詢 3～4 個不同的 AI，
彼此看得見、輪流發言，最後由使用者指定的**仲裁者**整合出結論。

**核心設計決定：council 不串接任何模型 API。**
它驅動使用者自己安裝並登入的官方 CLI 子行程（`claude` / `codex` / `gemini` / `opencode`），
因此吃的是使用者自己的**訂閱額度**，而非計費 API。

這個選擇同時決定了三件事：

- council **不接觸、不儲存、不轉發任何憑證**。登入狀態由各家 CLI 自己管。
- 不繞過任何服務條款，因此本專案可以公開發布。
- 使用者必須自備並登入 CLI。目標客群是清楚這件事、也清楚**這會大量消耗自己額度**的進階使用者。

### 非目標（v1 明確不做）

- 不做帳號代管、不做登入引導自動化
- 不做 API key 模式（即使技術上更簡單）
- 不做手機端
- 不做討論內容的雲端同步

---

## 2. 名詞

| 名詞 | 定義 |
|---|---|
| 席次 seat | **一個 `(CLI, 模型)` 組合**。席次才是議會的成員單位，不是 CLI |
| 顧問 advisor | 參與討論的席次，2～4 個 |
| 仲裁者 arbiter | 指定一個席次擔任。**不參與討論**，但看得見全部發言 |
| 一輪 round | 每位顧問各發言一次，順序固定 |
| 逐字稿 transcript | 由 council 自己保存的完整發言紀錄，是組 prompt 的唯一依據 |

### 2.1 一個 CLI 可以提供多個席次

**議會的成員是席次，不是 CLI。** 四個 CLI 都支援 `--model` 指定模型，
因此同一個 CLI 可以同時佔用多個席次、各跑不同模型。

2026-08-03 實測：`opencode` 以 `-m` 分別跑 `deepseek-v4-flash-free` 與
`nemotron-3-ultra-free`，兩者各自回報不同身分，互不干擾。

兩個直接後果：

- 使用者可以組出**完全由免費模型構成的議會**（例如 opencode 之下的數個 free 模型），
  不動用任何付費訂閱。
- 開發與測試時，`ask()` 的驗證可以全部跑在免費席次上，**不消耗任何人的付費額度**。

---

## 3. 架構

```
 使用者 ─▶ 本機服務（討論引擎）─▶ Adapter ─▶ CLI 子行程 ─▶ 各家訂閱
              │
              └── transcript（council 自己保存）
```

### 3.1 關鍵決定：Adapter 無狀態，逐字稿由 council 自己管

每次呼叫 CLI 都是**獨立、無狀態**的一次性請求；council 自己把逐字稿組進 prompt，
**不使用各家 CLI 的 session 續談功能**。理由：

1. `gemini` 沒有續談旗標，四家語意不統一，硬要統一會做出最脆弱的那一層。
2. 「誰看得到什麼」必須由 council 精確控制——仲裁者不參與討論卻要看得見全部發言，
   這個需求在「我們自己組 prompt」的前提下是免費的，靠 CLI session 反而做不到。
3. 無狀態的 adapter 可以獨立測試，壞掉時責任邊界清楚。

代價：每輪重送逐字稿，token 消耗較高。**接受**——使用者吃的是訂閱額度，
且第 5 節的邊界會把總量壓在可控範圍。

---

## 4. Adapter 介面契約

每個 CLI 一個 adapter，**只准實作這兩個函式**，不得增加公開介面。

```python
def detect() -> dict:
    """偵測此 CLI 是否可用。不得執行任何會消耗額度的呼叫。
    回傳：
      {"id": str, "installed": bool, "path": str|None,
       "version": str|None, "error": str|None}
    """

def ask(prompt: str, model: str | None, timeout_s: int, max_chars: int) -> dict:
    """送出一次性請求並取回純文字答覆。
    model=None 代表使用該 CLI 的預設模型；否則以該 CLI 的 --model 旗標指定。
    必須：以子行程呼叫 CLI 的非互動模式；逾時強制終止；
          輸出超過 max_chars 時截斷並標記 truncated=True。
    不得：續用 session、寫入專案外檔案、要求互動確認。
    回傳：
      {"ok": bool, "text": str, "truncated": bool,
       "error": str|None, "elapsed_s": float}
    """
```

⚠️ `src/adapters/` 目前的 `ask()` 佔位簽章**尚未包含 `model`**，實作 `ask()` 的
工作包必須一併更新四個模組與相關測試。

### 4.1 各 CLI 的非互動呼叫方式（2026-08-03 實測）

| id | 指令 | 指定模型 | 唯讀／限制 | 回覆文字在哪 |
|---|---|---|---|---|
| `claude` | `claude -p <prompt> --output-format json --tools ""` | `--model` | `--tools ""` 停用全部內建工具 | JSON 的 `result` |
| `codex` | `codex exec --sandbox read-only --skip-git-repo-check --output-last-message <檔案> <prompt>` | `-m` | `--sandbox read-only`，`-C` 圈住目錄 | 該檔案的純文字 |
| `gemini` | `gemini -p <prompt> -o json --approval-mode plan --skip-trust` | `-m` | `--approval-mode plan` | JSON 的 `response` |
| `opencode` | `opencode run --format json --agent advisor <prompt>` | `-m`（`provider/model`） | 自訂 agent 逐項 `deny`（見 §4.2） | 事件流中 `type=="text"` |

2026-08-03 **實機呼叫**四家各一次驗證上表；真實輸出樣本存於 `tests/fixtures/`，
擷取過程中發現的坑記於該目錄的 `README.md`，實作前必讀。其中兩點會直接讓呼叫失敗：

- **stdin 必須導向 `/dev/null`**（四家皆會讀 stdin）。未導向時 `claude` 會卡住，
  實測單次呼叫由 9.9 秒暴增為 176 秒後才被強制終止。
- **`gemini` 必須同時給 `--skip-trust`**，否則在不受信任的目錄會以 exit 55 中止，
  且 `--approval-mode plan` 會被**無聲**改回 `default`——唯讀保證會在使用者不知情下失效。

⚠️ **這些旗標是 2026-08-03 當天的事實，不是永久契約。** CLI 改版會變。
adapter 必須在 `detect()` 取得版本，並在 `ask()` 失敗時回傳可讀的錯誤，
而不是讓使用者看到一坨 stderr。

### 4.2 顧問一律唯讀

顧問的職責是出意見，不是動手。所有 adapter 必須以各 CLI 提供的**機制層**手段
限制工具與檔案存取，不得只靠 prompt 拜託模型別亂動。

#### `opencode` 的唯讀怎麼做（2026-08-03 實測確定）

⚠️ **`--dir` 不是權限邊界。** 曾誤記為「`--dir` 圈住工作目錄」，那是錯的——
`opencode run --help` 對它的說明只有 "directory to run in"。實測：`--dir` 指向空白
暫存目錄後，opencode 仍能用 bash 寫檔到該目錄**之外**，且全程沒有任何批准提示。

⚠️ **內建的 `--agent plan` 也不夠。** 其權限清單中 `edit` 為 `deny`，但**沒有任何
`bash` 條目**，bash 因而落在 `*: allow` 之下。實測它沒寫成檔案，但模型的回覆是
「目前處於 Plan Mode，不能執行寫檔操作」——那是**模型自願遵守**，屬 prompt 層，
正是本節禁止依賴的東西。換一個不那麼配合的模型就不成立。

**正解**：由 council 在當次的暫存目錄內寫一個自訂 agent 定義
`<暫存目錄>/.opencode/agents/advisor.md`，以 frontmatter 的 `permission` 區塊逐項
`deny`（至少 `bash`、`edit`、`webfetch`、`task`、`websearch`），再以 `--agent advisor` 執行。

實測此法確為機制層生效：事件流中**完全沒有 bash 工具呼叫**（該工具不存在），
stderr 出現 `permission requested: external_directory (...); auto-rejecting`，
目標檔案未被建立。

⚠️ **但 `--agent` 是 fail-open 的，必須自行補上失敗關閉。** 實測 `--agent` 指向
不存在的 agent 時，opencode **無聲退回完全可寫的預設 agent**、exit code 仍為 0、
檔案照樣被寫出，唯一訊號是 stderr 的一行
`agent "..." not found. Falling back to default agent`。
因此 adapter **必須**檢查 stderr 是否出現該退回訊息，出現即回 `ok=False`——
不得讓唯讀保證在無人察覺的情況下消失。

⚠️ 本專案自己的 `dispatch.sh` 同樣只用 `--dir`，所以 builder 被「關在 council
目錄內」這個說法**沒有機制層保證**。派工時要當成 builder 有能力寫到任何地方。

---

## 5. 停止邊界（本專案最重要的一節）

前提：AI 看到 input 就會產出 output，不會自己收斂。因此邊界必須由 council 施加，
且**機制層優先於 prompt 層**。共六道：

1. **輪與輪之間一定要人。** 一輪之內顧問自動連續發言（這是「熱鬧」的來源），
   但一輪結束後**永不自動進入下一輪**，等使用者按「再一輪」或「叫仲裁者」。
   這是最關鍵的一道——它把失控的可能性直接交回人手上。
2. **單次發言長度上限**（`max_chars`，預設 8000 字元）。超過即截斷並標記，
   避免一家把後面的人 context 撐爆。
3. **輪數硬上限**（預設 5 輪）。達上限後只剩「叫仲裁者」或「明確確認再開一輪」兩條路。
4. **逾時強制終止**（`timeout_s`，預設 **180 秒**）。子行程逾時即 kill，該顧問本輪記為
   「未回應」，討論繼續，不整場卡死。

   預設值原為 120 秒，2026-08-03 實測後調整為 180：`gemini` 遇到 503 會**自行重試並退避**，
   實測兩次**成功**的呼叫分別耗時 **119.5 秒**與 **102.5 秒**，前者差 0.5 秒就會被舊上限
   砍掉、並被誤記為「未回應」。證據見 `tests/fixtures/gemini_success.json` 的
   `stats.models.*.api`（`totalRequests: 3`、`totalErrors: 2`）。
   代價是卡住的顧問要多等一分鐘；但「把成功的回覆誤殺並謊報未回應」比多等更糟。
5. **收斂偵測**：每位顧問回覆結尾必須輸出一行
   `[立場: 同意|保留|反對] [補充: 有|無]`。
   全體皆「補充: 無」時，UI 提示可以收斂了。
   模型沒輸出這行 → 保守視為「補充: 有」並記錄一次格式違規（不重試、不懲罰）。
6. **額度可見性**：UI 常駐顯示本次討論已呼叫次數（總計與各家分計）。
   既然會大量燒額度，使用者必須隨時看得到自己燒了多少。

---

## 6. 討論流程

1. 使用者設定 2～4 個模型，指定其中一個為仲裁者（仲裁者**不列入**顧問輪替）。
2. 使用者提問。
3. 一輪開始，顧問依固定順序逐一發言。第 N 位收到的 prompt 包含：
   原始問題 + 本輪前 N-1 位的發言 + 先前各輪完整逐字稿。
4. 一輪結束，停下來等使用者（邊界 1）。
5. 使用者可：再開一輪 / 追問 / 叫仲裁者。
6. 仲裁者被呼叫時，收到完整逐字稿與原始問題，輸出整合結論。
   仲裁者**不曾**參與任何一輪發言。

---

## 7. 技術選型

- **Python 3**，標準函式庫優先，非必要不加依賴。理由：本機是 2012 iMac，
  避免建置步驟與重框架；同層 `lottrey` 亦為 Python。
- 本機服務：`http.server.ThreadingHTTPServer` + SSE 推送。討論本身是序列的，
  併發需求極低，不值得為它引入 web 框架。
- UI：單頁 HTML + 原生 JS，無建置步驟。
- 桌面殼（Tauri / Electron）**延後決定**，先確保核心在瀏覽器可用。

---

## 8. v1 範圍

**做**：adapter 偵測與呼叫、序列討論引擎、六道停止邊界、仲裁流程、本機 web UI、
Linux/macOS 支援。

**延後**：Windows 支援、桌面殼打包、討論存檔與匯出、模型參數調整 UI。

⚠️ **加入 Windows 支援時必須一併處理**：`shutil.which()` 在 Windows 會把**當前工作目錄**
納入搜尋範圍（POSIX 不會）。屆時若使用者從一個含有惡意 `claude.exe` 的目錄啟動 council，
該執行檔會先於真正的 CLI 被解析到。v1 不支援 Windows，故現在不是漏洞；
但這一條不解掉就不能宣稱支援 Windows。（2026-08-03 security review 提出）
