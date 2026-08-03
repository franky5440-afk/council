# council — Claude Code 專案入口

⚠️ **本檔不含任何規則，只負責載入與定位。**

專案規則的唯一來源是 **`AGENTS.md`**（builder 與 reviewer 共用同一份標準），
實作契約的唯一來源是 **`SPEC.md`**。本檔**刻意不重述**它們的任何一條——
一旦重述，兩份就會各自過期，然後沒人知道哪份算數。而 builder（opencode）
**只讀得到 `AGENTS.md`**，本檔對它不可見，所以任何寫進本檔的「規則」都只會單邊生效。

需要改規則 → 改 `AGENTS.md`。需要改契約 → 改 `SPEC.md`。**不要改本檔來解決那些事。**

## 開場先做這件事

```
讀 HANDOFF.md → SPEC.md → AGENTS.md
```

- **`HANDOFF.md`＝現況**（進度、待辦、剛驗證過什麼、已知的坑）。⚠️ 它被
  `.gitignore` 排除（本 repo 是 PUBLIC），只存在本機；離機副本在 private repo
  `imac-system-snapshot` 的 `BuilderEvals/council/`，且那是**會過期的快照**。
- **本檔＝不變的東西**（角色、流程、常用指令）。兩者分工如此，不要互相抄。

⚠️ `HANDOFF.md` 每一版都有東西過期——**接手時一律自己跑
`git fetch origin && git status` 再判斷狀態**，不要相信它寫的。

## 我在本專案的角色

**review gate ＋ push gate，不是 builder。** 實作一律派給 opencode 裡的 deepseek，
我審 diff、跑測試、縫合、負責版控。除非 Frank 明說要我實作，否則不自己改碼。

```bash
./dispatch.sh dispatch/packages/NNN-名稱.md            # 新開一輪
./dispatch.sh -s ses_xxxxx dispatch/packages/NNN.md    # 接續同一 session
```

派工紀錄自動追加到 `dispatch/LEDGER.md`；builder 卡關會寫 `dispatch/BLOCKED.md`
（它在 headless 下無法反問，所以**介面契約要寫死**）。版控由我負責，builder 不碰。

## 審查的三個硬動作

1. **讀 `git diff`，不信自述。** builder 的回報屬 Inference 層，只有 diff 是 Evidence。
2. **自己跑一次完整測試**：`python3 -m unittest discover tests`。
   （曾發生 builder 回報「交付完成」、實跑是 `FAILED (errors=1)`。）
3. **突變測試**：把被測邏輯改壞、確認測試真的翻紅，再還原。
   ⚠️ 突變只准動實作那一側——改到同時餵給對照組的常數，判定不會翻轉。

## 這是 PUBLIC repo

push 前掃 diff（比掃整棵樹精準），不得出現使用者名稱、家目錄絕對路徑、token：

```bash
git diff origin/master..HEAD | grep -nE "$(whoami)|/home/[a-z]|s[k]-[A-Za-z0-9]{16}|gh[p]_"
```

⚠️ 這行有兩個刻意的寫法，改動前先看懂：

- **用 `$(whoami)` 而不是把使用者名稱寫死**——本檔自己也會被推上 public repo，
  寫死等於在防洩漏的檢查清單裡洩漏。
- **`s[k]-` 與 `gh[p]_` 的方括號是為了不匹配到自己。** 字元類照樣匹配真正的
  OpenAI 與 GitHub token 前綴，但這幾行的字面文字不會匹配該樣式 ⇒ 掃描不命中本檔。
  ⚠️ 連解說文字都不要寫出未加方括號的前綴，否則又會自我命中（我改這段時踩過一次）。
  這不是龜毛：**已知的假陽性會訓練人習慣性忽略掃描結果，訊號就廢了。**

⚠️ **`dispatch/tmp/` 底下的探測輸出不得複製進 `tests/`**——codex 的 stderr 含
`workdir: /home/<使用者名稱>/…`，而且它會把整份 stdin 原樣回顯到 stderr。

⚠️ **push 需 Frank 逐次明確授權**，review 全過也只回報「可推＋推哪幾個 commit」等他點頭。

## 額度紀律

驗證能用免費席次就別動付費額度（`opencode/*-free` 有 6 個免費模型）。
`codex` 已無訂閱、只剩很低的免費額度，**非必要不要呼叫**。
任何會走到 `ask()` 的驗證，一律先把假執行檔目錄 prepend 到 `PATH`，
不要依賴「反正會被別的東西擋下來」。
