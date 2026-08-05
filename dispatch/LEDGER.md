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

## 2026-08-03 22:55 · 009-opencode-readonly.md

- 模式：接續 ses_0380df9ceffeh4tOwQ67EPX7cs
- session：`ses_0380df9ceffeh4tOwQ67EPX7cs`
- 派工前 HEAD：`d2b274436485bd1af9952ba1049f7df58cfddd92`（工作區未提交項目 2 個）
- opencode 退出碼：0
- 派工後工作區變更：
  - ` M SPEC.md`
  - ` M src/adapters/base.py`
  - ` M src/adapters/claude.py`
  - ` M src/adapters/codex.py`
  - ` M src/adapters/gemini.py`
  - ` M src/adapters/opencode.py`
  - ` M tests/test_adapters_ask.py`
  - `?? dispatch/packages/009-opencode-readonly.md`

## 2026-08-03 23:33 · 010-stdin-probe.md

- 模式：新開
- session：`ses_037be15c8ffew0jVNV6beozGTW`
- 派工前 HEAD：`6c16975b99ceb29f1a26cff4ab6295544d1e3a8a`（工作區未提交項目 1 個）
- opencode 退出碼：0
- 派工後工作區變更：
  - `?? dispatch/packages/010-stdin-probe.md`

## 2026-08-04 00:06 · 011-stdin-transport.md

- 模式：新開
- session：`ses_0379f4860ffe4aOmF62KKW1ob0`
- 派工前 HEAD：`d78e45f134de26b93142bccb877b277b99f6017f`（工作區未提交項目 3 個）
- opencode 退出碼：0
- 派工後工作區變更：
  - ` M dispatch/LEDGER.md`
  - ` M src/adapters/base.py`
  - ` M src/adapters/claude.py`
  - ` M src/adapters/codex.py`
  - ` M src/adapters/gemini.py`
  - ` M src/adapters/opencode.py`
  - ` M tests/test_adapters_ask.py`
  - `?? dispatch/packages/010-stdin-probe.md`
  - `?? dispatch/packages/011-stdin-transport.md`

## 2026-08-04 00:22 · 012-fix-011.md

- 模式：接續 ses_0379f4860ffe4aOmF62KKW1ob0
- session：`ses_0379f4860ffe4aOmF62KKW1ob0`
- 派工前 HEAD：`66b6b9a8f7edbfab011e715be0baeab7491dd535`（工作區未提交項目 10 個）
- opencode 退出碼：0
- 派工後工作區變更：
  - ` M dispatch/LEDGER.md`
  - ` M src/adapters/base.py`
  - ` M src/adapters/claude.py`
  - ` M src/adapters/codex.py`
  - ` M src/adapters/gemini.py`
  - ` M src/adapters/opencode.py`
  - ` M tests/test_adapters_ask.py`
  - `?? dispatch/packages/010-stdin-probe.md`
  - `?? dispatch/packages/011-stdin-transport.md`
  - `?? dispatch/packages/012-fix-011.md`

## 2026-08-04 00:48 · 013-codex-model-header-only.md

- 模式：新開
- session：`ses_0377928f8ffewS9jZ0gXYuzIFG`
- 派工前 HEAD：`c4a6f39932ddab55db24f9cf403b683cd07537c9`（工作區未提交項目 1 個）
- opencode 退出碼：0
- 派工後工作區變更：
  - ` M src/adapters/codex.py`
  - ` M tests/test_adapters_ask.py`
  - `?? dispatch/packages/013-codex-model-header-only.md`

## 2026-08-04 01:34 · 014-engine-state-boundaries.md

- 模式：新開
- session：`ses_0374e95c6ffezWPwpB6kVsmZxX`
- 派工前 HEAD：`78edd7d16ed0fb638071f347d7eb08de59418ed2`（工作區未提交項目 0 個）
- opencode 退出碼：0
- 派工後工作區變更：
  - `?? src/engine/`
  - `?? tests/test_engine_state.py`

## 2026-08-04 01:43 · 015-status-field-tests.md

