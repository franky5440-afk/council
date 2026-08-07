# 工作包 037c — `usage.total` 不是總和，別再宣稱它是

## 這一包在做什麼

`status()` 對外吐出一個叫 `usage.total` 的欄位。名字說它是總和，**它不是**。

`state.py` 的 `merge_usage()` 把每次呼叫的 usage 按**鍵名**相加。同一家 CLI 沒問題
（鍵名一致），但 council 的核心用法就是**混用不同家**，而各家鍵名完全不同：

```
gemini-1：{'input':10324, 'prompt':10324, 'candidates':34, 'total':11283, 'cached':0, 'thoughts':925, 'tool':0}
codex-2 ：{'tokens_used': 3174}
合併後 ：{...上面全部..., 'tokens_used': 3174}
```

⇒ 端出去的 **`total.total = 11283` 看起來像兩席總和，實際上只有 gemini 一家**，
codex 的 3174 躲在旁邊語意重疊的 `tokens_used` 裡。

（上面的數字是 2026-08-07 在 macOS 上的**真實呼叫**，不是編的。）

🔴 **這件事打到 `SPEC.md` §5 邊界 6（額度可見性）要保護的東西**：那道邊界存在的理由
就是讓使用者知道花了多少。**一個看起來像總和、實際不是的數字，比不顯示更糟。**

---

## 1. 修法已經定了：**移除**，不是改名

| 決定 | 內容 |
|---|---|
| **改哪裡** | `status()` 的對外欄位 |
| **不准改** | `merge_usage()` 本身。它在 `by_seat` 那一側**永遠是同一家 CLI**（一席不會換家）⇒ 那一側是對的，砍掉會壞掉現有行為 |
| **不准做** | 不准「正規化各家欄位名」（把 `tokens_used` 映射成 `total`）。那是猜語意，各家 token 定義本來就不同，映射只會製造一個看起來更可信的錯數字 |

**為什麼是移除而不是改名**：拿掉 `_usage_total` 之後，跨家的扁平合併
**在結構上不可能再發生**——不是靠註解叮嚀。而 `transcript.py`（Markdown 匯出）
**從頭到尾就沒用過這個欄位**，已經證明沒有它一樣活得好好的。

⚠️ `usage.calls` **要保留**。呼叫次數與 CLI 家別無關，它是真的總和。

---

## 2. 契約：這五條測試，交付後必須全綠

**新增檔案 `tests/test_contract_037c.py`，內容一字不改照抄**（下面這份主對話已經
親手跑過：目前 **2 紅 3 綠**）：

```python
"""037c 契約測試：現在會紅，交付後要綠。

跨 CLI 的 usage 不得被扁平合併成一個看起來像總和的數字。
資料來自 2026-08-07 macOS 上的真實呼叫（gemini ＋ codex 同一輪）。
"""
import copy
import sys
import unittest
from pathlib import Path

SRC_DIR = Path(__file__).resolve().parent.parent / "src"
sys.path.insert(0, str(SRC_DIR))

from engine import state  # noqa: E402

STATIC_DIR = SRC_DIR / "static"
INDEX_PATH = STATIC_DIR / "index.html"


def make_seats(advisor_ids=("a1", "a2"), arbiter_id="arb") -> list:
    seats = [{"seat_id": sid, "cli": "claude", "model": None, "role": "advisor"}
             for sid in advisor_ids]
    seats.append({"seat_id": arbiter_id, "cli": "codex", "model": "m",
                  "role": "arbiter"})
    return seats


def ok_result(text="答覆\n[立場: 同意] [補充: 無]", usage=None) -> dict:
    return {"ok": True, "text": text, "truncated": False, "error": None,
            "elapsed_s": 1.0, "model_used": "model-x", "usage": usage}


GEMINI = {"input": 10324, "prompt": 10324, "candidates": 34,
          "total": 11283, "cached": 0, "thoughts": 925, "tool": 0}
CODEX = {"tokens_used": 3174}


class CrossCliUsageContractTest(unittest.TestCase):
    def _two_families(self) -> dict:
        d = state.Discussion("q", make_seats())
        d.begin_round()
        d.record_speech("a1", ok_result(usage=copy.deepcopy(GEMINI)))
        d.record_speech("a2", ok_result(usage=copy.deepcopy(CODEX)))
        d.end_round()
        return d.status()

    def test_no_outward_field_claims_to_be_a_total(self):
        # 現在會紅：status()["usage"]["total"]["total"] == 11283，
        # 看起來像兩席總和、實際只有 gemini 一家。
        st = self._two_families()
        self.assertNotIn("total", st["usage"])

    def test_per_seat_usage_stays_verbatim(self):
        st = self._two_families()
        self.assertEqual(st["usage"]["by_seat"]["a1"]["usage"], GEMINI)
        self.assertEqual(st["usage"]["by_seat"]["a2"]["usage"], CODEX)

    def test_calls_is_still_a_real_total(self):
        # calls 與 CLI 家別無關，它是真的總和，不得一起被拿掉。
        st = self._two_families()
        self.assertEqual(st["usage"]["calls"], 2)

    def test_same_seat_across_rounds_still_accumulates(self):
        # merge_usage 在同一席（＝同一家 CLI）內仍必須累加，不得整個砍掉。
        d = state.Discussion("q", make_seats())
        for _ in range(2):
            d.begin_round()
            d.record_speech("a1", ok_result(usage={"input_tokens": 10}))
            d.record_speech("a2", ok_result(usage={"input_tokens": 1}))
            d.end_round()
            d.request_next_round()
        st = d.status()
        self.assertEqual(st["usage"]["by_seat"]["a1"]["usage"]["input_tokens"], 20)
        self.assertEqual(st["usage"]["by_seat"]["a1"]["calls"], 2)


class UiMustNotReadRemovedFieldTest(unittest.TestCase):
    def test_index_html_does_not_reference_usage_total(self):
        # 現在會紅：index.html 有 `var total = usage.total;`。
        # 這條同時守住空狀態條件不得再掛在該欄位上。
        html = INDEX_PATH.read_text(encoding="utf-8")
        self.assertNotIn("usage.total", html)


if __name__ == "__main__":
    unittest.main()
```

