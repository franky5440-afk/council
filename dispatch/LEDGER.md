# 派工紀錄（append-only）

由 `dispatch.sh` 自動追加，**不就地改寫既有紀錄**；要更正就在最後追加更正段，
保留完整決策歷程。時間一律台灣時間（UTC+8）。

工作包原文存放於 `dispatch/packages/`（納入版控），可依下方檔名回查當初派了什麼。

## 2026-08-03 20:49 · 000-smoke.md

- 模式：新開
- session：`ses_03853d00affezAfeRrQN8lgbu5`
- 派工前 HEAD：`92d446db6d9a784d4dc080027b32dadac89fe080`（工作區未提交項目 1 個）
- opencode 退出碼：0
- 派工後工作區變更：
  - `?? SMOKE.md`
  - `?? dispatch/packages/`

## 2026-08-03 20:50 · 001-ambiguity-probe.md

- 模式：新開
- session：`ses_0385317c0ffefcl9RICMkdLJcf`
- 派工前 HEAD：`92d446db6d9a784d4dc080027b32dadac89fe080`（工作區未提交項目 2 個）
- opencode 退出碼：0
- 派工後工作區變更：
  - ` M dispatch/LEDGER.md`
  - `?? dispatch/BLOCKED.md`
  - `?? dispatch/packages/`
- ⚠ builder 回報卡關（見 BLOCKED.md）

## 2026-08-03 20:52 · 000-smoke.md

- 模式：新開
- session：`ses_03851720cffeMv3JVE8pQr4wpg`
- 派工前 HEAD：`92d446db6d9a784d4dc080027b32dadac89fe080`（工作區未提交項目 5 個）
- opencode 退出碼：0
- 派工後工作區變更：
  - ` M README.md`
  - ` M dispatch.sh`
  - ` M dispatch/LEDGER.md`
  - `?? SMOKE.md`
  - `?? dispatch/blocked/`
  - `?? dispatch/packages/`
- 上一輪卡關報告已歸檔：`dispatch/blocked/20260803-205211.md`

## 2026-08-03 21:14 · 002-adapter-detect.md

- 模式：新開
- session：`ses_0383cebf0ffed06UiSpywc03uK`
- 派工前 HEAD：`a4e6c40c57e2bb02cd94ef5e36a05696fd151040`（工作區未提交項目 1 個）
- opencode 退出碼：0
- 派工後工作區變更：
  - `?? dispatch/packages/002-adapter-detect.md`
  - `?? src/`
  - `?? tests/`

## 2026-08-03 21:20 · 003-detect-review-fixes.md

- 模式：接續 ses_0383cebf0ffed06UiSpywc03uK
- session：`ses_0383cebf0ffed06UiSpywc03uK`
- 派工前 HEAD：`a4e6c40c57e2bb02cd94ef5e36a05696fd151040`（工作區未提交項目 5 個）
- opencode 退出碼：0
- 派工後工作區變更：
  - ` M dispatch/LEDGER.md`
  - `?? dispatch/packages/002-adapter-detect.md`
  - `?? dispatch/packages/003-detect-review-fixes.md`
  - `?? src/`
  - `?? tests/`

## 2026-08-03 21:35 · 004-ask-base-opencode.md

- 模式：新開
- session：`ses_03829fe55ffexR5DNmBD5mVXc4`
- 派工前 HEAD：`a7b1b025e8f8167ee8c0b29e54aaa5d211e16d3d`（工作區未提交項目 1 個）
- opencode 退出碼：0
- 派工後工作區變更：
  - ` M src/adapters/base.py`
  - ` M src/adapters/claude.py`
  - ` M src/adapters/codex.py`
  - ` M src/adapters/gemini.py`
  - ` M src/adapters/opencode.py`
  - ` M tests/test_adapters_detect.py`
  - `?? dispatch/packages/004-ask-base-opencode.md`
  - `?? tests/test_adapters_ask.py`

## 2026-08-03 22:05 · 005-ask-remaining-three.md

- 模式：新開
- session：`ses_0380df9ceffeh4tOwQ67EPX7cs`
- 派工前 HEAD：`67e3586c1d1e3de3b2b5a2d0ba0de5dd2c8bdf81`（工作區未提交項目 0 個）
- opencode 退出碼：0
- 派工後工作區變更：
  - ` M src/adapters/base.py`
  - ` M src/adapters/claude.py`
  - ` M src/adapters/codex.py`
  - ` M src/adapters/gemini.py`
  - ` M src/adapters/opencode.py`
  - ` M tests/test_adapters_ask.py`
  - ` M tests/test_adapters_detect.py`

## 2026-08-03 22:11 · 006-lock-readonly-flags.md

- 模式：接續 ses_0380df9ceffeh4tOwQ67EPX7cs
- session：`ses_0380df9ceffeh4tOwQ67EPX7cs`
- 派工前 HEAD：`67e3586c1d1e3de3b2b5a2d0ba0de5dd2c8bdf81`（工作區未提交項目 9 個）
- opencode 退出碼：0
- 派工後工作區變更：
  - ` M dispatch/LEDGER.md`
  - ` M src/adapters/base.py`
  - ` M src/adapters/claude.py`
  - ` M src/adapters/codex.py`
  - ` M src/adapters/gemini.py`
  - ` M src/adapters/opencode.py`
  - ` M tests/test_adapters_ask.py`
  - ` M tests/test_adapters_detect.py`
  - `?? dispatch/packages/006-lock-readonly-flags.md`

## 2026-08-03 22:22 · 007-stderr-error-detail.md

- 模式：接續 ses_0380df9ceffeh4tOwQ67EPX7cs
- session：`ses_0380df9ceffeh4tOwQ67EPX7cs`
- 派工前 HEAD：`67e3586c1d1e3de3b2b5a2d0ba0de5dd2c8bdf81`（工作區未提交項目 10 個）
- opencode 退出碼：0
- 派工後工作區變更：
  - ` M dispatch/LEDGER.md`
  - ` M src/adapters/base.py`
  - ` M src/adapters/claude.py`
  - ` M src/adapters/codex.py`
  - ` M src/adapters/gemini.py`
  - ` M src/adapters/opencode.py`
  - ` M tests/test_adapters_ask.py`
  - ` M tests/test_adapters_detect.py`
  - `?? dispatch/packages/006-lock-readonly-flags.md`
  - `?? dispatch/packages/007-stderr-error-detail.md`

## 2026-08-03 22:38 · 008-argument-injection.md

- 模式：接續 ses_0380df9ceffeh4tOwQ67EPX7cs
- session：`ses_0380df9ceffeh4tOwQ67EPX7cs`
- 派工前 HEAD：`67e3586c1d1e3de3b2b5a2d0ba0de5dd2c8bdf81`（工作區未提交項目 11 個）
- opencode 退出碼：0
- 派工後工作區變更：
  - ` M dispatch/LEDGER.md`
  - ` M src/adapters/base.py`
  - ` M src/adapters/claude.py`
  - ` M src/adapters/codex.py`
  - ` M src/adapters/gemini.py`
  - ` M src/adapters/opencode.py`
  - ` M tests/test_adapters_ask.py`
  - ` M tests/test_adapters_detect.py`
  - `?? dispatch/packages/006-lock-readonly-flags.md`
  - `?? dispatch/packages/007-stderr-error-detail.md`
  - `?? dispatch/packages/008-argument-injection.md`
