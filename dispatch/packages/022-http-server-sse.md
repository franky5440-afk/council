# 工作包 022：本機 HTTP 伺服器＋SSE 事件流

**動手前整段讀完 `SPEC.md` §7、§7.1、**§7.2（本包的安全規格，剛新增）**，
另讀 §5（六道停止邊界）、§6.1（仲裁前提）、§3.3（脈絡）。**

`sessions.py`（工作包 020／021）已經讓一個討論能跨請求存活，但**現在沒有任何東西
用到它**。本包把它接上 HTTP：讓瀏覽器建立討論、一輪一輪地開、叫仲裁者、
並用 SSE 看到進行中的即時進度。

⚠️ **本包不寫任何 HTML／CSS／JS。** 那是 023。本包交付後只有 JSON API 與 SSE，
用 `curl` 就能驗完，**這是刻意的**。

---

## 檔案

| 檔案 | 動作 |
|---|---|
| `src/server.py` | **新增**：HTTP 路由、SSE、執行權配對 |
| `src/serve.py` | **新增**：進入點（唯一 import adapters 的新檔） |
| `tests/test_server.py` | **新增**：本包的測試 |
| `src/engine/orchestrator.py` | **微幅修改**：只加一個 keyword-only 參數（見下） |
| `src/engine/sessions.py` | **微幅修改**：只補一行 docstring（見下） |
| `src/cli.py` | **微幅修改**：只改 docstring 裡的一句話（見下） |

🔴 **除了上表，一個字都不要動。** 特別是 `state.py`、`wiring.py`、`run.sh`、
`SPEC.md`、`AGENTS.md`、任何既有測試檔。

### 三個「微幅修改」的精確內容

**(1) `src/engine/orchestrator.py`——只加一個參數**

`run_round()` 目前跑完整輪才回傳，中途沒有任何對外訊號，
所以 SSE 看不到「第二位顧問正在說話」。加一個回呼：

```python
def run_round(discussion, ask_fn, *, max_chars=DEFAULT_MAX_CHARS,
              timeout_s=DEFAULT_TIMEOUT_S, on_record=None) -> dict:
```

- `on_record` 非 `None` 時，在**每一次 `discussion.record_speech()` 回傳之後**
  以那筆 record 呼叫一次：`on_record(record)`。位置就是那一行的正下方。
- 🔴 **`on_record` 丟出的例外必須被吞掉並忽略**（`try` / `except Exception: pass`）。
  理由寫進註解：**那一輪的錢已經花掉了**，讓一個事件通知的 bug 中斷整輪，
  會使 `end_round()` 不被呼叫、討論永遠卡在 `in_round` 相位——代價遠大於漏掉一個事件。
- ⚠️ `run_arbitration()` **不加這個參數**（它只有一次呼叫，事件由呼叫端自己發）。
- ⚠️ 除了這個參數與那一段 try/except，`orchestrator.py` 其他部分**一行都不准動**。
  既有 229 個測試必須全部照樣通過。

**(2) `src/engine/sessions.py`——只補 docstring**

`refresh()` 目前沒有 docstring（工作包 021 的契約要求但漏了）。補上一行即可，
說明「重新呼叫 `discussion.status()` 更新快照，回傳新快照的深拷貝」。
🔴 **`sessions.py` 的程式邏輯與 import 一個字都不准改**（它的三個 stdlib import
是工作包 020 的結構性紅線）。

**(3) `src/cli.py`——只改一句 docstring**

把這一句：

```
本檔案是全 repo 唯一允許 import adapters 的檔案。
```

改成：

```
本檔案與 src/serve.py 是全 repo 僅有的兩個允許 import adapters 的檔案。
```

🔴 **`cli.py` 其他部分一行都不准動。**

---

## 🔴 本包的四條結構性紅線（可用 grep 驗，驗收會逐條檢查）

1. **`src/server.py` 不得 import `adapters`，也不得 import `subprocess`。**
   真實呼叫由 `serve.py` 注入成 `ask_fn`（與 `orchestrator.py` 同一個手法）。

