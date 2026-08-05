# 工作包 025：024 的裁示與修正

承接工作包 024。**你交付的東西大致是對的**：`server.py`／`ui.py` 的 diff 與契約一致、
六條結構性紅線 grep 全部 0 命中、公開發布掃描乾淨、283 個測試只有你回報的那一條紅。
`BLOCKED.md` 停下來問而不是自己選一邊，是正確的行為。

本包做四件事：① 裁示 `//` ② 修一個我實測出來的真 bug ③ 幾個小修
④ 補做你還沒做的突變驗證與實機驗證。

---

## ① 裁示：`GET //` 採 **A**，但**不要刪測試，改成釘住事實**

你的分析我獨立複核過，成立（Evidence 層）：

- `/usr/lib/python3.12/http/server.py:337-342` 確實有 gh-87389 的
  `self.path = '/' + self.path.lstrip('/')`。
- 我自己起伺服器實測：`//` 與 `///` 都回 `200`，`/index.html`、`/static/index.html`、
  `/../src/server.py` 都回 `404`。

**根因是我的出題**：我在測試第 4 項寫了一個自己沒實測過的期望值。你照契約實作是對的。

⇒ 採用 **A**（路由程式碼一字不改），但**不要只是把 `//` 從測試裡拿掉**。
拿掉等於這件事從此沒人知道。改成**兩條測試**：

1. `test_index_only_exact_root_path`：只留 `/index.html`、`/static/index.html`、
   `/../src/server.py` 三條，斷言 `404`。
2. **新增** `test_double_slash_normalized_by_stdlib`：斷言 `GET //` 與 `GET ///`
   都回 `200`，並在測試的 docstring 裡寫明：

   > `http.server` 的 `parse_request()` 內建 gh-87389 的 open redirect 防護，
   > 在進入 handler 之前就把開頭的多個 `/` 併成一個 ⇒ `//` 到我們手上時
   > `self.path` 已經是 `/`。這不是我們的路由放寬：唯一的靜態路由仍然是
   > `== "/"`，沒有任何「路徑→檔案」的對映。此測試釘住 stdlib 的這個行為，
   > 哪天它改了要有人看一眼。

🔴 **不要為了讓 `//` 回 404 去翻 `self.requestline`。** 那會在單一靜態路由上長出
第二套路徑判斷，而換到的只是一個病態寫法的狀態碼。

---

## ② 🔴 真 bug：仲裁前提不成立時，畫面會永遠掛著「仲裁進行中」

### 我的實測（你的測試抓不到，因為它是時序問題）

`_post_arbitration()` 的順序是：`try_claim()` → `append_event("arbitration_started")`
→ `run_arbitration()` 丟 `BoundaryError` → 回 `409`。

我起了伺服器、掛一個 SSE 讀者、在沒跑過任何一輪的情況下打仲裁，**跑十次**：

```
409 回應耗時約 2 ms；SSE 迴圈是 time.sleep(0.25) 輪詢
十次中有 10 次，arbitration_started 事件在 409 回應「之後」才送達
```

⇒ 瀏覽器收到 `409` 時**佔位還不存在**，`clearArbitrationPlaceholder()` 收了個空；
0～250 ms 後佔位才長出來，**然後永遠不會被清掉**。

**根因是我的契約**：024 我寫「JS 收到非 `200` 就必須把那個佔位換成錯誤訊息」，
那句話預設佔位已經存在。你照字面實作完全正確。

### 修法：修在源頭，不要在 JS 裡加旗標

在 JS 裡加「已中止」旗標可以遮住單一分頁的症狀，但**沒有任何自動化測試測得到它**，
而且救不了「另一個分頁正在看」的情境。正確的修法是讓事件根本不要在前提不成立時發出，
同時**完整保留 022「畫面必須先亮」的性質**。

**(1) `src/engine/orchestrator.py`——`run_arbitration()` 加一個 keyword-only 參數**

```python
def run_arbitration(discussion, ask_fn, *, max_chars=DEFAULT_MAX_CHARS,
                    timeout_s=DEFAULT_TIMEOUT_S, on_start=None) -> dict:
```

- **動作順序就是規格，逐步照做，不要重排**：
  1. `if not discussion.can_arbitrate(): raise BoundaryError(...)`（**維持現狀，一字不改**）
  2. `on_start` 非 `None` ⇒ 呼叫一次 `on_start()`（**不帶參數**）
  3. `seat = discussion.arbiter`、`prompt = build_arbiter_prompt(discussion)`
  4. 既有的 `try` / `ask_fn` / `record_arbitration`（**一字不改**）
