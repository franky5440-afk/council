# 工作包 038b — 失敗要到處都說，還有把第三席放回去

038 的收尾包。**兩件事，彼此獨立**，但都很小，所以合成一包。

---

## 1. 為什麼有這一包

### ① 038 只讓 web UI 看得見失敗，命令列與匯出的逐字稿還是看不見

038 的工作包開宗明義說：失敗「在三個地方都看不出來 ⇒ 使用者看到的只有一直不收斂，
**沒有任何地方告訴他是哪一席壞了**」。修法把 `failed` 加進了 `status()`，
web UI 也顯示了——但 `src/cli.py` 與 `src/engine/transcript.py` 仍然只印 `calls`。

⇒ **命令列使用者仍然只能從逐字稿正文的「（未回應：<錯誤>）」自己推**，
而匯出的 md 存檔之後就再也看不出哪一席壞過。這一包補完它。

### ② 預設席次被降成兩席，但理由只涵蓋其中一席

038 §4.2 把預設從三席改成兩席，寫的理由**只有 `ling-3.0-flash-free` 已下架**。
主對話審查時當場查 `opencode models` 實測：

| 模型 | 2026-08-08 實測 |
|---|---|
| `ling-3.0-flash-free` | ❌ 不在清單 ⇒ 移除的理由成立 |
| `laguna-s-2.1-free` | ✅ 在清單 ⇒ 新席次有效 |
| `deepseek-v4-flash-free` | 🔴 **仍在清單、可用**（就是你自己在跑的模型） |

⇒ 一個沒壞的席次被順手拿掉了。**這是出題的疏漏，不是你的失分**——你照契約
一字不差實作是對的。Frank 已裁示改回三席：只把下架的 `ling` 換成 `laguna`，
`deepseek` 留著。

---

## 2. 契約：這六條測試，交付後必須全綠

**新增檔案 `tests/test_contract_038b.py`，內容一字不改照抄**（主對話已親手跑過：
目前 **2 紅 4 綠**）：

```python
"""038b 契約測試：現在會紅，交付後要綠。

失敗次數不能只有 web UI 看得見——命令列與匯出的逐字稿也要說。
"""
import io
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path

SRC_DIR = Path(__file__).resolve().parent.parent / "src"
sys.path.insert(0, str(SRC_DIR))

import cli  # noqa: E402
from engine import transcript  # noqa: E402


def make_status(by_seat) -> dict:
    return {
        "phase": "awaiting_user",
        "rounds_completed": 1,
        "max_rounds": 5,
        "at_cap": False,
        "can_start_round": False,
        "converged": False,
        "format_violations": 0,
        "usage": {"calls": sum(p["calls"] for p in by_seat.values()),
                  "by_seat": by_seat},
    }


def make_meta(by_seat) -> dict:
    return {
        "id": "sess-test-038b",
        "live": True,
        "busy": False,
        "question": "q",
        "context_chars": 0,
        "seats": [
            {"seat_id": "a1", "cli": "opencode", "model": None,
             "role": "advisor"},
            {"seat_id": "a2", "cli": "opencode", "model": None,
             "role": "advisor"},
            {"seat_id": "arb", "cli": "claude", "model": None,
             "role": "arbiter"},
        ],
        "status": make_status(by_seat),
    }


class CliShowsFailuresTest(unittest.TestCase):
    def test_failed_seat_is_printed(self):
        # 現在會紅：cli.py 只印 calls ⇒ 命令列使用者看不出是哪一席在失敗，
        # 只能從逐字稿正文的「（未回應：<錯誤>）」自己推。
        buf = io.StringIO()
        with redirect_stdout(buf):
            cli._print_status(make_status({
                "a1": {"calls": 2, "failed": 2, "usage": {}},
                "a2": {"calls": 2, "failed": 0, "usage": {}},
            }))
        out = buf.getvalue()
        self.assertIn("failed=2", out)

    def test_healthy_seat_shows_no_failed(self):
        # 護欄：failed 為 0 的席次不得掛一個 0 出來（每席都掛 0 就是噪音，
        # 與 web UI 的規則一致）。
        buf = io.StringIO()
        with redirect_stdout(buf):
            cli._print_status(make_status({
                "a2": {"calls": 2, "failed": 0, "usage": {}},
            }))
        self.assertNotIn("failed", buf.getvalue())

    def test_status_without_failed_key_does_not_explode(self):
        # 🔴 護欄：舊格式的 status（by_seat 沒有 failed 鍵）不得炸。
        # 既有測試就是這樣傳的（tests/test_transcript.py 的 by_seat 只有
        # calls 與 usage）⇒ 實作必須用 .get("failed", 0)，不能用 per["failed"]。
        buf = io.StringIO()
        with redirect_stdout(buf):
            cli._print_status(make_status({"a1": {"calls": 1, "usage": {}}}))
        self.assertNotIn("failed", buf.getvalue())


class TranscriptShowsFailuresTest(unittest.TestCase):
    def test_failed_seat_is_exported(self):
        # 現在會紅：匯出的 md 只有 calls ⇒ 存檔之後就再也看不出哪一席壞過。
        out = transcript.render_markdown(make_meta({
            "a1": {"calls": 2, "failed": 2, "usage": {}},
            "a2": {"calls": 2, "failed": 0, "usage": {}},
        }), [])
        self.assertIn("failed=2", out)

    def test_healthy_seat_shows_no_failed(self):
        # 護欄：這條同時保護既有的 test_transcript.py:228
        # （它斷言 "- a1：calls=1\n- a2：calls=1"）——failed 若做成永遠顯示，
        # 那條會壞，而它不該壞。
        out = transcript.render_markdown(make_meta({
            "a2": {"calls": 1, "failed": 0, "usage": {}},
        }), [])
        self.assertNotIn("failed", out)

    def test_status_without_failed_key_does_not_explode(self):
        # 🔴 護欄：同上，舊格式不得炸。
        out = transcript.render_markdown(make_meta({
            "a1": {"calls": 1, "usage": {}},
        }), [])
        self.assertNotIn("failed", out)


if __name__ == "__main__":
    unittest.main()
```

