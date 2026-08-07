# 工作包 033 — 中止按鈕 ＋ 啟動捷徑

## 這一包的性質

**做一個「能自己關掉」的 council。** 目前只能在終端機按 Ctrl-C，而這一包同時要做
桌面捷徑——**從桌面圖示啟動的程式沒有終端機可以按 Ctrl-C**，所以兩件事必須一起做，
先做捷徑不做按鈕就是做出一個關不掉的東西。

要動的檔案**只有這六個**：

| 檔案 | 動什麼 |
|---|---|
| `src/server.py` | 新增 `POST /api/shutdown` 端點 |
| `src/serve.py` | 新增 `--open` 旗標；迴圈結束後補 `server_close()` |
| `src/static/index.html` | 中止按鈕、已關閉畫面、README 指路句、兩個 CSS 修正 |
| `start.sh` | **新檔**，桌面捷徑用 |
| `tests/test_server.py` | 新端點的測試 |
| `tests/test_ui.py` | 頁面的結構性斷言 |

**不准動** `src/engine/*`、`src/cli.py`、`src/ui.py`、`src/adapters/*`、`run.sh`、
`SPEC.md`、`AGENTS.md`、`README.md`。
⚠️ **`README.md` 由主對話另外自己寫**，你只負責在頁面上加一句指過去的話（§6.3）。

---

## 1. 先做這件事：備份

```bash
mkdir -p dispatch/tmp/033-backup
cp src/server.py src/serve.py src/static/index.html \
   tests/test_server.py tests/test_ui.py dispatch/tmp/033-backup/
```

**所有臨時檔、備份、探測腳本一律放 `dispatch/tmp/`**，不要寫到 `/tmp/`、
不要寫到專案目錄以外的任何地方。

## 2. 環境紅線

- **不准碰 8765 埠**：Frank 可能有伺服器在上面跑。不要 `kill`／`pkill`／`fuser`，
  不要對 8765 發任何請求。要起伺服器驗證一律用 `--port 0`，或 8790 以上的埠。
- **不准跑 `--live`**（會花錢）。所有驗證用 dry run。
- **不准呼叫任何 CLI**（`opencode`／`claude`／`codex`／`gemini`）。
- **不准執行任何版控指令**（`git add`／`commit`／`checkout`／`stash`／`push`…）。
  版控由主對話負責。
- ⚠️ **不准執行 `start.sh`**（它預設 `--live`，會花錢）。你只負責把它寫出來、
  用 `bash -n start.sh` 檢查語法。要驗行為請直接跑 `python3 src/serve.py --open --port 0`。

---

## 3. 🔴 已經實測過的前提（Evidence，不要重驗，也不要「改良」）

以下四條是主對話在出這一包之前**親手跑過**的，直接照著做：

1. **`build_server()` 回傳時 socket 已經 bind＋listen。** 在 `serve_forever()` 之前
   連上來的請求會排進 listen backlog，**不會 connection refused**，等迴圈起來就被服務。
   ⇒ **開瀏覽器的時機就放在 `build_server()` 之後、`serve_forever()` 之前。**
   🔴 **不准用「睡幾秒再開」**，那是猜的。
2. **「handler 送完 200 → 另開執行緒呼叫 `shutdown()`」回應會完整送達。**
   實測 50,000 位元組的 body 完整收到，之後 `serve_forever()` 在 **0.50 秒**內返回。
3. 🔴 **`shutdown()` 只停迴圈，不關監聽 socket。** 只呼叫 `shutdown()` 的話，那個埠
   **還連得上、但永遠不會有回應**——使用者重整頁面會看到一直轉圈，比「連線被拒」更難
   分辨。⇒ **`serve_forever()` 返回後必須補 `server_close()`**（§5.2）。
4. **對已經停止的伺服器再呼叫一次 `shutdown()` 會立刻返回（0.00 秒），不會掛住。**
   ⇒ 測試裡的 `addCleanup(srv.shutdown)` 是安全的，照既有寫法即可。

