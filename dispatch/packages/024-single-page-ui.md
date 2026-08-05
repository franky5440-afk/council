# 工作包 024：單頁 web UI（HTML／CSS／JS）

**動手前整段讀完 `SPEC.md` §7、§7.1、§7.2**（後者是伺服器的安全規格），
另讀 §5（六道停止邊界，特別是邊界 3／5／6）、§6、§6.1（仲裁）、§3.3（脈絡）。

**然後直接讀 `src/server.py`。** 那是 HTTP API 的唯一權威形狀，本工作包引用它但
不重述細節；本檔與 `src/server.py` 的實際行為衝突時，以程式碼為準並照 BLOCKED 流程回報。

022／023 已經把 JSON API 與 SSE 做完了，但 **`GET /` 目前回 404，沒有任何畫面**。
本包補上那個畫面：一個沒有建置步驟、沒有任何第三方依賴的單頁 HTML。

---

## 檔案

| 檔案 | 動作 |
|---|---|
| `src/static/index.html` | **新增**：整個 UI（HTML ＋ 內嵌 `<style>` ＋ 內嵌 `<script>`，就這一個檔） |
| `src/ui.py` | **新增**：啟動時把上面那個檔讀進記憶體一次 |
| `src/server.py` | **修改**：只新增 `GET /` 一條路由（見下方精確內容） |
| `tests/test_ui.py` | **新增**：本包的測試 |
| `tests/test_server.py` | **只刪兩行**：既有那條 `GET / ⇒ 404` 的斷言（見下） |

🔴 **除了上表，一個字都不要動。** 特別是 `src/serve.py`、`src/cli.py`、`src/engine/` 底下
所有檔案、`run.sh`、`dispatch.sh`、`SPEC.md`、`AGENTS.md`、其他既有測試檔。

### 為什麼多一個 `src/ui.py`，不把讀檔寫進 `server.py`

022 有一條結構性紅線：**`server.py` 全檔不得出現 `open(` 或 `pathlib`**
（`SPEC.md` §7.2「伺服器不開檔」）。那條紅線保護的是「**請求不能決定要開哪個檔**」——
把路徑變成 HTTP 參數，等於讓任何打得到這個埠的東西指定要外送哪個本機檔案。

靜態頁面要從磁碟來，就得有人開檔。兩種放法：

- 把 HTML 塞成 `server.py` 裡的一個大字串常數 ⇒ 紅線完好，但那份 HTML 從此帶著
  Python 的跳脫規則，沒有語法高亮、改一行 CSS 都要跟引號搏鬥。
- **另開一個只做這件事的小模組**（採用這個）⇒ `server.py` 的紅線**原封不動**，
  而放寬的範圍縮到一個五行的檔案裡，審查時一眼看得完。

⇒ `src/ui.py` 是**唯一**被允許開檔的新檔，而且只准開一個**寫死在原始碼裡、
相對於模組自身**的檔名，在**模組載入時讀一次**。
🔴 **`server.py` 的四條 022 紅線在本包之後必須仍然全部成立**（驗收會逐條 grep）。

---

## 🔴 本包的結構性紅線（可用 grep 驗，驗收逐條檢查）

1. **`src/server.py` 全檔不得出現 `open(`、`pathlib`、`Access-Control`、`.status()`，
   也不得 import `adapters` 或 `subprocess`。**（022 的四條紅線，本包不放寬。）

2. **`src/ui.py` 全檔不得 import `server`、`engine`、`adapters`、`subprocess`。**
   它只認識 stdlib 與那一個檔名。也**不得有任何接受路徑參數的函式**——
   本模組的公開介面只有一個常數，沒有函式。

3. **`src/static/index.html` 全檔不得出現這些字串**：
   `innerHTML`、`outerHTML`、`insertAdjacentHTML`、`document.write`、`eval(`、
   `new Function`、`Function(`。
   ⚠️ **這是本包的頭號風險**：逐字稿是**模型產生的文字**，一段回覆裡出現
   `<img src=x onerror=...>` 是完全可能的，而它會被原樣塞進 DOM。
   **所有來自伺服器的文字一律走 `textContent` 或 `document.createTextNode`**，
   結構一律 `document.createElement`。

