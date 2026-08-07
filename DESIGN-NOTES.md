# council 設計註記——不要修正的刻意設計

以下每一條都是**故意寫成那樣**的，而且**理由在 repo 裡查不到**。看到它們覺得
「這寫錯了順手修一下」的時候，先讀這裡。

📌 **本檔與 `HANDOFF.md` 的分工**：`HANDOFF.md` 寫**會過期的東西**（現況、待辦、
剛驗證過什麼）；本檔寫**不會過期的東西**（程式碼為什麼長這樣）。
⇒ **開新 session 不必讀本檔**，要動到哪一塊程式碼時再查對應那一節。

⚠️ **本檔不是規格。** 契約的唯一來源是 `SPEC.md`，規則的唯一來源是 `AGENTS.md`。
本檔只解釋「為什麼」，**不重述它們的任何一條**——一旦重述，兩份就會各自過期。

⚠️ 每一條都是實作或審查時踩出來的，日期截至 2026-08-07（工作包 014～032）。
**改了對應的程式碼就要回來改這裡**，否則它會變成下一個誤導人的過期文件。

---

## 1. 隔離紅線（結構上不可能打到真 CLI）

- 🔴 **引擎模組全部不 import `subprocess`／`os`／`sys`／`adapters`。**
  唯一放寬：`orchestrator.py` 可以 `from engine.state import BoundaryError`
  （019，因為仲裁前置檢查必須在花錢之前）。
- 🔴 **`cli.py` 與 `serve.py` 是全 repo 僅有的兩個允許 import `adapters` 的檔案。**
- 🔴 **`ask_fn` 是必填參數、沒有預設值** ⇒ 忘了傳是 `TypeError` 當場失敗，
  不會安靜地打到真的 CLI。測試一律用純 Python 假函式當 `ask_fn`，連假子行程都不用。
- 🔴 **`sessions.py` 只 import `copy`／`secrets`／`threading`，不認識本專案任何東西。**
  存活層一旦認識狀態機，就會開始替它回答「能不能開下一輪」，而那個判斷 §5 已有唯一的家。
- 🔴 **`transcript.py` 整個檔案不得出現 `import`。** 它拿不到 discussion 物件 ⇒
  結構上不可能去讀 `discussion.rounds`（那是會被邊跑邊 append 的撕裂來源）。
  資料來源只有 `session.events_since(0)`，與 SSE 重播同一條路徑。
- 🔴 **`server.py` 不得出現 `open(`。** 靜態頁讀檔放在 `src/ui.py`——**全 repo 唯一開檔的
  伺服器端模組**，只開一個寫死、相對於模組自身的檔名，在模組載入時讀一次。
  ⇒ **改了 `index.html` 要重啟伺服器才看得到。**
- `max_chars`／`timeout_s`（§5 邊界 2／4）**只能在 `orchestrator.py` 出現一次**
  （`DEFAULT_MAX_CHARS`／`DEFAULT_TIMEOUT_S`），不得散落成各處寫死的預設值。

## 2. 狀態機與仲裁

- 🔴 **仲裁者不是第四個發言者**：不進 `rounds`、不套 `parse_marker`、不計入
  `format_violations`、不影響 `converged`。`record_speech()` 仍然只收顧問。
  仲裁者在狀態機裡**沒有任何方法**（刻意的）。
- 🔴 **仲裁 record 刻意只有八個鍵，沒有 `stance`／`more`／`violation`。**
  這不是省略——少了它們，將來若有人把仲裁記錄餵進收斂判定會**當場 `KeyError` 炸掉**，
  而不是安靜地汙染訊號。（突變實測確認會炸；2026-08-06 真實資料上也驗證了。）
- ⚠️ **仲裁前置檢查必須在 `ask_fn` 之前。** 順序反過來＝先花錢再發現不該花，
  而仲裁者拿的是最長的逐字稿。
- ⚠️ **`can_arbitrate()` 與 `record_arbitration()` 各寫了一份同樣的三條前提**
  （後者要給三種不同錯誤訊息）。今天兩邊等價，**改任一邊要同步改另一邊**——
  這是本專案唯一的結構性債。
- **`--arbitrate` 預設關閉**，與 `--live` 同一原則。`run.sh` 的仲裁席次是付費的 `claude`，
  **刻意沒把 `--arbitrate` 寫進去**。
