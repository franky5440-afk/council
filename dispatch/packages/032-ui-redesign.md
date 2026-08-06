# 工作包 032 — web UI 視覺改版（深色 dashboard 風格）

## 這一包的性質

**這是「換皮」，不是「改功能」。** 唯一要動的檔案是 `src/static/index.html`
（外加 `tests/test_ui.py` 補幾條結構性測試）。

- **不准動** `src/server.py`、`src/ui.py`、`src/engine/*`、`src/cli.py`、`src/serve.py`。
- **不准新增或修改任何 API 端點、事件種類、請求／回應格式。**
- 頁面的**行為**必須與現況完全一致：同樣的按鈕做同樣的事、同樣的 fetch、
  同樣的 SSE 事件處理、同樣的錯誤處理路徑。

⚠️ 本頁的 JS **互動行為沒有任何自動化測試**（本專案刻意不建 DOM 測試環境，
`SPEC.md` §7：無建置步驟）。所以 JS 邏輯**原樣搬過去**，只准做本文
「§5 允許的 JS 變更」列出的那幾項，**清單以外的 JS 一個字都不要動**——
包含變數名、函式名、判斷順序、字串內容。

---

## 1. 先做這件事：備份

```bash
mkdir -p dispatch/tmp/032-backup
cp src/static/index.html dispatch/tmp/032-backup/index.html
cp tests/test_ui.py dispatch/tmp/032-backup/test_ui.py
```

**所有臨時檔、備份、實驗檔一律放 `dispatch/tmp/`，不要寫到 `/tmp/`、
不要寫到專案目錄以外的任何地方。**

## 2. 環境紅線

- **不准碰 8765 埠**：Frank 可能有伺服器在上面跑。不要 `kill`、不要 `pkill`、
  不要 `fuser`、不要對 8765 發任何請求。要起伺服器驗證請用 `--port 0` 或 8790 以上的埠。
- **不准跑 `--live`**（會花錢）。所有驗證用 dry run。
- **不准執行任何版控指令**（`git add`／`commit`／`checkout`／`stash`／`push`…）。
  版控由主對話負責。
- **不准呼叫任何 CLI**（`opencode`／`claude`／`codex`／`gemini`）。

---

## 3. 🔴 絕對不可破壞的紅線（測試會抓，且我會做突變測試）

### 3.1 這些字串必須在新檔案裡**逐字**存在

| 字串 | 為什麼 |
|---|---|
| `default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; connect-src 'self'; img-src 'none'; form-action 'none'; base-uri 'none'` | CSP meta，測試逐字元比對，**一個空格都不能改** |
| `開始討論（可延續數輪）` | Frank 逐字指定的文案（全形括號） |
| `再一輪（需確認）` | 同上 |
| `rounds_completed === 0` | 首輪按鈕文案的判斷式 |
| `不是所有席次的總和` | 累加區的警語 |
| `由上到下就是發言順序` | 席次順序＝發言順序，只有實作知道 |
| `isCostKey` | 金額過濾函式名 |
| `id="btn-export"` | 匯出連結 |
| `confirm_over_cap` | **恰好出現一次**，多一次少一次都算失敗 |
| `textContent` | 至少一次 |
| `round_started` `speech` `round_finished` `arbitration_started` `arbitration_finished` `error` | 六種事件全都要監聽 |

### 3.2 這些字串**絕對不可以出現**

`innerHTML`、`outerHTML`、`insertAdjacentHTML`、`document.write`、`eval(`、
`new Function`、`Function(`、`http://`、`https://`、`localStorage`、`sessionStorage`、
`indexedDB`、`document.cookie`、`setInterval`、`setTimeout`、`createObjectURL`、
`usage-cost`、`<script src=`

**本包新增兩條**：

- 🔴 **不可出現 `url(`**。CSP 是 `img-src 'none'`、`default-src 'none'`
  ⇒ 任何 `background-image: url(...)`、`@font-face` 的字型檔、任何 `data:` URI
  都會被瀏覽器擋掉，畫面上只會留下空白，而**這件事在 Python 測試裡看不出來**。
  ⇒ 一律用純 CSS（漸層、邊框、`border-radius`、偽元素）畫，不要引用任何外部資源。
- 🔴 **不可出現 `<svg`**。理由同上再加一條：內嵌 SVG 常被寫成
  `<svg xmlns="http://www.w3.org/2000/svg">`，那個 `http://` 會**直接踩爆
  `test_no_http_urls`**。所有圖示改用 **unicode 字元**（見 §4.6）。