4. **`src/static/index.html` 全檔不得出現 `http://` 或 `https://`。**
   頁面完全自給自足：不載入任何 CDN、字型、圖示、外部圖片；所有請求都是相對路徑。

5. **`src/static/index.html` 全檔不得出現 `localStorage`、`sessionStorage`、
   `indexedDB`、`document.cookie`。**
   逐字稿裡含使用者自己送進去的專案脈絡（§3.3），而 §7.1 講明討論**只在記憶體**、
   一停就沒了。頁面把它抄一份到瀏覽器儲存，等於偷偷做了 §8 明確延後的「討論存檔」。

6. **`src/static/index.html` 全檔不得出現 `setInterval` 或 `setTimeout`。**
   §5 邊界 1：輪與輪之間一定要人。任何計時器都是「頁面自己決定何時再花一次錢」的
   起點，即使這一版沒那樣用。即時進度靠 SSE，不需要輪詢。

7. **JS 不得把任何檔案路徑送給伺服器。** 脈絡是**瀏覽器讀完檔案之後送出的內容本文**
   （`FileReader`），請求 body 只有下面契約列出的那幾個鍵。

---

## 介面契約（照字面實作，不要擴充公開介面）

### A. `src/ui.py`（新增）

實作**就是**下面這樣，不要多做：

```python
"""GET / 的靜態頁面：模組載入時讀一次，之後只在記憶體裡（工作包 024）。

本檔是全 repo 唯一開檔的伺服器端模組，而且只開一個寫死在原始碼裡、
相對於本模組的檔名——請求無法影響要開哪個檔（SPEC.md §7.2）。
"""

import os

_INDEX_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "static", "index.html")

with open(_INDEX_PATH, "rb") as handle:
    INDEX_HTML = handle.read()
```

- 🔴 讀成 **bytes**（`"rb"`），不要 decode、不要 `.format()`、不要做任何字串處理。
  頁面裡有 `{`／`}`（CSS 與 JS 到處都是），任何格式化都會炸。
- 🔴 **只在模組載入時讀一次**，不要每個請求重讀。改了 HTML 就重啟伺服器
  （討論本來就只在記憶體，重啟一律從零，這不構成額外損失）。
- 檔案不存在時讓例外原樣往外丟：伺服器直接起不來，比起來安靜地送出 404 好得多。

### B. `src/server.py`（修改：只加 `GET /`）

**(1) import**：在既有 import 區塊加一行 `import ui`（比照 `serve.py` 的 `import server`）。

**(2) 路由**：在 `_dispatch()` 的 `GET` 分支最前面加一條，其餘一行不動：

```python
            if self.command == "GET":
                if urlparse(self.path).path == "/":
                    self._get_index()
                elif kind == "discussion":
                    ...
```

**(3) 新增 handler**，比照既有 `_reply_json` 的寫法：

```python
    def _get_index(self) -> None:
        body = ui.INDEX_HTML
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)
```

- 🔴 **路徑比對必須是 `== "/"` 的完全相等**，不是 `startswith`、不是 `in`。
  `/index.html`、`/static/index.html`、`//`、`/../src/server.py` 全部維持 `404`。
  **這是本包唯一的靜態路由，不要長出任何路徑到檔案的對映。**
- 🔴 **`GET /` 必須照樣走 `_gate()`**（§7.2 的四道守門）。把它放在 `_dispatch()` 裡
  `self._gate()` **之後**的既有 GET 分支內就自然成立——**不要為了「靜態頁不需要檢查」
  把它提前到守門之前**。惡意網頁載入這個頁面本身沒有直接危害，但守門是**互相支撐的
  一組**（§7.2），開一個沒有理由的例外，下一個人就會以為那條檢查是可選的。
