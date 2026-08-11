#!/bin/zsh
# 雙擊此檔：啟動 council 本機伺服器並自動開瀏覽器（預設 --live，會消耗訂閱額度）。
# 用 Terminal 執行（不是 .app）是刻意的：council 需要登入 shell 的 PATH 才找得到
# claude / codex / gemini / opencode，而且視窗留著才能看見錯誤、按 Ctrl-C 收工。
export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"
# 以腳本所在位置定位專案，不寫死絕對路徑（Finder 啟動時 cwd 是家目錄）。
cd "$(dirname "$0")" || { echo "找不到 council 資料夾"; exit 1; }
exec ./start.sh
