# 工作包 029：把一場討論匯出成 Markdown

Frank 實測回報：**整輪討論完，沒有任何辦法把議會內容存下來。** 逐字稿只活在瀏覽器的
DOM 與伺服器的記憶體裡，關掉分頁或重啟伺服器就沒了（`SPEC.md` §7.1：討論只在記憶體）。
他要的東西很明確：**能輸出一份 md 檔就夠了。**

這一包的核心設計決定，**先讀懂再動手**：

- 🔴 **Markdown 由伺服器端產生，不在瀏覽器裡拼字串。** 本專案沒有 DOM 測試環境
  （`SPEC.md` §7 明訂無建置步驟），前端拼出來的東西**沒有任何測試守得住**。
  改成「純函式把事件流轉成 md」＋「一條下載路由」之後，整件事在純 Python 測得到。
- 🔴 **資料來源是事件流，不是 `discussion.rounds`。** `rounds` 會被邊跑邊 append，
  直接讀就是 §7.1 警告的撕裂。`session.events_since(0)` 有鎖保護、回深拷貝，
  討論正在跑的時候按匯出也是安全的。這與既有「逐字稿只從事件流重播」是同一條設計。
- 🔴 **前端只加一個 `<a download>`，不寫任何新的 JS 邏輯**，不用 `fetch`、
  不用 `Blob`、不用 `createObjectURL`。

---

## 檔案

| 檔案 | 動作 |
|---|---|
| `src/engine/transcript.py` | **新增**：純函式 `render_markdown(meta, events) -> str` |
| `src/server.py` | **修改**：`_match()` 加一條路由、新增 `_get_export()` |
| `src/static/index.html` | **修改**：一個 `<a>`、一段 CSS、`renderDiscussion()` 與 `showForm()` 各一行 |
| `tests/test_transcript.py` | **新增**：純函式測試 |
| `tests/test_server.py` | **修改**：路由與標頭測試 |
| `tests/test_ui.py` | **修改**：兩條結構性斷言 |

🔴 **除了上表，一個字都不要動。** 特別是 `src/engine/state.py`、
`src/engine/orchestrator.py`、`src/engine/sessions.py`、`src/engine/wiring.py`、
`src/ui.py`、`src/cli.py`、`src/serve.py`、`SPEC.md`、`AGENTS.md`、`README.md`、`run.sh`。

---

## 你會拿到的資料（這些形狀是我實際讀原始碼確認的，照著用）

### `events`：`session.events_since(0)` 的回傳

一個 list，每個元素是 `{"seq": int, "kind": str, "data": ...}`，`seq` 由 1 起遞增。
`kind` 有六種，`data` 的形狀分別是：

| kind | data |
|---|---|
| `round_started` | `{"round": N}` |
| `speech` | **顧問發言 record，十一個鍵**（見下） |
| `round_finished` | `{"round": N, "status": <status dict>}` |
| `arbitration_started` | `{"seat_id": "arb"}` |
| `arbitration_finished` | `{"record": <仲裁 record，八個鍵>, "status": <status dict>}` |
| `error` | 目前沒有人發，是保留的 |

**顧問發言 record（十一個鍵）**：
`seat_id`、`ok`、`text`、`truncated`、`error`、`elapsed_s`、`model_used`、`usage`、
`stance`、`more`、`violation`。

**仲裁 record（八個鍵）**：
`seat_id`、`ok`、`text`、`truncated`、`error`、`elapsed_s`、`model_used`、`usage`。

🔴 **仲裁 record 沒有 `stance`／`more`／`violation`，這是 `SPEC.md` §6.1 刻意的設計。**
用 `rec["stance"]` 去讀仲裁 record 會 `KeyError` 當場炸掉。**渲染仲裁時不准碰那三個鍵**
（連 `.get()` 都不要用——不要讓「仲裁者有立場」這件事在程式碼裡看起來成立）。

### `meta`：`server.py` 既有的 `_common_shape(session)` 回傳值