- `POST /` 與 `DELETE /` 維持現狀（會走到既有分支回 `404`）。**不要為它們加 `405`**——
  多一個分支換一個沒人在意的狀態碼，不值得。
- ⚠️ **不要實作 `do_HEAD`**、不要加 `ETag`／`Last-Modified`／gzip。

### C. `tests/test_server.py`（只刪兩行）

`test_get_missing_and_unknown_paths_404` 裡有這兩行，現在會失敗——**刪掉它們**：

```python
        status, _, _ = request("GET", port, "/")
        self.assertEqual(status, 404)
```

`GET /` 的行為改由 `tests/test_ui.py` 負責。
🔴 **這個檔案除了刪這兩行，其他一個字都不准動**（包含測試名稱）。

### D. `src/static/index.html`（新增：整個 UI）

單一檔案，結構是 `<!doctype html>` ＋ `<head>`（含一個 `<style>`）＋ `<body>`
（含一個 `<script>`）。**恰好一個 `<style>`、恰好一個 `<script>`，都內嵌，
不得有 `src=` 的外部腳本。**

`<head>` 必須含這一行，值**逐字元照抄**：

```html
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; connect-src 'self'; img-src 'none'; form-action 'none'; base-uri 'none'">
```

⚠️ **老實說這條 CSP 買到的不是 XSS 防護**（內嵌腳本必須 `'unsafe-inline'`，
那等於對注入的 `<script>` 開門）。它買到的是**這個頁面打不出去**：
`default-src 'none'` ＋ `connect-src 'self'` ＋ `img-src 'none'` 之下，就算真有東西
被注入，它也載不了外部資源、送不出請求。真正擋 XSS 的是紅線 3。兩者都要。

#### D-1. 畫面分區

三塊，由上而下：

1. **狀態列（常駐）**：模式徽章、討論 id、相位、輪次 `N / 上限`、收斂提示、忙碌指示。
2. **主區**：`建立討論表單`（尚未有討論時）**或**`逐字稿`（有討論時）。兩者擇一顯示。
3. **用量面板（常駐，§5 邊界 6）**：總計與各席次分計。

樣式要求就三條：內嵌、無外部資源、逐字稿用 `white-space: pre-wrap`
（模型輸出是多行純文字）。**不要做深色模式切換、動畫、RWD、圖示。**
1024px 寬看得清楚就夠了。

#### D-2. 模式徽章（會不會花錢，這是畫面上最重要的一件事）

- `live === true` ⇒ 紅底徽章「**LIVE — 每次開輪／仲裁都會消耗訂閱額度**」。
- `live === false` ⇒ 灰底徽章「DRY RUN — 不會呼叫任何 CLI」。
- **尚未收到任何 API 回應時** ⇒ 灰底「模式：尚未確認」。

⚠️ 頁面**無法在建立討論之前知道 `live`**——`live` 只出現在 API 回應裡，而頁面是
啟動時讀進記憶體的靜態位元組（§7.2：花不花錢由行程啟動時決定）。
**不要為此新增任何 API 端點或把 `live` 塞進 HTML。**
這不構成風險：建立討論**不花錢**，而兩個會花錢的按鈕只存在於討論檢視裡，
那時 `live` 必定已知。

#### D-3. 進入頁面時

1. 讀 `location.hash`。
2. 沒有 hash ⇒ 顯示建立表單。
3. 有 `#<id>` ⇒ `GET /api/discussions/<id>`：
   - `200` ⇒ 進討論檢視，開 SSE（見 D-6）。
   - `404` ⇒ 清掉 hash、回到建立表單，並顯示一行：
     「**找不到這個討論。伺服器一重啟，記憶體裡的討論就消失了（`SPEC.md` §7.1）。**」
     ⚠️ 這句不是客套，是 §7.1 明訂的行為，使用者必須知道自己不是遇到 bug。