2. **`src/server.py` 全檔不得出現 `.status()`。**
   讀狀態一律走 `session.snapshot` 或 `session.refresh()`（`SPEC.md` §7.1 讀者路徑）。
   直接對進行中的討論呼叫 `status()` 會讀到半更新的用量統計。

3. **`src/server.py` 全檔不得出現 `open(`、`pathlib`、`Access-Control`。**
   前兩者：`SPEC.md` §7.2「伺服器不開檔」。第三者：§7.2 第 4 點，
   回應永遠不帶 CORS 標頭，靠瀏覽器的 preflight 替我們擋下惡意網頁。

4. **綁定位址是白名單，不是預設值。** 見下面 `build_server()` 的契約。

---

## 介面契約（照字面實作，不要擴充公開介面）

### A. `src/server.py`

```python
def build_server(*, ask_fn, live, host="127.0.0.1", port=8765,
                 timeout_s=orchestrator.DEFAULT_TIMEOUT_S,
                 max_chars=orchestrator.DEFAULT_MAX_CHARS):
    """建立並回傳一個已綁定但尚未 serve_forever() 的伺服器物件。"""
```

- 🔴 `ask_fn` 與 `live` 是**必填的 keyword-only 參數，沒有預設值**。
  忘了傳 ⇒ `TypeError` 當場失敗。**`ask_fn` 絕不可以有預設值**——
  預設值一旦存在，漏傳就會安靜地打到某個東西（`AGENTS.md` 與工作包 016 的同一條）。
- 🔴 `host` **只接受 `"127.0.0.1"` 與 `"localhost"`**，其他值（含 `"0.0.0.0"`、
  `""`、任何實體網卡位址）一律丟 `ValueError`，訊息要說得出為什麼。
  `SPEC.md` §7.2：這是機制層的白名單，不是「預設安全、可以改」。
- `port=0` 必須可用（測試要靠它拿隨機埠）。
- `live` 是**純顯示用**的布林值，只會出現在 JSON 回應裡供 UI 顯示。
  它不參與任何判斷。
- 伺服器類別用 `ThreadingHTTPServer` 的子類，設 `daemon_threads = True`
  （SSE 連線會長期佔住執行緒，不設會讓行程關不掉）。
- `build_server()` 內部自己建立一個 `SessionStore()`，掛成伺服器物件的
  `.store` 屬性（測試要用）。`timeout_s`／`max_chars`／`ask_fn`／`live`
  同樣掛在伺服器物件上供 handler 取用。
- ⚠️ **不要覆寫 `log_message`**，保留 `http.server` 預設的 stderr 請求日誌。

#### 請求守門（`SPEC.md` §7.2，四道，**每一個請求都要過**）

順序就是下面的順序，先不過的先回：

| 檢查 | 不過時 |
|---|---|
| `Host` 標頭 ∈ {`127.0.0.1:<實際埠>`, `localhost:<實際埠>`} | `403` |
| `Origin` 標頭若**存在**，∈ {`http://127.0.0.1:<實際埠>`, `http://localhost:<實際埠>`} | `403` |
| 有 body 的請求，`Content-Type` 必須以 `application/json` 開頭 | `415` |
| `Content-Length` 必須存在且是 `0 ≤ n ≤ 5_000_000` 的十進位整數 | 缺／壞 `400`、過大 `413` |

- 🔴 **`<實際埠>` 一律從 `self.server.server_address[1]` 取得**，不要用傳進來的
  `port`——`port=0` 時那是 0，寫死會讓白名單永遠不匹配。
- 🔴 **回應永遠不帶任何 `Access-Control-*` 標頭**，也**不要實作 `do_OPTIONS`**。
- 🔴 **讀 body 一律 `self.rfile.read(content_length)`，恰好讀那麼多位元組。**
  用 `self.rfile.read()`（不給長度）會一直等到連線關閉 ⇒ 伺服器卡死。
