# 工作包 002：Adapter 骨架與 detect()

先讀 `SPEC.md`，特別是 §4（Adapter 介面契約）與 §7（技術選型）。本包只做 `detect()`。

## 目標

建立 adapter 套件骨架，並為四個 CLI 各實作 `detect()`。

`ask()` 本包**不實作**，只留簽章並 `raise NotImplementedError`——後續工作包會接手，
你現在把它寫掉會與後面的包衝突。

## 檔案配置（照這個路徑，不要自行更動）

```
src/adapters/__init__.py     registry：ADAPTERS 與 detect_all()
src/adapters/base.py         共用工具（找執行檔、跑子行程取版本）
src/adapters/claude.py
src/adapters/codex.py
src/adapters/gemini.py
src/adapters/opencode.py
tests/test_adapters_detect.py
```

## 介面

每個 CLI 模組提供：

```python
ID = "claude"          # 各模組換成自己的 id
def detect() -> dict   # 回傳格式見 SPEC.md §4
def ask(prompt: str, timeout_s: int, max_chars: int) -> dict:
    raise NotImplementedError
```

`src/adapters/__init__.py` 提供：

```python
ADAPTERS = {...}              # id -> module
def detect_all() -> list[dict]  # 依 ADAPTERS 順序回傳每個 detect() 的結果
```

## detect() 的具體行為

1. 用 `shutil.which(<cmd>)` 找執行檔。找不到 → `{"installed": False, "path": None,
   "version": None, "error": "not found in PATH"}`。
2. 找到就以子行程執行 `<cmd> --version`，**逾時 10 秒**，逾時即終止並回報。
3. 版本＝該指令輸出的第一行去除空白。抓不到或格式不符 →
   `installed=True, version=None`，並在 `error` 說明，**不要猜一個版本號**。
4. 執行檔存在但指令失敗（非零退出碼）→ `installed=True, version=None`，
   `error` 放**簡短可讀的說明**，不要整坨 stderr 倒進去。
5. 每個回傳的 dict 都必須含 `id` 欄位。

**`detect()` 絕對不可發出任何會消耗使用者訂閱額度的呼叫。** 只准 `--version`。

## 測試（`tests/test_adapters_detect.py`，用標準庫 `unittest`）

不要引入第三方測試套件。**不要在測試中呼叫真實 CLI。**
作法：在暫存目錄放假的可執行腳本，把該目錄加到 `PATH` 前面，藉此測試：

- 執行檔不存在 → `installed=False`
- 假執行檔印出版本 → `installed=True` 且版本正確
- 假執行檔以非零退出碼結束 → `installed=True, version=None, error` 非空
- 假執行檔卡住不結束 → 逾時被終止，`error` 非空（用很短的 timeout 測，別讓測試跑 10 秒）
- `detect_all()` 回傳筆數等於 `ADAPTERS` 筆數

## 驗收條件

1. `python3 -m unittest discover tests -v` 全數通過。**貼出真實輸出。**
2. 實際在本機跑一次 `detect_all()` 並貼出真實回傳（這只跑 `--version`，不耗額度）。
3. 不修改 `SPEC.md`、`AGENTS.md`、`dispatch.sh`、`README.md`。
4. 不使用任何第三方套件。

## 提醒

- 沒實際跑過的東西不要說它會動；沒驗證的部分明確標「未驗證」。
- 不要 `git add` / `git commit`。改動留在工作區。