#### D-4. 建立表單

| 欄位 | 型態 | 預設值 |
|---|---|---|
| 問題 | `<textarea>`，必填 | 空 |
| 顧問 | `<textarea>`，一行一席，空白行忽略 | `run.sh` 的那三席免費模型（見下） |
| 仲裁者 | `<input type="text">` | `claude` |
| 脈絡 | `<textarea>` ＋ `<input type="file">` | 空 |

顧問欄的預設值逐字是這三行：

```
opencode:opencode/deepseek-v4-flash-free
opencode:opencode/nemotron-3-ultra-free
opencode:opencode/ling-3.0-flash-free
```

理由：這三席是**已實測的零成本配置**，預設值不該讓人一按就花錢。
仲裁者預設 `claude` 是付費席，但仲裁是另一個按鈕、要另外按（§6.1），與 `run.sh` 一致。

- 席次字串格式 `<cli>[:<模型>]`，表單旁寫一行說明即可，**不要在 JS 裡驗證格式**——
  伺服器已經用 `parse_seat_spec()` 驗了，錯誤訊息會回來（在這裡寫第二份就是兩份會
  各自過期的規則）。
- 說明文字要寫明：**顧問 1～3 位（含仲裁者共 2～4 席）**。超過會被伺服器擋下並回 `400`。
- **脈絡的檔案輸入**：`FileReader.readAsText()` 讀完後把**內容**填進脈絡 textarea，
  使用者可以再編輯。textarea 下方常駐顯示目前字元數。
  🔴 檔名可以顯示，**但絕不送出**。表單旁必須寫明：
  「**檔案由你的瀏覽器讀取後送出內容，伺服器不會去開你的檔案（`SPEC.md` §7.2）。**」
- 送出 ⇒ `POST /api/discussions`，body **恰好**這四個鍵：

  ```json
  {"question": "...", "advisors": ["...", "..."], "arbiter": "...", "context": "..."}
  ```

  `advisors` 是把 textarea 逐行 trim、去掉空白行後的陣列。
- 非 `200` ⇒ 把回應的 `error` 欄位顯示在表單上方（`textContent`），**留在表單**。
- `200` ⇒ 設 `location.hash = id`，切到討論檢視，開 SSE。

#### D-5. 討論檢視

固定顯示：原始問題、席次表（`seat_id` / `cli` / `model` / `role`）、`context_chars`。
⚠️ **伺服器不回傳脈絡原文**（§7.2），畫面上只能有字元數，**不要試圖顯示脈絡內容**。

兩個會花錢的按鈕，`busy === true` 時一律 disabled：

**「再一輪」**

1. `status.at_cap === true` ⇒ 先跳 `window.confirm()`，訊息必須講出代價，例如：
   「已達 N 輪上限。再開一輪會再向每一位顧問各發出一次呼叫（會花錢）。確定要繼續嗎？」
   - 使用者取消 ⇒ **什麼都不送**。
   - 使用者確認 ⇒ body `{"confirm_over_cap": true}`。
2. `at_cap` 為 false ⇒ body `{}`，**不帶 `confirm_over_cap`**。
3. 🔴 **`confirm_over_cap` 為 `true` 的那個值在全檔只准出現一次，而且必須在
   使用者確認之後那條路徑上。** 用 `window.confirm()` 是刻意的選擇：它是零程式碼的
   阻斷式確認，不需要為二次確認長出一整套 DOM 狀態機。

**「叫仲裁者」** ⇒ `POST /api/discussions/<id>/arbitration`，body 送 `"{}"`。

🔴 **每一個 POST 都必須帶 `Content-Type: application/json`，即使 body 是空物件。**
§7.2 第 3 道現在對**所有 POST** 生效（023 修的就是這個），漏帶會拿到 `415`。

**回應處理（兩個按鈕共用）**

