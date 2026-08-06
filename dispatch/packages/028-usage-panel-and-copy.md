# 工作包 028：用量面板的呈現、按鈕文案、換模型說明

Frank 親手實測 web UI 後回報了三件事，全部是**呈現層**的問題，**沒有任何一件要改引擎**：

1. 用量面板把金額頂在最上面還加粗，看起來像 council 去打了 API 在跟你收費。
   實際上 council 不呼叫任何模型 API，用掉的是使用者自己 CLI 的訂閱額度
   （`README.md` 已經寫明這件事，但畫面上看不到）。⇒ **畫面不再顯示任何金額，只顯示 token 數。**
2. 按鈕文案要再調（027 改過一次，這次是加註「可延續數輪」）。
3. 他以為「不能選模型」——**其實建立討論的表單早就能選**，只是畫面沒說
   「一行一席、由上到下就是發言順序」，README 也沒有教學。⇒ **只補說明文字，不要寫新功能。**

順便修掉主對話先前實測抓到、但還沒修的兩個呈現問題（同一塊面板，一起改省一次重啟）：

- `usage.total` 是 `merge_usage()` **按鍵名相加**的結果，而 opencode 與 claude 的鍵名
  完全不同（`tokens.total` vs `output_tokens`）⇒ 那一區**沒有任何欄位代表所有席次的
  真正總量**，但它並排列在畫面上，看起來就像總計。實測數字：`tokens.total: 18437`
  只含三席 opencode，`output_tokens: 4830` 只含 claude。
- claude 實測回報 `input_tokens: 2`，而 18,919 個 token 全進了
  `cache_creation_input_tokens` ⇒ 畫面上「input_tokens：2」看起來像沒送東西進去。

⚠️ **這一包只動三個檔，而且只動文字與呈現。不要順手改別的東西。**

---

## 檔案

| 檔案 | 動作 |
|---|---|
| `src/static/index.html` | **修改**：`<style>` 一行、`renderUsageDict()`、`renderUsage()`、`renderStatusBar()` 的按鈕文案、建立討論表單的顧問 label |
| `tests/test_ui.py` | **修改**：改一條既有斷言、加三條新斷言 |
| `README.md` | **修改**：中英文各加一小節「換模型／調整發言順序」 |

🔴 **除了上表，一個字都不要動。** 特別是 `src/server.py`、`src/ui.py`、
`src/engine/` 底下所有檔案、`src/cli.py`、`src/serve.py`、`tests/test_server.py`、
`SPEC.md`、`AGENTS.md`、`run.sh`。

🔴 **不准動 `flattenUsage()`**（它是通用的攤平函式，這一包不改它的行為）。

---

## 介面契約（照字面實作）

### A. `src/static/index.html` ①：拿掉金額的樣式

`<style>` 裡目前有這一行：

```css
#usage-panel .usage-cost { font-weight: bold; }
```

🔴 **整行刪除。** 刪掉之後 `usage-cost` 這個 class 名**不得在整個檔案裡任何地方出現**
（測試會檢查）。

### B. `src/static/index.html` ②：`renderUsageDict()` 過濾掉金額欄位

目前的 `renderUsageDict()` 做了兩件現在不要的事：把含 `cost` 的鍵**排到最前面**、
並給它 `usage-cost` 這個 class。改成**整個過濾掉**。

在 `renderUsageDict` **之前**新增一個函式，並改寫 `renderUsageDict`：

```js
// 金額不進畫面：council 不呼叫任何模型 API，這些數字是各家 CLI 依 API 定價
// 換算的參考值，顯示出來會讓人以為 council 在跟他收費（Frank 實測回報）。
function isCostKey(key) {
  return key.toLowerCase().indexOf("cost") !== -1;
}

function renderUsageDict(label, usage) {
  var container = document.createElement("div");
  if (label) {
    var head = document.createElement("div");
    head.textContent = label;
    container.appendChild(head);
  }
  var flat = flattenUsage(usage, "");
  var keys = Object.keys(flat).filter(function (key) {
    return !isCostKey(key);
  });
  keys.sort();
  keys.forEach(function (key) {
    var row = document.createElement("div");
    row.textContent = key + "：" + flat[key];
    container.appendChild(row);
  });
  return container;
}
```

- 🔴 原本那個「cost 置頂」的 `keys.sort(function (a, b) {...})` 比較器**整段刪掉**，
  改成沒有參數的 `keys.sort()`（預設字典序）。
