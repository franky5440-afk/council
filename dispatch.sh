#!/usr/bin/env bash
#
# council 派工腳本
#
# 把工作包送給 opencode builder（deepseek），並留下可事後審查的軌跡。
# 設計前提：主對話是 review gate，所以本腳本刻意「不」把 builder 的自述
# 當成結果呈現——它印的是 git 實際變更，自述請自行讀原始事件流。
#
# 用法：
#   ./dispatch.sh <工作包檔案>                    新開一輪派工
#   ./dispatch.sh -s <session_id> <工作包檔案>     接續既有 session（補指示／要求修正）
#
# 產出：
#   dispatch/LEDGER.md                    append-only 派工紀錄（版控）
#   dispatch/sessions/<session_id>.jsonl  opencode 原始事件流（不版控）

set -uo pipefail

# 一律以腳本所在位置為專案根，不依賴呼叫時的 cwd（cwd 會漂移）
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MODEL="opencode/deepseek-v4-flash-free"
SESSIONS_DIR="$PROJECT_DIR/dispatch/sessions"
LEDGER="$PROJECT_DIR/dispatch/LEDGER.md"

usage() {
    echo "用法: $0 <工作包檔案>"
    echo "      $0 -s <session_id> <工作包檔案>"
    exit 2
}

SESSION_ID=""
if [[ "${1:-}" == "-s" ]]; then
    SESSION_ID="${2:-}"
    PACKAGE_FILE="${3:-}"
    [[ -n "$SESSION_ID" ]] || usage
else
    PACKAGE_FILE="${1:-}"
fi

[[ -n "$PACKAGE_FILE" ]] || usage

if [[ ! -f "$PACKAGE_FILE" ]]; then
    echo "錯誤：找不到工作包檔案 '$PACKAGE_FILE'" >&2
    exit 1
fi

mkdir -p "$SESSIONS_DIR"

# ---- 先歸檔上一輪的 BLOCKED.md ----
# 沒有這步的話，舊的卡關報告會讓之後每一輪都跳假警報，訊號就廢了。
# 歸檔而非刪除：卡關報告是決策歷程的一部分，只追加、不銷毀。
BLOCKED_FILE="$PROJECT_DIR/dispatch/BLOCKED.md"
ARCHIVED_BLOCKED=""
if [[ -f "$BLOCKED_FILE" ]]; then
    mkdir -p "$PROJECT_DIR/dispatch/blocked"
    ARCHIVED_BLOCKED="dispatch/blocked/$(TZ=Asia/Taipei date '+%Y%m%d-%H%M%S').md"
    mv "$BLOCKED_FILE" "$PROJECT_DIR/$ARCHIVED_BLOCKED"
    echo "· 上一輪的 BLOCKED.md 已歸檔至 $ARCHIVED_BLOCKED"
fi

# ---- 派工前基準線（審查靠這條線）----
BEFORE_HEAD="$(git -C "$PROJECT_DIR" rev-parse HEAD 2>/dev/null || echo NO_COMMIT)"
DIRTY_BEFORE="$(git -C "$PROJECT_DIR" status --porcelain | wc -l)"
STARTED_AT="$(TZ=Asia/Taipei date '+%Y-%m-%d %H:%M')"

PENDING="$SESSIONS_DIR/.pending.jsonl"
ERRLOG="$SESSIONS_DIR/.pending.stderr"
MESSAGE="$(cat "$PACKAGE_FILE")"

if [[ -n "$SESSION_ID" ]]; then
    MODE="接續 $SESSION_ID"
    echo "▶ 接續 session $SESSION_ID，工作包：$PACKAGE_FILE"
    opencode run --dir "$PROJECT_DIR" --model "$MODEL" --format json \
        --session "$SESSION_ID" "$MESSAGE" >"$PENDING" 2>"$ERRLOG"
else
    MODE="新開"
    echo "▶ 新開派工，工作包：$PACKAGE_FILE"
    opencode run --dir "$PROJECT_DIR" --model "$MODEL" --format json \
        "$MESSAGE" >"$PENDING" 2>"$ERRLOG"
fi
RC=$?

# ---- 取回 session id 並歸檔原始事件流 ----
SID="$(grep -o '"sessionID":"[^"]*"' "$PENDING" 2>/dev/null | head -1 | cut -d'"' -f4)"
if [[ -z "$SID" ]]; then
    SID="${SESSION_ID:-unknown-$(TZ=Asia/Taipei date '+%Y%m%d-%H%M%S')}"
fi
RAW="$SESSIONS_DIR/$SID.jsonl"
cat "$PENDING" >>"$RAW" && rm -f "$PENDING"
if [[ -s "$ERRLOG" ]]; then
    cat "$ERRLOG" >>"$SESSIONS_DIR/$SID.stderr"
fi
rm -f "$ERRLOG"

# ---- 派工後實際變更（這才是審查依據）----
CHANGED="$(git -C "$PROJECT_DIR" status --porcelain)"
if [[ "$BEFORE_HEAD" != "NO_COMMIT" ]]; then
    DIFFSTAT="$(git -C "$PROJECT_DIR" diff --stat "$BEFORE_HEAD" 2>/dev/null)"
else
    DIFFSTAT=""
fi

echo
echo "──────── 派工結果 ────────"
echo "session id : $SID   ← 要接續就用 -s $SID"
echo "退出碼     : $RC"
echo "原始事件流 : ${RAW#"$PROJECT_DIR"/}"
if [[ -f "$BLOCKED_FILE" ]]; then
    echo "⚠ builder 這輪回報卡關：dispatch/BLOCKED.md（先讀它）"
fi
echo
if [[ -n "$CHANGED" ]]; then
    echo "工作區變更："
    echo "$CHANGED" | sed 's/^/  /'
else
    echo "工作區無變更（builder 沒有動任何檔案）"
fi
[[ -n "$DIFFSTAT" ]] && { echo; echo "$DIFFSTAT" | sed 's/^/  /'; }
echo "──────────────────────────"

# ---- 追加 ledger（只可追加，不改寫既有紀錄）----
{
    echo
    echo "## $STARTED_AT · $(basename "$PACKAGE_FILE")"
    echo
    echo "- 模式：$MODE"
    echo "- session：\`$SID\`"
    echo "- 派工前 HEAD：\`$BEFORE_HEAD\`（工作區未提交項目 $DIRTY_BEFORE 個）"
    echo "- opencode 退出碼：$RC"
    if [[ -n "$CHANGED" ]]; then
        echo "- 派工後工作區變更："
        echo "$CHANGED" | sed 's/^/  - `/; s/$/`/'
    else
        echo "- 派工後工作區變更：無"
    fi
    [[ -n "$ARCHIVED_BLOCKED" ]] && echo "- 上一輪卡關報告已歸檔：\`$ARCHIVED_BLOCKED\`"
    [[ -f "$BLOCKED_FILE" ]] && echo "- ⚠ builder 這輪回報卡關（見 dispatch/BLOCKED.md）"
} >>"$LEDGER"

exit "$RC"
