# 工作包 030：顧問的工具權限改成「全關再單開 websearch」

Frank 實測回報：問顧問「比較兩家 CLI 的訂閱費率」，三席全部只給推論、沒有實際去搜。
主對話已用免費席次做過探測，結論是**顧問沒有搜尋工具，是我們自己 deny 掉的**，
不是模型不會。Frank 2026-08-06 拍板：**開 `websearch`、`webfetch` 維持關閉、
順便把 `read`／`grep`／`glob` 關掉。**

實作方式**不是**在 deny 清單上加三行，而是換成**萬用字元全關、再單開一項**。理由：

- 今天 `read` 是開著的，根因是「**沒被列到的工具落在 `*: allow` 之下**」。
  逐項列舉治不了這個病：opencode 將來新增任何工具，一樣會自動變成 allow。
- 主對話 2026-08-06 已實測確認（三個免費模型）：`"*": deny` 生效，且**單項 `allow`
  勝過萬用字元**——websearch 正常呼叫、檔案讀取工具**根本沒被掛載**、canary 未外洩、
  沒有退回預設 agent。
- 規格已經先改好並 commit：**`SPEC.md` §4.2 現在明訂萬用字元寫法**，以及
  「`webfetch` 仍然 deny」「這個放寬只發生在 opencode 這一家」兩條。
  **實作以 SPEC 為準。**

⚠️ **這一包極小**：一個 agent 定義的 frontmatter、若干測試、README 兩段文字。
**不要順手改別的東西。**

---

## 檔案

| 檔案 | 動作 |
|---|---|
| `src/adapters/opencode.py` | **修改**：只有 `AGENT_DEF` 這個常數 |
| `tests/test_adapters_ask.py` | **修改**：新增一個測試類別（見下） |
| `README.md` | **修改**：中英文各一段 |

🔴 **除了上表，一個字都不要動。** 特別是 `src/adapters/` 底下其他三家
（`claude.py`／`codex.py`／`gemini.py`）、`src/adapters/base.py`、
`src/engine/` 全部、`src/server.py`、`src/static/index.html`、`SPEC.md`、`AGENTS.md`。

🔴 **`opencode.py` 的其他部分一律不動**：`ask()` 的 argv 組法、`FALLBACK_MSG` 的檢查、
`_extract_text()`、`_usage()`、暫存目錄的寫法全部維持原樣。

---

## 介面契約（照字面實作）

### A. `src/adapters/opencode.py`

目前是：

```python
AGENT_DEF = """\
---
description: Read-only council advisor.
mode: primary
permission:
  bash: deny
  edit: deny
  webfetch: deny
  task: deny
  todowrite: deny
  websearch: deny
  lsp: deny
  skill: deny
---

You are a council advisor. Answer the question directly.
"""
```

改成：

```python
# 權限是「全關再單開」，不是逐項 deny（SPEC.md §4.2）。列舉清單會讓沒被列到的
# 工具落在 opencode 的 *: allow 之下——顧問一度因此握有 read/grep/glob，而且
# opencode 將來新增的任何工具都會自動變成 allow。萬用字元版是 fail-closed 的。
# websearch 是唯一的例外：查得到現況與唯讀是兩件事（§4.2）。webfetch 維持關閉,
# 它是「對任意 URL 發請求」，等於給模型一條主動把脈絡送出去的路。
AGENT_DEF = """\
---
description: Read-only council advisor. Web search allowed, nothing else.
mode: primary
permission:
  "*": deny
  websearch: allow
---

You are a council advisor. Answer the question directly.
"""
```

- 🔴 **`"*"` 的雙引號不可省略**（YAML 裡裸的 `*` 是別名語法，會解析失敗）。
- 🔴 **`websearch: allow` 必須排在 `"*": deny` 之後。** 實測是這個順序生效的，
  不要調換去賭另一個順序也行。
