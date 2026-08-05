#!/usr/bin/env bash
# 用固定的席次配置開一輪討論。存在的理由：cli.py 的完整指令太長，
# 貼進終端機會折行拆斷。改席次請直接編輯下面兩個陣列。
#
#   ./run.sh "問題"            真實呼叫（顧問三席都是免費模型）
#   ./run.sh --dry "問題"      不呼叫任何 CLI，只看 prompt 怎麼組
#   ./run.sh "問題" --max-chars 2000    多餘參數原樣轉給 cli.py
set -euo pipefail

# 顧問席次，依序發言。格式 <cli>[:<模型>]。
ADVISORS=(
    "opencode:opencode/deepseek-v4-flash-free"
    "opencode:opencode/nemotron-3-ultra-free"
    "opencode:opencode/ling-3.0-flash-free"
)
# 仲裁者。要仲裁請自行加上 --arbitrate（多餘參數會原樣轉給 cli.py）。
# ⚠️ 這一席是 claude，一次仲裁會消耗付費額度；不加 --arbitrate 時本席不會被呼叫。
ARBITER="claude"

LIVE="--live"
if [[ "${1:-}" == "--dry" ]]; then
    LIVE=""
    shift
fi

if [[ $# -lt 1 || -z "${1:-}" ]]; then
    echo "用法：$0 [--dry] \"問題\" [其他 cli.py 參數...]" >&2
    exit 2
fi
QUESTION="$1"
shift

ARGS=()
for spec in "${ADVISORS[@]}"; do
    ARGS+=(--advisor "$spec")
done
ARGS+=(--arbiter "$ARBITER")
# ⚠️ 用 if 不用 `[[ ... ]] && ...`：後者在條件為假時整行回傳 1，
# 配上 set -e 會讓 --dry 模式的腳本在這裡靜默結束。
if [[ -n "$LIVE" ]]; then
    ARGS+=("$LIVE")
fi

# 以腳本所在位置定位專案，不寫死絕對路徑（cwd 會漂移）。
cd "$(dirname "$0")"
exec python3 src/cli.py "$QUESTION" "${ARGS[@]}" "$@"
