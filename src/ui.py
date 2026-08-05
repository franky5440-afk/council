"""GET / 的靜態頁面：模組載入時讀一次，之後只在記憶體裡（工作包 024）。

本檔是全 repo 唯一開檔的伺服器端模組，而且只開一個寫死在原始碼裡、
相對於本模組的檔名——請求無法影響要開哪個檔（SPEC.md §7.2）。
"""

import os

_INDEX_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "static", "index.html")

with open(_INDEX_PATH, "rb") as handle:
    INDEX_HTML = handle.read()
