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
| **Status** | **Alpha, under active development.** The engine, the local server and the web UI now work end to end. Interfaces may still change without notice. |
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
do not act. One exception is deliberate — advisors running on `opencode` are
allowed to search the web, because being able to check current facts is a
different thing from being able to change your machine. They still cannot read
your files, run commands, or fetch arbitrary URLs. Note that this means a search
provider may see fragments of whatever context you attach. See `SPEC.md` §4.2.

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

## Running it

```bash
python3 src/serve.py          # dry run — no CLI is ever launched
python3 src/serve.py --live   # real calls — spends your subscription quota
```

Then open the `http://127.0.0.1:8765/` it prints. On the command line the same
distinction applies: `./run.sh "your question"` calls the CLIs for real, and
`./run.sh --dry "your question"` does not.

### Dry run is the default, and it will fool you

**Without `--live`, council never starts a CLI subprocess.** Every advisor still
appears to speak, and the transcript still fills up with cards — but the text is
a placeholder generated locally. It begins with `【DRY RUN】`, names the model
that *would* have been called, and reports how many characters the prompt was.
Elapsed time is `0.0` seconds; the calls are counted, but no token usage is
reported, because nothing reported any.

This exists so you can click through the entire interface — create a discussion,
open several rounds, call the arbiter, export the transcript — without spending
anything. It is genuinely useful. It is also the single thing most likely to
confuse you, so it is worth saying outright:

> **If the advisors seem not to have answered, or every seat says the same thing
> in the same shape, check which mode you are in before concluding the models are
> broken.**

A badge shows the current mode, but the transcript is the better tell. Real
advisors disagree with each other, name each other, and take visibly different
amounts of time to answer; dry-run seats are uniform and instant.

`--live` is opt-in for the same reason a round never advances on its own: what
costs money should be what you asked for. A running server cannot be switched
between the two modes — stop it and start a new one. Discussions live in memory
only, so restarting discards them; export anything you want to keep first.

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
| **狀態** | **Alpha，開發中。** 引擎、本機伺服器與 web UI 目前已能端到端運作，但介面仍可能隨時變動。 |
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

顧問在 CLI 支援的範圍內一律以唯讀模式執行：它們只出意見，不動手。**有一個刻意的例外**：
跑在 `opencode` 上的顧問可以使用網路搜尋——查得到現況與能不能動你的機器是兩件事。
它們仍然讀不到你的檔案、不能執行指令、不能對任意網址發請求。
⚠️ 這也代表**你貼進去的脈絡片段有可能出現在搜尋查詢裡**，被搜尋供應商看到。
詳見 `SPEC.md` §4.2。

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

## 怎麼跑

```bash
python3 src/serve.py          # dry run——完全不會啟動任何 CLI
python3 src/serve.py --live   # 真實呼叫——會消耗你的訂閱額度
```

然後開它印出來的 `http://127.0.0.1:8765/`。命令列同一套規則：
`./run.sh "你的問題"` 會真的呼叫 CLI，`./run.sh --dry "你的問題"` 不會。

### dry run 是預設值，而且它會騙過你

**沒有加 `--live` 時，council 不會啟動任何 CLI 子行程。** 但畫面上每一位顧問**照樣會
發言**、逐字稿照樣長出卡片——那些文字是本機生成的假回覆，開頭是 `【DRY RUN】`，
內容只寫出「本來會呼叫哪個模型」與「收到的 prompt 有幾個字元」。耗時一律 `0.0` 秒；
呼叫次數照算，但**沒有任何 token 用量統計**，因為根本沒有人回報。

這個模式的存在是為了讓你**把整個介面點過一遍**——建討論、開好幾輪、叫仲裁者、匯出
逐字稿——完全不花錢。它真的很有用。但它也是**最容易讓你誤判的一件事**，所以直說：

> **如果你覺得「顧問怎麼都沒回應」，或每一席講的話長得一模一樣，
> 先確認你在哪個模式，再去懷疑模型壞了。**

畫面上有徽章標示模式，但**逐字稿本身是更可靠的判斷依據**：真實的顧問會彼此反駁、
會指名回應對方、耗時長短明顯不同；dry run 的席次則整齊劃一、瞬間完成。

`--live` 之所以是 opt-in，理由和「一輪結束後永不自動進入下一輪」是同一個：
**會花錢的事應該是你主動要求的。** 已經在跑的伺服器沒辦法切換模式，要換就關掉重開。
⚠️ 討論只活在記憶體裡，重開就會全部消失——**想留的內容請先匯出。**

## 開發方式

實作由本機的 builder agent 承接；`dispatch/` 保存了每一份工作包、append-only 的派工
紀錄，以及所有卡關回報。這段歷程刻意公開——你可以確切看到當初要求了什麼、又交回了什麼。

```bash
python3 -m unittest discover tests -v
```

測試不會呼叫任何真實 CLI。

## 授權

MIT，見 `LICENSE`。