- body 為空字串時，視同 `{}`。body 不是合法 JSON、或不是 JSON 物件 ⇒ `400`。

#### 路由

| 方法 | 路徑 | 會花錢 |
|---|---|---|
| `POST` | `/api/discussions` | 否 |
| `GET` | `/api/discussions/<id>` | 否 |
| `POST` | `/api/discussions/<id>/rounds` | 🔴 **是** |
| `POST` | `/api/discussions/<id>/arbitration` | 🔴 **是** |
| `GET` | `/api/discussions/<id>/events` | 否（SSE） |

- 路徑不匹配任何一條 ⇒ `404`。路徑對但方法不對 ⇒ `405`。
- `<id>` 找不到 ⇒ `404`。
- ⚠️ **不要實作 `GET /`，不要提供任何靜態檔案服務。** 那是 023 的事，
  現在做會變成「先有一個空殼路由，下一包再改」。

#### 共用的回應內容

所有成功回應（上面前四條路由）的 body 都是**同一個形狀**，讓 023 的 JS 只需要
一份解析程式碼：

```json
{
  "id": "<session id>",
  "live": true,
  "busy": false,
  "question": "<原始問題>",
  "context_chars": 0,
  "seats": [{"seat_id": "...", "cli": "...", "model": null, "role": "advisor"}],
  "status": { ... session.snapshot 的內容 ... }
}
```

- 🔴 **不得回傳 `context` 原文**，只回 `context_chars`（`SPEC.md` §7.2 最後一條）。
- `seats` 直接用 `discussion.seats`（它已經是建構時的副本）。
- `status` 一律取自 `session.snapshot` 或 `session.refresh()`。
- 錯誤回應一律 `{"error": "<看得懂的中文訊息>"}`；`409` 額外多一個
  `"code"` 鍵，值是 `"busy"` 或 `"boundary"`。
- 所有 JSON 回應：`Content-Type: application/json; charset=utf-8`，
  帶 `Content-Length`，body 以 `json.dumps(..., ensure_ascii=False)` 產生後編成 UTF-8。
- ⚠️ **不要設定 `protocol_version`**（保持 `http.server` 預設的 HTTP/1.0）。

#### `POST /api/discussions`——建立討論

body **恰好**接受這四個鍵，其中 `context` 選填：

```json
{"question": "...", "advisors": ["claude", "opencode:opencode/xxx-free"],
 "arbiter": "claude", "context": ""}
```

- 🔴 **出現任何其他鍵 ⇒ `400`**（不要默默忽略；那會讓使用者的錯字變成沉默的失效）。
- `advisors` 必須是非空的字串 list；`arbiter` 必須是字串；`question` 必須是字串。
- 席次字串一律用 `wiring.parse_seat_spec()` 解析，`seat_id` 的產生規則**比照
  `cli.py` 的 `_build_seats()`**：顧問是 `f"{cli}-{i+1}"`、仲裁者固定 `"arb"`。
- `context` 是**字串本文**，直接原樣傳給 `state.Discussion(..., context=...)`。
  🔴 **不接受檔案路徑、不開檔**（`SPEC.md` §7.2）。
- `max_rounds` **不接受**，一律用 `state.DEFAULT_MAX_ROUNDS`（比照 `cli.py`）。
- `parse_seat_spec()` 或 `Discussion()` 丟 `ValueError` ⇒ `400` ＋ 該例外的訊息。
- 成功 ⇒ `store.create(discussion)`，回 `200` ＋ 上面的共用形狀。

#### `POST /api/discussions/<id>/rounds`——開一輪（🔴 會花錢）

body 選填 `{"confirm_over_cap": true}`（預設 `false`）。其他鍵 ⇒ `400`。

**動作順序就是規格，逐步照做，不要重排**（工作包 020 的教訓）：

1. `session.try_claim()`；**回 `False` 就立刻回 `409` ＋ `{"code": "busy"}`**，
   ⚠️ **此時不可以呼叫 `release()`**（執行權是別人的）。