- 🔴 **`on_start` 必須在前提檢查「之後」、`ask_fn`「之前」。** 這兩個邊界缺一不可：
  在前提之前 ⇒ 就是現在這個 bug；在 `ask_fn` 之後 ⇒ 畫面在最久的那一次呼叫期間全黑，
  正是 022 要避免的事。
- 🔴 **`on_start` 丟出的例外必須被吞掉並忽略**（`try` / `except Exception: pass`），
  理由寫進註解：它是**通知**，不是閘門；一個事件通知的 bug 不應該取消使用者要求的仲裁。
  （與 `run_round()` 的 `on_record` 同一條政策。）
- ⚠️ `run_round()` **不動**。`orchestrator.py` 除了這個參數與那段 try/except，
  **其他一行都不准動**。

**(2) `src/server.py`——把事件的發出移進回呼**

`_post_arbitration()` 裡目前是：

```python
                session.append_event(
                    "arbitration_started",
                    {"seat_id": discussion.arbiter["seat_id"]})
                record = orchestrator.run_arbitration(
                    discussion, self.server.ask_fn,
                    timeout_s=self.server.timeout_s,
                    max_chars=self.server.max_chars)
```

改成（把那句 `append_event` **移進** `on_start`，不要留兩份）：

```python
                record = orchestrator.run_arbitration(
                    discussion, self.server.ask_fn,
                    timeout_s=self.server.timeout_s,
                    max_chars=self.server.max_chars,
                    on_start=lambda: session.append_event(
                        "arbitration_started",
                        {"seat_id": discussion.arbiter["seat_id"]}))
```

原本那段解釋「事件先發是刻意的」的註解要一起改寫成現在的實情：
**事件仍然在 `ask_fn` 之前發出（畫面先亮），但已經在前提檢查之後 ⇒
前提不成立時不會發出一則沒有結局的事件。**

🔴 `_post_rounds()` **完全不動**。

**(3) `src/static/index.html`——保留現有的防守，不要加旗標**

`runAction` 裡非 `200` 時呼叫 `clearArbitrationPlaceholder()` 的那兩處**原樣保留**
（成本是零，而且對「另一個分頁把討論搶走」之類的情形仍有用）。
🔴 **不要新增任何「已中止」旗標或狀態變數。**

### (4) 回歸測試（🔴 必要，不是選配）

加進 `tests/test_ui.py`（或 `tests/test_server.py`，你選一個，寫在一起就好）：

1. 🔴 **前提不成立時不得發出事件**：新建討論（沒跑過任何一輪）⇒
   `POST /arbitration` 得到 `409` ＋ `code == "boundary"` ⇒ 接上
   `GET /events?cursor=0` ⇒ **收到的事件裡不得有 `arbitration_started`**。
   ⚠️ SSE 不會自己結束，讀法比照 `tests/test_server.py` 既有的 SSE 測試
   （讀固定位元組或設 timeout 後解析已收到的部分）。
2. 🔴 **前提成立時事件仍在花錢之前**：直接呼叫
   `orchestrator.run_arbitration(discussion, ask_fn, on_start=f)`，用一個共用的 list
   記錄呼叫順序 ⇒ 斷言 `on_start` 的記錄**排在** `ask_fn` 的記錄**之前**。
3. **前提不成立時 `on_start` 一次都不被呼叫**，且 `ask_fn` 也是 0 次。
4. **`on_start` 丟例外不得中斷仲裁**：傳一個必定 `raise` 的回呼 ⇒
   `run_arbitration()` 仍然正常回傳 record。
5. 不傳 `on_start` 時行為與現在完全相同（既有測試已覆蓋，補一條斷言即可）。

---

## ③ 三個小修（`src/static/index.html`）與一個註解修正

**(a) 🔴 `error` 事件的監聽與 `EventSource` 內建的 `error` 撞名**

```js
  es.addEventListener("error", function () {
    $("st-sse").textContent = "收到 error 事件";
  });
```

