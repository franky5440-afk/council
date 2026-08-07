# 工作包 035 — `start.sh`：已經有一台在跑就開瀏覽器連過去

## 這是修正包，接續 033／034 的 session

**只動一個檔案：`start.sh`。** 不新增測試檔（本專案的測試是 Python，不涵蓋 shell），
但**驗證步驟是強制的**，見 §5。

## 1. 問題（實際發生過）

桌面圖示是 `Terminal=false`（`~/.local/share/applications/council.desktop`，不在 repo 裡）。
使用者上一台 council 忘了關時，`start.sh` 會在 `serve.py` 綁 socket 那一步失敗：

```
OSError: [Errno 98] Address already in use
```

而 `Terminal=false` 代表**那個 traceback 沒有任何地方顯示得出來** ⇒ 使用者看到的是
「點了圖示完全沒反應」，無從判斷。實際發生於 2026-08-07。

## 2. 要做的事

`start.sh` 在啟動 `serve.py` **之前**先看目標埠是不是已經有人在聽：

- **有人在聽** ⇒ **不要**再起第二台。印一行說明，直接用瀏覽器開那個網址，正常結束（exit 0）。
- **沒人在聽** ⇒ 行為與現在**完全一樣**。

🔴 **要檢查的埠必須從參數解析出來，不准寫死 8765。**
理由：`start.sh` 會把多餘參數原樣轉給 `serve.py`，使用者可以下 `--port 8790`。
寫死 8765 的話會變成「檢查 A 埠、卻去開 B 埠的網址」——**靜默給出錯誤答案，
比現在的靜默失敗更糟**。

## 3. 🔴 逐字照抄的完整新版 `start.sh`

現有全文逐字是：

```bash
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
```

**整個檔案換成下面這一份**（前半段一字未改，新增的是「解析埠」與「已在跑就開瀏覽器」）：

```bash
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
```

### 3.1 為什麼是這幾個寫法（不要「順手改良」）

- **訊息刻意寫「已經有服務在聽」而不是「已經有 council 在跑」**：那個埠上的東西
  未必是 council，我們只知道有人在聽。**不要為了話講得漂亮而宣稱一件沒查證的事。**
- 🔴 **不准用 `nc`／`ss`／`lsof` 做偵測。** `nc` 不一定裝、`ss` 是 GNU/Linux 專屬
  （macOS 沒有，036 要用 macOS）。`python3` 已經是本專案的硬依賴。
- 🔴 **不准用陣列累積參數**（`args=()` ＋ `"${args[@]}"`）：macOS 的 `/bin/bash` 是 3.2，
  `set -u` 下展開空陣列會報 unbound variable。
- **`--port=8790` 與 `--port 8790` 兩種寫法都要支援**（argparse 兩種都收）。
- **`connect_ex` 回 0 代表連得上**，非 0 代表沒人聽。用 `connect_ex` 不用 `connect`，
  後者失敗會丟例外。

## 4. 🔴 不准做的事

- **不准動** `src/`、`tests/`、`run.sh`、`README.md`、`SPEC.md`、`AGENTS.md`、
  `DESIGN-NOTES.md`。這一包**只有 `start.sh` 一個檔案會變**。
- **不准新增測試檔**（Python 測試不涵蓋 shell，硬加只會製造看起來有測到的假象）。
- **不准碰 8765 埠**：使用者可能有伺服器在上面跑。不要 `kill`／`pkill`／`fuser`，
  **也不要對 8765 發任何請求或做連線偵測**。驗證一律用 8790／8791。
- **不准跑 `--live`**、**不准呼叫任何 CLI**、**不准執行任何版控指令**。
- 臨時檔一律放 `dispatch/tmp/`。先備份：

```bash
mkdir -p dispatch/tmp/035-backup && cp start.sh dispatch/tmp/035-backup/
```

## 5. 驗證（強制，逐項附上實際輸出）

### 5.1 語法

```bash
bash -n start.sh && echo "語法 OK"
ls -l start.sh          # 必須仍有可執行權限
```

### 5.2 埠解析（**不要真的起伺服器**，只驗解析對不對）

把解析那一段複製成 `dispatch/tmp/035-backup/probe_port.sh`，結尾 `echo "$PORT"`，
然後確認這四種情況：

| 呼叫方式 | `PORT` 應該是 |
|---|---|
| （無參數） | `8765` |
| `--port 8790` | `8790` |
| `--port=8791` | `8791` |
| `--dry --port 8790` | `8790` |

⚠️ **最後一種要注意**：`--dry` 會被 `shift` 掉，所以迴圈看到的 `"$@"` 已經不含它。

### 5.3 「已經有一台在跑」的實際行為（用 8790，不准用 8765）

```bash
# 先在 8790 起一台 dry run 當作「已經在跑的那台」
python3 src/serve.py --port 8790 &
SRV=$!
sleep 2

# 這一次應該「不起第二台，直接開瀏覽器」
./start.sh --dry --port 8790
echo "退出碼=$?"          # 應為 0

# 確認真的沒有起第二台（8790 上的 python3 應該仍然只有一個）
ps -eo pid,args | grep '[s]erve\.py' | grep 8790

# 收尾：關掉它。用我們自己的端點，不要 kill。
curl -s -X POST http://127.0.0.1:8790/api/shutdown -H "Content-Type: application/json" -d '{}'
sleep 2
ps -eo pid,args | grep '[s]erve\.py' | grep 8790 || echo "已關閉，無殘留"
```

🔴 **驗證結束後不得留下任何背景程序。** 交付前跑一次
`ps -eo pid,args | grep '[s]erve\.py'` 確認乾淨，並把結果貼進回報。

### 5.4 「沒有人在跑」的行為沒被改壞

在**沒有任何東西監聽的 8791** 上直接跑：

```bash
./start.sh --dry --port 8791
```

應該**正常起一台 dry run 伺服器**：印出 `dry run 模式：…` 與 `http://127.0.0.1:8791/`。
關掉它（用我們自己的端點，不要 `kill`）：

```bash
curl -s -X POST http://127.0.0.1:8791/api/shutdown -H "Content-Type: application/json" -d '{}'
```

同樣不准留殘留程序。

### 5.5 既有測試

```bash
python3 -m unittest discover tests
```

這一包沒動 Python，**338 個應該原封不動全過**。
🔴 附上實際最後三行（`Ran N tests`／`OK`）。

## 6. 交付前自己確認

- [ ] `bash -n start.sh` 過、可執行權限still在
- [ ] §5.2 四種埠解析情況全部正確，附實際輸出
- [ ] §5.3 已在跑 ⇒ 不起第二台、開瀏覽器、exit 0，附實際輸出
- [ ] §5.4 沒在跑 ⇒ 正常起伺服器，附實際輸出
- [ ] `python3 -m unittest discover tests` → 338 OK，附實際輸出
- [ ] `ps -eo pid,args | grep '[s]erve\.py'` → **沒有殘留程序**，附實際輸出
- [ ] `git diff --stat` → **只有 `start.sh` 一個檔**
- [ ] 全程沒有碰 8765、沒有 `--live`、沒有呼叫任何 CLI、沒有執行版控指令

## 7. 卡住怎麼辦

契約有矛盾、或某條驗收條件在任何實作下都不可能成立 ⇒ 寫 `dispatch/BLOCKED.md`
說明卡在哪一條，不要自己選一個讀法硬做。
