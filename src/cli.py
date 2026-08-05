"""council 命令列進入點（工作包 017）。

一次執行 ＝ 一輪：解析參數 →（--live 時先偵測）→ 建立討論 → 跑一輪 → 印出逐字稿與狀態。
不會自動進入下一輪、不會存檔、不做互動確認（SPEC.md §5 邊界 1、§8）。

--live 是刻意設計成「明確加上才會花錢」的旗標：不加就是 dry-run，不碰任何真實 CLI。
本檔案是全 repo 唯一允許 import adapters 的檔案。
"""

import argparse
import sys

from adapters import ADAPTERS
from engine import orchestrator
from engine import state
from engine.wiring import dry_run_ask_fn, make_ask_fn, parse_seat_spec


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="council",
        description="在同一對話框裡徵詢多位 AI、依序發言，由仲裁者整合結論。",
    )
    parser.add_argument("question", help="討論的原始問題")
    parser.add_argument(
        "--advisor", dest="advisors", action="append", metavar="SPEC", required=True,
        help="顧問席次，格式為 claude 或 gemini:gemini-2.5-pro；可重複指定（至少一個）")
    parser.add_argument(
        "--arbiter", metavar="SPEC", required=True,
        help="仲裁者席次，格式同 --advisor。v1 尚未實作仲裁流程，本席次此輪不會發言")
    parser.add_argument(
        "--live", action="store_true",
        help="真實呼叫各家 CLI（會消耗訂閱額度）。不加此旗標一律是 dry-run，不碰任何 CLI")
    parser.add_argument(
        "--timeout-s", type=int, default=orchestrator.DEFAULT_TIMEOUT_S,
        help=f"單次呼叫逾時秒數（預設 {orchestrator.DEFAULT_TIMEOUT_S}）")
    parser.add_argument(
        "--max-chars", type=int, default=orchestrator.DEFAULT_MAX_CHARS,
        help=f"單次發言長度上限（預設 {orchestrator.DEFAULT_MAX_CHARS}）")
    return parser


def _build_seats(args) -> list:
    seats = []
    for i, spec in enumerate(args.advisors):
        seat = parse_seat_spec(spec, seat_id="", role=state.ADVISOR)
        seat["seat_id"] = f"{seat['cli']}-{i + 1}"
        seats.append(seat)
    seat = parse_seat_spec(args.arbiter, seat_id="", role=state.ARBITER)
    seat["seat_id"] = "arb"
    seats.append(seat)
    return seats


def _detect_used(seats) -> list:
    problems = []
    used = sorted({seat["cli"] for seat in seats})
    for cli_id in used:
        if cli_id not in ADAPTERS:
            problems.append(
                f"錯誤：未知的 CLI id「{cli_id}」；可用：{', '.join(sorted(ADAPTERS))}")
            continue
        result = ADAPTERS[cli_id].detect()
        if not result["installed"]:
            problems.append(
                f"錯誤：CLI「{cli_id}」未安裝（{result.get('error') or 'not found in PATH'}）")
    return problems


def _print_transcript(discussion) -> None:
    for record in discussion.rounds[-1]:
        print(f"── {record['seat_id']} ──")
        if record["ok"]:
            print(record["text"])
            if record["truncated"]:
                print("（本則發言超過長度上限，已被截斷）")
            model_used = record["model_used"]
            print(f"（回答者：{model_used}）" if model_used else "（回答者：未經確認）")
        else:
            error = record["error"]
            print(f"（未回應：{error}）" if error else "（未回應）")


def _print_status(status) -> None:
    usage = status["usage"]
    print()
    print("── 狀態 ──")
    print(f"已完成輪數：{status['rounds_completed']} / {status['max_rounds']}")
    print(f"已達輪數上限：{'是' if status['at_cap'] else '否'}")
    print(f"已收斂：{'是' if status['converged'] else '否'}")
    print(f"格式違規次數：{status['format_violations']}")
    print(f"總呼叫次數：{usage['calls']}")
    print(f"累計 usage：{usage['total']}")
    for seat_id in sorted(usage["by_seat"]):
        per = usage["by_seat"][seat_id]
        line = f"  {seat_id}：calls={per['calls']}"
        if per["usage"]:
            line += f"，usage={per['usage']}"
        print(line)


def main(argv=None) -> int:
    args = _build_parser().parse_args(argv)
    seats = _build_seats(args)

    if args.live:
        problems = _detect_used(seats)
        if problems:
            for msg in problems:
                print(msg, file=sys.stderr)
            return 1
        advisor_count = sum(1 for s in seats if s["role"] == state.ADVISOR)
        print(f"⚠️ LIVE 模式：即將對 {advisor_count} 個顧問席次發出真實呼叫，會消耗訂閱額度。")
        ask_fn = make_ask_fn(ADAPTERS)
    else:
        ask_fn = dry_run_ask_fn

    discussion = state.Discussion(args.question, seats)
    status = orchestrator.run_round(discussion, ask_fn,
                                    timeout_s=args.timeout_s,
                                    max_chars=args.max_chars)
    _print_transcript(discussion)
    _print_status(status)
    return 0


if __name__ == "__main__":
    sys.exit(main())