- 🔴 **不要加回任何逐項 deny。** 加了不會更安全，只會讓人以為清單就是全部，
  下次又漏掉新工具。
- ⚠️ `description` 那行照抄上面的新字串（它會被人讀到，要說實話）。

### B. `tests/test_adapters_ask.py`

🔴 **目前整個 `tests/` 沒有任何一條測試碰過 `AGENT_DEF`**——SPEC §4.2 稱為「機制層
保證」的東西，今天零覆蓋，改壞了不會有人叫。**這一包要把它補上。**

在檔案末尾（`if __name__ == "__main__":` 之前）新增：

```python
class OpenCodeAgentPermissionTest(unittest.TestCase):
    """SPEC.md §4.2：顧問的工具權限是「全關再單開」。

    這幾條守的是機制層保證本身，不是某次呼叫的行為 ⇒ 直接斷言 AGENT_DEF 的內容。
    2026-08-06 之前這裡沒有任何測試，於是 read/grep/glob 一直開著沒人發現。
    """

    def test_wildcard_deny_present(self):
        self.assertIn('"*": deny', opencode.AGENT_DEF)

    def test_websearch_allowed_after_wildcard(self):
        # 順序就是規格：單項 allow 必須排在萬用字元 deny 之後。
        wildcard = opencode.AGENT_DEF.index('"*": deny')
        websearch = opencode.AGENT_DEF.index("websearch: allow")
        self.assertLess(wildcard, websearch)

    def test_webfetch_never_allowed(self):
        # webfetch 是「對任意 URL 發請求」，與 websearch 不是同一件事（§4.2）。
        self.assertNotIn("webfetch: allow", opencode.AGENT_DEF)

    def test_no_other_tool_is_allowed(self):
        # 全檔只准出現一個 allow，而且必須是 websearch 那一個。
        allows = [line.strip() for line in opencode.AGENT_DEF.splitlines()
                  if line.strip().endswith(": allow")]
        self.assertEqual(allows, ["websearch: allow"])

    def test_agent_def_is_used_by_ask(self):
        # 寫進暫存目錄的那份定義必須就是 AGENT_DEF 本身，不是另一份複製品。
        self.assertIn("permission:", opencode.AGENT_DEF)
        self.assertEqual(opencode.AGENT_NAME, "advisor")
```

🔴 **`test_no_other_tool_is_allowed` 是這組裡最重要的一條**：它讓「將來有人多開一個
工具」變成一定會翻紅的事，而不是只擋住今天已知的那幾個名字。**不要把它改成
`assertIn`**，那就不成立了。

⚠️ 既有測試**一條都不得修改或刪除**。若有既有測試因為 `AGENT_DEF` 改動而翻紅，
**停手、寫進 `dispatch/BLOCKED.md` 回報**，不要自行改測試遷就。

### C. `README.md`

README 是中英雙份。目前兩邊各有一句「顧問唯讀」的說明，**現在那句話不完整了**
——顧問拿得到網路搜尋。兩邊都要補。

英文，把這一段：

```markdown
Advisors are run read-only wherever the CLI supports it: they give opinions, they
do not act.
```

改成：

```markdown
Advisors are run read-only wherever the CLI supports it: they give opinions, they
do not act. One exception is deliberate — advisors running on `opencode` are
allowed to search the web, because being able to check current facts is a
different thing from being able to change your machine. They still cannot read
your files, run commands, or fetch arbitrary URLs. Note that this means a search
provider may see fragments of whatever context you attach. See `SPEC.md` §4.2.
```

中文，把這一句：

```markdown
顧問在 CLI 支援的範圍內一律以唯讀模式執行：它們只出意見，不動手。
```

改成：