- 模式：接續 ses_0374e95c6ffezWPwpB6kVsmZxX
- session：`ses_0374e95c6ffezWPwpB6kVsmZxX`
- 派工前 HEAD：`ea68b5a8dcf2c37b53eaa56724f12d96b3fa9b01`（工作區未提交項目 1 個）
- opencode 退出碼：0
- 派工後工作區變更：
  - ` M tests/test_engine_state.py`
  - `?? dispatch/packages/015-status-field-tests.md`

## 2026-08-05 21:05 · 016-round-orchestration.md

- 模式：新開
- session：`ses_02df81bc4ffeedx4wtvRphoMxC`
- 派工前 HEAD：`7036813c418346589ddaf5c48a1f3c29c1fc66c0`（工作區未提交項目 1 個）
- opencode 退出碼：0
- 派工後工作區變更：
  - `?? dispatch/packages/016-round-orchestration.md`
  - `?? src/engine/orchestrator.py`
  - `?? tests/test_engine_orchestrator.py`

## 2026-08-05 21:32 · 017-wiring-and-cli-entry.md

- 模式：新開
- session：`ses_02ddfcb39ffeVRWasvW9NeeGRv`
- 派工前 HEAD：`2a19bc7e0035e69a0dbaac63ca1d8e0c2c6319c7`（工作區未提交項目 1 個）
- opencode 退出碼：0
- 派工後工作區變更：
  - `?? dispatch/packages/017-wiring-and-cli-entry.md`
  - `?? src/cli.py`
  - `?? src/engine/wiring.py`
  - `?? tests/test_engine_wiring.py`

## 2026-08-05 22:07 · 018-context-injection.md

- 模式：新開
- session：`ses_02dc02a43ffeH4r0Tt3KDBGm29`
- 派工前 HEAD：`44b9441cb101f79630e00c2ef47be23f2d9aae10`（工作區未提交項目 1 個）
- opencode 退出碼：0
- 派工後工作區變更：
  - ` M src/cli.py`
  - ` M src/engine/orchestrator.py`
  - ` M src/engine/state.py`
  - ` M src/engine/wiring.py`
  - ` M tests/test_engine_orchestrator.py`
  - ` M tests/test_engine_state.py`
  - ` M tests/test_engine_wiring.py`
  - `?? dispatch/packages/018-context-injection.md`

## 2026-08-05 22:29 · 019-arbitration.md

- 模式：新開
- session：`ses_02dabad5dffeLxt0TiVcocmEOT`
- 派工前 HEAD：`7becc42f5526cd04881c9e2e55adad7513c84532`（工作區未提交項目 0 個）
- opencode 退出碼：0
- 派工後工作區變更：
  - ` M run.sh`
  - ` M src/cli.py`
  - ` M src/engine/orchestrator.py`
  - ` M src/engine/state.py`
  - ` M tests/test_engine_orchestrator.py`
  - ` M tests/test_engine_state.py`

## 2026-08-05 22:54 · 020-session-store.md

- 模式：新開
- session：`ses_02d948804ffeU1IXO46y5pjRav`
- 派工前 HEAD：`fdac57caac9169a00034dbe2fcbacf5c79a9ba42`（工作區未提交項目 0 個）
- opencode 退出碼：0
- 派工後工作區變更：
  - `?? src/engine/sessions.py`
  - `?? tests/test_engine_sessions.py`

## 2026-08-05 23:02 · 021-fix-020-release-order.md

- 模式：接續 ses_02d948804ffeU1IXO46y5pjRav
- session：`ses_02d948804ffeU1IXO46y5pjRav`
- 派工前 HEAD：`fdac57caac9169a00034dbe2fcbacf5c79a9ba42`（工作區未提交項目 4 個）
- opencode 退出碼：0
- 派工後工作區變更：
  - ` M dispatch/LEDGER.md`
  - `?? dispatch/packages/021-fix-020-release-order.md`
  - `?? src/engine/sessions.py`
  - `?? tests/test_engine_sessions.py`

## 2026-08-05 23:30 · 022-http-server-sse.md

