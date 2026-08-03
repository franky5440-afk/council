# 工作包 009：補上 opencode 的機制層唯讀

接續 008。這是**安全性修正**，補的是 `SPEC.md` §4.2 的硬要求。
先讀 `SPEC.md` §4.2（已更新，含本次實測結論），本包不重述那裡寫過的東西。

範圍限定在 `src/adapters/base.py`、`src/adapters/opencode.py` 與測試。
**不要動 claude / codex / gemini 的邏輯。**

---

## 1. `base.py`：`run()` 要把 stderr 帶回來

目前 `run()` 只在非零退出時把 stderr 榨成一行錯誤訊息，成功時 stderr 直接丟掉。
第 3 節需要在**成功**的情況下檢查 stderr，所以回傳的 dict 要多帶一個鍵：

```python
"stderr": proc.stderr or ""
```

**四條回傳路徑都要有這個鍵**（逾時、OSError、非零退出、成功），值取不到時放 `""`，
不要讓呼叫端遇到 `KeyError`。逾時與 OSError 路徑沒有 `proc`，放 `""` 即可。

⚠️ 這是**新增**鍵，不要動既有鍵的名稱或語意。`ask()` 對外回傳的 dict
仍必須完全符合 `SPEC.md` §4 的形狀——`stderr` 只在 `base.run()` 與 adapter 之間流通，
**不得**出現在 `ask()` 的回傳值裡。

## 2. `opencode.py`：寫出唯讀 agent 定義並使用它

在既有的暫存目錄流程內，於呼叫 opencode **之前**建立：

```
<暫存目錄>/.opencode/agents/advisor.md
```

內容（frontmatter 格式已由 `opencode agent create` 實地產生確認，照抄即可）：

```markdown
---
description: Read-only council advisor.
mode: primary
permission:
  bash: deny
  edit: deny
  webfetch: deny
  task: deny
  todowrite: deny
  websearch: deny
  lsp: deny
  skill: deny
---

You are a council advisor. Answer the question directly.
```

然後在 argv 中加入 `--agent advisor`。

- agent 名稱請以模組層級常數定義（例如 `AGENT_NAME = "advisor"`），
  檔名與 `--agent` 的值要由同一個常數推出，不要在兩處各寫一次字串。
- agent 定義內容同樣放模組層級常數，不要在函式裡拼字串。
- **不要**去呼叫 `opencode agent create`（那會發出一次模型呼叫，浪費額度且沒必要）。

## 3. ⚠️ 必做：把 fail-open 關掉

`--agent` 找不到指定 agent 時，opencode **不會報錯**——它印一行 stderr 警告然後
**退回完全可寫的預設 agent**，exit code 仍是 0。實測確認過：目標檔案照樣被寫出來。

所以呼叫回來之後、萃取文字之前，檢查 stderr 是否含有下列**子字串**：

```
Falling back to default agent
```

含有就回 `ok=False`，錯誤訊息要講清楚是唯讀 agent 沒生效、拒絕使用這次結果。
**不可以**只記個 log 就繼續用回覆內容——唯讀失效時這次呼叫必須整個作廢。

比對用子字串請定義成模組層級常數，方便日後 opencode 改字串時只改一處。

## 4. 測試

沿用既有的假腳本 + argv 側錄手法。至少涵蓋：

- argv 中含 `--agent advisor`（斷言旗標與值**成對**，不是只斷言字串出現）
- 呼叫時 `<暫存目錄>/.opencode/agents/advisor.md` **確實存在**，且內容含
  `bash: deny` 與 `edit: deny`
  （提示：讓假腳本把該檔案內容抄到一個測試看得到的位置，因為暫存目錄呼叫完就被刪了）
- 假腳本在 **stderr** 印出 `agent "advisor" not found. Falling back to default agent`
  並以 **exit 0** 退出、stdout 給正常事件流 → `ask()` 必須回 `ok=False`，
  **不得**回傳那段文字
- stderr 沒有該訊息時 → 正常回 `ok=True`（確認上一項不是無條件失敗）
- `base.run()` 的四條回傳路徑都含 `stderr` 鍵

## 5. 自我檢查

補完後自己做突變測試並貼出**實際輸出**，每項都必須 FAILED：

1. 拿掉 argv 裡的 `--agent`
2. 把 agent 定義中的 `bash: deny` 改成 `bash: allow`
3. 拿掉第 3 節的 fallback 檢查

⚠️ 突變前先用 `assert '要替換的字串' in s` 確認替換真的套用得上。
本專案上一輪發生過突變沒生效、結果顯示 OK、差點被誤判成「有覆蓋」。
驗完全部還原，`git diff --stat` 確認沒有殘留。

## 6. 界線

- 不改 claude / codex / gemini 的任何邏輯
- 不改 `SPEC.md`、`AGENTS.md`、`dispatch.sh`、`tests/fixtures/`
- 不改 `_pick_error_line()`、不改前置的 `-` 開頭守衛
- 不 `git add` / `git commit`
- 不引入第三方套件
