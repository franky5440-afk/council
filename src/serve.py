"""council 本機 HTTP 伺服器進入點（工作包 022）。

本檔與 src/cli.py 是全 repo 僅有的兩個允許 import adapters 的檔案。
--live 存在才注入真實 ask_fn（make_ask_fn(ADAPTERS)），否則一律 dry-run——
沒有任何請求能把 dry run 切成 live（SPEC.md §7.2）。
"""

import argparse
import sys
import webbrowser

from adapters import ADAPTERS
from engine import orchestrator
from engine.wiring import dry_run_ask_fn, make_ask_fn
import server


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="council-serve",
        description="啟動 council 本機 HTTP 伺服器（討論只活在記憶體）。",
    )
    parser.add_argument(
        "--live", action="store_true",
        help="真實呼叫各家 CLI（會消耗訂閱額度）。不加此旗標一律是 dry-run，不碰任何 CLI")
    parser.add_argument("--port", type=int, default=8765,
                        help="監聽埠號（預設 8765）")
    parser.add_argument(
        "--open", action="store_true",
        help="啟動後自動用系統預設瀏覽器開啟頁面")
    parser.add_argument(
        "--timeout-s", type=int, default=orchestrator.DEFAULT_TIMEOUT_S,
        help=f"單次呼叫逾時秒數（預設 {orchestrator.DEFAULT_TIMEOUT_S}）")
    parser.add_argument(
        "--max-chars", type=int, default=orchestrator.DEFAULT_MAX_CHARS,
        help=f"單次發言長度上限（預設 {orchestrator.DEFAULT_MAX_CHARS}）")
    args = parser.parse_args(argv)

    # 兩個值必須一起決定，不能分成兩段判斷——
    # 那會長出「顯示 dry run、實際卻在花錢」的可能。
    if args.live:
        ask_fn = make_ask_fn(ADAPTERS)
        live = True
        print("⚠️ LIVE 模式：這個伺服器上的每一次開輪／仲裁都會消耗訂閱額度。")
    else:
        ask_fn = dry_run_ask_fn
        live = False
        print("dry run 模式：不會呼叫任何真實 CLI，討論內容全部是假的。")

    httpd = server.build_server(
        ask_fn=ask_fn, live=live, port=args.port,
        timeout_s=args.timeout_s, max_chars=args.max_chars)
    url = f"http://127.0.0.1:{httpd.server_address[1]}/"
    print(url)
    if args.open and not webbrowser.open(url):
        print("（無法自動開啟瀏覽器，請自己貼上上面的網址）")
    try:
        httpd.serve_forever()
        print("已由網頁的「關閉 council」停止；討論只在記憶體，已全部消失。")
    except KeyboardInterrupt:
        print("已停止；討論只在記憶體，已全部消失。")
    finally:
        # shutdown() 只停迴圈、不關監聽 socket：不補這一行，那個埠會變成
        # 「連得上但永遠沒有回應」，比連線被拒更難判斷（實測確認）。
        httpd.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