| 回應 | 畫面 |
|---|---|
| `200` | 用回應的 `status`／`busy`／`live` 更新狀態列與用量面板 |
| `409` ＋ `code === "busy"` | 「另一個分頁正在跑這個討論。」並重新 `GET` 一次同步狀態 |
| `409` ＋ `code === "boundary"` | 直接顯示回應的 `error` 文字 |
| 其他非 `200` | 顯示 `error` 文字；沒有 `error` 鍵就顯示狀態碼 |

🔴 **仲裁失敗時要把「仲裁進行中」的佔位收掉**（見 D-7 的 `arbitration_started`）。
`arbitration_started` 事件是**在呼叫之前**發出的（022 刻意如此：仲裁者拿最長的逐字稿，
畫面必須先亮），所以前提不成立時**事件已經發出、仲裁卻沒發生**。
JS 收到非 `200` 就必須把那個佔位換成錯誤訊息，否則畫面會永遠掛著一個不會結束的「進行中」。

**邊界的可見性**

- `status.converged === true` ⇒ 醒目提示「**全體顧問都表示沒有補充了 — 可以收斂**」（邊界 5）。
- `status.at_cap === true` ⇒ 狀態列顯示「已達 N 輪上限」，按鈕文字改成「再一輪（需確認）」（邊界 3）。
- `status.format_violations > 0` ⇒ 顯示「格式違規 N 次」。

#### D-6. SSE

- 用 `new EventSource("/api/discussions/" + id + "/events?cursor=0")`（相對路徑）。
- 🔴 **切進討論檢視、開連線之前，先清空逐字稿容器。** 逐字稿**只從事件流重播**
  （GET 不回傳 `rounds`，那是 022 刻意的設計），所以「重新整理頁面」與
  「SSE 斷線重連」走的是同一條路徑——這是它唯一需要的程式碼，不要另外寫一份。
- 每一種事件各自 `addEventListener("<kind>", …)`。
  🔴 **不要用 `onmessage`**：伺服器的每一則事件都帶 `event:` 名稱，
  預設事件根本不會發生，用 `onmessage` 會是一條永遠不執行的死路。
- 每則的 `event.data` 一律 `JSON.parse()`（伺服器保證是單行 JSON）。
- `onerror` ⇒ 在狀態列顯示「連線中斷，瀏覽器會自動重連」。
  🔴 **不要自己實作重連**：`EventSource` 內建重連並會帶 `Last-Event-ID`，
  伺服器認這個標頭（`> cursor`，不重不漏）。自己寫一份只會重播出重複的發言。
- 回到建立表單或換討論時，先 `close()` 舊連線。**同時只准有一條。**

#### D-7. 事件 → 畫面

| 事件 | `data` | 畫面動作 |
|---|---|---|
| `round_started` | `{round}` | 新增一個「第 N 輪」標題 |
| `speech` | **就是那筆 record 本身**（不是包一層） | 新增一張發言卡（見下） |
| `round_finished` | `{round, status}` | 用 `status` 更新狀態列與用量面板 |
| `arbitration_started` | `{seat_id}` | 新增「仲裁者 X 正在讀完整逐字稿…」佔位，**留住參照** |
| `arbitration_finished` | `{record, status}` | 把佔位換成仲裁結果卡；用 `status` 更新用量 |
| `error` | 未定 | 顯示成一則錯誤列 |

⚠️ **目前沒有任何地方會發出 `error` 事件**（022 保留的）。**保留處理但不要為它發明產生端。**

**發言卡的內容**（record 的鍵見 `state.record_speech()`）：

- 標題：`seat_id`。
- 徽章（有才顯示）：`stance` ⇒「立場: X」；`more === false` ⇒「補充: 無」；
  `truncated` ⇒「已截斷」；`violation` ⇒「格式違規」；
  `model_used === null` ⇒「模型未經確認」（§2.2：`opencode` 不回報，這是常態不是錯誤）；
  `elapsed_s` ⇒「N.N 秒」。