🔴 **不要在 handler 裡同步呼叫 `shutdown()`。** 它會等 `serve_forever()` 迴圈退出
（預設 poll 0.5 秒），期間回應還沒送出去 ⇒ 瀏覽器看到連線被重置，
**使用者無法分辨「成功關閉」與「當掉了」**。必須是「先回應，再另開執行緒關」。

---

## 4. `src/server.py`：新增 `POST /api/shutdown`

### 4.1 介面契約（寫死，沒有第二種讀法）

| 項目 | 值 |
|---|---|
| 方法與路徑 | `POST /api/shutdown` |
| 接受的 body | 空 body 或 `{}` |
| 有任何 body 鍵 | `400`，`{"error": "shutdown 不接受任何 body 鍵"}` |
| 成功回應 | `200`，body 逐字是 `{"stopping": true}` |
| 成功之後 | `self.wfile.flush()` → 另開一條 daemon 執行緒呼叫 `self.server.shutdown()` |

### 4.2 🔴 這個端點必須走完整條守門

這是一個「讓遠端請求關掉你的伺服器」的端點。`_gate()` 的三道守門
（Host／Origin／Content-Type）足以擋住惡意網頁，**但前提是新路由掛在守門之後**。

⇒ **路由判斷必須寫在 `_dispatch()` 裡、`self._gate()` 回傳 `True` 之後。**
🔴 **不准**在 `_gate()` 之前攔截、**不准**在 `_gate()` 裡替這個路徑開任何例外、
**不准**因為「反正是本機」就放寬。

### 4.3 `_dispatch()` 的 POST 分支改成這樣

原本是：

```python
            elif self.command == "POST":
                if kind not in ("discussions", "rounds", "arbitration"):
                    self._reply_error(404, "找不到該路徑")
                    return
                body = self._parse_json_body(self._read_body())
                if body is None:
                    self._reply_error(400, "請求 body 不是合法的 JSON 物件")
                    return
                if kind == "discussions":
                    self._post_discussions(body)
                elif kind == "rounds":
                    self._post_rounds(arg, body)
                else:
                    self._post_arbitration(arg, body)
```

改成：

```python
            elif self.command == "POST":
                is_shutdown = urlparse(self.path).path == "/api/shutdown"
                if not is_shutdown and kind not in (
                        "discussions", "rounds", "arbitration"):
                    self._reply_error(404, "找不到該路徑")
                    return
                body = self._parse_json_body(self._read_body())
                if body is None:
                    self._reply_error(400, "請求 body 不是合法的 JSON 物件")
                    return
                if is_shutdown:
                    self._post_shutdown(body)
                elif kind == "discussions":
                    self._post_discussions(body)
                elif kind == "rounds":
                    self._post_rounds(arg, body)
                else:
                    self._post_arbitration(arg, body)
```

**這樣寫的理由**：`/api/shutdown` 不屬於 `/api/discussions/...` 那組路由，塞進
`_match()` 會讓那個函式同時管兩件事。用完全相等比對，與既有的 `GET /` 同一手法。

### 4.4 `_post_shutdown()`

```python
    def _post_shutdown(self, body) -> None:
        if body:
            self._reply_error(400, "shutdown 不接受任何 body 鍵")
            return
        # 🔴 順序就是規格，不可對調：回應必須先完整送出去，才能停迴圈。
        # 反過來（handler 裡同步 shutdown()）會讓瀏覽器看到連線被重置，
        # 使用者分不出「成功關閉」與「當掉了」。
        self._reply_json(200, {"stopping": True})
        self.wfile.flush()
        threading.Thread(target=self.server.shutdown, daemon=True).start()
```

- `import threading` 加到 `src/server.py` 的 import 區（照既有字母序放在 `time` 之前）。
- 🔴 **`src/server.py` 仍然不得出現 `open(`**（既有紅線：靜態檔只由 `src/ui.py` 開）。
- 🔴 **仍然不得 import `adapters` 或 `subprocess`**。

### 4.5 其他方法不受影響（不要「順手」加）

- `GET /api/shutdown` 目前落到 `_reply_error(404, ...)`，**維持 404，不要改成 405**，
  也**絕對不准**讓 GET 能停伺服器（§7.2 有測試守這件事）。
