# 工作包 026：讓靜態頁拒絕被內嵌（`SPEC.md` §7.2 第 5 道）

**先讀 `SPEC.md` §7.2**（剛更新，多了第 5 道、並修正了第 3 道的措辭）。

024／025 讓伺服器**第一次回傳 HTML**。§7.2 原本的四道守門防的都是「跨來源 `fetch()`」，
但**內嵌 iframe 繞過的是整組、不是其中任一道**：被框住的頁面自己發出的請求，
`Host` 正確、`Origin` 同源、`Content-Type` 由頁面自己設、同源不需要 CORS 標頭
——四道全部通過。SPEC 已補上第 5 道，本包實作它。

⚠️ **這是一個很小的包**：兩行標頭、一條測試、一個 docstring 修正。
**不要順手改別的東西。**

---

## 檔案

| 檔案 | 動作 |
|---|---|
| `src/server.py` | **修改**：`_get_index()` 加兩行標頭；`_gate()` 的 docstring 修一句 |
| `tests/test_ui.py` | **修改**：加一條測試 |

🔴 **除了上表，一個字都不要動。** 特別是 `src/ui.py`、`src/static/index.html`、
`src/engine/` 底下所有檔案、`src/serve.py`、`src/cli.py`、`tests/test_server.py`、
`SPEC.md`、`AGENTS.md`、`run.sh`、`dispatch.sh`。

---

## 介面契約（照字面實作）

### A. `src/server.py` — `_get_index()` 加兩行標頭

在既有的 `Cache-Control` 那行**之後**、`self.end_headers()` **之前**，加這兩行：

```python
        # SPEC.md §7.2 第 5 道：前四道防的是跨來源 fetch()，內嵌 iframe 繞過的
        # 是整組——被框住的頁面自己發的請求，四道全部通過。frame-ancestors 只在
        # 回應標頭有效，寫在頁面的 <meta> 裡瀏覽器不認。
        self.send_header("Content-Security-Policy", "frame-ancestors 'none'")
        self.send_header("X-Frame-Options", "DENY")
```

- 🔴 **兩個標頭都要**，不是二選一。`frame-ancestors` 是現行標準，
  `X-Frame-Options` 是給不支援它的舊瀏覽器；兩者的值都寫死，不接受任何參數。
- 🔴 **只加在 `_get_index()`**。**不要**加進 `_reply_json()`、`_reply_error()`
  或 SSE 的回應——那些不是可點擊的畫面，加了只是雜訊。
- 🔴 **`Content-Security-Policy` 這個回應標頭的值就只有 `frame-ancestors 'none'`。**
  不要把 `index.html` 裡 `<meta>` 的那串 CSP 抄過來、不要合併、不要加其他指示詞。
  那兩者管的是不同的事，混在一起會讓將來改動任一邊時弄不清楚哪個在生效。
- ⚠️ **不要加 `X-Content-Type-Options`／`Referrer-Policy`／`Permissions-Policy`
  或任何其他標頭。** 沒被要求。

### B. `src/server.py` — `_gate()` 的 docstring

現在是：

```python
        """SPEC.md §7.2 的四道請求守門，順序即規格順序。"""
```

§7.2 現在有五道，而這個函式只做請求層的那幾道（第 5 道是回應標頭、不在這裡）。
改成：

```python
        """SPEC.md §7.2 的請求守門（第 1～3 道），順序即規格順序。"""
```

🔴 **`_gate()` 的程式邏輯一行都不准動。**

### C. `tests/test_ui.py` — 加一條測試

放在 `test_index_no_access_control_headers` 旁邊，比照它的寫法：

```python
    def test_index_refuses_to_be_framed(self):
        """SPEC.md §7.2 第 5 道：內嵌 iframe 會讓前四道全部通過（Host 正確、
        Origin 同源、Content-Type 由頁面自己設、同源不需要 CORS），所以拒絕被
        內嵌必須靠回應標頭。frame-ancestors 寫在 <meta> 裡無效。"""
```

斷言 `GET /` 的回應：

1. `X-Frame-Options` 標頭等於 `DENY`。
2. `Content-Security-Policy` 標頭等於 `frame-ancestors 'none'`。

