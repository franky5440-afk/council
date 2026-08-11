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
| **Prerequisites** | **Python 3.10 or newer**, and you must install and log into the CLIs yourself — council will not do it for you. See *Platform notes* below. |
| **Cost** | Every round calls every advisor, and the full transcript is resent each round. **This burns your subscription quota quickly.** |
| **Audience** | Intended for advanced users comfortable with CLI tooling who understand the quota cost. |
| **Affiliation** | Not affiliated with, endorsed by, or supported by Anthropic, OpenAI, Google, or any model provider. |

CLI flags change between releases. The invocations council relies on were verified
on 2026-08-03 against `claude` 2.1.220, `codex` 0.145.0, `gemini` 0.53.1 and
`opencode` 1.18.11. Other versions may not work.

### Platform notes

**Python 3.10 or newer is required.** `src/adapters/` uses PEP 604 type
annotations (`str | None`) and deliberately does not carry
`from __future__ import annotations`, so an older interpreter fails at import
time with `TypeError: unsupported operand type(s) for |`.

On macOS this is easy to trip over: the `python3` shipped with the Xcode Command
Line Tools is often 3.9.x, which is not enough. Check with `python3 --version`
and install a newer one (python.org or Homebrew) if needed. On a machine with no
Command Line Tools at all, `/usr/bin/python3` is a stub that only prompts you to
install them.

**On macOS, start council from a terminal.** A process launched from Finder or
the Dock does not read your shell profile, so `PATH` will not include Homebrew's
`/opt/homebrew/bin` (Apple Silicon) or `/usr/local/bin` (Intel). council would
then report every advisor as *not found in PATH* even though the CLIs are
installed and working.

Verified on macOS 2026-08-07 (Apple Silicon, Python 3.13, bash 3.2.57): the test
suite, the local server, the web UI in both Safari and Chrome, transcript export,
and `./start.sh --dry` all behave as they do on Linux. Real CLI invocation on
macOS has **not** been verified yet.

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

You can have 1–3 advisors plus exactly one arbiter — 2 to 4 seats in total.
Seats are not hardcoded. In the web UI, the "advisors" field takes one seat per
line and **top-to-bottom is the speaking order**; on the command line it is the
order of the `--advisor` flags (see the `ADVISORS` array in `run.sh`).

The format is always `<cli>[:<model>]`. Omit the model to use that CLI's own
default. A complete, all-free configuration you can paste into the advisors
field:

```
opencode:opencode/deepseek-v4-flash-free
opencode:opencode/nemotron-3-ultra-free
opencode:opencode/laguna-s-2.1-free
```

#### Finding out which models you can name

council keeps no model list, so this is a question for each CLI — and only one of
the four can enumerate them:

| CLI | How to see the names |
|---|---|
| `opencode` | `opencode models` — one id per line, several hundred of them. For the free tier: `opencode models \| grep -E "^opencode/.*-free$"` |
| `claude` | No listing command. `--model` takes an alias (`opus`, `sonnet`, `fable`) or a full name such as `claude-fable-5` |
| `codex` | No listing command; `-m/--model` takes a name you already know |
| `gemini` | No listing command; `-m/--model` takes a name you already know |

For the three without a listing command, that CLI's own documentation is the
source of truth. Leaving the model off entirely (just `claude`, `gemini`, or
`codex`) always works and uses whatever that CLI is configured to use.

#### If you get the name wrong

council does not validate model names — it cannot, since it keeps no list. The
name goes straight to the CLI, the CLI fails, and **that one seat reports a
failure while the discussion carries on without it**; the transcript records
`（未回應：<error>）` for that seat. So if a seat contributes nothing, check it
against this section before concluding the model itself is broken.

#### Free models disappear — that is normal

The free-model list changes constantly: a model gets delisted or renamed, or
your account is not entitled to it and the CLI returns 401. council does not
track this and cannot — it keeps no model list. So **check for yourself before
choosing seats** (`opencode models`); any model name in this README is only an
example from the moment it was written. A broken seat does not drag down the
round: the rest keep speaking, arbitration still works, and since 038 **a
failed seat no longer blocks convergence** — its failure count is shown in the
usage panel.

#### The arbiter field is not a fourth advisor

The advisors field holds one to three seats that each speak, in order, every
round. The arbiter is a single seat that **never joins the rounds** — it is
called only when you press the arbiter button, and it then reads the whole
transcript at once. Its answer is not scored for stance or convergence.

The cost consequence follows from that: an advisor is called once per round,
whereas the arbiter is called only when you ask — but with the longest prompt in
the system. Putting a paid CLI in an advisor seat multiplies its cost by the
number of rounds; putting it in the arbiter seat does not. The default in
`run.sh` reflects this: three free advisors, and `claude` as an arbiter that is
never called unless you add `--arbitrate`.

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

### Double-clicking it on macOS

`Council.command` starts the server and opens the browser, so it can be launched
from Finder without a terminal. ⚠️ **It runs `./start.sh`, which is `--live`** —
clicking it spends quota. That is the point of a shortcut: it lands you in a
usable state. If you want the free mode, run `./start.sh --dry` yourself.

It deliberately opens a Terminal window rather than being an `.app`. That window
is the only place errors are visible, and the only place Ctrl-C exists — a server
launched with no terminal cannot be stopped from the keyboard.