- `DELETE /api/shutdown` 目前 `kind` 是 `None` ⇒ 404。**維持原狀。**

---

## 5. `src/serve.py`

### 5.1 新增 `--open` 旗標

- `import webbrowser`（stdlib，符合「零依賴」）。
  🔴 **不准用 `xdg-open`／`subprocess`／`os.system`**——`webbrowser` 自己會在 Linux 用
  `xdg-open`、在 macOS 用 `open`，寫死其中一個等於把 macOS 支援做掉（034 要用）。
- argparse 加：

```python
    parser.add_argument(
        "--open", action="store_true",
        help="啟動後自動用系統預設瀏覽器開啟頁面")
```

- 開啟的時機**必須**在 `build_server()` 之後、`serve_forever()` 之前（§3 第 1 條）。
  把現有的 `print(f"http://127.0.0.1:{httpd.server_address[1]}/")` 改成：

```python
    url = f"http://127.0.0.1:{httpd.server_address[1]}/"
    print(url)
    if args.open and not webbrowser.open(url):
        print("（無法自動開啟瀏覽器，請自己貼上上面的網址）")
```

  ⚠️ `webbrowser.open()` 找不到瀏覽器時回傳 `False` 而不是丟例外，所以要看回傳值；
  **失敗不可以讓伺服器停掉**，它只是少了一個便利功能。

### 5.2 迴圈結束後關 socket

原本是：

```python
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("已停止；討論只在記憶體，已全部消失。")
    return 0
```

改成：

```python
    try:
        httpd.serve_forever()
        print("已由網頁的「關閉 council」停止；討論只在記憶體，已全部消失。")
    except KeyboardInterrupt:
        print("已停止；討論只在記憶體，已全部消失。")
    finally:
        # shutdown() 只停迴圈、不關監聽 socket：不補這一行，那個埠會變成
        # 「連得上但永遠沒有回應」，比連線被拒更難判斷（實測確認）。
        httpd.server_close()
    return 0
```

🔴 **`已停止；討論只在記憶體，已全部消失。` 這一句逐字保留**，不要改字、不要合併。

### 5.3 🔴 `serve.py` 自己的預設值一個字都不准動

**不加旗標＝dry run**，這是命令列的對外契約，既有測試依賴它。
**不准**新增 `--dry`，**不准**讓 `--open` 順便打開 `--live`。
「捷徑要預設 live」這件事**只在 `start.sh` 裡實現**（§7），閘門是往上移，不是拿掉。

---

## 6. `src/static/index.html`

### 6.0 🔴 這個頁面既有的紅線（測試會抓，也會被突變測試）

一條都不准破：

| 紅線 | 說明 |
|---|---|
| 不得出現 `innerHTML`／`outerHTML`／`insertAdjacentHTML`／`document.write`／`eval(`／`new Function`／`Function(` | 一律 `createElement` ＋ `textContent` |
| 不得出現 `http://`／`https://` | **所以中止畫面的 README 指路句只能是純文字，不准寫成 `<a href>`** |
| 不得出現 `localStorage`／`sessionStorage`／`indexedDB`／`document.cookie` | |
| 不得出現 `setInterval`／`setTimeout` | 任何計時器都是「頁面自己決定何時再花錢」的起點 |
| 不得出現 `url(` 與 `<svg` | 圖示一律用 unicode 字元 |
| `confirm_over_cap` 這個字串**恰好出現一次** | ⚠️ 你新增的 `confirm(` 不影響它，**但新增的文案裡不准出現 `confirm_over_cap` 這幾個字** |
| CSP `<meta>` 的值逐字元固定 | 一個空格都不能改 |
| `[hidden] { display: none !important; }` **必須留在 stylesheet 最後一條** | 🔴 **你新增的 CSS 一律加在它前面。** 加在後面會讓兩個畫面同時顯示 |
| `<script>` 與 `<style>` 各恰好一個，不得有 `<script src=` | |

### 6.1 中止按鈕放哪：sidebar 最下面

