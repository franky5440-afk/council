# 工作包 038 — 一席失敗，不該讓整場討論永遠開不完

## 這一包在做什麼

顧問席次**會失敗**，而且是常態：免費模型隨時會從清單下架、帳號對某模型可能沒授權
（401）、免費席次的延遲不穩。council 不驗證模型名（這是刻意的，`README` 已寫明），
所以打錯字也是同一種失敗。

**失敗本身不是 bug，council 對失敗的處理才是。** 目前：

```python
# record_speech()：呼叫失敗時
else:
    stance = None
    more = True          # ← 失敗被記成「還有補充」
    violation = False

# converged()
return all(rec["more"] is False for rec in self.rounds[-1])   # ← 要求全體
```

⇒ **只要有一席持續失敗，這場討論在數學上永遠不可能收斂**，只能一路跑到 `max_rounds`，
每一輪都對還活著的席次白花一次呼叫。

而失敗**在對外狀態上完全不留痕跡**：`violation` 記 `false`、`format_violations` 不計、
`usage.by_seat[席次].calls` 照記 1（一次 401 和一次成功回答被記成同一件事）。
⇒ 使用者看到的只有「一直不收斂」，**沒有任何地方告訴他是哪一席壞了。**

（來源：2026-08-08 macOS 實測，`north-mini-code-free` 穩定 401、`nemotron` 有一輪 transient
失敗。但**這與平台無關**，Linux 上同一段程式碼行為相同。）

---

## 1. 🔴 修法的方向已經定了

| 決定 | 內容 |
|---|---|
| **改 `converged()`** | 收斂判定**只看成功的席次**。失敗席次不參與。 |
| **不改記錄欄位** | 失敗席次的 `more` **維持 `True`**，`stance` 維持 `None`，`violation` 維持 `False`。那個 `more=True` 是刻意的 fail-safe（解析失敗時寧可不收斂、也不要提早結束討論），這一包**不動它**。 |
| **新增失敗計數** | `status()["usage"]["by_seat"][席次]` 多一個 `failed` 整數欄位。 |
| **不要做** | 不要在失敗時「重試」、不要自動把壞掉的席次踢出討論。那是另一件事，本包不碰。 |

🔴 **修法自己有一個陷阱，契約有一條測試專門守它**：
若把 `converged()` 改成「只看成功的席次」而忘了處理空集合，**`all([])` 回 `True`**
⇒ 全部席次都失敗時會宣告「已收斂」，**零份意見卻說討論完成，比原本的 bug 更糟。**

---

## 2. 契約：這八條測試，交付後必須全綠

**新增檔案 `tests/test_contract_038.py`，內容一字不改照抄**（主對話已親手跑過：
目前 **5 紅 3 綠**；套用修法後 **8 綠**，且全套只有第 5 節那 2 條既有測試會壞）：

