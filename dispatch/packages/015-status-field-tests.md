# 工作包 015：補上 `status()` 三個沒被守住的欄位的測試

**這是 014 的續包，接續同一個 session。** 014 的實作我審過，**沒有錯、不要改它**。
本包只加測試。

## 為什麼要加

我對 `src/engine/state.py` 做了三個突變，測試**照樣全過**——代表這三個欄位目前沒有
任何回歸防護：

| 突變 | 結果 |
|---|---|
| `"format_violations": …` 改成 `0` | 119 測試全過 |
| `"can_start_round": …` 改成 `False` | 119 測試全過 |
| `status()` 裡 `"converged": self.converged()` 改成 `False` | 119 測試全過 |

`format_violations` 是 `SPEC.md` §5 邊界 5 明文要求記錄的數字，`can_start_round` 與
`converged` 是 UI 判斷「現在能不能開下一輪／要不要提示收斂」的依據。沒測試等於下一個
改到 `status()` 的人可以無聲弄壞它們。

## 要做的事

只動 `tests/test_engine_state.py`，加三個測試（可放進既有的測試類別，或新增一個類別）：

1. **`format_violations` 會累計、且跨輪累加**：
   讓一位顧問的回覆**沒有**結尾標記（⇒ violation）、另一位有正常標記，`end_round()` 後
   `status()["format_violations"] == 1`。再跑一輪、再製造一次違規 ⇒ 變成 `2`。
   同時斷言**逾時（`ok=False`）不計入**：一輪裡放一筆 `ok=False`，該輪的違規數不因它增加。
2. **`can_start_round` 隨 phase 改變**：初始為 `True`；`begin_round()` 後為 `False`；
   `end_round()` 後（awaiting_user）為 `False`；`request_next_round()` 後回到 `True`。
3. **`status()["converged"]` 與 `converged()` 一致**：至少涵蓋「全體補充: 無 ⇒ 皆為 True」
   與「有人補充: 有 ⇒ 皆為 False」兩種情形。

## 驗收條件（貼真實輸出）

1. `python3 -m unittest discover tests` 全過，貼最後三行；測試總數應為 119 + 新增數。
2. **突變驗證三項**，就是上表那三個改動，**每一項都必須讓你新加的測試翻紅**：
   改壞 → 貼失敗輸出 → 還原 → 最後貼還原後全過。
   - 改之前先斷言檔案內容確實變了，否則沒套用會看起來像有覆蓋。
   - ⚠️ **突變只准動 `src/engine/state.py`，改完務必還原**——本包最終不得留下任何
     對 `state.py` 的修改。收尾請貼 `git status --short`，應只顯示
     `tests/test_engine_state.py` 被修改。

## 不要做的事

- **不要改 `src/engine/state.py` 的任何一行**（突變驗證除外，且必須還原）。
- 不要動既有的 36 個測試，除非它們因你的新增而重複；重複就留著，不要刪。
- 不要新增第二個測試檔。
- 不要碰版控、不要動 `SPEC.md`／`AGENTS.md`／`dispatch/` 底下任何檔案。