### 3.3 結構紅線

- `<script` 恰好一個、`<style` 恰好一個，兩者都內嵌（零依賴、零建置）。
- 🔴 **`[hidden] { display: none !important; }` 必須寫進 stylesheet，而且要寫在
  所有 layout 規則之後。** 兩個主要畫面（`#form-view`／`#discussion-view`）靠
  `hidden` 屬性切換；一旦你給它們 `display: grid`／`display: flex`，
  **`hidden` 就會失效、兩個畫面會同時顯示**。這是本包最容易踩的坑。
- 所有既有的 **element id 全部保留**（見 §4.1 清單），JS 靠它們抓元素。

---

## 4. 設計規格（照做，不要自己發揮）

參考風格：深色 fintech dashboard——近黑底、大圓角面板、少量高飽和粉彩色塊、
黃色作為唯一的主動作色、大量留白、次要資訊用低對比灰。

### 4.1 版面

三欄 grid，桌機寬度：

```
┌──────────┬─────────────────────────────┬────────────┐
│ sidebar  │  topbar                     │  用量面板   │
│ 260px    │  ─────────────────────────  │  320px     │
│          │  main（表單 or 討論）        │  (sticky)  │
│ (sticky) │                             │            │
└──────────┴─────────────────────────────┴────────────┘
```

```css
.app {
  display: grid;
  grid-template-columns: 260px minmax(0, 1fr) 320px;
  gap: 16px;
  padding: 16px;
  min-height: 100vh;
  align-items: start;
}
@media (max-width: 1180px) {
  .app { grid-template-columns: 1fr; }
  /* sidebar 與用量面板變成單欄堆疊，取消 sticky */
}
```

⚠️ `minmax(0, 1fr)` 的 `0` 不可省略——省了之後長逐字稿會把中欄撐爆版面。

**必須保留的 element id（全部）**：
`status-bar`（可改成 topbar 的容器）、`mode-badge`、`st-id`、`st-phase`、`st-rounds`、
`converged-hint`、`st-violations`、`st-busy`、`st-sse`、`form-view`、`form-error`、
`create-form`、`question`、`advisors`、`arbiter`、`context-file`、`context`、
`context-chars`、`discussion-view`、`btn-new`、`question-text`、`context-chars-text`、
`seat-list`、`transcript`、`action-row`、`btn-round`、`btn-arbitration`、`btn-export`、
`live-cost-warning`、`usage-panel`、`usage-content`。

**本包新增的 id**：`st-cap`、`st-calls`（見 §5）。

### 4.2 色票（寫成 `:root` 的 CSS 變數，全部用變數引用，不要散落硬編色碼）

```css
:root {
  --bg:         #0F0F10;   /* 頁面底 */
  --panel:      #17181A;   /* 側欄、面板 */
  --panel-2:    #1E1F22;   /* 卡片、輸入框 */
  --panel-3:    #26282C;   /* hover、次要按鈕 */
  --line:       #2A2C30;   /* 邊框 */
  --text:       #F2F2F3;
  --muted:      #8B8D93;
  --accent:     #E6D07C;   /* 黃：唯一的主動作色 */
  --accent-ink: #141414;   /* 黃底上的字 */
  --mint:       #B9E8CE;
  --sage:       #CFE9D4;
  --danger:     #FF6B6B;
  --radius-lg:  20px;
  --radius:     14px;
  --radius-sm:  10px;
}
```

- `body { background: var(--bg); color: var(--text); font-family: system-ui, -apple-system, "Noto Sans TC", "Noto Sans CJK TC", sans-serif; margin: 0; }`
- **不要 `@font-face`、不要載任何字型**（CSP 擋掉，而且會 fallback 成醜的）。
- **深色單一主題，不做切換開關**（要記住偏好就得用 `localStorage`，那是紅線）。

### 4.3 側欄 `#sidebar`

```
背景 var(--panel)，圓角 var(--radius-lg)，padding 20px 16px，
position: sticky; top: 16px;（≤1180px 時取消）

內容由上到下：
  1. 品牌列：「◆ council」（1.25rem、600），下一行小字
     「多個 AI CLI 輪流發言的議會」（0.8rem、var(--muted)）
  2. 分隔線（1px solid var(--line)，margin 16px 0）
  3. 動作區：#btn-new「＋ 開新討論」——次要按鈕樣式，寬度 100%
  4. 標題「席次」（0.75rem、var(--muted)、letter-spacing .08em、大寫感）
     底下是 #seat-list
  5. flex spacer（margin-top: auto）
  6. 底部：#mode-badge
```