```python
"""038 契約測試：現在會紅，交付後要綠。

一席呼叫失敗不得讓整場討論永遠無法收斂，且失敗必須在對外狀態上看得見。
"""
import sys
import unittest
from pathlib import Path

SRC_DIR = Path(__file__).resolve().parent.parent / "src"
sys.path.insert(0, str(SRC_DIR))

from engine import state  # noqa: E402


def make_seats(advisor_ids=("a1", "a2"), arbiter_id="arb") -> list:
    seats = [{"seat_id": sid, "cli": "opencode", "model": None, "role": "advisor"}
             for sid in advisor_ids]
    seats.append({"seat_id": arbiter_id, "cli": "claude", "model": "m",
                  "role": "arbiter"})
    return seats


def done(text="答覆\n[立場: 同意] [補充: 無]") -> dict:
    """成功且表示沒有補充。"""
    return {"ok": True, "text": text, "truncated": False, "error": None,
            "elapsed_s": 1.0, "model_used": "model-x", "usage": None}


def more() -> dict:
    """成功且表示還有補充。"""
    return done("答覆\n[立場: 保留] [補充: 有]")


def failed() -> dict:
    """呼叫失敗（模型下架、401、逾時都長這樣）。"""
    return {"ok": False, "text": "", "truncated": False,
            "error": "command exited with code 1", "elapsed_s": 6.8,
            "model_used": None, "usage": None}


def one_round(d, results: dict) -> None:
    d.begin_round()
    for seat_id, result in results.items():
        d.record_speech(seat_id, result)
    d.end_round()


class FailedSeatMustNotBlockConvergenceTest(unittest.TestCase):
    def test_failed_seat_does_not_block_convergence(self):
        # 現在會紅：失敗席次被記成 more=True，而 converged() 要求全體 more is False
        # ⇒ 一席持續失敗的討論在數學上永遠不可能收斂，只能跑滿 max_rounds。
        d = state.Discussion("q", make_seats())
        one_round(d, {"a1": failed(), "a2": done()})
        self.assertTrue(d.converged())
        self.assertTrue(d.status()["converged"])

    def test_all_seats_failed_is_not_convergence(self):
        # 🔴 這條防的是修法本身的陷阱：若改成「只看成功的席次」而忘了處理空集合，
        # all([]) 回 True ⇒ 零份意見卻宣告收斂，比原本的 bug 更糟。
        d = state.Discussion("q", make_seats())
        one_round(d, {"a1": failed(), "a2": failed()})
        self.assertFalse(d.converged())
        self.assertFalse(d.status()["converged"])

    def test_successful_seat_wanting_more_still_blocks(self):
        # 護欄：成功且說「還有補充」的席次仍必須擋住收斂，這是邊界 5 的本體。
        d = state.Discussion("q", make_seats())
        one_round(d, {"a1": failed(), "a2": more()})
        self.assertFalse(d.converged())

    def test_unanimous_no_more_still_converges(self):
        # 護欄：沒有任何失敗時的原本行為不得被改動。
        d = state.Discussion("q", make_seats())
        one_round(d, {"a1": done(), "a2": done()})
        self.assertTrue(d.converged())


class FailuresMustBeVisibleTest(unittest.TestCase):
    def test_failed_count_is_reported_per_seat(self):
        # 現在會紅：by_seat 只有 calls，一次 401 與一次成功回答記成同一件事
        # ⇒ 使用者看不出是哪一席壞了，只看到「一直不收斂」。
        d = state.Discussion("q", make_seats())
        one_round(d, {"a1": failed(), "a2": done()})
        by_seat = d.status()["usage"]["by_seat"]
        self.assertEqual(by_seat["a1"]["calls"], 1)
        self.assertEqual(by_seat["a1"]["failed"], 1)
        self.assertEqual(by_seat["a2"]["calls"], 1)
        self.assertEqual(by_seat["a2"]["failed"], 0)

    def test_failed_count_accumulates_across_rounds(self):
        d = state.Discussion("q", make_seats())
        one_round(d, {"a1": failed(), "a2": done()})
        d.request_next_round()
        one_round(d, {"a1": failed(), "a2": done()})
        by_seat = d.status()["usage"]["by_seat"]
        self.assertEqual(by_seat["a1"]["failed"], 2)
        self.assertEqual(by_seat["a1"]["calls"], 2)
        self.assertEqual(by_seat["a2"]["failed"], 0)

    def test_arbitration_failure_also_counted(self):
        d = state.Discussion("q", make_seats())
        one_round(d, {"a1": done(), "a2": done()})
        d.record_arbitration(failed())
        by_seat = d.status()["usage"]["by_seat"]
        self.assertEqual(by_seat["arb"]["failed"], 1)


class SeatCountErrorMessageTest(unittest.TestCase):
    def test_message_speaks_in_advisor_units(self):
        # 現在會紅：訊息是「seats 長度須為 2～4」，它數的是總席次，
        # 但使用者數的是顧問 ⇒ 填 4 個顧問的人看到「須為 2～4」會以為自己合規。
        seats = [{"seat_id": f"a{i}", "cli": "opencode", "model": None,
                  "role": "advisor"} for i in range(1, 5)]
        seats.append({"seat_id": "arb", "cli": "claude", "model": None,
                      "role": "arbiter"})
        with self.assertRaises(ValueError) as cm:
            state.Discussion("q", seats)
        msg = str(cm.exception)
        self.assertIn("顧問", msg)
        self.assertIn("仲裁者", msg)
        self.assertIn("5", msg)          # 要說出實際收到幾席


if __name__ == "__main__":
    unittest.main()
```

🔴 **其中 3 條現在就是綠的，它們是護欄，不是目標**：
`test_all_seats_failed_is_not_convergence`、`test_successful_seat_wanting_more_still_blocks`、
`test_unanimous_no_more_still_converges`。交付時**必須維持綠**。

⚠️ **最後那條刻意不釘死訊息的字面**（只要求出現「顧問」「仲裁者」與實際席數）
——措辭由你決定，但那三件事必須說到。

