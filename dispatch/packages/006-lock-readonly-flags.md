# 工作包 006：把唯讀保證鎖進測試

接續 005。**實作本身審過了，不要改 `src/` 的邏輯。** 本包只補測試。

---

## 為什麼要補

我對你交付的成果做了突變測試（故意改壞程式碼，看測試會不會失敗）。結果：

| 我做的破壞 | 測試反應 |
|---|---|
| `claude` 拿掉 `is_error` 檢查 | ✅ FAILED（抓到） |
| `gemini` 欄位改成 `respons` | ✅ FAILED（抓到） |
| `codex` 拿掉空檔檢查 | ✅ FAILED（抓到） |
| **`gemini` 唯讀旗標整組換成 `--yolo`** | ❌ **OK（沒抓到）** |
| **`codex` 拿掉 `--sandbox read-only`** | ❌ **OK（沒抓到）** |
| **`base.run()` 拿掉 `stdin=subprocess.DEVNULL`** | ❌ **OK（沒抓到）** |

前三項證明你的斷言是真的、不是恆真——這部分做得好。

問題在後三項：**`SPEC.md` §4.2 的唯讀是本專案的硬要求，卻沒有任何測試在守它。**
現在有人重構時把唯讀旗標刪掉，40 個測試會全過，沒有人會發現顧問變成可以動檔案。
`--yolo` 那一項尤其嚴重：它是「自動同意所有操作」，語意跟 plan 模式完全相反。

## 要補的測試

### 1. 三家的唯讀旗標與必要旗標（`tests/test_adapters_ask.py`）

沿用各 class 既有 `test_model_flag_presence` 的 argv 側錄手法，不要另造新機制。
每家新增一個測項，斷言實際送出的 argv **確實含有**下列旗標：

| adapter | 必須出現在 argv 的旗標 |
|---|---|
| `claude` | `--tools` 且其值為空字串 `""` |
| `codex` | `--sandbox` 且其值為 `read-only` |
| `gemini` | `--approval-mode` 且其值為 `plan`，以及 `--skip-trust` |

⚠️ **要斷言「旗標與它的值成對」**，不能只斷言字串有出現在 argv 裡。
例如 `--sandbox` 後面被改成 `danger-full-access` 時，測試必須失敗。

### 2. `base.run()` 一定關掉 stdin

`stdin=subprocess.DEVNULL` 是修掉「claude 卡住 176 秒」那個坑的關鍵，同樣沒被守住。

建議做法：在 `BaseRunTest` 內 patch `subprocess.run`，攔下呼叫參數，
斷言 `stdin` 這個 keyword argument 確實是 `subprocess.DEVNULL`。

這是白箱測試、直接驗實作細節，通常我不會這樣要求；此處刻意採用，理由是
行為式測法（讓假腳本去讀 stdin）在 stdin 沒被關掉時會**卡住整個測試**，
不穩定的測試比白箱測試更糟。你若想到既能穩定又是行為式的寫法，可以改用，
但**不得讓任何測試有卡住的可能**。

## 自我檢查（本包的驗收重點）

補完後，**自己重做一次突變測試**，逐項確認新測試真的會失敗：

1. 把 `gemini` 的 `"--approval-mode", "plan", "--skip-trust"` 換成 `"--yolo"` → 應 FAILED
2. 把 `codex` 的 `"--sandbox", "read-only"` 拿掉 → 應 FAILED
3. 把 `codex` 的 `read-only` 改成 `danger-full-access` → 應 FAILED
4. 把 `base.run()` 的 `stdin=subprocess.DEVNULL` 拿掉 → 應 FAILED
5. 每項驗完**務必把程式碼還原**，最後 `git diff --stat` 確認 `src/` 只剩你原本的改動

**貼出這五項的實際輸出。** 只說「補好了」不算交付；要看到它們真的會失敗。

## 界線

- **不要改 `src/` 的任何邏輯**（唯讀旗標現在是對的，別動它）
- 不改 `SPEC.md`、`AGENTS.md`、`dispatch.sh`、`tests/fixtures/`
- 不 `git add` / `git commit`
- 不引入第三方套件