```python
{
  "id": str,             # session id
  "live": bool,          # 伺服器啟動時決定的
  "busy": bool,
  "question": str,
  "context_chars": int,  # 只有字元數，沒有脈絡原文
  "seats": [ {"seat_id": str, "cli": str, "model": str | None, "role": "advisor"|"arbiter"}, ... ],
  "status": {            # discussion.status()
     "phase": str, "rounds_completed": int, "max_rounds": int, "at_cap": bool,
     "can_start_round": bool, "converged": bool, "format_violations": int,
     "usage": {"calls": int, "total": {...}, "by_seat": {seat_id: {"calls": int, "usage": {...}}}}
  }
}
```

🔴 **`meta` 裡沒有脈絡原文，md 裡也不准有。** `SPEC.md` §7.2：狀態查詢不回傳脈絡原文。
md 只寫字元數。

---

## 介面契約（照字面實作）

### A. `src/engine/transcript.py`（新檔）

```python
def render_markdown(meta, events) -> str:
```

🔴 **這個檔案裡不得出現 `import` 這個字。** 它只做字串組裝，不需要任何東西。
（`sessions.py` 只 import 三個 stdlib 是同一個理由：一個不認識別人的模組，
不可能替別人回答問題。）

🔴 **它不接受 `discussion` 物件、不呼叫 `.status()`、不認識 `state`／`sessions`／
`orchestrator`。** 拿到什麼就渲染什麼。

**輸出格式（就是下面這個結構，不要自己加減區塊）**：

````markdown
# council 討論逐字稿

- 討論 id：<meta["id"]>
- 模式：LIVE（真的呼叫過 CLI）      ← meta["live"] 為 True 時
- 模式：DRY RUN（未呼叫任何 CLI）   ← meta["live"] 為 False 時
- 原始問題：<meta["question"]>
- 脈絡：<context_chars> 字元（未包含在本檔）
- 完成輪次：<rounds_completed> / <max_rounds>
- 收斂：全體顧問都表示沒有補充了     ← converged 為 True
- 收斂：尚未收斂                     ← 否則
- 格式違規：<format_violations> 次
- 席次：
  - opencode-1 — opencode：opencode/deepseek-v4-flash-free（顧問）
  - arb — claude（仲裁者）

> 以下逐字稿由各家 CLI 背後的模型產生，未經任何淨化或改寫。

---

## 第 1 輪

### opencode-1

立場: 同意｜補充: 有｜11.5 秒｜模型：未經確認

<發言正文，一個字都不動>

### opencode-2

未回應：<error 內容>

## 仲裁

### arb（仲裁者 — 不參與輪替、不計入收斂）

90.8 秒｜模型：claude-opus-5

<仲裁正文，一個字都不動>

---

## 用量

總呼叫 4 次。金額欄位不列入（council 不呼叫任何模型 API，那些數字是各家 CLI
依 API 定價換算的參考值）。

- opencode-1：calls=1
  - tokens.input：1234
  - tokens.total：5678
- arb：calls=1
  - cache_creation_input_tokens：18919
  - input_tokens：2
  - output_tokens：4830
````

**組裝規則（逐條照做）**：

1. **走訪 `events` 的順序就是它們在 list 裡的順序**，不要重排、不要依 `seq` 排序
   （它本來就已經遞增）。
2. `round_started` ⇒ 輸出 `## 第 <round> 輪`。
3. `speech` ⇒ 輸出 `### <seat_id>`，接一行**徽章行**，接發言正文。
   - 徽章行的項目**只列有內容的**，用 `｜`（全形豎線）串接，順序固定為：
     `立場: <stance>`（`stance` 為 `None` 時整項不列）、
     `補充: 有`／`補充: 無`（`more` 為 True／False）、
     `已截斷`（`truncated` 為 True 才列）、
     `格式違規`（`violation` 為 True 才列）、
     `<elapsed_s 保留一位小數> 秒`、
     `模型：<model_used>`（為 `None` 時寫 `模型：未經確認`）。
   - `ok` 為 True ⇒ 正文就是 `text`，**逐字輸出，不逃逸、不截斷、不改任何字元**。
   - `ok` 為 False ⇒ **不輸出徽章行**，正文寫 `未回應：<error>`；
     `error` 為 `None` 或空字串時只寫 `未回應`。