🔴 **其中 3 條現在就是綠的，它們是護欄，不是目標**：
`test_per_seat_usage_stays_verbatim`、`test_calls_is_still_a_real_total`、
`test_same_seat_across_rounds_still_accumulates`。
**它們防的是你修過頭**——把 `calls` 一起砍掉、或把 `merge_usage` 整個刪掉，
它們就會翻紅。交付時這 3 條**必須維持綠**。

---

## 3. 🔴 先自己想，再看我的清單

**在動任何一行程式碼之前**，先做這件事，並把結果寫進交付報告：

1. 讀完第 1 節的問題描述後，**先自己列出「這個修法應該要有哪些測試」**，
   不要先看第 2 節。
2. 然後對照第 2 節那五條，寫出**差集**：
   - **你列了、我沒列的** —— 為什麼你覺得需要？
   - **我列了、你沒列的** —— 你當初為什麼沒想到？

⚠️ **兩個方向都要寫，不准只寫一邊。** 「我列了你沒列」不是要抓你的錯——
那一格如果空著，代表你只是照抄；「你列了我沒列」那一格才是這一節真正的價值，
**很可能是我漏了。**

⇒ 若你認為該補測試，**就補**（寫進 `tests/test_contract_037c.py`），
並在報告裡說明補了什麼、為什麼。

---

## 4. 要改的三個檔

### 4.1 `src/engine/state.py`

`status()` 裡刪掉這一行（**檔案裡只出現一次**）：

```python
                "total": copy.deepcopy(self._usage_total),
```

`self._usage_total` 這個內部欄位以及它的兩處 `merge_usage` 更新，**你自行判斷**要不要
一起清掉——判準是「清掉之後還有沒有人讀它」。清或不清都可以，但**不准清到
`_usage_by_seat` 那一側**（護欄測試會抓）。

### 4.2 `src/cli.py`

刪掉這一行（**檔案裡只出現一次**）：

```python
    print(f"累計 usage：{usage['total']}")
```

🔴 **這一行是整個 bug 唯一裸奔的地方**：「累計 usage」四個字沒有任何但書，
使用者在終端機看到的就是那個假總和。

### 4.3 `src/static/index.html`

`renderUsage()` 裡目前這一整段（**原文照抄，這就是規格**）：

```javascript
  var total = usage.total;
  if (total && Object.keys(total).length > 0) {
    content.appendChild(renderUsageDict("各席次同名欄位累加", total));
    var mixed = document.createElement("div");
    mixed.className = "hint";
    mixed.textContent = "⚠️ 各家 CLI 的欄位名稱不同（opencode 是 tokens.*，"
      + "claude 是 input_tokens／output_tokens），上面這一區只是把名稱相同的欄位"
      + "各自相加，不是所有席次的總和。要看真實用量請看上面各席次分列。";
    content.appendChild(mixed);
  } else {
    var none = document.createElement("div");
    none.textContent = "（本次未取得用量統計）";
    content.appendChild(none);
  }
```