2. 取得執行權之後，用 `try` / `finally` 包住剩下**全部**動作，
   `finally` 裡**一定**是 `session.release()`。
3. `try` 內部，依序：
   1. 若 `discussion.phase == state.PHASE_AWAITING_USER`，
      呼叫 `discussion.request_next_round(confirm_over_cap=<body 的值>)`。
      （第一輪時 phase 是 `ready`，這一步跳過。）
   2. `session.append_event("round_started", {"round": len(discussion.rounds) + 1})`
   3. `orchestrator.run_round(discussion, ask_fn, timeout_s=…, max_chars=…,
      on_record=lambda rec: session.append_event("speech", rec))`
   4. `snapshot = session.refresh()`
   5. `session.append_event("round_finished", {"round": len(discussion.rounds),
      "status": snapshot})`
4. 回 `200` ＋ 共用形狀。

- 🔴 **`try_claim()` 必須是第一個動作**，在任何 phase 判斷、任何 `ask_fn` 之前。
  `SPEC.md` §7.1：兩個分頁同時按「再一輪」，兩條執行緒會同時通過邊界 1 的相位檢查，
  跑出兩輪、花兩倍的錢。
- 🔴 **`state.BoundaryError` ⇒ `409` ＋ `{"code": "boundary"}` ＋ 例外訊息**，
  並且**仍然要經過 `finally` 釋放執行權**。已達輪數上限（邊界 3）與相位不對
  （邊界 1）都會走到這裡。
- ⚠️ 邊界 1 沒有被繞過：**這個 HTTP 請求本身就是「使用者按了再一輪」**。
  引擎不會自己呼叫 `request_next_round()`，一次請求只跑一輪。

#### `POST /api/discussions/<id>/arbitration`——叫仲裁者（🔴 會花錢）

body 必須是 `{}`（或空）。其他鍵 ⇒ `400`。順序同上：

1. `try_claim()`，搶不到 ⇒ `409` / `busy`，**不 release**。
2. `try` / `finally`，`finally` 一定 `release()`。
3. `try` 內部依序：
   1. `session.append_event("arbitration_started", {"seat_id": discussion.arbiter["seat_id"]})`
   2. `record = orchestrator.run_arbitration(discussion, ask_fn, timeout_s=…, max_chars=…)`
   3. `snapshot = session.refresh()`
   4. `session.append_event("arbitration_finished", {"record": record, "status": snapshot})`
4. 回 `200` ＋ 共用形狀。

- ⚠️ **不要自己重寫 `SPEC.md` §6.1 的三條前提。** `run_arbitration()` 已經在
  任何 `ask_fn` 之前檢查 `can_arbitrate()` 並丟 `BoundaryError` ⇒ `409` / `boundary`。
  在 server 這一層再寫一份，就會出現兩份會各自過期的規則。
- ⚠️ **`arbitration_started` 事件在 `run_arbitration()` 之前發出，是刻意的**：
  仲裁者拿的是最長的逐字稿，等待時間最久，畫面必須先亮起來。
  前提不成立時該事件已經發出而仲裁沒發生——那沒關係，緊接著回的是 `409`，
  023 會處理；**不要為了「事件要漂亮」把它移到呼叫之後**。

#### `GET /api/discussions/<id>/events`——SSE

- 回應標頭：`Content-Type: text/event-stream; charset=utf-8`、
  `Cache-Control: no-cache`、`Connection: close`。**不帶 `Content-Length`。**
- 游標來源，依序：`Last-Event-ID` 標頭 → 查詢字串 `?cursor=N` → `0`。
  值不是十進位非負整數 ⇒ 當成 `0`（重播全部，寧可重播也不要讓使用者看到空白畫面）。
- 迴圈：`events_since(cursor)` 取出新事件 → 逐則寫出 → 更新 cursor →
  `time.sleep(0.25)` → 再來一次。**永遠不主動結束**，直到客戶端斷線。
