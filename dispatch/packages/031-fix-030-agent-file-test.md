# 工作包 031：030 的裁示——把那條翻紅的既有測試改成斷言「寫出去的就是 `AGENT_DEF`」

你在 030 開了 `dispatch/BLOCKED.md`，**停手是對的**，回報也精確：
`test_agent_file_created_with_deny` 斷言 `bash: deny`／`edit: deny`，
而新的 `AGENT_DEF` 依 `SPEC.md` §4.2 換成萬用字元寫法後這兩行必然消失。
你的三個解讀我看過了，**採用解讀 1 的方向，但不用你提的寫法**。

- 你提的是把兩行斷言換成新方案的兩行（`"*": deny`／`websearch: allow`）。
  這樣可以動，但**期望值會有兩份**：那兩行在你新增的
  `OpenCodeAgentPermissionTest` 裡已經守著了，再寫一次，將來改規格就要記得改兩個地方。
- 這條既有測試真正的職責是**「`ask()` 有沒有把 agent 定義寫進 `--dir` 指向的目錄」**
  （它用假執行檔把檔案複製出來比對），**不是**「權限清單長什麼樣」。
  ⇒ 斷言改成「複製出來的內容**就等於** `opencode.AGENT_DEF`」，職責回歸單一，
  而且將來規格再變時這條不用跟著改。

🔴 **這個期望值主對話已經親手跑過一次確認會過**（暫時改寫、單跑該條測試、再還原）。
不是推測。

⚠️ **工作區現況**：030 的三個檔改動都在（`opencode.py`、`README.md`、
`tests/test_adapters_ask.py` 的五條新測試都在工作區裡）。全套跑起來是
**319 條、1 條紅**，紅的就是下面要修的那條。**不要重做 030 的內容。**

---

## 檔案

| 檔案 | 動作 |
|---|---|
| `tests/test_adapters_ask.py` | **修改**：只動 `test_agent_file_created_with_deny` 這一個方法 |

🔴 **除了上表，一個字都不要動。** 特別是 `src/adapters/opencode.py`（030 已經改好了、
不要再動）、`README.md`、`SPEC.md`、你自己新增的 `OpenCodeAgentPermissionTest`。

---

## 介面契約（照字面實作）

`tests/test_adapters_ask.py` 目前是：

```python
    def test_agent_file_created_with_deny(self):
```

改成（**方法名要換**，因為它已經不是在驗 deny 清單）：

```python
    def test_agent_file_written_matches_agent_def(self):
        """驗證 ask() 真的把 agent 定義寫進 --dir 指向的目錄。

        這條的職責是「檔案有沒有被寫出去、內容是不是那一份」，不是「權限清單
        長什麼樣」——後者由 OpenCodeAgentPermissionTest 直接斷言 AGENT_DEF 守著。
        期望值寫成 AGENT_DEF 本身，規格再變時這條不必跟著改（SPEC.md §4.2）。
        """
```

方法本體**其他每一行都不動**，只把最後那兩行：

```python
            self.assertIn("bash: deny", content)
            self.assertIn("edit: deny", content)
```

換成一行：

```python
            self.assertEqual(content, opencode.AGENT_DEF)
```

- 🔴 **`self.assertTrue(result["ok"])` 與 `content = copy.read_text()` 兩行保留**。
- 🔴 **不要動假執行檔那段 shell**（它是這條測試的機制，改了就不是在驗同一件事）。
- ⚠️ 測試總數不變，仍是 **319**。

---

## 驗收條件（貼真實輸出，不要只描述）

1. `python3 -m unittest discover tests` **全過**，貼出最後三行。
   🔴 **319 條全過，0 紅。**
2. 貼出 `tests/test_adapters_ask.py` 的**完整 `git diff`**
   （會包含 030 新增的五條測試，那是預期的）。
3. **補完 030 沒做完的突變驗證三項**，每項：改壞 → 貼失敗輸出（**含翻紅的測試名**）
   → 還原 → 最後貼還原後全過的結果。
   - (a) 把 `websearch: allow` 改成 `webfetch: allow`
     ⇒ `test_no_other_tool_is_allowed` 與 `test_webfetch_never_allowed` 應翻紅。
   - (b) 在 `websearch: allow` 之後多加一行 `read: allow`
     ⇒ `test_no_other_tool_is_allowed` 應翻紅。
   - (c) 把 `"*": deny` 整行刪掉 ⇒ `test_wildcard_deny_present` 與
     `test_websearch_allowed_after_wildcard` 應翻紅。
   - 🔴 **注意 (a) 與 (c) 也會讓上面那條剛改好的測試翻紅**（寫出去的檔案內容仍然
     等於 `AGENT_DEF`，所以其實不會——**照做並如實回報實際翻紅的是哪幾條**，
     不要事先假設）。
   - 🔴 **突變只准動 `src/adapters/opencode.py`**，不准動測試檔。
   - 🔴 **動手前先確認要取代的字串在檔案裡唯一**：印出 `text.find(old)` 與
     `text.rfind(old)`，位置相同才可取代。
   - 🔴 **備份放 `dispatch/tmp/031-backup/`，不要放 `/tmp`。**
     還原後用 `cmp` 確認位元組相同並貼出。
4. 貼出 `grep -n 'allow' src/adapters/opencode.py`。
5. 貼出 `git status --short`。
6. 🔴 **公開發布掃描**：
   `grep -rnE "$(whoami)|/home/[a-z]" src/adapters/opencode.py tests/test_adapters_ask.py README.md`
   ——**應為空**。
7. 🔴 **刪掉 `dispatch/BLOCKED.md`**（那一輪的卡關已經裁示完畢）。

---

## 不要做的事

- 🔴 **全程不得執行 `--live`、不得呼叫任何真實 CLI、不得執行 `opencode` 指令。**
  ⚠️ Frank 有一個 `--live` 伺服器在 8765 埠上跑，**不准對它送請求、不准 kill 任何行程**。
- 🔴 **不要再動 `AGENT_DEF`**（030 已經照 SPEC §4.2 改好，主對話已驗過）。
- 🔴 **不要為了讓突變翻紅去改測試。**
- 不要碰版控（`git add` / `commit` / `push` 一律不執行）。
