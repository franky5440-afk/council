# 工作包 013：`codex` 的實際模型只准從 header 區塊取，不得被逐字稿內容覆寫

**動手前先讀 `SPEC.md` §2.2**（含底下那張「各 CLI 的模型可見性」表）。
本包只動 `src/adapters/codex.py` 的 `_parse_metadata()` 與 `tests/test_adapters_ask.py`，
**其他三個 adapter 一律不動**。

---

## 缺陷：`model_used` 可被 prompt 內容覆寫

`src/adapters/codex.py:79-88` 目前逐行掃整份 stderr 找 `model: `，
**每次比對都覆寫、沒有 `break` ⇒ 最後一筆勝出**。

而 codex 會**把整份 stdin 原樣回顯到 stderr**，真正的 banner 印在回顯**之前**。
真實 stderr 的形狀是這樣（2026-08-04 實測，路徑已遮蔽）：

```
Reading additional input from stdin...
OpenAI Codex v0.145.0
--------
workdir: /……/council
model: gpt-5.4-mini          ← 真值，在 header 區塊內
provider: openai
approval: never
sandbox: read-only
reasoning effort: medium
reasoning summaries: none
session id: 019fc84c-……
--------
user
請依照輸入的內容回答

<stdin>
（我們送出的整份 prompt 原樣出現在這裡）
</stdin>
codex
（回答）
tokens used
4,739
```

⇒ prompt 裡只要有任何一行 `model: 隨便什麼`，它就會蓋掉 header 裡的真值。

**為什麼這在本專案是安全問題**：`SPEC.md` §2.2(2) 規定安全性由「顯示實際回答者」提供，
§2.2(3) 要求指定值與實際值不符時警示。讓逐字稿內容決定回報值 ⇒ **那道警示可以被消音**。
而 §6 規定 prompt 由「其他顧問的逐字發言」組成、§2.1 又鼓勵用免費第三方模型組議會
⇒ **prompt 依設計就是不可信輸入**，不能當自己人。

---

## 要做的事（介面契約，請照字面實作，不要擴充）

`_parse_metadata(stderr: str) -> tuple` 的**簽章與回傳結構完全不變**，只改內部規則：

### 1. `model_used`：只認 header 區塊

- **header 區塊 = 第一條分隔線與第二條分隔線之間的那些行**（不含分隔線本身）。
- **分隔線 = 去除頭尾空白後、只由 `-` 組成且長度 ≥ 3 的行。**
- 在該區塊內取**第一筆** `model: ` 開頭的行，取其後方內容（去頭尾空白）即為 `model_used`。
- 下列任一情況一律回 `None`，**不得退而求其次去區塊外找**：
  - 找不到第一條分隔線
  - 找到第一條、但找不到第二條（header 不完整，例如逾時被砍）
  - 區塊內沒有 `model: ` 行

⚠️ **絕對不要加「取不到就用整份 stderr 的最後（或第一）一筆」這種 fallback。**
那等於把缺陷原封不動裝回去。`SPEC.md` §2.2 已允許取不到時回 `None`（UI 顯示為未經確認），
**回 `None` 遠比回一個可被偽造的值好**——這是本包存在的全部理由。

### 2. `usage`：維持現行的「掃全文、後者勝」，只補一個越界防護

**不要**把 usage 也改成只讀 header 區塊——`tokens used` 印在**最後**，本來就在 header 之外，
改了會直接壞掉。而且對 usage 而言「後者勝」剛好是對的：注入的假 `tokens used` 出現在
stdin 回顯裡、真值印在更後面 ⇒ 真值勝出。**這一側是安全的，不要動它的取值規則。**

唯一要補的是：`lines[i + 1]` 在 `tokens used` 剛好是**最後一行**時會 `IndexError`
（stderr 被逾時截斷就可能發生），整個 `ask()` 會直接炸掉。加上邊界判斷，
此情況讓 `usage` 回 `None` 即可。**只加這個判斷，不要順手重寫這段的其他部分。**