- 每則事件的格式**恰好**是：

  ```
  id: <seq>
  event: <kind>
  data: <json.dumps(data, ensure_ascii=False)>
  <空行>
  ```

  🔴 **`data` 一律是 `json.dumps` 的結果，絕不可以直接塞原始文字。**
  顧問的發言是**模型產生的多行文字**，SSE 的 `data:` 欄位遇到換行就會被切成
  兩個欄位、後半段變成殘缺的協定內容。`json.dumps` 會把換行編成 `\n` 兩個字元，
  結果保證是單行。**這是本包最容易寫錯、也最容易在小測資上看起來正常的一行。**
- 每則寫完呼叫 `self.wfile.flush()`。
- 連續 **15 秒**沒有新事件就寫一行心跳：`: keep-alive` ＋ 空行（同樣要 flush）。
- 客戶端斷線 ⇒ 寫入時會丟 `BrokenPipeError` 或 `ConnectionResetError`，
  **捕捉後直接 return**，不要讓 traceback 淹沒終端機。
- 🔴 **這條路由絕對不可以呼叫 `try_claim()`。** 它是讀者路徑；拿執行權會讓
  「有人在看畫面」變成「沒有人能開下一輪」。
- `kind` 只准是這六個字面值之一，寫成模組層常數
  `EVENT_KINDS = ("round_started", "speech", "round_finished",
  "arbitration_started", "arbitration_finished", "error")`。
  ⚠️ 目前 `"error"` 沒有任何地方會發出，**保留它但不要為它發明用途**。

#### 未預期的例外

把整個路由分派包在 `try` / `except Exception` 裡：回 `500` ＋
`{"error": "內部錯誤"}`（**固定字串，不要把例外訊息或 traceback 放進 body**），
並用 `traceback.print_exc()` 印到 stderr。理由：body 會進到瀏覽器，
stderr 只在使用者自己的終端機。

### B. `src/serve.py`

```
python3 src/serve.py [--live] [--port N] [--timeout-s N] [--max-chars N]
```

- 檔案開頭 docstring 要寫明：**本檔與 `cli.py` 是全 repo 僅有的兩個允許
  import adapters 的檔案。**
- `--live` 存在 ⇒ `ask_fn = make_ask_fn(ADAPTERS)`、`live = True`，
  並印一行警告說明「這個伺服器上的每一次開輪／仲裁都會消耗訂閱額度」；
  否則 `ask_fn = dry_run_ask_fn`、`live = False`，印一行說明現在是 dry run。
  🔴 **兩個值必須在同一個 `if` / `else` 裡一起決定**，不要分成兩段判斷
  （那會長出「顯示 dry run、實際卻在花錢」的可能）。
- `--port` 預設 `8765`。`--timeout-s`／`--max-chars` 預設沿用
  `orchestrator.DEFAULT_TIMEOUT_S` / `DEFAULT_MAX_CHARS`，比照 `cli.py` 的寫法。
- 建立伺服器後印出 `http://127.0.0.1:<實際埠>/`（從 `server_address[1]` 取），
  然後 `serve_forever()`。
- `KeyboardInterrupt` ⇒ 印一行「已停止；討論只在記憶體，已全部消失。」並正常結束
  （回傳 0）。⚠️ 那句話不是客套，是 `SPEC.md` §7.1 明訂的行為，使用者要知道。
- 🔴 **不要在這裡做 `detect()`**、不要做席次檢查。席次是瀏覽器建立討論時才給的，
  這裡拿不到；CLI 不存在時 `ask_fn` 會丟例外，`run_round()` 已經會把它記成
  「未回應」並繼續。**不要為此發明新的檢查路徑。**

---

## 測試（`tests/test_server.py`，新增）

比照既有測試檔開頭的寫法把 `src` 加進 `sys.path`。

🔴 **測試檔不得 import `adapters`、`subprocess`、`unittest.mock`。**
`ask_fn` 一律自己寫純 Python 假函式。可以 import
`json`、`threading`、`time`、`urllib.request`、`urllib.error`、`unittest`、`sys`、`pathlib`、
以及 `server`／`engine.state`／`engine.orchestrator`／`engine.sessions`。