側欄用 `display: flex; flex-direction: column;` 才能讓第 5 項的 `margin-top: auto` 生效。

**`#seat-list` 的每一列**（由 JS 產生，見 §5.3）改成：
`padding: 10px 12px; background: var(--panel-2); border-radius: var(--radius-sm);
margin-bottom: 8px; font-size: .82rem; line-height: 1.5;`

### 4.4 頂欄（原 `#status-bar`）

```
背景 var(--panel)，圓角 var(--radius-lg)，padding 16px 20px，
display: flex; flex-wrap: wrap; gap: 10px; align-items: center;

左邊：頁面標題（「建立討論」或「討論」——沿用兩個 view 裡的 <h1>，
      但把 <h1> 移進頂欄不是必要的；維持在各自 view 內也可以，
      只要 <h1> 樣式改成 1.35rem/600、margin 0 0 4px）
右邊：狀態 chip 群 —— #st-phase / #st-busy / #st-sse / #st-id
```

**chip 樣式**（`.chip`）：
`display:inline-flex; align-items:center; gap:6px; padding:6px 12px;
border-radius:999px; background:var(--panel-2); color:var(--muted);
font-size:.78rem; border:1px solid var(--line);`

- `#st-busy` 有內容時加 `.chip-busy`（黃字 `var(--accent)`）。
- `#st-sse` 是**錯誤與連線訊息的唯一出口**，有內容時要顯眼：
  `.chip-alert { color: var(--danger); border-color: var(--danger); }`
  ⚠️ 目前它被當成小灰字，實際上承載「無法連上伺服器」「另一個分頁正在跑」
  這類要人看到的訊息。
- **空字串時不要留下空的 chip 外框**：用 `.chip:empty { display: none; }` 處理。

**`#mode-badge`**（在側欄底部）三種狀態：
- 尚未確認：`background: var(--panel-2); color: var(--muted);`
- DRY RUN：`background: var(--panel-2); color: var(--mint); border:1px solid var(--mint);`
- LIVE：`background: var(--danger); color: #fff; font-weight: 600;`
  （沿用既有的 `badge-live`／`badge-gray` class 名，只改樣式，**不要改 JS 裡的 class 字串**）

### 4.5 統計卡列（討論檢視最上方，三張粉彩卡）

這是參考風格裡最明顯的元素：三張並排的粉彩卡，每張＝一個圓形圖示 ＋ 標籤 ＋ 大數字。

```html
<div id="stat-row">
  <div class="stat stat-accent">
    <span class="stat-icon">◷</span>
    <span class="stat-label">輪次</span>
    <span class="stat-value" id="st-rounds"></span>
    <span class="stat-note" id="st-cap"></span>
  </div>
  <div class="stat stat-mint">
    <span class="stat-icon">⚑</span>
    <span class="stat-label">格式違規</span>
    <span class="stat-value" id="st-violations"></span>
  </div>
  <div class="stat stat-sage">
    <span class="stat-icon">◎</span>
    <span class="stat-label">總呼叫</span>
    <span class="stat-value" id="st-calls"></span>
  </div>
</div>
```

```
#stat-row { display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; }
@media (max-width: 700px) { #stat-row { grid-template-columns: 1fr; } }

.stat  { border-radius: var(--radius-lg); padding: 16px; color: var(--accent-ink);
         display: flex; flex-direction: column; gap: 6px; }
.stat-accent { background: var(--accent); }
.stat-mint   { background: var(--mint); }
.stat-sage   { background: var(--sage); }
.stat-icon   { width: 32px; height: 32px; border-radius: 50%;
               background: rgba(0,0,0,.82); color: #fff;
               display: flex; align-items: center; justify-content: center;
               font-size: .95rem; }
.stat-label  { font-size: .78rem; opacity: .72; }
.stat-value  { font-size: 1.6rem; font-weight: 600; line-height: 1.1; }
.stat-note   { font-size: .74rem; opacity: .72; }
```

⚠️ 粉彩底上的字**一律用 `var(--accent-ink)`**（近黑），不要用 `var(--text)`，
否則對比度不足看不見。

### 4.6 圖示

**只准用 unicode 字元**（`<svg>` 與 `url()` 都是紅線，見 §3.2）。建議：
`◆`（品牌）、`＋`（新討論）、`◷`（輪次）、`⚑`（違規）、`◎`（呼叫數）、
`▸`（開輪）、`⚖`（仲裁）、`↓`（匯出）。

