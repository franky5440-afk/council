# council

**專案方向待定**（2026-08-03 建立）。目前 repo 內只有派工基礎設施。

本專案的實作由 opencode 的 deepseek 擔任 builder，Claude Code 主對話直接派工並負責審查與版控。
（同層的 `lottrey` 不同：那個專案完全由 Claude agent 撰寫，不經 deepseek。）

## 派工

```bash
./dispatch.sh dispatch/packages/001-範例.md          # 新開一輪
./dispatch.sh -s ses_xxxxx dispatch/packages/002.md  # 接續同一 session 補指示
```

腳本會印出 session id 與**實際的 git 變更**，並把該輪追加到 `dispatch/LEDGER.md`。
builder 的自述不會被當成結果呈現——審查一律讀 diff（自述請看 `dispatch/sessions/<id>.jsonl`）。

若 builder 遇到需求歧義，它會寫 `dispatch/BLOCKED.md` 並停手（headless 下它無法反問）。

## 檔案

| 路徑 | 用途 |
|---|---|
| `AGENTS.md` | builder 與 reviewer 共用的專案規則（唯一規則檔） |
| `dispatch.sh` | 派工入口 |
| `dispatch/packages/` | 工作包原文（版控，可回查派了什麼） |
| `dispatch/LEDGER.md` | append-only 派工紀錄 |
| `dispatch/sessions/` | opencode 原始事件流（不版控） |
