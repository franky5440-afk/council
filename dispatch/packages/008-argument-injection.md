# 工作包 008：擋掉旗標走私（argument injection）

接續 007。安全性修正，範圍限定，**不要順手改別的**。

---

## 問題

`prompt` 與 `model` 是字串，直接被放進 argv。若字串以 `-` 開頭，CLI 會把它**當成旗標解析**，
而不是當成內容。實測四家全部如此：

| CLI | 送出 `--totally-bogus-xyz` 當 prompt 的結果 |
|---|---|
| `claude` | `error: unknown option '--totally-bogus-xyz'` |
| `codex` | `error: unexpected argument ... tip: use '-- ...'` |
| `gemini` | `Not enough arguments following: p` |
| `opencode` | 直接印出 usage、不執行 |

危險之處不是「會壞掉」，而是**攻擊者可藉此關掉唯讀保護**。各家都有單一 token 就能
解除沙箱的旗標，例如 `codex` 的 `--dangerously-bypass-approvals-and-sandbox`、
`gemini` 的 `--approval-mode=yolo`、`claude` 的 `--permission-mode=bypassPermissions`、
`opencode` 的 `--auto`。這會讓 `SPEC.md` §4.2 的唯讀硬要求被**輸入內容**直接繞過。

來源不是假想的：`SPEC.md` §6 規定顧問的 prompt 由「使用者問題 + 其他模型的逐字稿」
組成，逐字稿是模型生成的內容，只要開頭是 `-`（例如 markdown 條列符號）就會踩到。

## 要改什麼

### 1. `base.py`：新增前置檢查（四家共用）

新增一個模組層級函式，供四個 adapter 在**啟動子行程之前**呼叫。
`prompt` 或 `model` 只要以 `-` 開頭，就回 `ok=False` 與明確錯誤，**不啟動子行程**。

比照現有 `MAX_ARG_CHARS` 那個檢查的位置與回傳形狀（放在 `shutil.which()` 之前或之後都可以，
但必須在建 argv 之前）。錯誤訊息要說清楚是哪個參數、以及為什麼被擋。

`model=None` 時不檢查 model。

### 2. 三家加上 `--` 分隔符（已實測有效）

`prompt` 以**位置參數**傳入的三家，在 prompt 前插入 `--`：

- `claude`：`claude -p --output-format json --tools "" -- <prompt>`
  ⚠️ 注意 `-p` 是布林旗標，prompt 是位置參數，`--` 要放在所有選項之後、prompt 之前。
  **已實測**：加了 `--` 之後 `--totally-bogus-xyz` 被正確當成文字內容處理。
- `codex`：`codex exec ... -- <prompt>`（CLI 自己的錯誤訊息就建議這樣做）
- `opencode`：`opencode run ... -- <prompt>`

**`gemini` 不要加 `--`。** 它的 prompt 是 `-p` 的**值**不是位置參數，
yargs 不會把以 `-` 開頭的 token 綁給 `-p`（實測報 `Not enough arguments following: p`）。
gemini 這家靠第 1 項的前置檢查擋住即可。

⚠️ 這兩項是**互補**的，不要只做一項：`--` 讓合法但以 `-` 開頭的內容仍可正常送出，
前置檢查則是 gemini 的唯一防線、也是 `--` 萬一被未來重構刪掉時的第二道防線。

## 測試

`tests/test_adapters_ask.py`，沿用既有的 argv 側錄與假腳本手法：

- 四家各一項：`prompt` 為 `--dangerously-bypass-approvals-and-sandbox` → `ok=False`、
  錯誤訊息可讀、且**根本沒啟動子行程**（用既有的標記檔手法實際驗證）
- 四家各一項：`model` 以 `-` 開頭 → 同上
- `claude` / `codex` / `opencode` 各一項：正常 prompt 時 argv 中 `--` 確實出現，
  **且位置在 prompt 正前方**（斷言索引關係，不要只斷言 `--` 有出現）
- `gemini` 一項：argv 中**不含** `--`（避免有人日後「順手補齊」而弄壞它）

## 自我檢查

補完後自己做突變測試並貼出實際輸出，至少三項，每項都必須 FAILED：

1. 拿掉 `base.py` 的前置檢查
2. 拿掉 `codex` 的 `--`
3. 把 `claude` 的 `--` 移到 prompt 後面

驗完全部還原，`git diff --stat` 確認沒有殘留。

## 界線

- 不改唯讀旗標、不改三家的解析邏輯、不改 `_pick_error_line()`
- 不改 `SPEC.md`、`AGENTS.md`、`dispatch.sh`、`tests/fixtures/`
- **不要**試圖修 opencode 的唯讀問題（那是另一個議題，需求方尚未裁示）
- 不 `git add` / `git commit`
- 不引入第三方套件