- ⚠️ **狀態機刻意不管發言順序**（`record_speech` 不檢查），順序是編排層的責任。
- **顧問失敗（逾時／例外）記為「未回應」後繼續下一位**，逐字稿只寫
  `（未回應：<error>）`，**絕不把 error 內容當成發言餵給下一位**。
  `try` 只包住 `ask_fn` 呼叫與取值，狀態機自己的拒絕不會被吞掉。
- ⚠️ **prompt 區塊順序是「問題 → 舊輪 → 本輪 → 任務」，刻意不照 `SPEC.md` §6 的字面
  順序**——SPEC 那句是在列「包含什麼」，照字面組會變成時序錯亂。

## 3. 討論存活層（`sessions.py`，97 行）

| 東西 | 介面 | 要點 |
|---|---|---|
| 容器 | `SessionStore.create/get/list_ids/remove` | id 是 `secrets.token_urlsafe(16)`（128 bit）。`get()` 找不到回 `None` 不丟例外 |
| 執行權 | `session.try_claim()`／`release()`／`is_busy` | **非阻塞**，搶不到立刻回 `False` |
| 讀者路徑 | `session.snapshot`／`refresh()` | 回深拷貝。**快照不會自己更新**，這是刻意的 |
| 事件流 | `append_event(kind, data)`／`events_since(cursor)` | seq 從 1 遞增、**`>` 不是 `>=`**（給 SSE 的 `Last-Event-ID`） |

- 🔴 **`release()` 的順序本身就是規格**：檢查 → 刷新快照 → 清 `_claimed` → **最後才放鎖**。
  （原本寫成「先放鎖 → 再讀 `status()`」是真的 bug，見 `HANDOFF.md` §5.1。）
- ⚠️ **`threading.Lock` 沒有擁有者概念**：任何人都能放掉別人的執行權。本層刻意不做擁有者
  追蹤 ⇒ **請求處理必須自己 `try` / `finally` 配對。**

## 4. HTTP 伺服器與 SSE

| 方法 | 路徑 | 花錢 |
|---|---|---|
| `POST` | `/api/discussions` | 否 |
| `GET` | `/api/discussions/<id>` | 否 |
| `POST` | `/api/discussions/<id>/rounds` | 🔴 是 |
| `POST` | `/api/discussions/<id>/arbitration` | 🔴 是 |
| `GET` | `/api/discussions/<id>/events` | 否（SSE） |
| `GET` | `/api/discussions/<id>/export.md` | 否 |

（⚠️ 出題前仍請直接讀 `src/server.py`，本表會過期。）前四條回同一個形狀：
`{id, live, busy, question, context_chars, seats, status}`。事件種類：`round_started`／
`speech`／`round_finished`／`arbitration_started`／`arbitration_finished`／`error`
（最後一個目前沒人發，是保留的）。

- 🔴 **逐字稿不從 `GET` 回傳，只從事件流重播。** `discussion.rounds` 會被邊跑邊 append，
  GET 去讀它就是 §7.1 警告的撕裂。副作用很好：**頁面重整與 SSE 斷線重連是同一條路徑。**
- 🔴 **一次 `POST /rounds` ＝ 一輪**，`request_next_round()` 由該 handler 呼叫。
  邊界 1 沒被繞過——**那個 HTTP 請求本身就是「使用者按了再一輪」**。
  超過輪數上限要送 `{"confirm_over_cap": true}`。
- 🔴 **脈絡只收字串本文，伺服器不開檔**（§7.2）。狀態查詢**不回傳脈絡原文**，只回
  `context_chars`。要讓使用者送檔案，是**瀏覽器讀完再送內容**。
- ⚠️ **`live` 是啟動時決定的**，`server.live` 只供顯示。沒有任何請求能把 dry run 切成 live。
- ⚠️ `run_round()` 的 `on_record` 回呼**丟的例外會被吞掉**——那一輪的錢已經花了，讓事件
  通知的 bug 中斷整輪會使 `end_round()` 不被呼叫、討論卡在 `in_round` 相位。
- 🔴 **`run_arbitration()` 的 `on_start` 回呼在 `can_arbitrate()` 之後、`ask_fn` 之前觸發。**
  這是修在源頭，不要退回去在 JS 裡加旗標（理由見 `HANDOFF.md` 出題紀律第 11 條「修在源頭」）。
- 🔴 **`GET /` 是 `== "/"` 完全相等比對**，不是路徑→檔案對映。`/index.html`、
  `/static/index.html`、`/../src/server.py` 全部 404。
  ⚠️ **但 `//` 與 `///` 回 200**：`http.server.parse_request()` 內建 gh-87389 的
  open redirect 防護，進 handler 之前就把開頭多個 `/` 併成一個。
  `test_double_slash_normalized_by_stdlib` **刻意釘住這個 stdlib 行為**——哪天它改了要有
  人看一眼。**不要為了讓 `//` 回 404 去翻 `self.requestline`。**
