# 工作包 036 — web UI 淡化背景圖（元老院）

## 這一包在做什麼

Frank 要在 web UI 背後放一張淡化的元老院圖。**視覺方案已經由他看過三個變體後拍板**
（面板半透明那一版），所以本包**沒有任何設計選擇留給你**——色值、CSP、CSS 全部寫死在下面。

**動兩個檔：`src/static/index.html` 與 `tests/test_ui.py`。** 其他一律不准動。

🔴 **這件事會打到兩條既有的紅線測試，那是預期中的，不是意外。**
但**紅線不是刪掉，是收窄**——理由見 §4.2。**不准用「反正要放圖」為由把守門整條拿掉。**

---

## 1. 素材（已經產好，不要重新生成）

檔案：`output/council-bg.jpg`（1280×853、JPEG、約 54 KB）

🔴 **先驗這是不是同一個檔**，不對就開 BLOCKED，不要將就：

```bash
sha256sum output/council-bg.jpg
# 必須是 816b5ec84525dace8bc9b31fc116e91a3f4e2d3d1cef1096ba3fdf5dde7a443a
```

⚠️ **不准自己重新產生這個 jpg**（不要跑 PIL／ffmpeg 去 resize 或調亮度）。
它的淡化程度是 Frank 本人挑過的，重壓一次就不是他核可的那一版了。

⚠️ **`output/` 是未版控目錄**，這個 jpg 只是編碼來源、不是交付物。
**交付物是 `index.html` 裡的那串 base64。**

---

## 2. 為什麼是內嵌 data URI，不是開一條圖片路由

（背景說明，不用你做決定，但**不要「順手改良」成路由版**。）

- 開路由要動 `src/server.py`——那是資安敏感檔，為一張裝飾圖去動它不划算。
- `DESIGN-NOTES.md` §1 有一條紅線：**`server.py` 不得出現 `open(`**。內嵌 data URI
  完全不碰伺服器端程式碼，`src/ui.py` 讀檔的方式一個字都不用改。
- CSP 改成 `img-src data:` **比改成 `img-src 'self'` 更保守**：`data:` 根本發不出網路請求。

---

## 3. 改 `src/static/index.html`

🔴 **不要手動貼那串 base64。** 它有七萬多字元，手貼必然出錯，而且錯了看起來還很像對的。
**用下面這支腳本改**，逐字照抄：

```bash
mkdir -p dispatch/tmp/036-backup
cp src/static/index.html tests/test_ui.py dispatch/tmp/036-backup/
```

```python
# 存成 dispatch/tmp/036-backup/apply.py，然後 python3 dispatch/tmp/036-backup/apply.py
import base64, hashlib, pathlib

jpg = pathlib.Path("output/council-bg.jpg").read_bytes()
assert hashlib.sha256(jpg).hexdigest() == (
    "816b5ec84525dace8bc9b31fc116e91a3f4e2d3d1cef1096ba3fdf5dde7a443a"), "素材不對"
b64 = base64.b64encode(jpg).decode("ascii")

p = pathlib.Path("src/static/index.html")
html = p.read_text(encoding="utf-8")

BODY_NEW = (
    '  background-color: var(--bg);\n'
    f'  background-image: url("data:image/jpeg;base64,{b64}");\n'
    '  background-size: cover;\n'
    '  background-position: center center;\n'
    '  background-attachment: fixed;\n'
    '  background-repeat: no-repeat;'
)

EDITS = [
    ("  background: var(--bg);", BODY_NEW),
    ("img-src 'none'", "img-src data:"),
    ("  --panel:      #17181A;", "  --panel:      rgba(23,24,26,.80);"),
    ("  --panel-2:    #1E1F22;", "  --panel-2:    rgba(30,31,34,.85);"),
    ("  --panel-3:    #26282C;", "  --panel-3:    rgba(38,40,44,.88);"),
]
for old, new in EDITS:
    # 取代前先確認樣式唯一：打到同名的另一段，症狀跟成功長得一模一樣。
    n = html.count(old)
    assert n == 1, f"樣式不唯一：{old!r} 出現 {n} 次"
    html = html.replace(old, new, 1)

p.write_text(html, encoding="utf-8")
print("已套用")
```

### 3.1 這五處改動分別是什麼（供你核對，不是要你另外做）

| # | 原文 | 改成 |
|---|---|---|
| 1 | `body` 裡的 `background: var(--bg);` | 六行 `background-*`（底色＋data URI 圖＋cover／center／fixed／no-repeat） |
| 2 | CSP 的 `img-src 'none'` | `img-src data:` |
| 3 | `--panel:      #17181A;` | `rgba(23,24,26,.80)` |
| 4 | `--panel-2:    #1E1F22;` | `rgba(30,31,34,.85)` |
| 5 | `--panel-3:    #26282C;` | `rgba(38,40,44,.88)` |

⚠️ **三個色票的 RGB 與原本的 hex 完全相同**（`#17181A` ＝ 23,24,26），**只加了 alpha**。
不是換色，是讓面板透出背景。**不要順手調整色相或亮度。**