- 🔴 `row.className = "usage-cost";` 那一句連同它的 `if` **整個刪掉**。
- ⚠️ **不要改成「顯示但變小」或「摺疊」**，Frank 要的是不顯示。

### C. `src/static/index.html` ③：`renderUsage()` 的順序與說明文字

整個函式換成下面這一份。**區塊順序就是下面的順序，不要重排**：

```js
function renderUsage(status) {
  var content = $("usage-content");
  clearChildren(content);
  var heading = document.createElement("div");
  heading.textContent = "用量（token 消耗）";
  content.appendChild(heading);
  var note = document.createElement("div");
  note.className = "hint";
  note.textContent = "council 不呼叫任何模型 API：這些數字由你自己的 CLI 回報，"
    + "用掉的是那個 CLI 的訂閱額度。";
  content.appendChild(note);
  if (!status || !status.usage) { return; }
  var usage = status.usage;
  var calls = document.createElement("div");
  calls.textContent = "總呼叫 " + usage.calls + " 次";
  content.appendChild(calls);
  // 各席次分列排在累加區之前：累加區是同名欄位各自相加的混合體，
  // 先看到它會把它讀成總計。
  Object.keys(usage.by_seat).sort().forEach(function (seatId) {
    var per = usage.by_seat[seatId];
    var block = document.createElement("div");
    block.className = "seat-block";
    var line = document.createElement("div");
    line.textContent = seatId + "：calls=" + per.calls;
    block.appendChild(line);
    if (per.usage && Object.keys(per.usage).length > 0) {
      block.appendChild(renderUsageDict("", per.usage));
    }
    content.appendChild(block);
  });
  var total = usage.total;
  if (total && Object.keys(total).length > 0) {
    content.appendChild(renderUsageDict("各席次同名欄位累加", total));
    var mixed = document.createElement("div");
    mixed.className = "hint";
    mixed.textContent = "⚠️ 各家 CLI 的欄位名稱不同（opencode 是 tokens.*，"
      + "claude 是 input_tokens／output_tokens），上面這一區只是把名稱相同的欄位"
      + "各自相加，不是所有席次的總和。要看真實用量請看上面各席次分列。";
    content.appendChild(mixed);
  } else {
    var none = document.createElement("div");
    none.textContent = "（本次未取得用量統計）";
    content.appendChild(none);
  }
  var cacheNote = document.createElement("div");
  cacheNote.className = "hint";
  cacheNote.textContent = "claude 的輸入多半計在 cache_creation_input_tokens，"
    + "input_tokens 顯示得很小是正常的，不代表逐字稿沒送進去。";
  content.appendChild(cacheNote);
}
```

- 🔴 **`by_seat` 的區塊內容與原本完全相同**，只是位置從「總計之後」搬到「總計之前」。
  不要順手改它的格式。
- 🔴 **「本次未取得用量統計」那一支要保留**（dry run 時 `total` 是空的）。

### D. `src/static/index.html` ④：按鈕文案

`renderStatusBar()` 目前是：

```js
  if (status.at_cap === true) {
    $("btn-round").textContent = "再一輪（需確認）";
  } else if (status.rounds_completed === 0) {
    $("btn-round").textContent = "開始討論";
  } else {
    $("btn-round").textContent = "再一輪";
  }
```

🔴 **只改中間那一支的字串**，改成 `"開始討論（可延續數輪）"`。

```js
    $("btn-round").textContent = "開始討論（可延續數輪）";
```

- 🔴 **文案就是「開始討論（可延續數輪）」，括號是全形**，不要自己換字、換標點。
- 🔴 **`at_cap` 的分支必須留在最前面**（花錢前的閘門提示不能被別的文案蓋掉）。
- ⚠️ **另外兩支的文案（「再一輪（需確認）」「再一輪」）不動。**
- ⚠️ 不要動 `phaseLabel()`、`setBusy()`、`runAction()`。

### E. `src/static/index.html` ⑤：顧問欄位的說明

目前建立討論表單裡是：

```html
      <label>顧問（一行一席，顧問 1～3 位，含仲裁者共 2～4 席；格式 &lt;cli&gt;[:&lt;模型&gt;]）
        <textarea id="advisors" rows="4">opencode:opencode/deepseek-v4-flash-free
opencode:opencode/nemotron-3-ultra-free
opencode:opencode/ling-3.0-flash-free</textarea>
      </label>
```

