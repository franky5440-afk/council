# 真實 CLI 輸出樣本

本目錄的檔案是**各家 CLI 實機呼叫後的真實輸出**，2026-08-03 擷取。
用途是讓 adapter 的解析與測試有據可依，**不必為了寫解析而消耗任何人的訂閱額度**。

已去識別化：`session_id` / `uuid` 一律置換為全零，內容不含絕對路徑或個人資訊。
除此之外**未經修改**，欄位形狀即為真實形狀。

⚠️ **這些是證據，不是素材。** 不要為了讓測試好寫而改動它們。
CLI 改版導致格式變更時，做法是重新實機擷取並在此追加新樣本。

| 檔案 | 來源指令 | 文字在哪 |
|---|---|---|
| `claude_success.json` | `claude -p <prompt> --output-format json --tools ""` | `result`（`is_error` 為 `false`） |
| `claude_error.json` | 同上，但呼叫中途失敗 | **沒有 `result` 欄位**；`is_error` 為 `true` |
| `gemini_success.json` | `gemini -p <prompt> -o json --approval-mode plan --skip-trust` | `response` |
| `codex_last_message.txt` | `codex exec --output-last-message <此檔>` | 整個檔案就是內容（**純文字，非 JSON**） |

## 擷取時實測到的四件事（會影響 adapter 怎麼寫）

1. **三家都會讀 stdin，必須把 stdin 導向 `/dev/null`。**
   未導向時 `claude` 印出 `no stdin data received in 3s`，並且**整個行程掛住**——
   實測一次呼叫從 9.9 秒暴增到 176 秒後被強制終止（即 `claude_error.json` 那次）。
   `codex` 也會印 `Reading additional input from stdin...`。
   這是子行程呼叫最容易踩、又最難從症狀反推原因的一個坑。

2. **`gemini` 在不受信任的目錄會把 `--approval-mode plan` 無聲改回 `default`**，
   並以 exit code 55 中止，訊息為 `not running in a trusted directory`。
   必須加 `--skip-trust`。⚠️ 這代表**唯讀不能只靠 `--approval-mode plan`**——
   沒加 `--skip-trust` 時它連跑都跑不起來，加了之後 plan 才真正生效
   （本次樣本的 `stats.tools.totalCalls` 為 `0`，可佐證 plan 模式確實擋住了工具呼叫）。

3. **`claude` 失敗時回的仍是合法 JSON，但沒有 `result` 欄位。**
   因此解析**必須先檢查 `is_error`**，不能直接取 `result`，否則會是 `KeyError`
   而不是一則可讀的錯誤訊息。可一併參考 `subtype`（`success` / `error_during_execution`）。

4. **`gemini` 會在內部自行重試並退避。** 本次樣本的 `stats` 顯示
   `totalRequests: 3`、`totalErrors: 2`（兩次 503），整通呼叫耗時 **119.5 秒**。
   `SPEC.md` §5 的預設 `timeout_s = 120` 差 0.5 秒就會把這次**其實成功**的呼叫砍掉。
   這不是 adapter 自己能解的問題，屬於預設值該不該調整的規格層議題。
