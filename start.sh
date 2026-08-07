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

# 目標埠要從參數解析，不能寫死：寫死的話 --port 8790 會變成
# 「檢查 8765、卻去開 8790 的網址」，那是靜默給錯答案。
# ⚠️ 不用陣列：macOS 內建的 bash 是 3.2，set -u 下展開空陣列會報 unbound variable。
PORT=8765
PREV=""
for ARG in "$@"; do
    case "$ARG" in
        --port=*) PORT="${ARG#--port=}" ;;
    esac
    if [[ "$PREV" == "--port" ]]; then
        PORT="$ARG"
    fi
    PREV="$ARG"
done

# 已經有一台在跑就不要起第二台：桌面圖示是 Terminal=false，
# serve.py 綁不到 socket 的 traceback 沒有任何地方顯示得出來，
# 使用者只會看到「點了沒反應」。把它叫到面前才是他要的。
if python3 -c "import socket, sys; sys.exit(0 if socket.socket().connect_ex(('127.0.0.1', $PORT)) == 0 else 1)"; then
    echo "127.0.0.1:$PORT 已經有服務在聽，沒有起第二台，直接開瀏覽器連過去。"
    exec python3 -c "import webbrowser; webbrowser.open('http://127.0.0.1:$PORT/')"
fi

# ⚠️ 用 if 不用 `[[ ... ]] && ...`：後者在條件為假時整行回傳 1，
# 配上 set -e 會讓 --dry 模式的腳本在這裡靜默結束。
if [[ -n "$LIVE" ]]; then
    exec python3 src/serve.py --open "$LIVE" "$@"
fi
exec python3 src/serve.py --open "$@"