**必須在兩個畫面都看得到**（表單畫面也要——那時沒有討論可損失，反而是最安全的
關閉時機）。`#sidebar` 在 `#form-view`／`#discussion-view` 之外，**放進去就同時滿足兩者**。

在既有的 `#mode-badge` **之後**加一個按鈕：

```html
    <div id="mode-badge" class="badge badge-gray">模式：尚未確認</div>
    <button id="btn-shutdown" class="btn btn-ghost">⏻ 關閉 council</button>
```

CSS（加在 `[hidden]` 那條**之前**）：

```css
#sidebar #btn-shutdown {
  width: 100%;
  margin-top: 12px;
  color: var(--danger);
  border-color: var(--danger);
}
```

### 6.2 已關閉畫面

在 `<main>` 裡、`#discussion-view` 之後加第三個畫面，**逐字照抄**：

```html
      <div id="stopped-view" hidden>
        <h1>council 已關閉</h1>
        <div class="question-card">
          <div id="stopped-reason"></div>
          <span class="hint">記憶體裡的討論已經全部消失——council 不把討論寫到磁碟。要再開一場討論，重新啟動 council 即可。</span>
        </div>
      </div>
```

🔴 **不准給那段說明文字 `id="context-chars-text"`**——那是討論檢視已經在用的 id，
重複的 id 會讓 `$("context-chars-text")` 抓到錯的元素。用 `class="hint"`，如上。

### 6.3 顧問欄位補一句指向 README

既有的說明文字**逐字**是（請直接從檔案複製，不要憑本文重打）：

```
可用的 cli：claude／codex／gemini／opencode，可以混搭。模型清單用各 CLI 自己的指令查（opencode 是 <code>opencode models</code>）。換模型就是改這一欄的文字，不必動任何程式碼。
```

在它**結尾**接上一句（同一個 `<span class="hint">` 之內）：

```
完整說明（各家 CLI 查模型的指令、打錯模型名會怎樣）見 README 的「換模型／調整發言順序」。
```

🔴 **前面那段原文一個字都不准改**（`一行一席`、`由上到下就是發言順序` 都有測試守著）。
🔴 **不准寫成連結**：測試禁止 `http://`，而且伺服器只服務 `/` 這一條靜態路由，
連到 README 是不可能的。就是純文字。

### 6.4 JS：中止的動作順序

🔴 **下列順序本身就是規格，逐步照做，不准合併也不准對調。**

```js
$("btn-shutdown").addEventListener("click", function () {
  // 1. 先問。使用者說不要就什麼都不做，一個請求都不發。
  var ok = window.confirm(
    "確定要關閉 council 嗎？\n\n" +
    "伺服器會立刻停止，記憶體裡的討論會全部消失（council 不把討論寫到磁碟）。\n" +
    "想留下逐字稿的話，先按取消，用「↓ 匯出 Markdown」存檔之後再關。");
  if (!ok) { return; }
  // 2. 🔴 一定要在發出請求之前關掉 SSE。伺服器一停，EventSource 會觸發
  //    onerror、把畫面訊息蓋成「連線中斷，瀏覽器會自動重連」，而且會無限重試
  //    ——那對「使用者自己按的關閉」是錯的語氣，讀起來像故障。
  closeSse();
  // 3. 防連按。
  $("btn-shutdown").disabled = true;
  // 4. 發請求。
  postJson("/api/shutdown", {}).then(function (result) {
    if (result.status === 200) {
      showStopped("你按下了「關閉 council」，伺服器已經停止，這個分頁不會再更新。");
    } else {
      $("btn-shutdown").disabled = false;
      $("st-sse").textContent =
        (result.data && result.data.error) || ("HTTP " + result.status);
    }
  }).catch(function () {
    // 回應理論上會完整送達（已實測），但真的斷了也不要謊稱成功。
    showStopped("已送出關閉請求，但在收到回應之前連線就中斷了；伺服器很可能已經停止。");
  });
});
```

配套的函式（放在 `showForm()` 附近）：