改成（**`<textarea>` 的三行預設內容原封不動**）：

```html
      <label>顧問（一行一席，由上到下就是發言順序；顧問 1～3 位，含仲裁者共 2～4 席；格式 &lt;cli&gt;[:&lt;模型&gt;]）
        <textarea id="advisors" rows="4">opencode:opencode/deepseek-v4-flash-free
opencode:opencode/nemotron-3-ultra-free
opencode:opencode/ling-3.0-flash-free</textarea>
        <span class="hint">可用的 cli：claude／codex／gemini／opencode，可以混搭。模型清單用各 CLI 自己的指令查（opencode 是 <code>opencode models</code>）。換模型就是改這一欄的文字，不必動任何程式碼。</span>
      </label>
```

🔴 **不得在這裡寫任何網址**（整份 `index.html` 不得出現 `http://` 或 `https://`，
既有測試會檢查）。

### F. `tests/test_ui.py`

在 `IndexHtmlStructureTest` 裡：**改一條、加三條**。

① 既有的 `test_first_round_button_label`，把

```python
        self.assertIn("開始討論", self.source)
```

改成

```python
        self.assertIn("開始討論（可延續數輪）", self.source)
```

（該測試其餘兩行斷言不動。）

② 新增三條：

```python
    def test_usage_panel_shows_no_money(self):
        """Frank 實測回報：畫面出現金額會讓人以為 council 去打了 API 在收費。
        實際上 council 不呼叫任何模型 API，金額只是各家 CLI 依 API 定價換算的
        參考值 ⇒ 一律不顯示，只顯示 token 數。
        ⚠️ 這是結構性斷言（只檢查原始碼字串），JS 的實際行為沒有自動化測試，
        本專案刻意不建 DOM 測試環境（SPEC.md §7：無建置步驟）。"""
        self.assertNotIn("usage-cost", self.source)
        self.assertIn("isCostKey", self.source)

    def test_usage_total_is_labelled_as_not_a_sum(self):
        """merge_usage() 按鍵名相加，而 opencode 與 claude 的鍵名完全不同
        ⇒ total 區塊沒有任何欄位代表所有席次的真正總量，必須在畫面上講明白。"""
        self.assertIn("不是所有席次的總和", self.source)

    def test_advisor_order_is_documented(self):
        """席次順序就是發言順序，這件事只有實作知道，使用者看不出來。"""
        self.assertIn("由上到下就是發言順序", self.source)
```

🔴 **既有的其他測試一條都不得修改或刪除**，包含
`test_no_html_injection_strings`、`test_no_http_urls`、`test_no_browser_storage`、
`test_no_timers`、`test_csp_meta_exact`、`test_confirm_over_cap_once_and_uses_confirm`。

### G. `README.md`

README 是**中英雙份**（英文在上、中文在下）。**兩邊都要加**，加在各自的
「How it works」／「運作方式」那一節的**最後面**（中文那節的最後一行是
「`SPEC.md` 是正式規格，建議從它開始讀。」，新小節加在它**之後**）。

英文那節加：

````markdown
### Changing models and speaking order

Seats are not hardcoded. In the web UI, the "advisors" field takes one seat per
line and **top-to-bottom is the speaking order**; on the command line it is the
order of the `--advisor` flags (see the `ADVISORS` array in `run.sh`).

The format is always `<cli>[:<model>]`, for example:

```
opencode:opencode/deepseek-v4-flash-free
gemini
claude:claude-sonnet-5
```

Omit the model to use that CLI's own default. Ask each CLI for its model list
(`opencode models`, and the equivalent for the others) — council does not keep a
model list and does not check whether a model name exists: a typo simply makes
that one seat report a failure.
````

中文那節加：

````markdown
### 換模型／調整發言順序

**席次不是寫死的。** web UI 的「顧問」欄位一行一席，**由上到下就是發言順序**；
命令列則是 `--advisor` 參數出現的順序（見 `run.sh` 裡的 `ADVISORS` 陣列）。

格式一律是 `<cli>[:<模型>]`，例如：

```
opencode:opencode/deepseek-v4-flash-free
gemini
claude:claude-sonnet-5
```

省略模型就用該 CLI 自己的預設。可用模型請用各 CLI 自己的指令查
（opencode 是 `opencode models`，其他家同理）——council 不維護模型清單，
也不會替你檢查模型名是否存在：**打錯就是那一席回報失敗**。
````