- 模式：新開
- session：`ses_02d743649ffelhbWr7u7xDq23n`
- 派工前 HEAD：`c5379279b4a4f81a94a743ed323f2105ed2862f2`（工作區未提交項目 0 個）
- opencode 退出碼：0
- 派工後工作區變更：
  - ` M src/cli.py`
  - ` M src/engine/orchestrator.py`
  - ` M src/engine/sessions.py`
  - `?? src/serve.py`
  - `?? src/server.py`
  - `?? tests/test_server.py`

## 2026-08-05 23:58 · 023-fix-022-content-type-gate.md

- 模式：接續 ses_02d743649ffelhbWr7u7xDq23n
- session：`ses_02d743649ffelhbWr7u7xDq23n`
- 派工前 HEAD：`c5379279b4a4f81a94a743ed323f2105ed2862f2`（工作區未提交項目 8 個）
- opencode 退出碼：0
- 派工後工作區變更：
  - ` M dispatch/LEDGER.md`
  - ` M src/cli.py`
  - ` M src/engine/orchestrator.py`
  - ` M src/engine/sessions.py`
  - `?? dispatch/packages/023-fix-022-content-type-gate.md`
  - `?? src/serve.py`
  - `?? src/server.py`
  - `?? tests/test_server.py`

## 2026-08-06 00:32 · 024-single-page-ui.md

- 模式：接續 ses_02d743649ffelhbWr7u7xDq23n
- session：`ses_02d743649ffelhbWr7u7xDq23n`
- 派工前 HEAD：`29f6a2fb9b88c4bcb8f41e44975b6e569611a763`（工作區未提交項目 1 個）
- opencode 退出碼：0
- 派工後工作區變更：
  - ` M src/server.py`
  - ` M tests/test_server.py`
  - `?? dispatch/BLOCKED.md`
  - `?? dispatch/packages/024-single-page-ui.md`
  - `?? src/static/`
  - `?? src/ui.py`
  - `?? tests/test_ui.py`
- ⚠ builder 這輪回報卡關（見 dispatch/BLOCKED.md）

## 2026-08-06 00:48 · 025-fix-024-arbitration-event-race.md

- 模式：接續 ses_02d743649ffelhbWr7u7xDq23n
- session：`ses_02d743649ffelhbWr7u7xDq23n`
- 派工前 HEAD：`29f6a2fb9b88c4bcb8f41e44975b6e569611a763`（工作區未提交項目 9 個）
- opencode 退出碼：0
- 派工後工作區變更：
  - ` M dispatch/LEDGER.md`
  - ` M src/engine/orchestrator.py`
  - ` M src/server.py`
  - ` M tests/test_server.py`
  - `?? dispatch/blocked/20260806-004841.md`
  - `?? dispatch/packages/024-single-page-ui.md`
  - `?? dispatch/packages/025-fix-024-arbitration-event-race.md`
  - `?? src/static/`
  - `?? src/ui.py`
  - `?? tests/test_ui.py`
- 上一輪卡關報告已歸檔：`dispatch/blocked/20260806-004841.md`

## 2026-08-06 01:25 · 026-frame-ancestors-header.md

- 模式：接續 ses_02d743649ffelhbWr7u7xDq23n
- session：`ses_02d743649ffelhbWr7u7xDq23n`
- 派工前 HEAD：`4ec29402e5b4c1f94d9078d8ea7de3da87a6bdfc`（工作區未提交項目 1 個）
- opencode 退出碼：0
- 派工後工作區變更：
  - ` M src/server.py`
  - ` M tests/test_ui.py`
  - `?? dispatch/packages/026-frame-ancestors-header.md`

## 2026-08-06 01:54 · 027-first-round-button-label.md

- 模式：接續 ses_02d743649ffelhbWr7u7xDq23n
- session：`ses_02d743649ffelhbWr7u7xDq23n`
- 派工前 HEAD：`8a97bcbbca1c0504e813c16ec6714aeec2f571d5`（工作區未提交項目 1 個）
- opencode 退出碼：0
- 派工後工作區變更：
  - ` M src/static/index.html`
  - ` M tests/test_ui.py`
  - `?? dispatch/packages/027-first-round-button-label.md`