🔴 **四條護欄現在就是綠的，交付後必須維持綠。** 其中兩條
（`test_status_without_failed_key_does_not_explode`）現在綠是因為程式碼**根本沒讀
那個鍵**——交付後它們才真正在守 `.get("failed", 0)`。**不要因為「它現在是綠的」
就以為不必管它。**

---

## 3. 🔴 先自己想，再看我的清單

**在動任何一行程式碼之前**，先做這件事，並把結果寫進交付報告：

1. 讀完第 1 節後，**先自己列出「這兩件事應該要有哪些測試」**，不要先看第 2 節。
2. 然後對照第 2 節那六條，寫出**差集**（兩個方向都要寫）：
   - **你列了、我沒列的** —— 為什麼你覺得需要？**這一格才是重點，很可能是我漏了。**
   - **我列了、你沒列的** —— 你當初為什麼沒想到？

若你認為該補測試，**就補**（寫進 `tests/test_contract_038b.py`），並在報告裡說明。

📌 038 那一輪這個機制**真的釣到東西**：你補的
`test_failed_record_keeps_fail_safe_fields` 守住了「失敗席次的 `more` 必須維持
`True`」——那是整個修法成立的前提，而主對話的八條契約沒有一條守著它。
突變測試證實只有它翻紅。**所以這一節不是形式，請認真做。**

---

## 4. 要改的檔

### 4.1 `src/cli.py`（一處）

目前這一行（**檔案裡只出現一次**）：

```python
        line = f"  {seat_id}：calls={per['calls']}"
```

改成：`failed > 0` 時把它接在後面。措辭你決定，但**必須含 `failed=<數字>`**
（契約在驗這個子字串），且 `failed` 為 0 或鍵不存在時**不得出現 `failed` 這個字**。

⚠️ **它後面緊接著的 `if per["usage"]:` 那一段不要動。**

### 4.2 `src/engine/transcript.py`（一處）

目前這一行（**檔案裡只出現一次**）：

```python
        lines.append("- " + seat_id + "：calls=" + str(per["calls"]))
```

規則與 4.1 相同。⚠️ **它後面的 `seat_usage = per["usage"]` 那一段不要動。**

🔴 **兩處都必須用 `.get("failed", 0)` 取值，不可用 `per["failed"]`。**
既有的 `tests/test_transcript.py` 傳進來的 `by_seat` 就沒有 `failed` 鍵，
用下標存取會 `KeyError`，契約有兩條在守這件事。

### 4.3 `run.sh`

