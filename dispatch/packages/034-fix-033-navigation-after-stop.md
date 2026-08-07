# 工作包 034 — 修 033：關閉之後上一頁會讓兩個畫面疊在一起

## 這是修正包，接續 033 的 session

**這是主對話出題時漏掉的情況，不是你做錯。** 033 交付的每一條都照契約，
是契約本身沒有涵蓋「關閉之後使用者又動了瀏覽器導覽」這件事。

## 1. 問題

`showStopped()` 會把 `#stopped-view` 顯示出來、把另外兩個畫面藏起來。
但 `window.addEventListener("hashchange", onLoad)` **仍然是註冊著的**，
而 `onLoad()` 走到 `showForm()` 或 `openDiscussion()` 時，
**兩者都不會去藏 `#stopped-view`**，也不會把 `#status-bar` 復原。

⇒ 使用者按下「關閉 council」之後，再按瀏覽器的**上一頁／下一頁**（或任何會改動
`location.hash` 的動作），畫面上會**同時出現表單畫面與「council 已關閉」面板**，
看起來像故障。伺服器那時已經停了，所以那個表單也不可能運作。

## 2. 修法：伺服器關掉之後，不准再切換任何畫面

**不要**去替 `showForm()` 和 `openDiscussion()` 各補一行「藏起 stopped-view」——
那是在症狀端修，將來多一個畫面切換點就會再漏一次。**在源頭擋掉**：
關閉之後整個頁面就是終態，`onLoad()` 直接不做事。

### 2.1 新增模組層旗標

現有的宣告區（檔案裡逐字是這五行）：

```js
var currentId = null;
var live = null;
var lastStatus = null;
var es = null;
var arbitrationPlaceholder = null;
```

在**最後面**再加一行：

```js
var stopped = false;
```

### 2.2 `showStopped()` 設旗標

現有全文逐字是：

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

改成（**只加第二行，其餘一個字都不動**）：

```js
function showStopped(message) {
  stopped = true;
  closeSse();
  $("status-bar").hidden = true;
  $("form-view").hidden = true;
  $("discussion-view").hidden = true;
  $("stopped-view").hidden = false;
  $("stopped-reason").textContent = message;
}
```

🔴 **`stopped = true;` 必須是函式的第一行**，在任何 DOM 操作之前。
理由：這樣不論後面哪一行丟例外，旗標都已經設好了。

### 2.3 `onLoad()` 早退

現有全文逐字是：

```js
function onLoad() {
  var id = location.hash.slice(1);
  if (id) {
    openDiscussion(id);
  } else {
    showForm();
  }
}
```

改成（**只加開頭三行，其餘一個字都不動**）：

```js
function onLoad() {
  // 伺服器已經關掉之後，頁面就是終態：再切換畫面只會讓「已關閉」面板
  // 跟表單／討論畫面疊在一起，而且那時什麼請求都發不出去。
  if (stopped) { return; }
  var id = location.hash.slice(1);
  if (id) {
    openDiscussion(id);
  } else {
    showForm();
  }
}
```

## 3. 🔴 不准做的事

- **不准動 `showForm()`／`openDiscussion()`／`renderDiscussion()`** 或任何其他函式。
- **不准新增或修改任何 API 端點、事件種類、請求／回應格式。**
- **不准動** `src/server.py`、`src/serve.py`、`src/engine/*`、`src/cli.py`、`src/ui.py`、
  `start.sh`、`README.md`、`SPEC.md`、`AGENTS.md`。
- **不准移除 `hashchange` 監聽器**（`removeEventListener` 對匿名函式無效，
  而且改動監聽器的註冊時機會牽動頁面初次載入的路徑）。
- 033 既有的紅線一條都不准破：不得出現 `innerHTML` 類、`http(s)://`、`localStorage` 類、
  `setInterval`／`setTimeout`、`url(`、`<svg`；`confirm_over_cap` 恰好一次；
  `id="context-chars-text"` 恰好一次；CSP `<meta>` 逐字元固定；
  `[hidden] { display: none !important; }` 仍是 stylesheet 最後一條。

## 4. 環境紅線

- **不准碰 8765 埠**（Frank 可能有伺服器在跑）。要起伺服器驗證用 `--port 0` 或 8790 以上。
- **不准跑 `--live`**、**不准呼叫任何 CLI**、**不准執行任何版控指令**。
- **不准執行 `start.sh`**（它預設 `--live`）。
- 臨時檔一律放 `dispatch/tmp/`，先備份：

```bash
mkdir -p dispatch/tmp/034-backup
cp src/static/index.html tests/test_ui.py dispatch/tmp/034-backup/
```

## 5. 測試

在 `tests/test_ui.py` 的 `IndexHtmlStructureTest` 裡加**一條**結構性測試：

```python
    def test_navigation_disabled_after_stop(self):
        """關掉伺服器之後 hashchange 仍會觸發 onLoad()，而 showForm() 與
        openDiscussion() 都不會藏起 #stopped-view ⇒ 按上一頁會讓兩個畫面
        疊在一起。修在源頭：關閉之後 onLoad() 直接早退。
        ⚠️ 這是結構性斷言（只檢查原始碼字串），JS 的實際行為沒有自動化測試，
        本專案刻意不建 DOM 測試環境（SPEC.md §7：無建置步驟）。"""
        self.assertIn("var stopped = false;", self.source)
        self.assertIn("stopped = true;", self.source)
        self.assertIn("if (stopped) { return; }", self.source)
```

跑全套：

```bash
python3 -m unittest discover tests
```

目前是 337 個，你會讓它變成 338。
🔴 **回報時附上實際的最後三行輸出**（`Ran N tests`／`OK` 或 `FAILED`），
不准只寫「測試通過」。

## 6. 交付前自己確認

- [ ] `python3 -m unittest discover tests` 全過，附實際輸出
- [ ] `grep -c "var stopped = false;" src/static/index.html` → 恰好 1
- [ ] `grep -c "if (stopped) { return; }" src/static/index.html` → 恰好 1
- [ ] `grep -nE "innerHTML|outerHTML|document\.write|eval\(|localStorage|setTimeout|setInterval|url\(|<svg|https?://" src/static/index.html` → 0 命中
- [ ] `grep -c "confirm_over_cap" src/static/index.html` → 恰好 1
- [ ] `[hidden] { display: none !important; }` 仍是 stylesheet 最後一條規則
- [ ] `git diff --stat` 只有 `src/static/index.html` 與 `tests/test_ui.py` 兩個檔
- [ ] 沒有執行版控指令、沒有碰 8765、沒有跑 `--live`、沒有呼叫任何 CLI

## 7. 卡住怎麼辦

契約有矛盾就寫 `dispatch/BLOCKED.md` 說明卡在哪一條，不要自己選一個讀法硬做。
