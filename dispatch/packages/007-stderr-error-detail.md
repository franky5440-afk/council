# 工作包 007：`base.run()` 的錯誤訊息取錯行

接續 006。範圍**只有 `base.run()` 的錯誤字串組法**與其測試，其他一律不動。

---

## 問題（實機驗證時抓到的）

`base.run()` 目前這樣組錯誤訊息：

```python
detail = ": " + stderr.splitlines()[0].strip()
```

它取 **stderr 的第一行**。但 CLI 常在真正的錯誤之前先印無害的警告，
於是使用者拿到的「失敗原因」是錯的那一行。

實測（真實呼叫 `gemini`，該次因上游 503 而失敗）回傳的是：

```
command exited with code 1: Ripgrep is not available. Falling back to GrepTool.
```

而 `Ripgrep is not available` 只是一句無關的警告，真正的錯誤在後面幾行。
使用者會照著這句話去查 ripgrep，方向完全錯誤。

`SPEC.md` §4.1 要求「`ask()` 失敗時回傳可讀的錯誤，而不是讓使用者看到一坨 stderr」。
**回報錯誤的那一行，比整坨 stderr 更糟**——它看起來很確定，但是錯的。

## 要改成什麼

從 stderr 挑出最可能是真正錯誤的那一行，規則如下（依序）：

1. 丟掉堆疊追蹤行：以空白開頭、且去掉開頭空白後以 `at ` 起始的行
   （例如 `    at throwErrorIfNotOK (file:///...)`）
2. 丟掉空白行
3. 取**剩下的最後一行**（真正的錯誤通常在警告之後，所以是最後、不是最前）
4. 該行超過 **300 字元**就截到 300 並在結尾加上 `…`
   （stderr 可能夾帶整包 JSON，不設上限會把錯誤訊息撐爆）
5. 過濾完沒有任何行可用 → 就不附 detail，只回
   `command exited with code N`（維持現行行為）

`detect()` 裡也有一段一樣的 `splitlines()[0]` 寫法，**一併改用同一套規則**，
不要複製兩份邏輯——抽一個模組層級的小函式給兩邊共用即可。

## 測試

在 `tests/test_adapters_ask.py` 的 `BaseRunTest` 內補，用既有的假腳本手法
（`printf` 寫進 stderr、以非零碼退出）。至少涵蓋：

- 警告在前、真正錯誤在後 → 錯誤訊息含**後面那行**，且**不含**前面的警告
- stderr 尾端有堆疊追蹤行 → 那些 `at ...` 行被略過，取到的是堆疊之前的錯誤行
- 單行超過 300 字元 → 被截斷且結尾為 `…`
- stderr 全空 → 訊息為 `command exited with code N`，後面不接冒號

⚠️ 用**真實形狀**當素材：`gemini` 那次失敗的 stderr 長這樣（節錄，可直接拿來當測試素材）

```
Ripgrep is not available. Falling back to GrepTool.
Attempt 1 failed with status 503. Retrying with backoff... _ApiError: {"error":{"code":503}}
    at throwErrorIfNotOK (file:///usr/local/lib/node_modules/@google/gemini-cli/bundle/chunk.js:267191:24)
    at process.processTicksAndRejections (node:internal/process/task_queues:104:5)
```

這段的期望結果是取到 `Attempt 1 failed with status 503...` 那行。

## 自我檢查

補完後自己做突變測試並貼出實際輸出：把挑選規則改回 `splitlines()[0]`，
上述第一項測試**必須** FAILED。驗完還原，並以 `git diff --stat` 確認沒有殘留。

## 界線

- 不改三家 adapter 的解析邏輯、不改唯讀旗標
- 不改 `SPEC.md`、`AGENTS.md`、`dispatch.sh`、`tests/fixtures/`
- 不 `git add` / `git commit`
- 不引入第三方套件