---

## 3. 🔴 先自己想，再看我的清單

**在動任何一行程式碼之前**，先做這件事，並把結果寫進交付報告：

1. 讀完第 1 節後，**先自己列出「這個修法應該要有哪些測試」**，不要先看第 2 節。
2. 然後對照第 2 節那八條，寫出**差集**：
   - **你列了、我沒列的** —— 為什麼你覺得需要？
   - **我列了、你沒列的** —— 你當初為什麼沒想到？

⚠️ **兩個方向都要寫。**「你列了我沒列」那一格才是這一節真正的價值，**很可能是我漏了。**
若你認為該補測試，**就補**（寫進 `tests/test_contract_038.py`），並在報告裡說明。

---

## 4. 要改的檔

### 4.1 `src/engine/state.py`（三處）

**① `converged()`**。目前這一行（**檔案裡只出現一次**）：

```python
        return all(rec["more"] is False for rec in self.rounds[-1])
```

改成「只看本輪成功的席次；一個成功的都沒有時不算收斂」。
⚠️ **`if self.phase != PHASE_AWAITING_USER: return False` 那個前置判斷保持原樣。**

**② 失敗計數**。`record_speech()` 與 `record_arbitration()` 兩處都要記
（**仲裁失敗也算**，契約有一條驗它）。⚠️ **注意兩個方法不一樣**：
`record_speech()` 有區域變數 `ok`，`record_arbitration()` **沒有**（它用 `bool(result["ok"])` 內嵌）
——用一個兩邊都成立的寫法，不要假設 `ok` 到處都在。
（主對話第一次寫這個補丁就踩到，`NameError` 讓 18 個仲裁測試一起爆。）

**③ 席次數的錯誤訊息**。目前這一行（**檔案裡只出現一次**）：

```python
            raise ValueError("seats 長度須為 2～4")
```

改成用**使用者的單位**講：他填的是「顧問」，訊息卻在數「總席次」
⇒ 填 4 個顧問的人看到「須為 2～4」會以為自己合規。要說到顧問上限、仲裁者恰好一個、
以及實際收到幾席。

### 4.2 `src/static/index.html`

**① 用量面板要顯示失敗次數。** 目前每席那一行是：

```javascript
    line.textContent = seatId + "：calls=" + per.calls;
```

改成：`failed > 0` 時把它顯示出來（措辭你決定，但要讓人一眼看出**是哪一席在失敗**）。
`failed === 0` 時**不要顯示**，避免每一席都掛一個 0 變成噪音。

**② 預設席次**。目前 textarea 的內容（**原文照抄，這就是規格**）：

```html
            <textarea id="advisors" rows="4">opencode:opencode/deepseek-v4-flash-free
opencode:opencode/nemotron-3-ultra-free
opencode:opencode/ling-3.0-flash-free</textarea>
```

改成兩席：`opencode:opencode/nemotron-3-ultra-free` 與
`opencode:opencode/laguna-s-2.1-free`。

🔴 **理由（不要理解成「維護模型清單」）**：`ling-3.0-flash-free` **已從 opencode 的可用
清單下架**（Linux 1.18.11 與 macOS 1.18.10 都查不到，實測呼叫回 `Unexpected server error`）
⇒ 預設配置目前開箱即壞第三席。這是**一次性刷新**，不是承諾追著上游改。
⚠️ 上面那一行 `<label>` 的文字**一個字都不要動**。

### 4.3 `run.sh`

目前（**原文照抄**）：

```bash
ADVISORS=(
    "opencode:opencode/deepseek-v4-flash-free"
    "opencode:opencode/nemotron-3-ultra-free"
    "opencode:opencode/ling-3.0-flash-free"
)
```

改成與 4.2 相同的兩席。**上下的註解不要動。**

### 4.4 `README.md`（四處）

**① 顧問席次上限要寫在使用者設定席次的地方。** 現在「顧問 1～3 席」只出現在
「#### 仲裁者欄位不是第四位顧問」小節裡，而人是在「### 換模型／調整發言順序」那節
設定席次的 ⇒ 在那一節開頭補一句：**顧問 1～3 席，加上恰好一個仲裁者，總席次 2～4。**

**② 範例配置換掉已下架的模型。** 目前這個區塊（**原文照抄**）：

````
```
opencode:opencode/deepseek-v4-flash-free
opencode:opencode/nemotron-3-ultra-free
opencode:opencode/ling-3.0-flash-free
```
````