建議的共用夾具（自己實作，細節可調整，但**必須用 `port=0`**）：

```python
def make_ask_fn(text="意見。\n[立場: 保留] [補充: 有]", usage=None, delay=0.0):
    """回傳一個純 Python 的假 ask_fn，計數自己被呼叫幾次。"""

class ServerCase(unittest.TestCase):
    def start(self, **kwargs):
        srv = server.build_server(ask_fn=..., live=False, port=0, **kwargs)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        self.addCleanup(srv.shutdown)
        self.addCleanup(srv.server_close)
        return srv, srv.server_address[1]
```

⚠️ **`port=0` 是硬性要求**：寫死 `8765` 會在使用者自己開著伺服器時整組測試爆掉，
而且測試之間會互搶。

### 要涵蓋的行為

**建立討論**

1. 合法 body ⇒ `200`，回應含 `id`／`question`／`seats`／`status`／`live`／`busy`，
   `busy` 為 `False`。
2. `seats` 的 `seat_id` 依序是 `<cli>-1`、`<cli>-2`…，仲裁者是 `arb`（比照 `cli.py`）。
3. 🔴 **回應中不得出現 `context` 這個鍵**，且 `context_chars` 等於送進去的字串長度。
4. body 多一個未知的鍵 ⇒ `400`。
5. `advisors` 是空 list ⇒ `400`；`question` 是空字串 ⇒ `400`；
   席次字串是 `":x"` 之類的壞值 ⇒ `400`。
6. body 不是合法 JSON ⇒ `400`。

**守門（`SPEC.md` §7.2）**

7. `Host` 標頭改成 `evil.example.com` ⇒ `403`（DNS rebinding）。
8. `Host` 是 `localhost:<port>` ⇒ 通過。
9. `Origin` 標頭是 `https://evil.example.com` ⇒ `403`；
   `Origin` 是 `http://127.0.0.1:<port>` ⇒ 通過；**完全不帶 `Origin`** ⇒ 通過。
10. POST 帶 `Content-Type: text/plain` ⇒ `415`。
11. 🔴 **任何一個回應都不得含以 `Access-Control-` 開頭的標頭**
    （檢查上面幾個回應的 headers）。
12. `Content-Length` 超過 5,000,000 ⇒ `413`。
    （⚠️ 不要真的送 5 MB，偽造一個過大的 `Content-Length` 標頭即可。）

**取狀態**

13. `GET` 已存在的 id ⇒ `200` ＋ 共用形狀。
14. `GET` 不存在的 id ⇒ `404`。未知路徑 ⇒ `404`。`GET /` ⇒ `404`。
15. 對 `/api/discussions/<id>` 送 `DELETE` ⇒ `405`。

**開一輪**

16. 對新討論 `POST .../rounds` ⇒ `200`，假 `ask_fn` 被呼叫的次數 **＝顧問數**，
    `status.rounds_completed` 變成 1。
17. 連續開兩輪 ⇒ 第二次也 `200`、`rounds_completed` 為 2
    （證明 `request_next_round()` 有被呼叫）。
18. 🔴 **開到 `max_rounds`（5）之後再開一輪 ⇒ `409` ＋ `code == "boundary"`；
    改送 `{"confirm_over_cap": true}` ⇒ `200`**（邊界 3）。
19. 🔴 **執行權互斥**：用一個會 `time.sleep(0.5)` 的假 `ask_fn`，開兩條執行緒
    同時 `POST .../rounds`，**恰好一個 `200`、一個 `409` ＋ `code == "busy"`**，
    且假 `ask_fn` 的呼叫次數**只有一輪的量**（不是兩倍）。
    ⚠️ 這條測的是 `SPEC.md` §7.1 那條「兩個分頁同時按會花兩倍的錢」。
