# council

Convene several AI models as a council: advisors speak in turn and can see each
other's answers, then an arbiter you designate integrates the discussion into a
single conclusion.

council runs the **official CLIs you have already installed and logged into**
(`claude`, `codex`, `gemini`, `opencode`) as local subprocesses. It does not call
any model API, and it never sees, stores, or forwards your credentials — each CLI
manages its own login. What it consumes is **your own subscription quota**.

---

## ⚠️ Scope and limits — read this first

| | |
|---|---|
| **Status** | **Alpha, under active development. Not usable yet.** The adapter detection layer works; the discussion engine and UI are not built. |
| **Platforms** | Linux and macOS only. **Windows is not supported** and will not work — see `SPEC.md` §8. |
| **Prerequisites** | You must install and log into the CLIs yourself. council will not do it for you. |
| **Cost** | Every round calls every advisor, and the full transcript is resent each round. **This burns your subscription quota quickly.** |
| **Audience** | Intended for advanced users comfortable with CLI tooling who understand the quota cost. |
| **Affiliation** | Not affiliated with, endorsed by, or supported by Anthropic, OpenAI, Google, or any model provider. |

CLI flags change between releases. The invocations council relies on were verified
on 2026-08-03 against `claude` 2.1.220, `codex` 0.145.0, `gemini` 0.53.1 and
`opencode` 1.18.11. Other versions may not work.

## How it works

```
 you ─▶ local service (discussion engine) ─▶ adapter ─▶ CLI subprocess ─▶ your subscription
            │
            └── transcript (kept by council)
```

A **seat** is a `(CLI, model)` pair, and seats — not CLIs — are the members of the
council. Since every CLI accepts a model flag, one CLI can fill several seats with
different models. You can therefore assemble a council entirely out of free models
without touching a paid subscription.

Advisors are run read-only wherever the CLI supports it: they give opinions, they
do not act.

Because AI produces output whenever it is given input, council imposes explicit
stop boundaries — most importantly, **a round never advances to the next round on
its own**. It stops and waits for you. See `SPEC.md` §5 for all six.

`SPEC.md` is the authoritative specification and the place to start reading.

### Changing models and speaking order

Seats are not hardcoded. In the web UI, the "advisors" field takes one seat per
line and **top-to-bottom is the speaking order**; on the command line it is the
order of the `--advisor` flags (see the `ADVISORS` array in `run.sh`).

The format is always `<cli>[:<model>]`, for example:

```
opencode:opencode/deepseek-v4-flash-free
gemini
claude:claude-sonnet-5
```

Omit the model to use that CLI's own default. Ask each CLI for its model list
(`opencode models`, and the equivalent for the others) — council does not keep a
model list and does not check whether a model name exists: a typo simply makes
that one seat report a failure.

## Development

Implementation is dispatched to a local builder agent; `dispatch/` holds every
work package, an append-only ledger of dispatches, and any blocking reports. The
history is intentionally public — you can read exactly what was asked for and what
came back.

```bash
python3 -m unittest discover tests -v
```

Tests never invoke a real CLI.

## License

MIT — see `LICENSE`.

---
---

# council（繁體中文）

把數個 AI 組成一個議會：顧問輪流發言、彼此看得見對方的回答，最後由你指定的**仲裁者**
把討論整合成一個結論。

council 驅動**你自己安裝並登入的官方 CLI**（`claude`、`codex`、`gemini`、`opencode`）
作為本機子行程。它不呼叫任何模型 API，也**不接觸、不儲存、不轉發你的憑證**——登入狀態
由各家 CLI 自己管。它消耗的是**你自己的訂閱額度**。

---

## ⚠️ 範圍與限制——請先讀這裡

| | |
|---|---|
| **狀態** | **Alpha，開發中，還不能用。** 目前只有 CLI 偵測層可運作，討論引擎與 UI 尚未實作。 |
| **平台** | 僅支援 Linux 與 macOS。**不支援 Windows**，在 Windows 上不會運作——原因見 `SPEC.md` §8。 |
| **前置條件** | 你必須自行安裝並登入那些 CLI，council 不會代勞。 |
| **成本** | 每一輪都會呼叫每一位顧問，且每輪重送完整逐字稿。**這會很快消耗你的訂閱額度。** |
| **適用對象** | 熟悉 CLI 工具、並清楚上述額度成本的進階使用者。 |
| **關係聲明** | 與 Anthropic、OpenAI、Google 或任何模型供應商無隸屬關係，未獲其背書或支援。 |

各家 CLI 的旗標會隨版本改變。council 所依賴的呼叫方式是 2026-08-03 對
`claude` 2.1.220、`codex` 0.145.0、`gemini` 0.53.1、`opencode` 1.18.11 實測的結果，
其他版本未必適用。

## 運作方式

**席次（seat）是一個 `(CLI, 模型)` 組合，議會的成員是席次、不是 CLI。** 由於四個 CLI
都支援指定模型的旗標，同一個 CLI 可以用不同模型佔用多個席次。因此你可以組出
**完全由免費模型構成的議會**，不動用任何付費訂閱。

顧問在 CLI 支援的範圍內一律以唯讀模式執行：它們只出意見，不動手。

因為 AI 只要有輸入就會產生輸出，council 施加了明確的停止邊界——其中最重要的一道是
**一輪結束後永不自動進入下一輪**，它會停下來等你。六道邊界全部列於 `SPEC.md` §5。

`SPEC.md` 是正式規格，建議從它開始讀。

### 換模型／調整發言順序

**席次不是寫死的。** web UI 的「顧問」欄位一行一席，**由上到下就是發言順序**；
命令列則是 `--advisor` 參數出現的順序（見 `run.sh` 裡的 `ADVISORS` 陣列）。

格式一律是 `<cli>[:<模型>]`，例如：

```
opencode:opencode/deepseek-v4-flash-free
gemini
claude:claude-sonnet-5
```

省略模型就用該 CLI 自己的預設。可用模型請用各 CLI 自己的指令查
（opencode 是 `opencode models`，其他家同理）——council 不維護模型清單，
也不會替你檢查模型名是否存在：**打錯就是那一席回報失敗**。

## 開發方式

實作由本機的 builder agent 承接；`dispatch/` 保存了每一份工作包、append-only 的派工
紀錄，以及所有卡關回報。這段歷程刻意公開——你可以確切看到當初要求了什麼、又交回了什麼。

```bash
python3 -m unittest discover tests -v
```

測試不會呼叫任何真實 CLI。

## 授權

MIT，見 `LICENSE`。