`EventSource` 在**連線失敗時**也會派發一個叫 `error` 的事件到同一個物件上，
所以這個 listener 會連傳輸層的斷線一起接到——而它註冊在 `es.onerror` 之後，
會**把「連線中斷，瀏覽器會自動重連」那句有用的訊息蓋掉**。
Frank 手測時只要 Ctrl-C 一次伺服器就會看到。

修法：伺服器送來的事件一定有 `data`，傳輸層的錯誤沒有 ⇒ 在 handler 開頭加

```js
    if (!ev.data) { return; }   // 傳輸層斷線也叫 error，那個由 onerror 負責
```

**(b) 初次載入沒有套用 `busy`**

`renderDiscussion()` 沒有呼叫 `setBusy()`，所以帶著 `#<id>` 重新整理頁面時，
就算另一個分頁正在跑，兩顆按鈕都是可按的（按下去會拿到 `409 busy`，不會出事，
但契約 D-5 要求 `busy === true` 時 disabled）。
⇒ 在 `renderDiscussion()` 裡 `renderStatusBar(data.status)` 之前加
`setBusy(data.busy === true);`。

**(c) `fetch` 失敗沒有 `.catch`**

`runAction()` 先 `setBusy(true)` 才發請求；伺服器如果已經被 Ctrl-C，`fetch` 會 reject，
**兩顆按鈕就永遠停在 disabled、畫面上一個字都沒有**。
⇒ 給 `runAction()`、`refreshDiscussion()`、`openDiscussion()` 各補一個 `.catch`：
`setBusy(false)`（只有 `runAction` 需要）並在 `#st-sse` 顯示
「無法連上伺服器（它可能已經停止）」。

**(d) LIVE 時按鈕旁的常駐紅字（024 契約 D-5 漏做）**

在 `#action-row` 裡加一個 `<span>`，`live === true` 時 `textContent` 設成
「⚠️ 按下去會消耗訂閱額度」並上紅色，否則設成空字串。
在 `updateModeBadge()` 裡一起更新即可，不要另外開一條路徑。

**(e) `src/server.py` 的 `_get_index()` 註解寫錯了**

```python
        # 單頁 UI 的回傳不設 no-cache 以外的快取：檔案一改就要馬上拿到
        # 新版，不要讓瀏覽器跟伺服器各持己見。
```

**這句與實際行為矛盾**：`ui.py` 是在**模組載入時**讀一次，改了 `index.html`
不重啟伺服器根本拿不到新版。註解描述了一個不存在的性質，比沒有註解更糟。
改寫成實情，例如：

```python
        # no-store：頁面內容在行程啟動時就固定了（ui.py 只讀一次），
        # 讓瀏覽器也不要留舊的，重啟伺服器就一定看到新版。
```

---

## ④ 補做 024 沒做完的驗證

你在 BLOCKED 之後停下來，所以下面這些都還沒做。**全部補上**。

### 驗收條件（貼真實輸出，不要只描述）

1. `python3 -m unittest discover tests` **全過**，貼出最後三行。
   🔴 **283 個測試（扣掉／加上本包的增減）一個都不得變紅。** 說明數字怎麼算的。
   ⚠️ 工作包 011 曾回報「交付完成」而實跑是 `FAILED (errors=1)`。**自己實際跑完再回報。**
2. 貼出 022 四條紅線仍然成立（本包改了 `server.py`，要重驗）：
   - `grep -nE '^(import|from)' src/server.py` ——不得有 `adapters`／`subprocess`。
   - `grep -nE 'open\(|pathlib|Access-Control' src/server.py` ——**應為空**。
   - `grep -n '\.status()' src/server.py` ——**應為空**。
   - `grep -n 'try_claim' src/server.py` ——仍**恰好兩處**。
3. 貼出 024 六條新紅線的 grep（本包改了 `index.html`，要重驗），連空輸出也要貼：
   - `grep -nE 'innerHTML|outerHTML|insertAdjacentHTML|document\.write|eval\(|new Function|Function\(' src/static/index.html`
   - `grep -nE 'https?://' src/static/index.html`
   - `grep -nE 'localStorage|sessionStorage|indexedDB|document\.cookie' src/static/index.html`
   - `grep -nE 'setInterval|setTimeout' src/static/index.html`
   - `grep -nE 'server|engine|adapters|subprocess' src/ui.py`
   - `grep -c 'confirm_over_cap' src/static/index.html` ——應為 `1`。
4. 貼出 `git diff --stat` 與 `src/engine/orchestrator.py`、`src/server.py`、
   `tests/test_server.py` 的**完整 `git diff`**，證明變更都很小。