**整段刪掉**，改成：累加區與那段 ⚠️ 警語**都不再存在**，而
「（本次未取得用量統計）」這個空狀態**改成從 `usage.by_seat` 推導**
——「沒有任何一席回報 usage」才顯示它。

🔴 **這一步不做的話會出現自相矛盾的畫面**：`usage.total` 消失後
`if (total && …)` 恆為 false ⇒ `else` 恆成立 ⇒ 面板會在剛印完各席次的真實數字之後，
緊接著說「（本次未取得用量統計）」。

⚠️ 其餘部分**一律不動**：各席次分列的排版、`isCostKey()` 的金額過濾、
「council 不呼叫任何模型 API…」那段說明、`cacheNote` 那段，**全部保持原樣**。

---

## 5. 🔴 既有測試：7 條要改、1 條要刪

主對話已經在沙盒實跑過，移除該欄位後**恰好這 8 條會壞**。名單給你，
**不准用「跑跑看還有誰紅」代替**——你要確認的是**只有這 8 條**，多一條都要回報。

### 5.1 這 7 條要**改**（不准刪）

| 檔案 | 測試 |
|---|---|
| `tests/test_engine_state.py` | `Boundary6Test.test_by_seat_and_total` |
| `tests/test_engine_state.py` | `Boundary6Test.test_failed_call_counts` |
| `tests/test_engine_state.py` | `Boundary6Test.test_status_usage_is_copy` |
| `tests/test_engine_state.py` | `RecordArbitrationTest.test_usage_accounted` |
| `tests/test_engine_state.py` | `RecordArbitrationTest.test_usage_deep_copied` |
| `tests/test_engine_state.py` | `RecordArbitrationTest.test_failed_arbitration_still_counts` |
| `tests/test_engine_orchestrator.py` | `RunRoundNormalTest.test_returned_status_fields` |

**它們真正在守的性質是「用量有記到帳」與「回傳是深拷貝、外部改不動內部」**，
`total` 只是順手多驗了一遍。⇒ **把斷言改到 `by_seat` 那一側，性質一條都不會少。**

⚠️ **不准為了讓它們過而放寬斷言**（例如把 `assertEqual` 改成 `assertIn`、
或整段註解掉）。改完之後每一條守的東西**必須跟改之前一樣強**。

### 5.2 這 1 條要**刪**

`tests/test_ui.py` 的 `IndexHtmlStructureTest.test_usage_total_is_labelled_as_not_a_sum`：

```python
        self.assertIn("不是所有席次的總和", self.source)
```

🔴 **這是唯一一條准你刪的測試，理由要寫進報告**：它守的是那段 ⚠️ 免責文字，
而那段文字存在的**唯一**理由就是替 `usage.total` 這個欄位道歉。欄位沒了，
它守的東西就不存在了。第 2 節新增的 `test_index_html_does_not_reference_usage_total`
是它的替代守門。

🔴 **這裡有一個字面陷阱，請特別小心**：
你只要**不刪 HTML 裡那段警語文字**，這條測試就會一直是綠的——
於是留下一段**孤兒警語**（畫面上寫著「上面這一區只是把名稱相同的欄位各自相加」，
但上面已經沒有那一區了）。**綠燈不代表做對了。**
⇒ 警語文字與這條測試**必須一起刪**。

---

## 6. 驗收條件

1. `python3 -m unittest discover tests` **全綠**。
2. `tests/test_contract_037c.py` 五條全綠，且**你沒有修改過那五條的斷言**
   （可以新增你自己補的測試，但第 2 節那五條一字不改）。
3. 第 5 節的 8 條已按規定處理；**若你發現第 9 條**，停下來寫進報告，不要自行決定怎麼辦。
4. 第 3 節的差集分析已寫進報告（兩個方向都有內容）。
5. 報告裡列出你改了哪些檔、每個檔改了什麼、為什麼。

---

## 7. 🔴 紅線

- **不准呼叫任何真實 CLI。** 這一包完全不需要 `--live`，假的 usage dict 餵進
  `record_speech()` 就能重現全部行為。真實資料已經寫在第 1 節，不用再花額度去拿。
- **不准碰 8765 埠，不准 kill 任何程序。** Frank 可能有一台 `--live` 伺服器在上面跑。
- **不准動 git**（`add`／`commit`／`checkout`／`stash` 一律不准）。版控由主對話負責。
- **臨時檔一律放 `dispatch/tmp/037c/`**，不要放 `/tmp`、不要放 repo 其他地方。
- **不准改 `AGENTS.md`、`SPEC.md`、`CLAUDE.md`、`README.md`** 或任何本工作包沒點名的檔。
- 這是 **PUBLIC repo**：新增或修改的內容裡**不得出現使用者名稱、家目錄絕對路徑、token**。