⚠️ **不要用 emoji 當版面圖示**（各平台字型差異大、還會被算成彩色圖片般的視覺重量）。
既有文案裡的 `⚠️` 是內文的一部分，保留原樣。

### 4.7 表單檢視 `#form-view`

一張卡：`background: var(--panel); border-radius: var(--radius-lg); padding: 24px;`
（≤1180px 時 padding 縮到 16px）。

每個欄位包成 `.field { margin-bottom: 20px; }`：
- `label` → `display:block; font-size:.85rem; font-weight:600; margin-bottom:8px;`
- 輸入元件 →
  `width:100%; box-sizing:border-box; background:var(--panel-2); color:var(--text);
   border:1px solid var(--line); border-radius:var(--radius-sm);
   padding:10px 12px; font-family:inherit; font-size:.9rem; line-height:1.55;`
- `:focus` → `outline:none; border-color:var(--accent);`
- `.hint` → `display:block; margin-top:6px; font-size:.78rem; color:var(--muted); line-height:1.6;`
- `#form-error` → 有內容時是紅色警示條：
  `color:var(--danger); background:rgba(255,107,107,.08);
   border:1px solid var(--danger); border-radius:var(--radius-sm);
   padding:10px 12px; margin-bottom:16px;`
  同樣用 `:empty { display:none }` 讓它平常不佔位。

⚠️ 欄位的**文字內容一字不改**（尤其「顧問（一行一句…由上到下就是發言順序…」那段，
它被測試守著），只改排版。`<code>` 元素給
`background:var(--panel-3); padding:1px 5px; border-radius:4px; font-size:.85em;`。

### 4.8 討論檢視 `#discussion-view`

由上到下：
1. `#stat-row`（§4.5）
2. **問題卡**：包住 `#question-text` 與 `#context-chars-text`。
   `background:var(--panel); border-radius:var(--radius-lg); padding:20px;`
   `#question-text` 用 1.05rem/500、`#context-chars-text` 用 .78rem/var(--muted)。
3. **`#converged-hint`**：獨立一條橫幅，有內容才顯示（`:empty{display:none}`）：
   `background:rgba(185,232,206,.12); border:1px solid var(--mint);
    color:var(--mint); border-radius:var(--radius); padding:12px 16px;`
4. **`#transcript`**：卡片流。
5. **`#action-row`**：**sticky 底部操作列**
   `position: sticky; bottom: 16px; background: var(--panel);
    border: 1px solid var(--line); border-radius: var(--radius-lg);
    padding: 14px 16px; display: flex; flex-wrap: wrap; gap: 10px;
    align-items: center;`
   ⚠️ 逐字稿會很長，操作按鈕要一直搆得到——這是本次改版實際要解決的可用性問題之一。

**逐字稿卡片 `.card`**：
```
background: var(--panel); border: 1px solid var(--line);
border-radius: var(--radius); padding: 16px 18px; margin: 12px 0;
```
- `.card-head` → `font-weight:600; font-size:.92rem; margin-bottom:8px;`
- `.speech-text` → `white-space:pre-wrap; line-height:1.75; font-size:.92rem;
  overflow-wrap:anywhere;`（⚠️ `overflow-wrap` 不可省，模型會吐超長 URL／路徑，
  沒有它會把整欄撐爆）
- `.card.arbitration` → 左邊界標色：`border-left: 3px solid var(--accent);`
- `.card.arbitration.pending` → `color:var(--muted); font-style:italic;`
- `.badge-small`（發言徽章）→
  `display:inline-flex; padding:3px 9px; margin:0 6px 8px 0; font-size:.72rem;
   background:var(--panel-3); color:var(--muted); border-radius:999px;`
- `.round-heading` → 不要用底線，改成：
  `font-size:.78rem; color:var(--muted); letter-spacing:.08em; font-weight:600;
   margin:28px 0 4px; display:flex; align-items:center; gap:12px;`
  後面接一條 `::after` 畫的細線（`content:""; flex:1; height:1px; background:var(--line);`）

### 4.9 按鈕

```
.btn        { font: inherit; font-size:.88rem; font-weight:600;
              padding:11px 20px; border-radius:var(--radius-sm);
              border:1px solid transparent; cursor:pointer; }
.btn-primary{ background:var(--accent); color:var(--accent-ink); }
.btn-ghost  { background:var(--panel-2); color:var(--text); border-color:var(--line); }
.btn:disabled { opacity:.45; cursor:not-allowed; }
```
- `#btn-round` → `.btn .btn-primary`
- `#btn-arbitration`、`#btn-new` → `.btn .btn-ghost`
- `#btn-export` 是 `<a download>` → `.btn .btn-ghost` ＋ `text-decoration:none;
  display:inline-flex; align-items:center;`（它不是 `<button>`，記得 `line-height` 對齊）