```js
function showStopped(message) {
  closeSse();
  $("status-bar").hidden = true;
  $("form-view").hidden = true;
  $("discussion-view").hidden = true;
  $("stopped-view").hidden = false;
  $("stopped-reason").textContent = message;
}
```

⚠️ **既有的「無法連上伺服器（它可能已經停止）」三處一律不准改。** 那是**非預期**斷線
的訊息，仍然正確；這一包新增的是「使用者自己按的」那條路徑，兩者要分得開。

### 6.5 順手收掉的兩個 UI 小問題

**(1) 表單畫面上方那條空的深色圓角條。** 四個 chip 在表單檢視全是空字串 ⇒ 被
`.chip:empty` 隱藏 ⇒ 剩一個空面板。純 CSS 解，加在 `.chip-alert` 那條**之後**、
`[hidden]` 那條**之前**：

```css
#status-bar:not(:has(.chip:not(:empty))) { display: none; }
```

**(2) 檔案選擇按鈕還是瀏覽器預設的淺色。** 加在 `#form-view input[type="file"]`
那組規則**之後**：

```css
#form-view input[type="file"]::file-selector-button {
  font: inherit;
  font-size: .85rem;
  background: var(--panel-3);
  color: var(--text);
  border: 1px solid var(--line);
  border-radius: var(--radius-sm);
  padding: 6px 12px;
  margin-right: 10px;
  cursor: pointer;
}
```

### 6.6 🔴 其他 JS 一個字都不准動

變數名、函式名、判斷順序、既有字串內容——**本文沒點名的一律原樣保留**。
本頁的 JS 互動行為**沒有任何自動化測試**（本專案刻意不建 DOM 測試環境，
`SPEC.md` §7：無建置步驟），所以改動範圍越小，被守住的比例越高。

---

## 7. `start.sh`（新檔）

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

🔴 **要求逐字照抄上面這段**，理由：

- **`--dry` 的處理方式與 `run.sh` 完全一致**（只看第一個參數、`shift` 掉），
  兩支腳本行為一致才不用記兩套。
- 🔴 **不准用陣列累積參數**（`args=()` ＋ `"${args[@]}"`）。macOS 內建的
  `/bin/bash` 是 3.2，在 `set -u` 下展開空陣列會直接報 unbound variable
  ——034 要在 Mac 上跑，現在就守住。`"$@"` 沒有這個問題。
- **檔案權限**：`chmod +x start.sh`。
- ⚠️ **不准執行它**（預設 `--live`，會花錢）。用 `bash -n start.sh` 檢查語法即可。

---

## 8. 測試（必做，不是加分項）

### 8.1 `tests/test_server.py`

新增一個獨立的 test class（**不要改 `ServerCase.start()`**，那會動到所有既有測試）。
它需要自己留住 `serve_forever` 的執行緒才能斷言「伺服器真的停了」：

```python
class ShutdownTest(unittest.TestCase):
    def start(self):
        srv = server.build_server(ask_fn=make_ask_fn(), live=False, port=0)
        thread = threading.Thread(target=srv.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(srv.server_close)
        self.addCleanup(srv.shutdown)
        return srv, srv.server_address[1], thread
```

必須有這幾條（每一條都要能單獨翻紅）：

| # | 測什麼 | 斷言 |
|---|---|---|
| 1 | 正常關閉 | `POST /api/shutdown` 回 `200`、body 解析後 `== {"stopping": True}` |
| 2 | **真的停了** | 承上，`thread.join(timeout=5)` 之後 `thread.is_alive()` 是 `False` |
| 3 | 回應先送完 | 第 1 條能讀到完整 body 這件事本身就是證明——請在該測試的 docstring 寫明這是在守什麼 |
| 4 | 🔴 跨來源被擋 | `Origin: http://evil.example.com` ⇒ `403`，**且伺服器仍活著**（`thread.is_alive()` 是 `True`） |
| 5 | 🔴 Host 不符被擋 | `Host: evil.example.com` ⇒ `403`，**且伺服器仍活著** |
| 6 | 🔴 Content-Type 被擋 | 不送 `Content-Type`（或送 `text/plain`）⇒ `415`，**且伺服器仍活著** |
| 7 | 有 body 鍵 | `{"x": 1}` ⇒ `400`，**且伺服器仍活著** |
| 8 | 空 body 也可以 | 不帶 body 的 POST（但帶 `Content-Type: application/json`）⇒ `200` |
| 9 | 🔴 `GET /api/shutdown` | ⇒ `404`，**且伺服器仍活著** |