20. 🔴 **失敗之後執行權要還回來**：先製造一次 `409 boundary`
    （例如在 `in_round` 以外的方式，或用第 18 條的上限情境），
    之後再送一次合法請求 ⇒ 拿得到執行權（不是永遠 `busy`）。
    ⚠️ 這條守的是 `finally` 有沒有寫對。
21. body 多一個未知的鍵 ⇒ `400`。

**仲裁**

22. 尚未跑過任何一輪就叫仲裁 ⇒ `409` ＋ `code == "boundary"`，
    且**假 `ask_fn` 一次都沒被呼叫**（`SPEC.md` §6.1：檢查必須擋在花錢之前）。
23. 跑過一輪之後叫仲裁 ⇒ `200`，`status.usage.calls` 比仲裁前多 1。
24. 仲裁**不影響輪次**：仲裁後 `status.rounds_completed` 不變，
    且之後還能再開一輪。

**SSE**

25. 先跑完一輪，再連上 `/events`（不帶游標）⇒ 依序收到
    `round_started`、N 個 `speech`、`round_finished`，
    `id:` 欄位是 1、2、3… 單調遞增。
26. 🔴 **多行發言不會破壞協定**：假 `ask_fn` 回傳含換行與 `:` 的文字
    （例如 `"第一行\n第二行: 有冒號\n[立場: 保留] [補充: 有]"`），
    連上 SSE 後把每則的 `data:` 行 `json.loads()` 回來，
    **內容與原文逐字相同**，且**每則事件恰好只有一行 `data:`**。
    ⚠️ 這條是本包最重要的測試之一，不要簡化成單行文字。
27. 帶 `?cursor=2` ⇒ 只收到 seq **大於** 2 的事件（不含 seq 2）。
28. 帶 `Last-Event-ID: 2` 標頭 ⇒ 效果同上；
    同時帶標頭與查詢字串時**以標頭為準**。
29. `?cursor=abc` ⇒ 當成 0，收到全部。
30. 🔴 **SSE 不佔執行權**：SSE 連線開著的同時 `POST .../rounds` ⇒ `200`（不是 `409`）。

**回呼（`orchestrator.on_record`）**

31. 直接呼叫 `orchestrator.run_round(..., on_record=f)`：`f` 被呼叫的次數＝顧問數，
    且每次拿到的是那一位的 record（`seat_id` 依序）。
32. 🔴 **`on_record` 丟例外不得中斷該輪**：傳一個必定 `raise` 的回呼，
    `run_round()` 仍然正常回傳、`rounds_completed` 為 1、相位是 `awaiting_user`。
33. 不傳 `on_record` 時行為與現在完全相同（既有測試已覆蓋，這裡補一條斷言即可）。

---

## 驗收條件（貼真實輸出，不要只描述）

1. `python3 -m unittest discover tests` **全過**，貼出最後三行。
   🔴 **既有 229 個測試一個都不得減少或變紅。**
   ⚠️ 工作包 011 那次回報「交付完成」但實跑是 `FAILED (errors=1)`。**自己實際跑完再回報。**
2. 說明新增了幾個測試（貼出數字怎麼算出來的）。
3. 貼出四條結構性紅線的 grep 結果：
   - `grep -nE '^(import|from)' src/server.py` ——不得出現 `adapters`、`subprocess`。
   - `grep -n '\.status()' src/server.py` ——**應為空**。
   - `grep -nE 'open\(|pathlib|Access-Control' src/server.py` ——**應為空**。
   - `grep -n 'try_claim' src/server.py` ——應**恰好兩處**（rounds 與 arbitration），
     且**不在** SSE 的處理函式裡（貼出前後文說明）。
4. 貼出 `grep -n '0\.0\.0\.0\|127\.0\.0\.1' src/server.py`，
   說明白名單寫在哪一行。
5. 貼出 `git diff --stat`，證明 `orchestrator.py`／`sessions.py`／`cli.py`
   的變更**都非常小**，並貼出這三個檔的完整 `git diff`。
