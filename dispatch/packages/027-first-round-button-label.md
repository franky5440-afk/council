# 工作包 027：第一輪的按鈕文案

Frank 實測 web UI 時回報：討論剛建立、一輪都還沒跑過時，按鈕寫「再一輪」，
**「再」這個字預設前面已經有過一輪**，讀起來像系統已經在跑、這顆是追加用的。
實際上球在使用者手上（`SPEC.md` §5 邊界 1：輪與輪之間一定要人，第一輪也要人按）。

⚠️ **這是一個極小的包**：一段三分支的文案判斷、一條測試。**不要順手改別的東西。**

---

## 檔案

| 檔案 | 動作 |
|---|---|
| `src/static/index.html` | **修改**：`renderStatusBar()` 裡設定按鈕文字的那一行 |
| `tests/test_ui.py` | **修改**：加一條結構性斷言 |

🔴 **除了上表，一個字都不要動。** 特別是 `src/server.py`、`src/ui.py`、
`src/engine/` 底下所有檔案、`tests/test_server.py`、`SPEC.md`、`AGENTS.md`。

---

## 介面契約（照字面實作）

### A. `src/static/index.html`

`renderStatusBar()` 目前最後一行是：

```js
  $("btn-round").textContent = status.at_cap === true ? "再一輪（需確認）" : "再一輪";
```

改成三分支，**順序就是下面的順序**：

```js
  if (status.at_cap === true) {
    $("btn-round").textContent = "再一輪（需確認）";
  } else if (status.rounds_completed === 0) {
    $("btn-round").textContent = "開始討論";
  } else {
    $("btn-round").textContent = "再一輪";
  }
```

- 🔴 **文案就是「開始討論」四個字**，不要自己改成「開始第一輪」之類的（Frank 指定的）。
- 🔴 **`at_cap` 的分支必須排在最前面。** 今天 `at_cap` 為真時 `rounds_completed`
  不可能是 0（`at_cap` 的定義是 `rounds_completed >= max_rounds`，而 `max_rounds` 是 5），
  所以兩者今天不會同時成立——**但順序不能靠這個巧合**。「需確認」是花錢前的閘門提示，
  任何情況下都不該被別的文案蓋掉。
- ⚠️ **只改文案，不要動按鈕的 disabled 邏輯**（那是 `setBusy()` 的事）、
  也不要動 `runAction` 送出的 body（`confirm_over_cap` 全檔仍須恰好一處）。
- ⚠️ **不要改相位標籤 `phaseLabel()`**（「準備中」／「等你操作」）。
  我提過那組字也可以更清楚，但 Frank 明確說**只改按鈕文案即可**。

### B. `tests/test_ui.py`

在 `IndexHtmlStructureTest` 裡加一條：

```python
    def test_first_round_button_label(self):
        """一輪都還沒跑過時按鈕不該寫「再一輪」——「再」預設前面有過一輪。
        ⚠️ 這是結構性斷言（只檢查原始碼字串），JS 的實際行為沒有自動化測試，
        本專案刻意不建 DOM 測試環境（SPEC.md §7：無建置步驟）。"""
        self.assertIn("開始討論", self.source)
        self.assertIn("再一輪（需確認）", self.source)
        self.assertIn("rounds_completed === 0", self.source)
```

🔴 **既有的 `test_confirm_over_cap_once_and_uses_confirm` 必須照樣通過**
（`confirm_over_cap` 仍恰好一處）。

---

## 驗收條件（貼真實輸出，不要只描述）

1. `python3 -m unittest discover tests` **全過**，貼出最後三行。
   🔴 **既有 290 個測試一個都不得變紅**，新的總數應為 291。
   ⚠️ 工作包 011 曾回報「交付完成」而實跑是 `FAILED (errors=1)`。**自己實際跑完再回報。**
2. 貼出 `src/static/index.html` 與 `tests/test_ui.py` 的**完整 `git diff`**。
   `index.html` 的變更應該只有那一段。
3. 貼出 024 六條紅線仍然成立（連空輸出也要貼）：
   - `grep -nE 'innerHTML|outerHTML|insertAdjacentHTML|document\.write|eval\(|new Function|Function\(' src/static/index.html`
   - `grep -nE 'https?://' src/static/index.html`
   - `grep -nE 'localStorage|sessionStorage|indexedDB|document\.cookie' src/static/index.html`
   - `grep -nE 'setInterval|setTimeout' src/static/index.html`
   - `grep -c 'confirm_over_cap' src/static/index.html` ——應為 `1`。
4. **突變驗證兩項**，每項：改壞 → 貼失敗輸出（**含翻紅的測試名**）→ 還原 →
   最後貼還原後全過的結果。
   - (a) 把「開始討論」那一支改回「再一輪」⇒ 新測試翻紅。
   - (b) 把 `at_cap` 那一支移到 `rounds_completed === 0` 之後 ⇒
     **這一項不會翻紅**（今天兩者不會同時成立）。⚠️ **照做並如實回報「沒有翻紅」**，
     不要為了讓它翻紅去改測試——這是刻意要你確認的一件事：
     **那個順序今天沒有測試守得住，它靠的是註解。** 回報時說明這一點。
   - 🔴 **突變只准動 `src/static/index.html`**，不准動測試檔。
   - 🔴 **每一項動手前先確認要取代的字串在檔案裡是唯一的**：印出 `text.find(old)`
     與 `text.rfind(old)`，兩個位置必須相同才可以取代。
   - 🔴 **備份放 `dispatch/tmp/027-backup/`，不要放 `/tmp`。**
     還原後用 `cmp` 確認與備份**位元組相同**，並貼出結果。
5. 貼出 `git status --short`。
6. 🔴 **公開發布掃描**：貼出
   `grep -rnE "$(whoami)|/home/[a-z]" src/static/index.html tests/test_ui.py` ——**應為空**。

---

## 不要做的事

- 🔴 **全程不得執行 `--live`，不得呼叫任何真實 CLI。**
  ⚠️ **Frank 現在有一個 `--live` 的伺服器正在 8765 埠上跑，記憶體裡有他的討論。
  絕對不要對它送任何請求，也不要 kill 它。** 測試一律用 `port=0`。
- ⚠️ **不要改 `phaseLabel()`、不要改 `setBusy()`、不要改 `runAction()`。**
- ⚠️ 不要新增功能、抽象層、設定項。
- 不要引入第三方套件、框架、建置步驟。
- 不要碰版控（`git add` / `commit` / `push` 一律不執行）。