⚠️ 上面兩段用四個反引號框住只是為了在本工作包裡包住內層的三反引號區塊；
**寫進 `README.md` 時內層維持三個反引號即可，不要把四反引號抄進去。**

---

## 驗收條件（貼真實輸出，不要只描述）

1. `python3 -m unittest discover tests` **全過**，貼出最後三行。
   🔴 **既有 291 個測試一個都不得變紅**；新增三條 ⇒ 總數應為 **294**。
   ⚠️ 工作包 011 曾回報「交付完成」而實跑是 `FAILED (errors=1)`。**自己實際跑完再回報。**
2. 貼出三個檔的**完整 `git diff`**。
3. 貼出既有六條紅線仍然成立（**連空輸出也要貼**）：
   - `grep -nE 'innerHTML|outerHTML|insertAdjacentHTML|document\.write|eval\(|new Function|Function\(' src/static/index.html`
   - `grep -nE 'https?://' src/static/index.html`
   - `grep -nE 'localStorage|sessionStorage|indexedDB|document\.cookie' src/static/index.html`
   - `grep -nE 'setInterval|setTimeout' src/static/index.html`
   - `grep -c 'confirm_over_cap' src/static/index.html` ——應為 `1`。
   - `grep -c 'usage-cost' src/static/index.html` ——應為 `0`。
     ⚠️ `grep -c` 找不到時退出碼為 1，若你用 `set -e` 會中斷，請單獨跑。
4. **突變驗證三項**，每項：改壞 → 貼失敗輸出（**含翻紅的測試名**）→ 還原 →
   最後貼還原後全過的結果。
   - (a) 把 `className = "usage-cost"` 那一句加回 `renderUsageDict`
     ⇒ `test_usage_panel_shows_no_money` 應翻紅。
   - (b) 把按鈕文案改回 `"開始討論"` ⇒ `test_first_round_button_label` 應翻紅。
   - (c) 把 label 裡的「由上到下就是發言順序」刪掉
     ⇒ `test_advisor_order_is_documented` 應翻紅。
   - (d) **額外一項，預期不會翻紅**：把 `isCostKey` 的函式主體改成 `return false;`
     ⇒ 金額會重新出現在畫面上，但**測試應該照樣全過**。
     🔴 **照做並如實回報「沒有翻紅」**，不要為了讓它翻紅去改測試。
     這是刻意要你確認的一件事：**過濾邏輯本身沒有測試守得住，守得住的只有
     class 名與函式名的存在**（本專案沒有 DOM 測試環境，`SPEC.md` §7 明訂無建置步驟）。
   - 🔴 **突變只准動 `src/static/index.html`**，不准動測試檔。
   - 🔴 **每一項動手前先確認要取代的字串在檔案裡是唯一的**：印出 `text.find(old)`
     與 `text.rfind(old)`，兩個位置必須相同才可以取代。**位置不同就換一段更長的樣式**。
   - 🔴 **備份放 `dispatch/tmp/028-backup/`，不要放 `/tmp`。**
     還原後用 `cmp` 確認與備份**位元組相同**，並貼出結果。
5. 貼出 `git status --short`。
6. 🔴 **公開發布掃描**：貼出
   `grep -rnE "$(whoami)|/home/[a-z]" src/static/index.html tests/test_ui.py README.md`
   ——**應為空**。

---

## 不要做的事

- 🔴 **全程不得執行 `--live`，不得呼叫任何真實 CLI。** 測試一律用 `port=0`。
  ⚠️ **Frank 可能有一個 `--live` 的伺服器正在 8765 埠上跑，記憶體裡有他的討論。
  絕對不要對 8765 送任何請求，也不要 kill 任何行程。**
- 🔴 **不要動 `flattenUsage()`、`phaseLabel()`、`setBusy()`、`runAction()`、
  `addSpeechCard()`、`addArbitrationCard()`。**
- 🔴 **不要新增 API 端點、不要改 `src/server.py`**。這一包完全不碰伺服器。
- ⚠️ 不要新增功能、抽象層、設定項。金額欄位是**不顯示**，不是「做一個開關讓使用者切」。
- 不要引入第三方套件、框架、建置步驟。
- 不要碰版控（`git add` / `commit` / `push` 一律不執行）。
