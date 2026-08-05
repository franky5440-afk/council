# 工作包 023：修正 022 的守門缺口（Content-Type 檢查漏掉空 body 的 POST）

**這是工作包 022 的修正包，續同一個 session。** 022 的其他部分審查全過
（264 測試全過、六項突變全部翻紅、紅線稽核乾淨），**只有一處要改**。

⚠️ **本包只准動兩個檔：`src/server.py`（一行）與 `tests/test_server.py`（加一條測試）。**
其他一個字都不要動。

---

## 問題

`src/server.py` 的 `_gate()` 目前把 `Content-Type` 檢查綁在「有 body」的條件下：

```python
        if content_length > 0:
            content_type = self.headers.get("Content-Type", "")
            if not content_type.startswith("application/json"):
```

⇒ **body 為空的 POST 完全跳過這道檢查**。實測（主對話的獨立探測）：

```
無 Content-Type 的 POST /api/discussions/<id>/rounds  ⇒ 200，假 ask_fn 被呼叫 2 次
Content-Type: text/plain 的空 body POST              ⇒ 200，假 ask_fn 被呼叫 2 次
```

也就是**真的跑了一輪、真的會花訂閱額度**。

為什麼要緊：`SPEC.md` §7.2 第 3 道的唯一目的是**逼出 CORS preflight**。
而 `/rounds` 與 `/arbitration` **本來就接受空 body** ⇒ 惡意網頁的
`fetch(url, {method: 'POST'})` 是一個不需要 preflight 的 simple request，
這道防線對兩個最花錢的端點等於不存在。

⚠️ 目前還擋得住，因為第 2 道（`Origin`）會攔下瀏覽器的跨來源請求。
但 §7.2 明寫「這四道是**互相支撐的一組**，拿掉任何一道，另外三道各自都有繞過的方法」。

⚠️ **這不是你的失分。** 022 的工作包寫的是「**有 body 的請求**，`Content-Type` 必須是
`application/json`」，你照字面實作完全正確——是那個限定詞寫錯了。

---

## 改法（只有一行）

`src/server.py` 的 `_gate()` 裡：

```python
-        if content_length > 0:
+        if self.command == "POST":
             content_type = self.headers.get("Content-Type", "")
             if not content_type.startswith("application/json"):
```

- 語意變成：**所有 POST 一律要求 `application/json`，與 body 長短無關。**
  `GET` 與 `DELETE` 不受影響（它們本來就沒有 body）。
- ⚠️ **只改這一行的條件。** 該 `if` 區塊內部、以及 `Content-Length` 的解析、
  `-1`／`> MAX_CONTENT_LENGTH` 的兩個檢查，**一律維持原樣**。
- 順手在該行上方加一行註解，寫明**為什麼是 `command == "POST"` 而不是「有 body」**：
  兩個花錢的端點都接受空 body，綁在 body 長度上等於讓 simple request 繞過 preflight
  （`SPEC.md` §7.2）。

---

## 要加的測試（`tests/test_server.py`）

現況的問題不只是那一行——**套用修正後 264 個測試照樣全過**，
代表**沒有任何測試守住這個行為**。所以修正必須連同回歸防護一起交付。

新增**一條**測試（名稱自訂，建議 `test_post_without_content_type_415`），
內容至少要斷言下面三件事：

1. 對 `/api/discussions/<id>/rounds` 送一個 **`Content-Length: 0`、
   完全不帶 `Content-Type`** 的 POST ⇒ 狀態碼 **415**。
2. 同一個請求改帶 `Content-Type: text/plain`、body 仍為空 ⇒ 也是 **415**。
3. 🔴 **假 `ask_fn` 的呼叫次數在這兩次請求前後完全沒有增加**
   （光看狀態碼不夠——這條測的是「錢沒有被花掉」，那才是這道守門存在的理由）。

⚠️ **`urllib.request` 會自動補上 `Content-Type`**，用它測不出這個情境。
請改用 `http.client.HTTPConnection`，自己控制標頭：

```python
conn = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
conn.request("POST", f"/api/discussions/{sid}/rounds", body="", headers={})
resp = conn.getresponse()
```

（測試檔可以新增 `import http.client`。其餘禁用 import 的規定不變：
不得 import `adapters`、`subprocess`、`unittest.mock`。）

---

## 驗收條件（貼真實輸出，不要只描述）

1. 貼出 `git diff src/server.py` ——**應該恰好是一行的變更**（加上那行註解）。
2. `python3 -m unittest discover tests` **全過**，貼出最後三行。
   既有 264 個測試不得減少或變紅，新增後應為 **265**。
3. **突變驗證一項**：把那個條件改回 `if content_length > 0:` ⇒
   **新增的那條測試必須翻紅**（貼出翻紅的測試名）→ 還原 → 貼出還原後全過的結果。
   - 🔴 動手前先確認要取代的字串在檔案裡唯一：印出 `text.find(old)` 與
     `text.rfind(old)`，**兩個位置必須相同**才可以取代。
   - 🔴 **備份放 `dispatch/tmp/023-backup/`，不要放 `/tmp`。**
     還原後用 `cmp` 確認與備份**位元組相同**，並貼出結果。
4. 貼出 `git status --short`，證明只有 `src/server.py` 與 `tests/test_server.py`
   兩個 ` M`（`src/serve.py`、`src/server.py`、`tests/test_server.py` 仍是 `??`
   也算正常——它們尚未進版控）。

---

## 不要做的事

- ⚠️ **不要動 `Origin`／`Host`／`Content-Length` 那三道檢查。** 它們已經審查通過。
- ⚠️ **不要動 `src/serve.py`、`src/engine/` 底下任何檔案、`src/cli.py`。**
- ⚠️ **不要順手處理 `EVENT_KINDS` 沒被用到、或測試輸出有請求日誌這兩件事。**
  它們已經被記錄下來，但**不在本包範圍**。
- ⚠️ **不要重構 `_gate()`**、不要把四道檢查抽成函式、不要調整順序。
- 不要碰版控（`git add` / `commit` / `push` 一律不執行）。
- 不要修改 `AGENTS.md`、`SPEC.md`、`dispatch.sh`、`run.sh`。