4. `arbitration_finished` ⇒ 輸出 `## 仲裁`，接
   `### <record["seat_id"]>（仲裁者 — 不參與輪替、不計入收斂）`，
   接徽章行（**只有** `已截斷`／秒數／模型三項，理由見上），接正文（規則同第 3 點）。
   - 出現多次就輸出多個 `## 仲裁` 區塊。
5. `round_finished`、`arbitration_started` ⇒ **不輸出任何東西**（它們沒有逐字稿內容）。
6. **不認識的 `kind` ⇒ 直接忽略，不得丟例外。** 將來新增事件種類時，舊的匯出不該壞掉。
7. 最後固定輸出 `## 用量` 那一節：
   - 一行「總呼叫 <calls> 次。」加上金額說明（照上面的字）。
   - 依 `by_seat` 的**鍵名排序**逐席列出 `- <seat_id>：calls=<n>`，
     其下縮排列出該席的用量欄位。
   - 🔴 **欄位名（含巢狀展平後的名字）只要小寫化之後含有 `cost`，就整條不列。**
     `usage` 是巢狀 dict（例如 opencode 是 `{"tokens": {...}, "cost": 0}`），
     展平成 `tokens.input` 這種點號路徑；**只列數值型的葉節點**。
   - 某席的 `usage` 是 `None` 或空 dict ⇒ 只印那一行 `calls=`，底下不列任何欄位。
8. 回傳的字串**以單一換行結尾**。

### B. `src/server.py`

① `_match()` 目前是：

```python
        if len(rest) == 2 and rest[0] and rest[1] in (
                "rounds", "arbitration", "events"):
            return (rest[1], rest[0])
```

把 `"export.md"` 加進那個 tuple（**加在最後**）。

② `do_GET` 的分派加一支：`kind == "export.md"` ⇒ `self._get_export(arg)`。

③ 新增：

```python
    def _get_export(self, session_id) -> None:
        session = self.server.store.get(session_id)
        if session is None:
            self._reply_error(404, "找不到該討論")
            return
        # 讀者路徑：絕對不拿執行權（與 SSE 同一條規矩），否則「有人在匯出」
        # 會變成「沒有人能開下一輪」。逐字稿一律從事件流重播，不讀
        # discussion.rounds——那會被邊跑邊 append（SPEC.md §7.1）。
        body = transcript.render_markdown(
            self._common_shape(session), session.events_since(0)
        ).encode("utf-8")
        filename = "council-" + session.id + ".md"
        self.send_response(200)
        self.send_header("Content-Type", "text/markdown; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Disposition",
                         f'attachment; filename="{filename}"')
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)
```

- 🔴 **檔名一律用 `session.id`，絕對不准用 URL 裡那段字串。** URL 那段是使用者
  （或惡意網頁）可以隨便填的任意文字，直接放進回應標頭就是 CRLF 標頭注入；
  `session.id` 是 `secrets.token_urlsafe(16)` 產生的，字元集受控。
  **`store.get()` 回 `None` 時已經 404 出去了，走到這裡的 id 一定是我們自己發的。**
- 🔴 **不得 `try_claim()`**。
- 🔴 **`server.py` 仍然不得出現 `open(`**（024 立的紅線，讀檔只准在 `src/ui.py`）。
- import 加 `from engine import transcript`（放在既有那幾行 engine import 旁邊，
  維持字母序）。
- ⚠️ **不要動 `_gate()`**：Host／Origin 檢查對這條路由自動生效，不需要任何特例。
- ⚠️ **不要碰 POST 的路由白名單**：`POST /api/discussions/<id>/export.md` 應該
  照既有邏輯回 404，這是對的，不要為它加分支。

### C. `src/static/index.html`

① `#action-row` 裡，**排在兩個按鈕之後、`#live-cost-warning` 之前**：

```html
      <a id="btn-export" download>匯出 Markdown</a>
```

② `<style>` 裡，加在 `button { ... }` 那一行之後：

```css
#btn-export {
  display: inline-block;
  padding: 0.4rem 1rem;
  border: 1px solid #999;
  border-radius: 3px;
  color: #222;
  text-decoration: none;
}
```