⚠️ **`background-attachment: fixed` 是刻意的**：捲動時背景不動，圖才像襯底而不是內容。

---

## 4. 改 `tests/test_ui.py`

### 4.1 `CSP_EXACT` 常數（第 18–20 行）

原文逐字是：

```python
CSP_EXACT = ("default-src 'none'; script-src 'unsafe-inline'; "
             "style-src 'unsafe-inline'; connect-src 'self'; img-src 'none'; "
             "form-action 'none'; base-uri 'none'")
```

改成（**只有 `img-src` 那一段變**）：

```python
CSP_EXACT = ("default-src 'none'; script-src 'unsafe-inline'; "
             "style-src 'unsafe-inline'; connect-src 'self'; img-src data:; "
             "form-action 'none'; base-uri 'none'")
```

### 4.2 `test_no_external_resources`（約第 215–221 行）

原文逐字是：

```python
    def test_no_external_resources(self):
        """CSP 是 img-src 'none'／default-src 'none'，外部資源一律載不到
        （background-image: url(...)、@font-face 字型檔、data: URI 都被擋掉），
        而 SVG 的 xmlns 屬性會帶進 http:// 踩爆既有的 test_no_http_urls。
        ⇒ 不得出現 url() 與 <svg，一律用純 CSS 與 unicode 字元。"""
        self.assertNotIn("url(", self.source)
        self.assertNotIn("<svg", self.source)
```

🔴 **這條測試守的不是「不准有圖」，是「不准有 CSP 會靜默擋掉的資源」**——因為被擋掉的
後果是畫面留白，**而那件事在 Python 測試裡看不出來**。現在多了一個被 CSP 明確允許的
例外（那張內嵌背景），所以**守門要收窄成「例外恰好一個」，不是拿掉**。

**函式名不要改**（data URI 不是 external resource，原名仍然成立）。改成：

```python
    def test_no_external_resources(self):
        """CSP 是 default-src 'none'，凡它擋掉的資源都會靜默留白，
        而那件事在 Python 測試裡看不出來 ⇒ 這裡守住「頁面只引用被明確允許的資源」。

        目前**恰好一個**例外：工作包 036 內嵌的淡化背景圖，走 data: URI，
        對應 CSP 的 img-src data:。任何第二個 url()（外部字型、外部圖片、
        指向網路的背景）都會讓這條翻紅——那正是要攔的東西。

        <svg 仍然全面禁止：它的 xmlns 屬性會帶進 http:// 踩爆 test_no_http_urls。"""
        self.assertEqual(self.source.count("url("), 1)
        self.assertIn('url("data:image/jpeg;base64,', self.source)
        self.assertNotIn("<svg", self.source)
```

### 4.3 新增一條：內嵌的 blob 真的是一張完整 JPEG

🔴 **加在 `test_no_external_resources` 正下方，同一個 class 裡。**

理由：那串 base64 有七萬多字元，**沒有任何人會在 code review 時用眼睛看它**。
截斷或損壞的話畫面只是背景不見，不會有任何測試翻紅。這條是它唯一的完整性檢查。

```python
    def test_background_data_uri_decodes_to_a_jpeg(self):
        """背景是七萬多字元的 base64，沒有人會在 review 時用眼睛看它。
        截斷或損壞不會讓任何其他測試翻紅（畫面只是背景不見）⇒ 這裡機械檢查一次。"""
        match = re.search(
            r'url\("data:image/jpeg;base64,([A-Za-z0-9+/=]+)"\)', self.source)
        self.assertIsNotNone(match, "找不到背景圖的 data URI")
        raw = base64.b64decode(match.group(1), validate=True)
        self.assertTrue(raw.startswith(b"\xff\xd8\xff"), "不是 JPEG 開頭")
        self.assertTrue(raw.rstrip().endswith(b"\xff\xd9"), "JPEG 結尾不完整（可能被截斷）")
        self.assertGreater(len(raw), 20_000)
```

⚠️ 這條需要 `base64` 與 `re`。檔案開頭現在是：

```python
import json
import sys
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path
```

**只補缺的兩個 import，維持既有的字母順序**（`base64` 排在 `json` 前、`re` 排在
`json` 後）。不要動其他 import。

---

## 5. 🔴 不准做的事

- **不准動** `src/server.py`、`src/ui.py`、`src/serve.py`、`src/engine/`、`src/adapters/`、
  `run.sh`、`start.sh`、`README.md`、`SPEC.md`、`AGENTS.md`、`DESIGN-NOTES.md`、`.gitignore`。
  **這一包只有 `src/static/index.html` 與 `tests/test_ui.py` 兩個檔會變。**
- **不准新增任何檔案到 `src/`**（不要把 jpg 複製進去、不要開 `static/img/`）。
- **不准重新產生或修改 `output/council-bg.jpg`**，只准讀它。
- **不准刪掉任何一條既有測試。** `test_no_external_resources` 是**改**不是刪。
- **不准碰 8765 埠**：Frank 可能有伺服器在上面跑。不要 `kill`／`pkill`／`fuser`，
  也不要對 8765 發任何請求或做連線偵測。驗證一律用 8790。