- 內文：`ok === true` ⇒ `text`（🔴 `textContent`）；
  `ok === false` ⇒「未回應：<error>」（`error` 為 null 時只寫「未回應」）。
  ⚠️ 失敗時 `text` 是空字串，**不要顯示一張空白卡**。
- 仲裁結果卡用不同底色，並標明「**仲裁者 — 不參與輪替、不計入收斂**」（§6.1）。
  ⚠️ 仲裁 record **只有八個鍵，沒有 `stance`／`more`／`violation`**，那是刻意的
  （§6.1）——**不要對它套用發言卡那三個徽章**，也不要因為「少了鍵」就加預設值。

#### D-8. 用量面板（§5 邊界 6，常駐）

`status.usage` 的形狀是 `{calls, total, by_seat: {<seat_id>: {calls, usage}}}`。

- 一律顯示 `calls`（總計與各席次），**這一項永遠有值**。
- `total` 與各席次的 `usage` 是**由各家 CLI 的輸出決定的自由形狀 dict**
  （`claude` 有 `total_cost_usd`、`cache_creation_input_tokens`…，`opencode` 免費模型
  回 `cost: 0`）。
  🔴 **不得寫死任何 token／成本的鍵名。** 遞迴攤平巢狀 dict（鍵以 `.` 串接），
  把數值型的葉節點依鍵名排序後全部列出。非數值的值直接略過。
- 鍵名含 `cost` 的項目排在最前面並加粗——那是使用者最需要一眼看到的。
- `total` 是空物件 `{}` 時（dry run 就是這樣：假 ask_fn 的 `usage` 是 `None`）
  ⇒ 顯示「（本次未取得用量統計）」，但 **`calls` 仍然要照常顯示**。
  ⚠️ 這是最容易做出「面板看起來壞掉」的情境，dry run 全程都會遇到。
- 🔴 鍵名來自各家 CLI 的輸出 ⇒ **鍵名與值一律用 `textContent`**，和逐字稿同一條規矩。

---

## 測試（`tests/test_ui.py`，新增）

比照既有測試檔開頭的寫法把 `src` 加進 `sys.path`。
🔴 **不得 import `adapters`、`subprocess`、`unittest.mock`。** 可以 import
`json`、`threading`、`re`、`unittest`、`sys`、`pathlib`、`urllib.request`、`urllib.error`，
以及 `server`／`ui`。伺服器夾具比照 `tests/test_server.py`（🔴 **必須 `port=0`**）。

### 路由行為

1. `GET /` ⇒ `200`，`Content-Type` 為 `text/html; charset=utf-8`，
   `Cache-Control` 為 `no-store`，有 `Content-Length`，
   **body 的位元組與 `ui.INDEX_HTML` 完全相同**。
2. 🔴 **回應不得含任何以 `Access-Control-` 開頭的標頭。**
3. `GET /?x=1` ⇒ `200`（查詢字串不影響路徑比對）。
4. 🔴 `GET /index.html`、`GET /static/index.html`、`GET //`、
   `GET /../src/server.py` ⇒ **全部 `404`**。
5. 🔴 `GET /` 帶 `Host: evil.example.com` ⇒ `403`（守門對靜態頁一樣生效）。
6. `POST /` ⇒ `404`（維持現狀，不是 `405`）。
7. `GET /api/discussions/<不存在的 id>` 仍然 `404`（證明沒有把靜態路由做成 catch-all）。

### `src/ui.py`

8. `ui.INDEX_HTML` 是 `bytes` 且長度 > 0。
9. 讀 `src/ui.py` 的原始碼，斷言其中**不出現** `server`、`engine`、`adapters`、
   `subprocess` 這幾個字。

### `src/static/index.html` 的結構性紅線

以 `pathlib` 讀進原始碼字串後斷言（不要用外部工具）：

10. 🔴 不出現 `innerHTML`、`outerHTML`、`insertAdjacentHTML`、`document.write`、
    `eval(`、`new Function`、`Function(`。