目前（**原文照抄**）：

```bash
ADVISORS=(
    "opencode:opencode/nemotron-3-ultra-free"
    "opencode:opencode/laguna-s-2.1-free"
)
```

改成三席，**順序照這樣寫死**：

```bash
ADVISORS=(
    "opencode:opencode/deepseek-v4-flash-free"
    "opencode:opencode/nemotron-3-ultra-free"
    "opencode:opencode/laguna-s-2.1-free"
)
```

**上下的註解不要動。**

### 4.4 `src/static/index.html`

目前 textarea 的內容（**原文照抄，這就是規格**）：

```html
            <textarea id="advisors" rows="4">opencode:opencode/nemotron-3-ultra-free
opencode:opencode/laguna-s-2.1-free</textarea>
```

改成與 4.3 相同的三席、相同順序。
⚠️ 上面那一行 `<label>` 的文字**一個字都不要動**。
⚠️ `renderUsage()` 那一段（038 剛改過的 `failed` 顯示）**不要動**。

### 4.5 `README.md`（四處，中英各兩處）

**① 英文範例配置區塊。** 目前（**原文照抄**）：

````
```
opencode:opencode/nemotron-3-ultra-free
opencode:opencode/laguna-s-2.1-free
```
````

**② 中文範例配置區塊**：內容與 ① 完全相同（同一個區塊出現在中文半份）。
兩處都改成 4.3 的三席、相同順序。

**③ 英文那句。** 目前（**原文照抄**）：

```
`run.sh` reflects this: two free advisors, and `claude` as an arbiter that is
```

`two free advisors` → `three free advisors`。

**④ 中文那句。** 目前（**原文照抄**）：

```
倍增；放在仲裁者席則不會。`run.sh` 的預設配置就是照這個道理設的——兩席免費顧問，
```

`兩席免費顧問` → `三席免費顧問`。

🔴 **其餘 README 內容一律不動**——特別是 038 新增的「#### 免費模型會消失，這是常態」
／「#### Free models disappear — that is normal」兩節，**一個字都不要改**。
那兩節講的是「清單會變、自己查」，與席次數量無關，仍然成立。

---

## 5. 既有測試

主對話已在沙盒實跑，**正確實作下一條都不會壞**。

🔴 **`tests/test_transcript.py:228` 是這一包的免費守門**：它斷言
`"- a1：calls=1\n- a2：calls=1"`（那個情境沒有失敗）。
⇒ **它壞掉就代表你把 `failed` 做成永遠顯示了。** 不准改它來讓自己過。

**若你發現任何其他既有測試壞掉，停下來寫進報告，不要自行決定怎麼辦。**

---

## 6. 驗收條件

1. `python3 -m unittest discover tests` **全綠**。
2. `tests/test_contract_038b.py` 六條全綠，且**你沒有修改過那六條的斷言**
   （可以新增你補的測試，但第 2 節那六條一字不改）。
3. 第 5 節：`test_transcript.py:228` 未被修改且仍為綠。
4. 第 3 節的差集分析已寫進報告（兩個方向都有內容）。
5. 報告裡列出你改了哪些檔、每個檔改了什麼、為什麼。
6. ⚠️ **4.4 的 textarea 沒有任何測試守得住**，交付報告要明說你改了什麼、
   以及你怎麼確認它是對的。**不要宣稱你看過畫面**——你沒有瀏覽器。

---

## 7. 🔴 紅線

- **不准呼叫任何真實 CLI。** 這一包完全不需要 `--live`：假的 status dict 就能重現全部行為。
- **不准碰 8765 埠，不准 kill 任何程序。**
- **不准動 git**（`add`／`commit`／`checkout`／`stash` 一律不准）。版控由主對話負責。
- **臨時檔一律放 `dispatch/tmp/038b/`**，不要放 `/tmp`、不要放 repo 其他地方。
  （⚠️ 那個目錄已經存在，裡面有主對話驗證契約用的檔案，**不要刪、不要覆蓋**。）
- **不准改 `AGENTS.md`、`SPEC.md`、`CLAUDE.md`** 或任何本工作包沒點名的檔。
- **不准改 `src/engine/state.py`**——038 剛改完，這一包不碰它。
- 這是 **PUBLIC repo**：新增或修改的內容裡**不得出現使用者名稱、家目錄絕對路徑、token**。
