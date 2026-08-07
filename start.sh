#!/usr/bin/env bash
# 桌面捷徑用：起伺服器並自動開瀏覽器。預設 --live（點下去就是可用狀態）。
#
#   ./start.sh          真實呼叫，會消耗訂閱額度
#   ./start.sh --dry    不呼叫任何 CLI
#   ./start.sh --port 8790   多餘參數原樣轉給 serve.py
set -euo pipefail

LIVE="--live"
if [[ "${1:-}" == "--dry" ]]; then
    LIVE=""
    shift
fi

# 以腳本所在位置定位專案，不寫死絕對路徑（cwd 會漂移）。
cd "$(dirname "$0")"
# ⚠️ 用 if 不用 `[[ ... ]] && ...`：後者在條件為假時整行回傳 1，
# 配上 set -e 會讓 --dry 模式的腳本在這裡靜默結束。
if [[ -n "$LIVE" ]]; then
    exec python3 src/serve.py --open "$LIVE" "$@"
fi
exec python3 src/serve.py --open "$@"