- **不准跑 `--live`**、**不准呼叫任何 CLI**（claude／codex／gemini／opencode）、
  **不准執行任何版控指令**（`git add`／`commit`／`checkout`／`stash` 一律禁止）。
- 臨時檔一律放 `dispatch/tmp/036-backup/`，見 §3。

---

## 6. 驗證（強制，逐項附上實際輸出）

### 6.1 全套測試

```bash
python3 -m unittest discover tests
```

**目前是 338 條**，你會新增 1 條 ⇒ **應該是 `Ran 339 tests` ＋ `OK`**。
🔴 附上實際最後三行。**有任何一條紅就不要交付**，寫清楚哪條紅、為什麼。

### 6.2 突變測試（證明新的守門真的守得住）

🔴 **改壞之前先確認樣式唯一**（打到同名的另一段，翻紅的會是別人的測試，
畫面上是漂亮的一片紅但你要驗的那一側完全沒被驗到）。

三個突變，**每個做完都要還原**（用 python 原地改回去，**不准用 `git checkout`**）：

| # | 把什麼改壞 | 應該翻紅的是 |
|---|---|---|
| 1 | `index.html` 的 CSP 改回 `img-src 'none'` | `test_csp_meta_exact` |
| 2 | `index.html` 裡多塞一個 `url(https://example.com/x.png)` 進 `<style>` | `test_no_external_resources`（`url(` 從 1 變 2）**與** `test_no_http_urls` |
| 3 | 把 base64 blob 尾端砍掉 5000 字元 | `test_background_data_uri_decodes_to_a_jpeg` |

🔴 **翻紅之後要看一眼紅的是不是預期的那幾個測試名**，不是只看到 FAILED 就算過。
把實際的測試名貼進回報。

### 6.3 伺服器真的把背景送出去了

```bash
python3 src/serve.py --port 8790 &
sleep 2
curl -s http://127.0.0.1:8790/ | grep -c 'background-image: url("data:image/jpeg;base64,'
# 應為 1
curl -s -D- -o /dev/null http://127.0.0.1:8790/ | grep -i "content-security-policy\|x-frame-options"
# X-Frame-Options: DENY 與 frame-ancestors 'none' 都必須還在
curl -s -X POST http://127.0.0.1:8790/api/shutdown -H "Content-Type: application/json" -d '{}'
sleep 2
ps -eo comm,args | awk '$1=="python3" && /serve\.py/'
# 空的＝沒有殘留
```

⚠️ **最後那行的寫法是刻意的**：`ps -eo pid,args | grep '[s]erve\.py'` 會匹配到
包裹指令的那層 shell，回報出根本不存在的殘留程序。**按執行檔名過濾才準。**

🔴 **驗證結束後不得留下任何背景程序**，把上面最後一行的實際輸出貼進回報。

### 6.4 檔案範圍

```bash
git status --short
git diff --stat
```

**只准出現 `src/static/index.html` 與 `tests/test_ui.py` 兩個檔。**
（`dispatch/tmp/` 是被 `.gitignore` 排除的，不會出現，這是正常的。）

### 6.5 ⚠️ 視覺**不是**你的驗收項

背景好不好看、夠不夠淡，**由 Frank 用眼睛驗**。
**不要開瀏覽器、不要截圖、不要為了「確認看起來對」去調 alpha 或亮度。**
你的驗收止於「機械上正確」：測試全過、突變守得住、伺服器送得出去、範圍沒超出。

---

## 7. 交付前自己確認

- [ ] `sha256sum output/council-bg.jpg` 與 §1 相符
- [ ] `index.html` 五處改動全部套用（§3.1 表格逐項核對）
- [ ] `CSP_EXACT` 只有 `img-src` 那一段變
- [ ] `test_no_external_resources` 是**改**不是刪，函式名未改
- [ ] 新增 `test_background_data_uri_decodes_to_a_jpeg`，只補了 `base64` 與 `re` 兩個 import
- [ ] `python3 -m unittest discover tests` → **339 OK**，附實際輸出
- [ ] §6.2 三個突變**都翻紅**，且**紅的是預期那幾條測試名**，附實際測試名；三個都已還原
- [ ] §6.3 `curl` 抓到背景、安全標頭還在、**無殘留程序**，附實際輸出
- [ ] `git diff --stat` → **只有兩個檔**
- [ ] 全程沒有碰 8765、沒有 `--live`、沒有呼叫任何 CLI、沒有執行任何版控指令

---

## 8. 卡住怎麼辦

契約有矛盾、或某條驗收條件在任何實作下都不可能成立 ⇒ 寫 `dispatch/BLOCKED.md`
說明卡在哪一條，**不要自己選一個讀法硬做**。

特別是：如果 §3 的哪個「樣式唯一」斷言失敗（代表 `index.html` 已經不是我看到的那一版），
**立刻停手開 BLOCKED**，不要自己找一個相近的字串去替代。