- 🔴 **HTML 回應必須帶 `X-Frame-Options: DENY` ＋ `Content-Security-Policy:
  frame-ancestors 'none'`**（§7.2 第 5 道，只加在 `_get_index()`，不加在 JSON／SSE）。
  理由：iframe **繞過的是整組守門、不是其中任一道**——被框住的頁面自己發的請求，
  `Host` 正確、`Origin` 同源、`Content-Type` 自己設、同源不需要 CORS，四道全過。
  ⚠️ **`frame-ancestors` 寫在 `<meta>` 裡無效**，瀏覽器只認回應標頭（`report-uri`、
  `sandbox` 同理）。⚠️ 兩個 CSP 政策**不會合併**，各自獨立生效取交集。

## 5. 單頁 web UI（`src/static/index.html`，約 700 行，零依賴零建置）

- 🔴 **JS 的六條結構性紅線**（`tests/test_ui.py` 讀原始碼斷言）：不得出現 `innerHTML` 類、
  `http(s)://`、`localStorage` 類、`setInterval`／`setTimeout`；`confirm_over_cap` 恰好一處；
  CSP `<meta>` 值逐字元固定。
  ⚠️ **禁計時器**是因為 §5 邊界 1——任何計時器都是「頁面自己決定何時再花錢」的起點。
  ⚠️ **禁瀏覽器儲存**是因為逐字稿含使用者的專案脈絡，而 §7.1 講明討論只在記憶體。
- 🔴 **不得出現 `url(` 與 `<svg`**（`test_no_external_resources`）。CSP 是
  `default-src 'none'` ＋ `img-src 'none'` ⇒ 外部資源載不到、畫面只會留白，
  **而這件事在 Python 測試裡看不出來**。更陰險的是內嵌 SVG 常帶
  `xmlns="http://www.w3.org/2000/svg"`，那個 `http://` 會直接踩爆 `test_no_http_urls`。
  所有圖示用 unicode 字元（`◆ ◷ ⚑ ◎ ⚖ ↓`），分隔線用偽元素畫。
- 🔴 **`[hidden] { display: none !important; }` 必須留在 stylesheet 最後。**
  兩個主要畫面靠 `hidden` 屬性切換，任何 `display:grid`／`flex` 都會讓它失效、
  兩個畫面同時顯示。`test_hidden_attribute_still_hides` 釘住它。
- ⚠️ **JS 的互動行為沒有自動化測試，這是刻意的。** 那需要 headless 瀏覽器或 node 測試
  框架，而 §7 明訂「無建置步驟」、本 repo 至今純 stdlib Python。能機械驗的（路由、標頭、
  六條紅線）都有測試，**互動行為靠 Frank 實測**。
  🔴 **不要為了「看起來有測到」寫假的 DOM 模擬。**
- ⚠️ 頁面在建立討論之前**無法知道 `live`**（它是啟動時決定的，頁面是靜態位元組），
  模式徽章一開始是「尚未確認」。不構成風險：建立討論不花錢，兩個會花錢的按鈕只存在於
  討論檢視裡，那時 `live` 必定已知。**不要為此新增 API 端點或把 `live` 注入 HTML。**
- ⚠️ **`#mode-badge` 的「尚未確認」與「DRY RUN」外觀相同**（同一個 `badge-gray` class）。
  刻意接受：兩者靠文字分得出來，為了配色去動 `updateModeBadge()` 不划算。
- ⚠️ `.badge-row` 這個 class **沒有對應的 CSS 規則**。無害——徽章靠自己的 `.badge-small`
  排版。留著當掛點，不是漏掉的規則。

## 6. 逐字稿匯出（`GET /api/discussions/<id>/export.md`）

- 🔴 **仲裁區塊不准碰 `stance`／`more`／`violation`**（仲裁 record 只有八個鍵）。
  碰了就是 `KeyError` 當場炸——突變實測確認會炸。
- 🔴 **`_get_export` 不得拿執行權**（讀者路徑）。
- 🔴 **md 不含脈絡原文**（只寫字元數）、**不含金額**（與用量面板同一原則）。
- ⚠️ **模型文字逐字保留**（表格、程式碼區塊、`---` 全部原樣）。代價是模型自己的 `#` 標題
  會跟結構標題混在一起、`---` 會讓上一行被渲染成標題。檔頭已寫明「未經任何淨化或改寫」。
  要消掉得把正文改成引用區塊，但那會讓表格難讀——**Frank 尚未表示意見，不要自行改。**