```markdown
顧問在 CLI 支援的範圍內一律以唯讀模式執行：它們只出意見，不動手。**有一個刻意的例外**：
跑在 `opencode` 上的顧問可以使用網路搜尋——查得到現況與能不能動你的機器是兩件事。
它們仍然讀不到你的檔案、不能執行指令、不能對任意網址發請求。
⚠️ 這也代表**你貼進去的脈絡片段有可能出現在搜尋查詢裡**，被搜尋供應商看到。
詳見 `SPEC.md` §4.2。
```

🔴 **只改這兩段，README 其他地方一個字都不要動。**

---

## 驗收條件（貼真實輸出，不要只描述）

1. `python3 -m unittest discover tests` **全過**，貼出最後三行。
   🔴 **既有 314 個測試一個都不得變紅**；新增五條 ⇒ 總數應為 **319**。
   ⚠️ 工作包 011 曾回報「交付完成」而實跑是 `FAILED (errors=1)`。**自己實際跑完再回報。**
2. 貼出三個檔的**完整 `git diff`**。
3. 貼出 `AGENT_DEF` 的最終內容（`python3 -c` 印出來即可），以及
   `grep -n 'allow' src/adapters/opencode.py` ——**應該只有 `websearch: allow` 一行**
   （註解那行不算，若你的註解裡有 allow 這個字請自行說明）。
4. **突變驗證三項**，每項：改壞 → 貼失敗輸出（**含翻紅的測試名**）→ 還原 →
   最後貼還原後全過的結果。
   - (a) 把 `websearch: allow` 改成 `webfetch: allow`
     ⇒ `test_no_other_tool_is_allowed` 與 `test_webfetch_never_allowed` 應翻紅。
   - (b) 在 `websearch: allow` 之後多加一行 `read: allow`
     ⇒ `test_no_other_tool_is_allowed` 應翻紅。
   - (c) 把 `"*": deny` 整行刪掉 ⇒ `test_wildcard_deny_present` 與
     `test_websearch_allowed_after_wildcard` 應翻紅。
   - 🔴 **突變只准動 `src/adapters/opencode.py`**，不准動測試檔。
   - 🔴 **每一項動手前先確認要取代的字串在檔案裡是唯一的**：印出 `text.find(old)`
     與 `text.rfind(old)`，兩個位置必須相同才可以取代。
   - 🔴 **備份放 `dispatch/tmp/030-backup/`，不要放 `/tmp`。**
     還原後用 `cmp` 確認與備份**位元組相同**，並貼出結果。
5. 貼出 `git status --short`。
6. 🔴 **公開發布掃描**：貼出
   `grep -rnE "$(whoami)|/home/[a-z]" src/adapters/opencode.py tests/test_adapters_ask.py README.md`
   ——**應為空**。

---

## 不要做的事

- 🔴 **全程不得執行 `--live`，不得呼叫任何真實 CLI，也不得執行 `opencode` 這個指令。**
  ⚠️ 這一包改的正是真實呼叫的權限設定，**實機驗證由主對話負責**（它已經用免費席次
  做過探測）。你只做程式碼與測試，測試一律用既有的假執行檔手法。
  ⚠️ **Frank 有一個 `--live` 伺服器在 8765 埠上跑，記憶體裡有他的討論。
  絕對不要對 8765 送任何請求，也不要 kill 任何行程。**
- 🔴 **不要改另外三家 adapter。** `claude` 的 `--tools ""`、`codex` 的
  `--sandbox read-only`、`gemini` 的 `--approval-mode plan` 全部維持原樣——
  SPEC §4.2 明訂這個放寬只發生在 opencode 這一家。
- 🔴 **不要動 `FALLBACK_MSG` 的檢查邏輯。** `--agent` 是 fail-open 的，那段是唯一的
  失敗關閉，動它等於把整個權限機制的保險絲拔掉。
- ⚠️ 不要新增設定項（例如「讓使用者選要不要開搜尋」）。**這一包就是把預設改掉。**
- 不要引入第三方套件、框架、建置步驟。
- 不要碰版控（`git add` / `commit` / `push` 一律不執行）。