🔴 **第 4～7、9 條的「伺服器仍活著」是這一包最重要的斷言。** 023 的教訓：上一個新增的
POST 端點就是在守門上開了洞，當時 264 個測試全過、**沒有任何東西守住它**。
只斷言狀態碼不夠——狀態碼對了但伺服器已經停掉，一樣是災難。

⚠️ 第 9 條的 `GET` 用既有的 `request()` 輔助函式時**不要帶 body**
（帶了會變成 POST 語意）。

### 8.2 `tests/test_ui.py`

在 `IndexHtmlStructureTest` 裡加結構性斷言（只檢查原始碼字串——本專案沒有 DOM 測試
環境，這件事請寫進 docstring，不要假裝測到了互動行為）：

| 測什麼 | 斷言 |
|---|---|
| 中止按鈕存在 | `id="btn-shutdown"` 在原始碼裡 |
| 已關閉畫面存在 | `id="stopped-view"`、`id="stopped-reason"` 都在 |
| 中止有二次確認 | `關閉 council` 這幾個字出現在 `confirm(` 的文案裡（用 `assertIn("想留下逐字稿的話", source)` 這種逐字比對即可） |
| 🔴 `confirm_over_cap` 仍恰好一次 | **既有測試已經在守，不要動它，但你要確認它沒被你弄壞** |
| README 指路句 | `見 README 的「換模型／調整發言順序」` 在原始碼裡 |
| 沒有多的 id 衝突 | `id="context-chars-text"` 在原始碼裡**恰好出現一次** |

🔴 **不要為了「看起來有測到」寫假的 DOM 模擬。**

### 8.3 全套測試

```bash
python3 -m unittest discover tests
```

**必須全過。** 目前是 323 個，你會讓它變多。
🔴 **回報時附上實際的最後三行輸出**（`Ran N tests`／`OK` 或 `FAILED`）。
⚠️ 不准只回報「測試通過」——011 那次回報交付完成、實跑是 `FAILED (errors=1)`。

---

## 9. 交付前自己確認的清單

- [ ] `python3 -m unittest discover tests` 全過，附上實際輸出最後三行
- [ ] `bash -n start.sh` 無語法錯誤；`start.sh` 有可執行權限；**沒有執行過它**
- [ ] `python3 src/serve.py --open --port 8791` 起得來（dry run）、瀏覽器有被開啟或印出
      「無法自動開啟瀏覽器」；**用完自己關掉，不要留在背景**
- [ ] `grep -n "open(" src/server.py` → 0 命中
- [ ] `grep -nE "innerHTML|outerHTML|document\.write|eval\(|localStorage|setTimeout|setInterval|url\(|<svg|https?://" src/static/index.html` → 0 命中
- [ ] `grep -c "confirm_over_cap" src/static/index.html` → **恰好 1**
- [ ] `grep -c 'id="context-chars-text"' src/static/index.html` → **恰好 1**
- [ ] `[hidden] { display: none !important; }` 仍是 stylesheet 的**最後一條規則**
- [ ] 沒有動 `README.md`／`SPEC.md`／`AGENTS.md`／`run.sh`／`src/engine/*`／`src/cli.py`／`src/ui.py`
- [ ] 沒有執行任何版控指令、沒有碰 8765、沒有跑 `--live`、沒有呼叫任何 CLI

## 10. 卡住怎麼辦

契約有矛盾、或某條驗收條件在任何實作下都不可能成立 ⇒ **寫 `dispatch/BLOCKED.md`
說明卡在哪一條、為什麼**，不要自己選一個讀法硬做。
（030 那次你開 BLOCKED 是對的，是主對話出題漏看了一條既有測試。）
