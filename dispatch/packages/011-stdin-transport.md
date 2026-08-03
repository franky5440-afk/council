# 工作包 011：改走 stdin 傳輸、模型必填、回報實際模型與用量

`SPEC.md` 剛更新（commit `d78e45f`），新增 §2.2、§3.2 並改寫 §4 的介面契約。
**動手前先讀 §2.2、§3.2、§4、§4.1、§5 邊界 6。** 本包不重述那些內容。

範圍：`src/adapters/` 五個檔與 `tests/`。**不要動 `SPEC.md`、`AGENTS.md`、
`dispatch.sh`、`dispatch/`。**

---

## 介面已定死，照做不要自創

### 1. `base.run()` 新增 stdin 參數

```python
def run(argv: list, timeout_s: int, stdin_text: str | None = None,
        cwd: str | None = None) -> dict:
```

- `stdin_text is None` ⇒ 維持現行行為，`stdin=subprocess.DEVNULL`
  （`detect()` 這類不送 prompt 的呼叫要繼續走這條）
- `stdin_text` 為字串 ⇒ 把該內容寫入子行程 stdin **然後關閉**
- 參數順序與預設值照上面寫死，**不要改成關鍵字限定或調換位置**

⚠️ `cwd` 維持現有位置與語意，不要順手重排。

### 2. `MAX_ARG_CHARS` → `MAX_ARG_BYTES`

現行 `MAX_ARG_CHARS = 100000` 以 `len(prompt)` 比對，算的是**字元**。
UTF-8 中文一字 3 bytes ⇒ 10 萬中文字元＝30 萬 bytes，檢查會放行然後 `exec` 失敗
（實測 `OSError: [Errno 7] Argument list too long`）。

改為 `MAX_ARG_BYTES = 100000`，以 `len(s.encode("utf-8"))` 比對。
**常數要改名**——留著 `_CHARS` 這個名字就是留著一句謊話。四個 adapter 與相關測試
一併更新。

### 3. `ask()` 簽章與行為

```python
def ask(prompt: str, model: str, timeout_s: int, max_chars: int) -> dict:
```

- `model` **改為必要參數**，不再接受 `None`（理由見 §2.2）
- `prompt` **經 stdin 送出**，argv 只帶這句固定指示（實測四家皆可用）：

  ```
  請依照輸入的內容回答
  ```

- 回傳 dict 新增兩個鍵：`model_used`、`usage`（型別見 §4）

⚠️ **argv 上不得再出現 prompt 內容。** 這是本包的核心變更，不是選配。

### 4. `model_used` 與 `usage` 的取得位置（皆為 2026-08-04 實機輸出，已核實）

| CLI | `model_used` 來源 | `usage` 來源 |
|---|---|---|
| `claude` | stdout JSON 的 `modelUsage` 鍵名，或 `modelUsage.<鍵>.canonicalModel` | stdout JSON 的 `usage` 物件；成本在頂層 `total_cost_usd` |
| `gemini` | stdout JSON 的 `stats.models` 鍵名 | `stats.models.<鍵>.tokens` |
| `codex` | **stderr** 中形如 `model: <名稱>` 的一行 | **stderr** 中 `tokens used` 的**下一行**數字（含千分位逗號，如 `4,739`） |
| `opencode` | **不回報 ⇒ 一律 `None`** | JSONL 中 `type == "step_finish"` 事件的 `part.tokens` 與 `part.cost` |

規則：

- **取不到就回 `None`，不要回顯我們送出的 `model` 值**——回顯無法偵測 CLI 換掉模型，
  等於把 Unknown 偽裝成 Evidence。
- **不要自行估算 token**。
- 這些格式是當天的事實、不是永久契約（同 §4.1 的理由）。取不到時 `ask()` 仍須
  `ok=True`（只要回覆本身拿到了），`model_used` / `usage` 各自為 `None` 即可
  ——**不得因為取不到用量就讓整次呼叫失敗**。

---

## ⚠️ 兩條紅線

### 紅線一：不可呼叫任何真實 CLI

`AGENTS.md`「對本專案特別要求」訂明真實呼叫由主對話人工執行，那會消耗真實額度。
測試一律用假的子行程。

⚠️ **上一包（010）就是在這裡出事的**：驗收時只設了 4 個環境變數中的 1 個，
其餘退回預設值＝真實 binary，codex／gemini／opencode 被真的呼叫。
**因此本包額外要求：任何你寫的測試輔助工具，預設行為必須是「不呼叫真實 CLI」，
要打真的必須顯式 opt-in。** 預設值倒向危險是設計缺陷，不是使用者的疏忽。

### 紅線二：不得把本機路徑或逐字稿寫進版控

⚠️ 這是 **public repo**。實測發現 `codex` 的 stderr 含兩樣危險內容：

1. `workdir: /home/<使用者名稱>/...` ——本機絕對路徑與使用者名稱
2. **它會把整份 stdin 原樣回顯到 stderr** ⇒ 未來 stderr 會包含完整逐字稿

因此：

- `dispatch/tmp/probe_*.txt` 的真實輸出**可以參考結構**，但**不得原樣複製進
  `tests/fixtures/`**。要新增 fixture 必須先把絕對路徑與使用者名稱換成佔位字串。
- `ask()` 回傳的 `error` 訊息沿用現行的「只取首要錯誤行、截斷」做法，
  **不要改成回傳整坨 stderr**。

---

## 驗收條件（要貼出真實輸出，不是描述）

1. `python3 -m unittest discover tests` 全過，貼出最後三行。
2. **證明 stdin 傳輸真的有覆蓋**：把某個 adapter 的 stdin 傳輸拿掉（改回把 prompt
   放進 argv），測試**必須失敗**。貼出失敗輸出，再還原。
   ⚠️ 做這個驗證時務必先確認你的修改真的套用了（比對修改前後檔案內容確實不同）
   ——「改了但沒套用」會讓測試照樣全過，看起來像有覆蓋，實際上沒有。
3. **證明位元組檢查真的有效**：以超過 `MAX_ARG_BYTES` 的**中文**字串測試，
   證明會被擋下；並證明同樣字元數的 ASCII **不會**被誤擋。兩個方向都要。
4. `model_used` / `usage` 的解析：四家各至少一個測試，且**包含「該欄位缺失時回
   `None` 且 `ok` 仍為 `True`」**的案例。
5. 逐條說明哪些既有測試被你改了、為什麼——簽章變更會波及既有測試，
   我要能分辨「合理調整」與「為了讓它過而改壞斷言」。

## 交付說明

- 上述五項的真實輸出。
- 沒驗證的部分明確標「未驗證」（`AGENTS.md` 對本專案最看重這一點）。
- 卡關照 `AGENTS.md` 寫 `dispatch/BLOCKED.md` 停手，不要猜。