- `#live-cost-warning` → `color:var(--danger); font-weight:600; font-size:.82rem;`

### 4.10 用量面板 `#usage-panel`

右欄，`background:var(--panel); border-radius:var(--radius-lg); padding:20px;
position:sticky; top:16px; max-height:calc(100vh - 32px); overflow-y:auto;
font-size:.8rem;`（≤1180px 取消 sticky 與 max-height）

- 標題「用量（token 消耗）」→ `.85rem/600`
- `.hint` 的說明字 → `var(--muted)`、`line-height:1.6`
- `.seat-block` → `background:var(--panel-2); border-radius:var(--radius-sm);
  padding:12px; margin:10px 0;`
- 數值列（`key：value`）→ 用 `display:flex; justify-content:space-between; gap:12px;`
  讓數字靠右對齊。⚠️ 這要在 `renderUsageDict` 產生的 row 上加 class，
  屬於 §5 允許的變更。

⚠️ **金額一律不顯示**（`isCostKey` 過濾）。這不是樣式問題，不要因為改版就把它拿掉。

---

## 5. 允許的 JS 變更（**白名單，清單以外一律不動**）

### 5.1 `renderStatusBar` — 拆出輪次與上限

現況把「輪次 N / M（已達上限）」全塞進 `#st-rounds`。統計卡要「純數字」，所以：

```js
$("st-rounds").textContent = status.rounds_completed + " / " + status.max_rounds;
$("st-cap").textContent = status.at_cap === true ? "已達上限" : "";
```

`#st-violations` 改成**永遠顯示數字**（統計卡不能是空的）：

```js
$("st-violations").textContent = status.format_violations;
```

🔴 **按鈕文案那三個分支（`at_cap` / `rounds_completed === 0` / else）
連順序都不要動**，三個字串逐字保留。
（`at_cap` 排最前面是刻意的，而那個順序沒有測試守得住。）

`#st-phase` 加上前綴照舊（`"相位：" + phaseLabel(...)`）。

### 5.2 `renderUsage` — 補 `#st-calls`

在函式開頭附近（`if (!status || !status.usage)` 那個 early return **之前**）加：

```js
$("st-calls").textContent = (status && status.usage) ? status.usage.calls : 0;
```

⚠️ 順序很重要：現況 `renderUsage(null)`（`showForm()` 會這樣呼叫）必須把它歸零，
所以這一行**必須在 early return 之前**。

原本印「總呼叫 N 次」的那個 `calls` div **從面板裡移除**（已經在統計卡上了）。

### 5.3 `renderDiscussion` 的席次列 — 加 class

那個 `row.textContent = ...` 的迴圈，**文字內容一字不改**，只加一行：

```js
row.className = "seat-row";
```

### 5.4 `renderUsageDict` 的數值列 — 加 class 與拆成兩個 span

為了讓數字靠右對齊，把

```js
row.textContent = key + "：" + flat[key];
```

改成

```js
row.className = "usage-row";
var k = document.createElement("span");
k.textContent = key;
var v = document.createElement("span");
v.textContent = flat[key];
row.appendChild(k);
row.appendChild(v);
```

**必須用 `createElement` ＋ `textContent`**，不准用 `innerHTML`（紅線）。

### 5.5 `addSpeechCard` — 徽章包一層

徽章目前直接 append 到 card 上，與內文混在一起。改成先建一個
`<div class="badge-row">`，把所有 `badge(...)` append 進去，
**若該 row 有子元素才** append 到 card（沒有徽章時不要留空白列）。
判斷式用 `if (badgeRow.firstChild) { card.appendChild(badgeRow); }`。

**徽章的文字內容與判斷條件一字不改。**

### 5.6 允許的其他變更

- 為套用新樣式而設定 `className`／`classList.add`（不改任何既有的 class 字串語意，
  例如 `badge badge-live`／`badge badge-gray`／`card arbitration pending` 都要留著）。
- 因 DOM 結構調整而必須改的 `appendChild` 目標容器。

### 5.7 🔴 這些 JS **完全不准動**