換成 4.2 的兩席。

**③ 新增一段：免費模型會消失，這是常態。** 要說清楚三件事：
- 免費模型清單**隨時會變**（下架、改名、或帳號對某模型沒授權而回 401），
  council 不追這件事、也追不了；
- 因此**選席次前請自己查一次**（`opencode models`），
  README 裡列的任何模型名都只是**寫作當下**的例子；
- 一席壞掉不會拖垮整輪（其餘席次照常發言、仲裁照常可用），
  而且從 038 起**不會再擋住收斂**，失敗次數會顯示在用量面板上。

**④ 修正「三席免費顧問」。** 目前這一句（**原文照抄**）：

```
倍增；放在仲裁者席則不會。`run.sh` 的預設配置就是照這個道理設的——三席免費顧問，
```

預設改成兩席之後這句就錯了，要一起改。
🔴 **改預設值卻漏改描述它的文件，就是在製造下一個說謊的地方。**

---

## 5. 🔴 既有測試：恰好 2 條要改（不准刪）

主對話已在沙盒實跑，套用修法後**只有這 2 條會壞**。
**不准用「跑跑看還有誰紅」代替**——你要確認的是**只有這 2 條**，多一條都要回報。

**① `tests/test_engine_state.py` 的 `Boundary5Test.test_timeout_not_converged_no_violation`**

```python
        d.record_speech("a1", fail_result())
        d.record_speech("a2", ok_result())
        d.end_round()
        self.assertFalse(d.converged())
        rec = d.rounds[-1][0]
        self.assertFalse(rec["violation"])
        self.assertTrue(rec["more"])
        self.assertIsNone(rec["stance"])
```

🔴 **這條測試守的正是我們要改掉的行為**（a1 失敗、a2 說「無補充」⇒ 斷言未收斂）。
⇒ **只有 `assertFalse(d.converged())` 這一行要翻成 `assertTrue`。**
後面三行（`violation` / `more` / `stance`）**一個字都不要動**——因為第 1 節說了，
記錄欄位不改，只改 `converged()` 看誰。⚠️ 測試名稱裡的 `not_converged` 也要跟著改，
否則名字會與它斷言的內容相反（**這一包的主題就是「名字不可以說謊」**）。

**② `tests/test_engine_state.py` 的 `RecordArbitrationTest.test_failed_arbitration_still_counts`**

它斷言 `st["usage"]["by_seat"]["arb"]` **完全等於** `{"calls": 1, "usage": {}}`，
新增 `failed` 鍵就會壞。⇒ 把期望值補上 `failed`。
⚠️ **不准為了讓它過就把 `assertEqual` 放寬成 `assertIn` 或只比對部分鍵**——
那個「完全相等」的斷言是 037c 特意加強的，正是它讓這次的形狀改動被抓到。

---

## 6. 驗收條件

1. `python3 -m unittest discover tests` **全綠**。
2. `tests/test_contract_038.py` 八條全綠，且**你沒有修改過那八條的斷言**
   （可以新增你補的測試，但第 2 節那八條一字不改）。
3. 第 5 節的 2 條已按規定處理；**若你發現第 3 條**，停下來寫進報告，不要自行決定怎麼辦。
4. 第 3 節的差集分析已寫進報告（兩個方向都有內容）。
5. 報告裡列出你改了哪些檔、每個檔改了什麼、為什麼。
6. ⚠️ **UI 那一項（4.2 ①）沒有任何測試守得住**，交付報告要明說你改了什麼、
   以及你**怎麼確認它會顯示**（例如貼出你手動組一份含 `failed` 的 status 後的推導）。
   **不要宣稱你看過畫面**——你沒有瀏覽器。

---

## 7. 🔴 紅線

- **不准呼叫任何真實 CLI。** 這一包完全不需要 `--live`：假的 result dict 餵進
  `record_speech()` / `record_arbitration()` 就能重現全部行為。
- **不准碰 8765 埠，不准 kill 任何程序。**
- **不准動 git**（`add`／`commit`／`checkout`／`stash` 一律不准）。版控由主對話負責。
- **臨時檔一律放 `dispatch/tmp/038/`**，不要放 `/tmp`、不要放 repo 其他地方。
- **不准改 `AGENTS.md`、`SPEC.md`、`CLAUDE.md`** 或任何本工作包沒點名的檔。
- 這是 **PUBLIC repo**：新增或修改的內容裡**不得出現使用者名稱、家目錄絕對路徑、token**。