11. 🔴 不出現 `http://`、`https://`。
12. 🔴 不出現 `localStorage`、`sessionStorage`、`indexedDB`、`document.cookie`。
13. 🔴 不出現 `setInterval`、`setTimeout`。
14. 含 `textContent`（證明真的走了安全那條路，不是整頁沒有動態內容）。
15. CSP `<meta>` 存在，且 `content` 屬性的值與 D 節寫的**逐字元相同**。
16. `<script` 恰好出現一次、`<style` 恰好出現一次，且**不出現 `<script src=`**。
17. 🔴 `confirm_over_cap` 恰好出現一次，且全檔含 `confirm(`。
18. 六個事件名稱（`round_started`／`speech`／`round_finished`／
    `arbitration_started`／`arbitration_finished`／`error`）全部出現。

⚠️ **老實話：JS 的行為本身沒有自動化測試，本包也不要為它建一套。**
那需要 headless 瀏覽器或 node 測試框架，而 `SPEC.md` §7 明訂「無建置步驟」、
本 repo 至今是純 stdlib Python。上面 10～18 守的是**結構性紅線**（能 grep 的部分），
互動行為由 Frank 親手實測。**不要為了「看起來有測到」寫假的 DOM 模擬。**

---

## 驗收條件（貼真實輸出，不要只描述）

1. `python3 -m unittest discover tests` **全過**，貼出最後三行。
   🔴 **既有 265 個測試扣掉刪掉的那條斷言之後，一個都不得變紅。**
   ⚠️ 工作包 011 曾回報「交付完成」而實跑是 `FAILED (errors=1)`。**自己實際跑完再回報。**
2. 說明新增了幾個測試（貼出數字怎麼算的）。
3. 貼出 022 四條紅線在本包之後仍然成立：
   - `grep -nE '^(import|from)' src/server.py` ——不得有 `adapters`／`subprocess`。
   - `grep -nE 'open\(|pathlib|Access-Control' src/server.py` ——**應為空**。
   - `grep -n '\.status()' src/server.py` ——**應為空**。
   - `grep -n 'try_claim' src/server.py` ——仍**恰好兩處**。
4. 貼出本包新紅線的 grep 結果（每一條都要，包含**空輸出**也要貼出來證明跑過）：
   - `grep -nE 'innerHTML|outerHTML|insertAdjacentHTML|document\.write|eval\(|new Function|Function\(' src/static/index.html`
   - `grep -nE 'https?://' src/static/index.html`
   - `grep -nE 'localStorage|sessionStorage|indexedDB|document\.cookie' src/static/index.html`
   - `grep -nE 'setInterval|setTimeout' src/static/index.html`
   - `grep -nE 'server|engine|adapters|subprocess' src/ui.py`
   - `grep -c 'confirm_over_cap' src/static/index.html` ——應為 `1`。
5. 貼出 `git diff --stat` 與 `src/server.py`、`tests/test_server.py` 的**完整 `git diff`**，
   證明這兩個檔的變更都非常小。
6. **實際把伺服器跑起來驗一次（🔴 全程 dry run，不得加 `--live`）**，貼出真實輸出：
   ```bash
   python3 src/serve.py --port 0   # 背景跑；埠號從它印出的 URL 取
   curl -s -o /dev/null -w '%{http_code} %{content_type}\n' http://127.0.0.1:<port>/
   curl -s http://127.0.0.1:<port>/ | wc -c        # 與 index.html 的位元組數相同
   curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:<port>/index.html   # 應為 404
   ```
   ⚠️ `--port 0` 會拿到隨機埠，不會撞到 Frank 自己開著的伺服器。
   驗完把行程收掉，並貼出收掉的指令。