`postJson`、`runAction`、`refreshDiscussion`、`connectSse`、`closeSse`、
`openDiscussion`、`onLoad`、`showForm`、`showFormError`、`setBusy`、
`updateModeBadge`、`phaseLabel`、`flattenUsage`、`isCostKey`、
`clearArbitrationPlaceholder`、`addArbitrationCard`、`addArbitrationPlaceholder`、
`addRoundHeading`、以及所有 `addEventListener` 的處理函式內容
（表單送出、`btn-round`、`btn-arbitration`、`btn-new`、`context-file`、
`context`、`hashchange`）。

這些是唯一沒有自動化測試守著的邏輯，**動它們就等於在沒有安全網的地方走鋼索**。

---

## 6. 要新增的測試（`tests/test_ui.py`，加在 `IndexHtmlStructureTest` 裡）

只做**結構性字串斷言**（本專案沒有 DOM 測試環境，不要寫假的 DOM 模擬）：

1. `test_hidden_attribute_still_hides`
   斷言 `[hidden]` 與 `display: none !important` 同時出現。
   （加了 `display:grid`／`display:flex` 之後 `hidden` 會失效，這條守住它。）
2. `test_no_external_resources`
   斷言 `url(` 與 `<svg` 都不在原始碼裡。理由寫進 docstring：
   CSP 是 `img-src 'none'`／`default-src 'none'`，外部資源一律載不到，
   而 SVG 的 `xmlns` 會帶進 `http://` 踩爆既有的 `test_no_http_urls`。
3. `test_stat_tiles_present`
   斷言 `id="st-rounds"`、`id="st-violations"`、`id="st-calls"`、`id="st-cap"`
   四個 id 都在，且「輪次」「格式違規」「總呼叫」三個標籤字串都在。
4. `test_css_variables_defined`
   斷言 `:root` 存在，且 `--accent`、`--bg`、`--panel`、`--text`、`--muted` 都有定義。
5. `test_no_theme_toggle_storage`
   ——**不要寫這條**，既有的 `test_no_browser_storage` 已經涵蓋。（列在這裡是提醒你
   不要重複造測試。）

⚠️ **既有的測試一條都不准改、不准刪。** 若你認為某條既有測試與本包衝突，
**停下來寫 `dispatch/BLOCKED.md` 說明**，不要自行修改它。

---

## 7. 驗收（你必須實際跑過，並在回報裡貼出真實輸出）

```bash
# 1. 全套測試
python3 -m unittest discover tests

# 2. HTML／JS 語法
node --check <(sed -n '/<script>/,/<\/script>/p' src/static/index.html | sed '1d;$d')
#    ↑ 若這行在你的環境跑不起來，改成把 script 內容抽到 dispatch/tmp/032-check.js 再 node --check

# 3. 實機 dry run（⚠️ 用 8790，不是 8765）
python3 src/serve.py --port 8790
#    另一個終端：
curl -s -o /dev/null -w '%{http_code} %{size_download}\n' http://127.0.0.1:8790/
curl -s -D- -o /dev/null http://127.0.0.1:8790/ | grep -iE 'x-frame-options|content-security-policy|content-type|cache-control'
```

**驗收條件**：
- 全套測試全過，且**測試總數比現況（319）增加**（你新增了 4 條 ⇒ 應為 323）。
- `GET /` 回 200，且回傳位元組數與 `src/static/index.html` 的檔案大小相同。
- 四個回應標頭與現況一致（`X-Frame-Options: DENY`、
  `Content-Security-Policy: frame-ancestors 'none'`、
  `Content-Type: text/html; charset=utf-8`、`Cache-Control: no-store`）。
- **自己用 grep 逐條掃過 §3.1 與 §3.2 的字串清單**，把結果貼進回報。

⚠️ **`confirm_over_cap` 要恰好一次**：`grep -c confirm_over_cap src/static/index.html`
應為 `1`。

---

## 8. 回報格式

分成三段，**不要混寫**：

1. **實際執行輸出**：上面每個指令的真實 stdout（測試數字、curl 結果、grep 結果）。
   照貼，不要摘要成「都通過」。
2. **我做了什麼**：改了哪些區塊、§5 白名單裡動了哪幾項、為什麼。
3. **我沒驗證的部分**：明確列出。⚠️ 視覺效果（顏色、間距、對比度）你在
   headless 下**看不到**，一律列進這一段，不要宣稱「畫面很好看」。

如果本工作包有任何一處你認為有兩種讀法、或與既有程式碼／測試衝突，
**寫 `dispatch/BLOCKED.md` 停手**，不要挑一種猜著做。