⚠️ 標頭名稱比對要不分大小寫（既有的 `test_index_no_access_control_headers`
已經用 `.lower()`，比照它）。

---

## 驗收條件（貼真實輸出，不要只描述）

1. `python3 -m unittest discover tests` **全過**，貼出最後三行。
   🔴 **既有 289 個測試一個都不得變紅**，新的總數應為 290。
   ⚠️ 工作包 011 曾回報「交付完成」而實跑是 `FAILED (errors=1)`。**自己實際跑完再回報。**
2. 貼出 `src/server.py` 與 `tests/test_ui.py` 的**完整 `git diff`**
   （`test_ui.py` 目前已被追蹤，diff 看得到）。變更應該非常小。
3. 貼出 022／024 的紅線仍然成立：
   - `grep -nE 'open\(|pathlib|Access-Control' src/server.py` ——**應為空**。
     ⚠️ 這一條特別要看：本包加的是 `Content-Security-Policy` 與 `X-Frame-Options`，
     **都不是 `Access-Control-*`**。如果這個 grep 有輸出，代表你加錯標頭了。
   - `grep -n '\.status()' src/server.py` ——**應為空**。
   - `grep -n 'try_claim' src/server.py` ——仍**恰好兩處**。
4. **實機驗一次（🔴 全程 dry run，不得加 `--live`）**，貼出真實輸出：
   ```bash
   python3 -u src/serve.py --port 0 > dispatch/tmp/026-serve.log 2>&1 &
   # 從 log 取得埠號後：
   curl -s -D - -o /dev/null http://127.0.0.1:<port>/
   ```
   ⚠️ **`python3` 要加 `-u`**：stdout 重導向到檔案時是區塊緩衝，不加會讀不到埠號
   （我自己踩過這個坑）。
   貼出完整的回應標頭，確認兩個新標頭都在、且**沒有**任何 `Access-Control-*`。
   驗完把行程收掉，貼出收掉的指令。
5. **突變驗證兩項**，每項：改壞 → 貼失敗輸出（**含翻紅的測試名**）→ 還原 →
   最後貼還原後全過的結果。
   - (a) 拿掉 `X-Frame-Options` 那一行 ⇒ 新測試翻紅。
   - (b) 把 `Content-Security-Policy` 的值改成 `frame-ancestors 'self'` ⇒ 新測試翻紅。
   - 🔴 **突變只准動 `src/server.py`**，不准動測試檔、不准動測試裡的樣本值。
   - 🔴 **每一項動手前先確認要取代的字串在檔案裡是唯一的**：印出 `text.find(old)`
     與 `text.rfind(old)`，**兩個位置必須相同**才可以取代。翻紅之後也要看一眼
     **紅的是不是預期的那個測試名**。
   - 🔴 **備份放 `dispatch/tmp/026-backup/`，不要放 `/tmp`。**
     還原後用 `cmp` 確認與備份**位元組相同**，並貼出結果。
6. 貼出 `git status --short`。
7. 🔴 **公開發布掃描**（本 repo 是 PUBLIC）：貼出
   `grep -rnE "$(whoami)|/home/[a-z]" src/server.py tests/test_ui.py` ——**應為空**。

---

## 不要做的事

- 🔴 **全程不得執行 `--live`，不得呼叫任何真實 CLI。**
- ⚠️ **不要動 `src/static/index.html`。** 特別是**不要**把 `frame-ancestors`
  加進頁面裡那個 `<meta>` CSP——瀏覽器不認 meta 來的這個指示詞，加了會製造
  「看起來有防護」的假象，比沒加更糟。
- ⚠️ **不要在其他回應（JSON／SSE／錯誤）上加這兩個標頭。**
- ⚠️ **不要新增任何其他安全標頭。**
- ⚠️ **不要改 `_gate()` 的邏輯**，只改它的 docstring。
- 不要引入第三方套件、框架、建置步驟。
- 不要落檔、不要加 logging、不要覆寫 `log_message`。
- 不要碰版控（`git add` / `commit` / `push` 一律不執行）。