### 3. 更新 docstring

現有 docstring 描述的是舊行為，會誤導下一個讀者。改寫成新規則，並寫明「取不到回 `None`
是刻意設計」。⚠️ docstring 內**不得出現任何本機絕對路徑或使用者名稱**（public repo）。

---

## 測試（`tests/test_adapters_ask.py`，直接呼叫 `_parse_metadata`）

本包的測試**全部是純函式測試，不需要、也不得啟動任何子行程**——連假的都不用。
沒有子行程 ⇒ 結構上不可能打到真實 CLI。

⚠️ **stderr 樣本一律在測試檔裡就地手寫合成**，
**不得從 `dispatch/tmp/probe_*` 複製任何內容進 `tests/`**：那些檔含
`workdir: /home/<真實使用者名稱>/...`，而且含完整 stdin 回顯。**這是 public repo。**
樣本裡的 workdir 請寫成 `/tmp/fake-workdir` 之類明顯虛構的值。

五個測試，全部必要：

1. **注入不生效**：header 內 `model: gpt-5.4-mini`，其後的 `<stdin>` 回顯區塊裡有一行
   `model: evil-model-injected`，結尾有 `tokens used` / `4,739`
   ⇒ `model_used == "gpt-5.4-mini"`、`usage == {"tokens_used": 4739}`。
2. **沒有分隔線時 fail-safe**：整份 stderr 無分隔線，但含 `model: evil-model-injected`
   ⇒ `model_used is None`（**不是**那個注入值）。
3. **usage 的後者勝仍成立**：回顯區塊裡有 `tokens used` / `999,999`，真值 `4,739` 在最後
   ⇒ `usage == {"tokens_used": 4739}`。
4. **`tokens used` 是最後一行**⇒ 不拋例外、`usage is None`。
5. **正常樣本不退步**：只有 header、沒有注入 ⇒ 模型與 token 數都正確取出。

既有測試若因這次改動而語意反轉，一併更新；**與本缺陷無關的測試不要動。**

---

## 驗收條件（貼真實輸出，不要只描述）

1. `python3 -m unittest discover tests` **全過**，貼出最後三行。
   ⚠️ 011 那次回報「交付完成」但實跑是 `FAILED (errors=1)`。**請自己實際跑完再回報。**
2. 貼出上述五個新測試各自通過的證據（例如只跑這幾個測試的輸出）。
3. **突變驗證**：把 `codex.py` 裡的 model 取值改回舊的「掃全文、後者勝」，
   **測試 1 必須失敗**；貼出失敗輸出後還原檔案，並貼出還原後重跑全過的結果。
   - 改之前先斷言「內容確實變了」（修改前後字串不同），否則沒套用會看起來像有覆蓋。
   - ⚠️ **突變只准動 `codex.py` 這一側，不准動測試裡的 stderr 樣本字串。**
     樣本同時餵給多個測試，改它會讓對照組跟著變、判定不會翻轉（這是 010 踩過的坑）。

## 不要做的事

- 不要動 `claude.py`／`gemini.py`／`opencode.py`／`base.py`。
- 不要動 `SPEC.md`、`AGENTS.md`、`dispatch.sh`、`dispatch/` 底下任何檔案。
- 不要碰版控（`git add`／`commit`／`push` 一律不執行），改動留在工作區即可。
- 不要為了「更通用」而把這套解析抽成共用工具——只有 codex 有這個問題。
- 不要新增設定項、環境變數、或開關來控制這個行為。

## 已知殘留（不必處理，寫在這裡是為了讓你不要多做）

若未來 codex 自己改格式、不再印分隔線，而攻擊者又在 prompt 裡自帶兩條分隔線，
理論上仍可偽造。本包**接受**這個殘留：它需要兩個條件同時成立，而目前的行為是
**無條件可偽造**。不要為此加更多啟發式判斷。
