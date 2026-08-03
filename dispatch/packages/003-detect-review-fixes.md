# 工作包 003：002 的 review 修正

review 過了，`src/adapters/base.py` 與各 CLI 模組的實作**維持原樣、不要動**。
以下三項只改 `tests/test_adapters_detect.py`。

---

## 缺陷 1：假斷言（必修）

`test_detect_all_results_have_id` 裡有一行把同一個值拿來跟自己比對。
那個斷言恆真、驗不到任何東西，等於這個測試只做了一半。

改成真的有鑑別力的檢查：確認 `detect_all()` 回傳的 id 集合**確實對應 `ADAPTERS` 的鍵**，
順序也要一致（`SPEC.md` §4 的 `detect_all()` 明訂「依 ADAPTERS 順序」，目前沒有任何測試在保護這個保證）。

## 缺陷 2：測試依賴 shell 的 echo 行為（必修）

造假 CLI 的腳本用 `echo "...\n..."` 產生多行輸出。
**`echo` 對反斜線跳脫的處理各家 shell 不同**，這點我實測過：

- `dash`（本機 `/bin/sh`）會解讀 `\n`，輸出兩行 → 測試通過
- `bash` 不會解讀，輸出一行含字面 `\n` → 版本會變成 `v1.2.3  \nsecond line`，**測試失敗**

`SPEC.md` §8 說 v1 要支援 Linux 與 macOS，而 `/bin/sh` 指向哪個 shell 因系統而異，
所以這是真的可攜性缺陷，不是理論問題。

改用在各家 shell 行為一致的方式產生多行輸出。同時檢查其他假腳本有沒有同類依賴。

## 缺陷 3：單元測試呼叫真實 CLI（必修）

`RegistryTest` 直接呼叫 `detect_all()`，會真的去執行本機四個 CLI 的 `--version`。
雖然不消耗訂閱額度，但它讓單元測試變成環境相依、而且慢（整套跑 6.2 秒，大半耗在這裡）。

**這一項的責任在我**：工作包 002 一邊要求「不要在測試中呼叫真實 CLI」，
一邊又把「實跑 detect_all()」列為驗收條件，兩者矛盾，你的處理方式是合理的折衷。
現在把界線講清楚：

- **單元測試不得觸發任何真實子行程呼叫。** `RegistryTest` 要改成用假的 adapter
  替換 `ADAPTERS` 內容來驗證 `detect_all()` 的行為（測完要還原，不可污染其他測試）。
- 真實環境的 `detect_all()` 驗證屬於人工驗收，由主對話執行，**不放進測試套件**。

---

## 驗收條件

1. `python3 -m unittest discover tests -v` 全數通過，**貼出真實輸出**。
2. 整套測試**不再執行任何真實 CLI**。請說明你如何確認這一點（例如指出已無任何路徑會呼叫真實 adapter）。
3. 測試總耗時應明顯低於先前的 6.2 秒，貼出實際耗時。
4. 不修改 `src/` 下任何檔案、不修改 `SPEC.md`、`AGENTS.md`、`dispatch.sh`、`README.md`。
5. 不要 `git add` / `git commit`。

沒實際跑過的不要說它會動；沒驗證的部分標「未驗證」。