③ `renderDiscussion(data)` 裡，`currentId = data.id;` **那一行之後**加：

```js
  $("btn-export").href = "/api/discussions/" + data.id + "/export.md";
```

④ `showForm()` 裡，`currentId = null;` **那一行之後**加：

```js
  $("btn-export").removeAttribute("href");
```

- 🔴 **不准用 `fetch`／`Blob`／`URL.createObjectURL`／`document.createElement("a")`
  的下載手法。** 就是一個靜態的 `<a download>`，href 在開討論時填、回表單時拿掉。
- 🔴 **href 一定是相對路徑**。整份 `index.html` 不得出現 `http://` 或 `https://`
  （既有測試會檢查）。
- ⚠️ 不要改 `runAction()`、`setBusy()`、`renderUsage()`、`renderStatusBar()`。
  匯出不花錢，**不要把它綁進 `setBusy()` 的 disabled 邏輯**。

### D. `tests/test_transcript.py`（新檔）

只測純函式，**一條真實 CLI 都不准碰**。至少要涵蓋下面每一項（一項一條測試）：

1. `events` 為空 list ⇒ 仍然產出標題與 metadata 區塊，不丟例外。
2. 一輪三則成功發言 ⇒ 三個 `### <seat_id>` 標題都在，三段正文**逐字**出現。
3. `ok` 為 False 的發言 ⇒ 出現 `未回應：<error>`，且**不出現徽章行**。
4. 🔴 **仲裁 record 只有八個鍵**（自己手寫一個沒有 `stance`／`more`／`violation`
   的 dict）⇒ 正常渲染、不丟 `KeyError`。
5. 立場為 `None`（發言失敗時就是 `None`）⇒ 徽章行不出現 `立場:`。
6. `model_used` 為 `None` ⇒ 出現 `模型：未經確認`；有值 ⇒ 出現那個值。
7. 🔴 **金額不進 md**：餵一個含 `{"cost": 0.313167}` 與
   `{"total_cost_usd": 0.5}` 的 usage ⇒ 輸出裡**不得出現** `cost`、`0.313167`、
   `total_cost_usd`、`0.5` 這些字樣；但同一個 usage 裡的 token 欄位**必須出現**。
8. 🔴 **模型文字裡的 Markdown 不被改寫**：發言正文含 `# 標題`、`---`、
   三個反引號的區塊、`|表格|` ⇒ 輸出裡**逐字**保留。
9. 不認識的 `kind`（例如 `"unknown_kind"`）⇒ 被忽略，不丟例外，其他事件照常渲染。
10. 多個 `arbitration_finished` ⇒ 輸出多個 `## 仲裁` 區塊。
11. `by_seat` 某席的 `usage` 為 `None` ⇒ 只出現 `calls=`，不炸。

### E. `tests/test_server.py`（修改）

至少涵蓋：

12. `GET /api/discussions/<真實 id>/export.md` ⇒ 200，且
    `Content-Type` 是 `text/markdown; charset=utf-8`、
    `Cache-Control` 是 `no-store`、
    `X-Content-Type-Options` 是 `nosniff`、
    `Content-Disposition` **等於** `attachment; filename="council-<那個 id>.md"`。
13. body 逐位元組等於 `transcript.render_markdown(...)` 的 UTF-8 編碼結果。
14. 不存在的 id ⇒ 404。
15. `POST` 到同一個路徑 ⇒ 404。
16. `Host` 標頭改成 `evil.example.com` ⇒ 403。
17. 🔴 **匯出不拿執行權**：匯出回應拿到之後，`session.try_claim()` 仍應回 `True`
    （證明執行權沒被佔住）。

### F. `tests/test_ui.py`（修改）

18. `assertIn('id="btn-export"', self.source)`
19. `assertNotIn("createObjectURL", self.source)`

---

## 驗收條件（貼真實輸出，不要只描述）

1. `python3 -m unittest discover tests` **全過**，貼出最後三行。
   🔴 **既有 294 個測試一個都不得變紅**。新增測試**不得少於 18 條**，貼出實際總數。
   ⚠️ 工作包 011 曾回報「交付完成」而實跑是 `FAILED (errors=1)`。**自己實際跑完再回報。**