- ⚠️ 前端**只有一個 `<a download>`**，沒有 `fetch`／`Blob`／`createObjectURL`。
  理由：沒有 DOM 測試環境，JS 裡的東西越少、被守住的比例越高。

## 7. 顧問工具權限（`SPEC.md` §4.2）

```yaml
permission:
  "*": deny
  websearch: allow
```

**為什麼不是「把 read/grep/glob 加進 deny 清單」**：那三個之所以開著，根因是**沒被列到
的工具落在 opencode 的 `*: allow` 之下**——逐項列舉治不了這個病，opencode 將來新增的
工具一樣會自動變成 allow。萬用字元版是 fail-closed 的。

- 🔴 **`"*"` 的雙引號不可省略**（YAML 裸 `*` 是別名語法）；**`websearch: allow` 必須排在
  後面**，opencode 是「後匹配者勝出」（查官方文件確認，不只是實測）。
- 🔴 **`webfetch` 維持 deny**：websearch 是「送出查詢字串」，webfetch 是「對任意 URL 發
  請求」。前者攻擊者無法指定目的地，後者可以。**不要合併看待。**
- ⚠️ **這個放寬只發生在 opencode 一家**（claude 是 `--tools ""`、codex sandbox、
  gemini plan mode）⇒ 同一場議會裡各席能不能查證現況不一樣，**答案不可直接比較。**
- ⚠️ **搜尋讓 token 用量放大約 9 倍**（6,542 → 57,511，同一免費模型，實測）。
  免費席次 `cost: 0`，付費席次要算進 §5 邊界 6。
- ⚠️ **殘留脆弱性**：adapter 只偵測「`--agent` 找不到」那一種失敗（`FALLBACK_MSG`），
  **偵測不到「新版 opencode 靜默忽略某個 permission 鍵」**。不是新引入的，但記著。

## 8. Frank 逐字指定的文案（不要自作主張改）

- **「開始討論（可延續數輪）」**——全形括號，他指定的字。
- **「一行一席」**（顧問欄位說明）——032 曾被我引用時打成「一行一句」而改壞，已修回並
  加進 `test_advisor_order_is_documented` 當回歸守衛。
- **相位標籤 `phaseLabel()` 刻意沒動**：我提過 `ready` →「準備中」讀起來像系統在忙也該改，
  **Frank 說只改按鈕即可。**

## 9. 沒有測試守得住的四件事（改到那裡自己記得）

本專案沒有 DOM 測試環境（§7 明訂無建置步驟），以下是刻意接受的缺口：

| 東西 | 把它改壞會怎樣 |
|---|---|
| `isCostKey()` 的過濾邏輯 | 改成 `return false` 金額會重新出現在畫面上，測試照樣全過 |
| `at_cap` 分支排在最前面的順序 | 移到後面不會翻紅（今天 `at_cap` 為真時 `rounds_completed` 不可能是 0），它靠程式碼註解 |
| 「匯出檔名要用 `session.id`」 | 對不上的 id 一律 404 ⇒ 任何實作下都不會翻紅 |
| 用量面板的欄位呈現 | 見下方 §10 |

## 10. 用量數字為什麼長那樣（不是 bug，是呈現問題）

兩家 CLI 的鍵名完全不同：opencode 是 `tokens.{total,input,output,reasoning}`／`cost`，
claude 是 `input_tokens`／`output_tokens`／`cache_creation_input_tokens`／`total_cost_usd`。
`merge_usage` 按鍵名相加 ⇒ **沒有任何欄位代表四席的真正總量**。

這不是 `merge_usage` 的 bug——鍵名不同就各自累加是規格內行為，而 §4 明訂
「**不要自行估算 token**」。028 的修法是**改呈現**：各席次分列提前到累加區之前，
累加區明寫「不是所有席次的總和」，且 `isCostKey()` 過濾掉所有含 `cost` 的鍵
⇒ **畫面上不再有任何金額。**

⚠️ 同源的一個陷阱：實測 claude 的 `input_tokens: 2`，而 18,919 全進了
`cache_creation_input_tokens` ⇒ 畫面顯示「input_tokens：2」看起來像**沒送東西進去**，
實際上進去了近一萬九千。**直接把 CLI 欄位攤平顯示，會產生看起來很確定但讀錯方向的數字。**