7. **突變驗證六項**，每項：改壞 → 貼失敗輸出（**含翻紅的測試名**）→ 還原 →
   最後貼還原後全過的結果。
   - (a) `_get_index` 的路徑比對 `== "/"` 改成 `startswith("/")` ⇒ 測試 4 翻紅。
   - (b) 拿掉 `GET /` 那條路由 ⇒ 測試 1 翻紅。
   - (c) `Content-Type` 改成 `text/plain` ⇒ 測試 1 翻紅。
   - (d) 把 `GET /` 的處理提到 `_gate()` 之前 ⇒ 測試 5 翻紅。
   - (e) 在 `index.html` 的 JS 裡插入一行含 `innerHTML` 的程式碼 ⇒ 測試 10 翻紅。
   - (f) 拿掉 `index.html` 的 CSP `<meta>` ⇒ 測試 15 翻紅。
   - 🔴 **突變只准動 `src/server.py` 與 `src/static/index.html`**，
     不准動測試檔、不准動測試裡的樣本值。
   - 🔴 **每一項動手前先確認要取代的字串在檔案裡是唯一的**：印出 `text.find(old)`
     與 `text.rfind(old)`，**兩個位置必須相同**才可以取代。
     ⚠️ 工作包 019 踩過：要改的那幾行在另一個函式裡字面完全相同，
     `replace(old, new, 1)` 打到的是另一側，畫面上是漂亮的一片紅、
     **但要驗的那一側完全沒被驗到**。翻紅之後也要看一眼**紅的是不是預期的那幾個測試名**。
   - 🔴 **備份放 `dispatch/tmp/024-backup/`，不要放 `/tmp`。**
     還原後用 `cmp` 確認與備份**位元組相同**，並貼出結果。
8. 貼出 `git status --short`，應該只有三個新檔（`?? src/ui.py`、`?? src/static/`、
   `?? tests/test_ui.py`）與兩個 `M`（`src/server.py`、`tests/test_server.py`）。
   ⚠️ `dispatch/tmp/` 已被 `.gitignore` 排除，備份不會出現在這裡，這是正常的。
9. 🔴 **公開發布掃描**（本 repo 是 PUBLIC）：貼出
   `grep -rnE "$(whoami)|/home/[a-z]" src/ui.py src/static/index.html tests/test_ui.py`
   ——**應為空**。不得寫入任何本機絕對路徑、使用者名稱或個人資訊。

---

## 不要做的事

- 🔴 **全程不得執行 `--live`，不得呼叫任何真實 CLI。** 本包完全不需要花錢就能驗完。
- ⚠️ **不要引入任何第三方套件、CDN、字型、圖示庫、bundler、npm、node、建置步驟。**
  `SPEC.md` §7：單頁 HTML ＋ 原生 JS，無建置步驟。
- ⚠️ **不要用任何前端框架**（React／Vue／Svelte／htmx／Alpine／jQuery）。
- ⚠️ **不要動 API 的形狀**，不要新增端點、不要改回應欄位。API 是 022／023 的成果，
  本包只消費它。發現 API 缺了什麼 ⇒ 寫進 `dispatch/BLOCKED.md`，不要自己加。
- ⚠️ **不要在 JS 裡重寫任何停止邊界的判斷。** 邊界 1／3 在 `state.py`、
  仲裁前提在 `run_arbitration()`；畫面只負責**顯示**它們與把錯誤翻成人看得懂的字。
  在這裡寫第二份，就會出現兩份會各自過期的規則。
- ⚠️ **不要做自動再一輪、自動仲裁、自動重試、輪詢**（紅線 6）。
- ⚠️ **不要做討論存檔／匯出／列印／複製全部逐字稿到剪貼簿**（§8 明確延後）。
- **不要加使用者認證、token、密碼。** §7.1 的不可猜 id 就是憑證。
- 不要落檔：不寫 log、不寫 JSON、不做任何持久化。
- 不要覆寫 `log_message` 消音，也不要另外加 `logging`。
- 不要碰版控（`git add` / `commit` / `push` 一律不執行）。
- 不要修改 `AGENTS.md`、`SPEC.md`、`dispatch.sh`、`run.sh`。
