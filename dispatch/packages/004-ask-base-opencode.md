# 工作包 004：ask() 共用骨架 + opencode adapter

先讀 `SPEC.md` §4（介面契約）、§4.2（顧問唯讀）、§5（停止邊界）。

本包只實作 **opencode** 一家的 `ask()`。其餘三家維持 `NotImplementedError`，
但**四家的簽章都要更新**成含 `model` 參數，介面必須一致。

---

## 1. 簽章變更（四個模組都要改）

```python
def ask(prompt: str, model: str | None, timeout_s: int, max_chars: int) -> dict
```

`claude` / `codex` / `gemini` 三家仍 `raise NotImplementedError`。
`tests/test_adapters_detect.py` 裡呼叫 `ask()` 的既有測試要一併更新，不要讓它掛掉。

## 2. `src/adapters/base.py`：新增共用執行函式

供各 adapter 共用，負責與 CLI 無關的部分：

- 以 **list 形式**的 argv 呼叫子行程（**絕不可用 `shell=True`**，絕不可用字串拼接組指令）
- 逾時強制終止子行程，回傳 `ok=False` 與可讀錯誤
- 量測 `elapsed_s`
- 輸出超過 `max_chars` 時截斷並標記 `truncated=True`
- 回傳 `SPEC.md` §4 規定的 dict

### ⚠️ argv 長度上限（必做）

Linux 對**單一 argv 字串**有上限（`MAX_ARG_STRLEN`，典型為 128 KiB）。
逐字稿會隨輪次成長，遲早撞到，屆時會是難以判讀的 `E2BIG`。

因此送出前先檢查 prompt 長度，超過 **100000 字元**就直接回傳
`ok=False` 與明確錯誤訊息，**不要送出去讓它以難懂的方式失敗**。

## 3. `src/adapters/opencode.py`：實作 ask()

指令形式見 `SPEC.md` §4.1。要點：

- `model` 為 `None` 時不傳 `-m`，使用 CLI 預設模型。
- **`--dir` 必須指向一個當次呼叫新建的空白暫存目錄，用完刪除。**
  理由：顧問的職責是出意見、不是動手（`SPEC.md` §4.2）。opencode 會把子行程
  圈在 `--dir` 內，指向空白暫存目錄即可讓它讀不到也寫不到 council 的任何檔案。
  **不可以**把 `--dir` 指向專案目錄。
- 從 `--format json` 的事件流中萃取模型的文字回覆。
  **參考真實樣本**：`dispatch/sessions/*.jsonl` 是先前真實派工留下的完整事件流，
  直接讀它們來確認欄位形狀，不要憑猜測寫解析。
- 解析不到任何文字 → `ok=False` 並說明，不要回傳空字串假裝成功。

## 4. 測試（`tests/test_adapters_ask.py`）

標準庫 `unittest`。**不得呼叫真實 CLI。** 用假的可執行腳本（`printf`，不要用 `echo`）
模擬 opencode 的事件流輸出。至少涵蓋：

- 正常事件流 → 正確萃取文字、`ok=True`
- 輸出超過 `max_chars` → `truncated=True` 且文字確實被截斷
- 子行程卡住 → 逾時終止、`ok=False`、錯誤訊息含逾時字樣（用很短的 timeout，別讓測試跑很久）
- 子行程非零退出 → `ok=False` 且錯誤可讀
- 事件流中沒有任何文字 → `ok=False`
- prompt 超過長度上限 → `ok=False`，且**根本沒有啟動子行程**（請設法實際驗證這點）

## 5. 人工驗收（這部分要真的跑）

opencode 的免費模型**不消耗任何付費額度**，所以以下要實跑並貼出真實輸出：

1. `python3 -m unittest discover tests -v` 全數通過，貼出輸出與耗時。
2. 實際呼叫一次：`model="opencode/deepseek-v4-flash-free"`，prompt 用一句很短的問題，
   貼出回傳的完整 dict（`text` 過長可截斷顯示，但要註明）。
3. 證明 `--dir` 的暫存目錄用完已被刪除。

## 6. 界線

- 不改 `SPEC.md`、`AGENTS.md`、`dispatch.sh`、`README.md`、`LICENSE`
- 不動 `detect()` 既有邏輯
- 不實作 claude / codex / gemini 的 `ask()`
- 不要 `git add` / `git commit`
- 不引入第三方套件

沒實際跑過的不要說它會動；沒驗證的部分標「未驗證」。