6. **突變驗證六項**，每項：改壞 → 貼失敗輸出（**含翻紅的測試名**）→ 還原 →
   最後貼還原後全過的結果。
   - (a) `POST /rounds` 拿掉 `try_claim()`（直接往下跑）⇒ 測試 19 翻紅。
   - (b) 把 `finally: session.release()` 改成只在成功路徑 release ⇒ 測試 20 翻紅。
   - (c) 拿掉 `Host` 標頭檢查 ⇒ 測試 7 翻紅。
   - (d) 拿掉 `Content-Type` 檢查 ⇒ 測試 10 翻紅。
   - (e) SSE 的 `data:` 改成直接塞原始文字（不 `json.dumps`）⇒ 測試 26 翻紅。
   - (f) `build_server()` 拿掉 host 白名單 ⇒ 「`host="0.0.0.0"` 應丟 `ValueError`」
     那條翻紅（請一併寫這條測試）。
   - 🔴 **突變只准動 `src/server.py`**（(f) 同檔），不准動測試檔、不准動測試裡的樣本值。
   - 🔴 **每一項在動手前，先確認要取代的字串在檔案裡是唯一的**：
     印出 `text.find(old)` 與 `text.rfind(old)`，**兩個位置必須相同**才可以取代。
     ⚠️ 工作包 019 踩過：要改的六行在另一個函式裡字面完全相同，
     `replace(old, new, 1)` 打到的是另一側，畫面上是漂亮的一片紅、
     但**要驗的那一側完全沒被驗到**。翻紅之後也要看一眼**紅的是不是預期的那幾個測試名**。
   - 🔴 **備份放 `dispatch/tmp/022-backup/`，不要放 `/tmp`。**
     還原後用 `cmp` 確認與備份**位元組相同**，並貼出結果。
7. 貼出 `git status --short`，證明只有三個新檔（`?? src/server.py`、
   `?? src/serve.py`、`?? tests/test_server.py`）與三個 `M`
   （`orchestrator.py`、`sessions.py`、`cli.py`）。
   ⚠️ `dispatch/tmp/` 已被 `.gitignore` 排除，備份不會出現在這裡，這是正常的。
8. 🔴 **公開發布掃描**（本 repo 是 PUBLIC）：貼出
   `grep -rnE "$(whoami)|/home/[a-z]" src/server.py src/serve.py tests/test_server.py`
   ——**應為空**。不得寫入任何本機絕對路徑、使用者名稱、埠號以外的個人資訊。

---

## 不要做的事

- ⚠️ **不要寫任何 HTML／CSS／JS，不要提供靜態檔案，不要實作 `GET /`。** 那是 023。
- ⚠️ **不要引入任何第三方套件**（不要 Flask／FastAPI／aiohttp／sse-starlette）。
  `SPEC.md` §7：`http.server.ThreadingHTTPServer` ＋標準函式庫，無建置步驟。
- ⚠️ **不要用 `asyncio`。** 既有程式碼一律同步 ＋ `threading`。
- ⚠️ **不要落檔。** 不寫 JSON、不寫 log 檔、不做持久化（`SPEC.md` §7.1、§8）。
- ⚠️ **不要在 `server.py` 裡重寫任何停止邊界的判斷。** 邊界 1／3 在 `state.py`、
  仲裁前提在 `run_arbitration()`。server 只負責把 `BoundaryError` 翻成 `409`。
  在這裡寫第二份，就會出現兩份會各自過期的規則（工作包 019 已經有一處這種債，
  不要再增加）。
- **不要加使用者認證、token、密碼。** `SPEC.md` §7.1 的不可猜 id 就是憑證。
- **不要加 session 逾時清理、數量上限、事件數量上限、rate limit、
  執行緒數上限、gzip、HTTP/1.1 keep-alive。** 沒被要求。
- **不要覆寫 `log_message` 消音**，也不要另外加 `logging`。
- 不要碰版控（`git add` / `commit` / `push` 一律不執行）。
- 不要修改 `AGENTS.md`、`SPEC.md`、`dispatch.sh`、`run.sh`。