2. 貼出所有變更檔的**完整 `git diff`**，以及 `src/engine/transcript.py` 的完整內容。
3. 貼出結構性紅線（**連空輸出也要貼**）：
   - `grep -n 'import' src/engine/transcript.py` ——**應為空**。
   - `grep -n 'open(' src/server.py` ——**應為空**。
   - `grep -n 'try_claim' src/server.py` ——應只出現在 `_post_rounds` 與
     `_post_arbitration` 裡，**`_get_export` 內沒有**。
   - `grep -nE 'createObjectURL|Blob|fetch\(' src/static/index.html`
     ——`fetch(` 是既有的（`postJson` 用），**但 `createObjectURL` 與 `Blob` 必須是 0**。
   - `grep -nE 'https?://' src/static/index.html` ——**應為空**。
4. 🔴 **實機煙霧測試**（dry run，**不會呼叫任何 CLI**）：
   - 用 **8799** 埠起 `python3 src/serve.py --port 8799`。
     ⚠️ **絕對不要用 8765**，Frank 可能有一台 `--live` 的伺服器在那個埠上。
   - `curl` 建立一個討論（三席 opencode ＋ 仲裁者 claude 的規格字串即可，
     dry run 不會真的呼叫它們）、開一輪、叫一次仲裁。
   - `curl -i` 取 `export.md`，**把回應標頭與 md 全文原樣貼出來**。
   - 收工時**只 kill 你自己起的那個行程**（記下它的 pid），不要用 `pkill python3`
     這種會掃到別人的指令。
5. **突變驗證四項**，每項：改壞 → 貼失敗輸出（**含翻紅的測試名**）→ 還原 →
   最後貼還原後全過的結果。
   - (a) 讓仲裁區塊改用 `record["stance"]` ⇒ 第 4 條測試應翻紅（`KeyError`）。
   - (b) 拿掉金額過濾 ⇒ 第 7 條測試應翻紅。
   - (c) 把檔名改成用 URL 裡那段字串而不是 `session.id` ⇒ 第 12 條測試應翻紅。
   - (d) 在 `_get_export` 裡加一個 `session.try_claim()`（不 release）
     ⇒ 第 17 條測試應翻紅。
   - 🔴 **突變只准動實作側**（`transcript.py`／`server.py`），不准動測試檔。
   - 🔴 **每一項動手前先確認要取代的字串在檔案裡是唯一的**：印出 `text.find(old)`
     與 `text.rfind(old)`，兩個位置必須相同才可以取代。**位置不同就換一段更長的樣式**。
   - 🔴 **備份放 `dispatch/tmp/029-backup/`，不要放 `/tmp`。**
     還原後用 `cmp` 確認與備份**位元組相同**，並貼出結果。
6. 貼出 `git status --short`。
7. 🔴 **公開發布掃描**：貼出
   `grep -rnE "$(whoami)|/home/[a-z]" src/engine/transcript.py src/server.py src/static/index.html tests/test_transcript.py tests/test_server.py tests/test_ui.py`
   ——**應為空**。⚠️ 煙霧測試的輸出如果含家目錄路徑，回報時自己把它改成 `<省略>`。

---

## 不要做的事

- 🔴 **全程不得執行 `--live`，不得呼叫任何真實 CLI。** 單元測試一律用 `port=0`，
  煙霧測試用 8799。
- 🔴 **不要動 `src/engine/` 底下任何既有檔案**（`state.py`／`orchestrator.py`／
  `sessions.py`／`wiring.py`）。這一包不改引擎，只是把它已經發出來的事件重新排版。
- 🔴 **不要新增 `error` 事件的發送端**（它現在沒有人發，是保留的，維持原狀）。
- 🔴 **不要把脈絡原文放進 md**、不要新增回傳脈絡原文的端點。
- ⚠️ 不要新增設定項（例如「要不要含用量」的開關）、不要做匯出格式選擇（JSON／PDF）。
  **只有 Markdown 一種。**
- 不要引入第三方套件、框架、建置步驟。
- 不要碰版控（`git add` / `commit` / `push` 一律不執行）。