Two things it handles for you: Finder starts a process in your home directory, so
the script locates the project from its own path rather than the current one; and
Terminal runs a `.command` through your login shell, so the CLIs on `PATH` are
found (Homebrew's prefixes are added as a fallback for a profile that sets none).

It still cannot fix the prerequisites. **The `python3` it finds must be 3.10 or
newer** — see *Platform notes*. And if you downloaded a ZIP of this repository
rather than cloning it, macOS marks the file as quarantined and refuses to open
it; right-click → *Open* once to allow it. Files from `git clone` are not
quarantined.

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

顧問 1～3 席，加上恰好一個仲裁者，總席次 2～4。
**席次不是寫死的。** web UI 的「顧問」欄位一行一席，**由上到下就是發言順序**；
命令列則是 `--advisor` 參數出現的順序（見 `run.sh` 裡的 `ADVISORS` 陣列）。

格式一律是 `<cli>[:<模型>]`，省略模型就用該 CLI 自己的預設。
可以直接貼進「顧問」欄位的全免費配置：

```
opencode:opencode/deepseek-v4-flash-free
opencode:opencode/nemotron-3-ultra-free
opencode:opencode/laguna-s-2.1-free
```

#### 怎麼知道有哪些模型可以填

council 不維護模型清單，所以這件事要問各家 CLI。**而四家裡只有一家查得到**：

| CLI | 怎麼查 |
|---|---|
| `opencode` | `opencode models`，一行一個 id、有好幾百個。免費的那些：`opencode models \| grep -E "^opencode/.*-free$"` |
| `claude` | **沒有列出清單的指令。** `--model` 收 alias（`opus`／`sonnet`／`fable`）或完整名稱（例如 `claude-fable-5`） |
| `codex` | **沒有列出清單的指令**，`-m/--model` 收你已經知道的名字 |
| `gemini` | **沒有列出清單的指令**，`-m/--model` 收你已經知道的名字 |

沒有查詢指令的那三家，以該 CLI 自己的文件為準。
**不填模型永遠是安全的**（直接寫 `claude`／`gemini`／`codex`），
那會用它自己設定好的預設。

#### 填錯會怎樣

council **不會檢查模型名是否存在**——它沒有清單，也查不了。打錯的名字會原樣送給該
CLI，CLI 失敗，**那一席回報失敗，討論照樣繼續**，逐字稿上那一席寫的是
`（未回應：<錯誤>）`。所以看到某一席一直沒有內容，先回來對一下這一節，
不要先怪模型壞掉。

#### 免費模型會消失，這是常態

免費模型清單**隨時會變**：模型下架、改名、或你的帳號對某個模型沒有授權而回 401。
council 不追蹤這件事、也追蹤不了——它沒有模型清單。因此**選席次前請自己查一次**
（`opencode models`），README 裡列的任何模型名都只是**寫作當下**的例子。
一席壞掉不會拖垮整輪：其餘席次照常發言、仲裁照常可用，而且從 038 起
**壞掉的席次不會再擋住收斂**，失敗次數會顯示在用量面板上。

#### 仲裁者欄位不是第四位顧問

「顧問」欄位放 1～3 席，**每一輪都會依序各發言一次**。仲裁者是**不參與輪替**的單獨
一席，只有你按「叫仲裁者」才會被呼叫，那時它一次讀完整份逐字稿；它的回答不計立場、
也不計入收斂判定。

額度的後果直接由此而來：**顧問席次是「每輪 × 每席」各一次呼叫，仲裁者是「你按幾次
就幾次」，但每次都帶著全場最長的 prompt。** 所以把付費 CLI 放進顧問席，成本會隨輪數
倍增；放在仲裁者席則不會。`run.sh` 的預設配置就是照這個道理設的——三席免費顧問，
仲裁者是 `claude` 但**刻意沒加 `--arbitrate`**，不主動呼叫。

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

### 在 macOS 上雙擊啟動

`Council.command` 會起伺服器並開瀏覽器，不用開終端機也能從 Finder 啟動。
⚠️ **它跑的是 `./start.sh`，也就是 `--live`**——點下去就會花額度。捷徑的意義正是
如此：點完就是可用狀態。想要不花錢的模式，請自己跑 `./start.sh --dry`。

它刻意開出一個 Terminal 視窗，而不是做成 `.app`。那個視窗是**錯誤訊息唯一看得到的
地方**，也是**唯一按得到 Ctrl-C 的地方**——沒有終端機的伺服器，鍵盤關不掉。

它幫你處理掉兩件事：Finder 啟動的程式 cwd 是家目錄，所以腳本是**以自己的位置**定位
專案，不是用當下的工作目錄；而 Terminal 是透過**登入 shell** 執行 `.command`，所以
你 `PATH` 上的 CLI 找得到（另外補上 Homebrew 的路徑，是為了 profile 沒設的情況）。

但前提條件它救不了。**它找到的 `python3` 必須是 3.10 以上**——見〈平台注意事項〉。
另外，如果你是從網頁下載本專案的 ZIP 而不是 `git clone`，macOS 會把檔案標記為隔離
狀態而拒絕開啟，請右鍵 →〈打開〉放行一次。`git clone` 下來的檔案不會被隔離。

## 開發方式

實作由本機的 builder agent 承接；`dispatch/` 保存了每一份工作包、append-only 的派工
紀錄，以及所有卡關回報。這段歷程刻意公開——你可以確切看到當初要求了什麼、又交回了什麼。

```bash
python3 -m unittest discover tests -v
```

測試不會呼叫任何真實 CLI。

## 授權

MIT，見 `LICENSE`。