5. **實際把伺服器跑起來驗一次（🔴 全程 dry run，不得加 `--live`）**，貼出真實輸出：
   ```bash
   python3 src/serve.py --port 0    # 背景跑，埠號從它印出的 URL 取
   curl -s -o /dev/null -w '%{http_code} %{content_type}\n' http://127.0.0.1:<port>/
   curl -s http://127.0.0.1:<port>/ | wc -c          # 應與 index.html 位元組數相同
   curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:<port>/index.html   # 應 404
   ```
   再用 `curl` 走一次完整流程並貼出輸出：建立討論 → 開一輪 → `GET` 狀態 →
   仲裁。⚠️ 記得每個 POST 都要 `-H 'Content-Type: application/json'`。
   驗完把行程收掉，貼出收掉的指令。
6. **突變驗證七項**，每項：改壞 → 貼失敗輸出（**含翻紅的測試名**）→ 還原 →
   最後貼還原後全過的結果。
   - (a) `_get_index` 的路徑比對 `== "/"` 改成 `startswith("/")` ⇒ `/index.html` 那條翻紅。
   - (b) 拿掉 `GET /` 那條路由 ⇒ `GET / ⇒ 200` 那條翻紅。
   - (c) `Content-Type` 改成 `text/plain` ⇒ 同上那條翻紅。
   - (d) 把 `GET /` 的處理提到 `_gate()` 之前 ⇒ `Host` 那條翻紅。
   - (e) 在 `index.html` 的 JS 裡插入一行含 `innerHTML` 的程式碼 ⇒ 紅線測試翻紅。
   - (f) 拿掉 `index.html` 的 CSP `<meta>` ⇒ CSP 測試翻紅。
   - (g) 🔴 **把 `on_start` 的呼叫移到 `can_arbitrate()` 檢查之前** ⇒
     ②-(4) 第 1 條與第 3 條翻紅。**這一項是本包最重要的突變。**
   - 🔴 **突變只准動 `src/server.py`／`src/static/index.html`／
     `src/engine/orchestrator.py`**，不准動測試檔、不准動測試裡的樣本值。
   - 🔴 **每一項動手前先確認要取代的字串在檔案裡是唯一的**：印出 `text.find(old)`
     與 `text.rfind(old)`，**兩個位置必須相同**才可以取代。
     ⚠️ 工作包 019 踩過：要改的那幾行在另一個函式裡字面完全相同，
     `replace(old, new, 1)` 打到的是另一側，畫面上是漂亮的一片紅、
     **但要驗的那一側完全沒被驗到**。翻紅之後也要看一眼**紅的是不是預期的那幾個測試名**。
   - 🔴 **備份放 `dispatch/tmp/025-backup/`，不要放 `/tmp`。**
     還原後用 `cmp` 確認與備份**位元組相同**，並貼出結果。
7. 貼出 `git status --short`。
8. 🔴 **公開發布掃描**（本 repo 是 PUBLIC）：貼出
   `grep -rnE "$(whoami)|/home/[a-z]" src/ui.py src/static/index.html src/server.py src/engine/orchestrator.py tests/test_ui.py`
   ——**應為空**。
9. 🔴 **把 `dispatch/BLOCKED.md` 刪掉**（本包已裁示，卡關已解除）。
   ⚠️ 它會被下一次派工自動歸檔，但留著會讓人以為還卡著。

---

## 不要做的事

- 🔴 **全程不得執行 `--live`，不得呼叫任何真實 CLI。**
- ⚠️ **不要動 `src/ui.py`、`src/engine/state.py`、`src/engine/sessions.py`、
  `src/engine/wiring.py`、`src/cli.py`、`src/serve.py`、`run.sh`、`dispatch.sh`、
  `SPEC.md`、`AGENTS.md`。**
- ⚠️ **不要在 JS 裡加任何新的狀態旗標**（見 ②-(3)）。
- ⚠️ **不要改 `run_round()`，不要改 `_post_rounds()`。**
- ⚠️ **不要為了 `//` 去翻 `self.requestline`。**
- ⚠️ 不要引入第三方套件、框架、建置步驟、`asyncio`。
- 不要落檔、不要加 logging、不要覆寫 `log_message`。
- 不要碰版控（`git add` / `commit` / `push` 一律不執行）。
