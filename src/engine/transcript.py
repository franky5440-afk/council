"""把一次討論的事件流渲染成 Markdown（工作包 029）。

純函式：不認識 discussion、state、sessions、orchestrator，拿到什麼就渲染什麼。
本檔不引用任何模組——它只做字串組裝。逐字稿一律從事件流重播，
不讀 discussion.rounds（SPEC.md §7.1：那是會被邊跑邊 append 的撕裂來源）。
"""


def _flatten_usage(usage):
    """把巢狀 usage dict 展平成「點號路徑 → 數值」；只保留數值葉節點。"""
    out = {}
    for key, value in usage.items():
        if isinstance(value, dict):
            for sub_key, sub_value in _flatten_usage(value).items():
                out[key + "." + sub_key] = sub_value
        elif isinstance(value, (int, float)) and not isinstance(value, bool):
            out[key] = value
    return out


def _is_cost_key(key):
    return "cost" in key.lower()


def _model_badge(model_used):
    if model_used is None:
        return "模型：未經確認"
    return "模型：" + model_used


def _speech_badge(data):
    items = []
    if data["stance"] is not None:
        items.append("立場: " + data["stance"])
    if data["more"]:
        items.append("補充: 有")
    else:
        items.append("補充: 無")
    if data["truncated"]:
        items.append("已截斷")
    if data["violation"]:
        items.append("格式違規")
    items.append("{:.1f}".format(data["elapsed_s"]) + " 秒")
    items.append(_model_badge(data["model_used"]))
    return "｜".join(items)


def _arbitration_badge(record):
    # 仲裁 record 只有八個鍵，沒有 stance／more／violation（SPEC.md §6.1）。
    # 渲染時不准碰那三個鍵——不要讓「仲裁者有立場」在程式碼裡看起來成立。
    items = []
    if record["truncated"]:
        items.append("已截斷")
    items.append("{:.1f}".format(record["elapsed_s"]) + " 秒")
    items.append(_model_badge(record["model_used"]))
    return "｜".join(items)


def _render_body(rec):
    if rec["ok"]:
        return rec["text"]
    error = rec["error"]
    if error:
        return "未回應：" + error
    return "未回應"


def render_markdown(meta, events) -> str:
    status = meta["status"]
    usage = status["usage"]
    lines = []
    lines.append("# council 討論逐字稿")
    lines.append("")
    lines.append("- 討論 id：" + str(meta["id"]))
    if meta["live"]:
        lines.append("- 模式：LIVE（真的呼叫過 CLI）")
    else:
        lines.append("- 模式：DRY RUN（未呼叫任何 CLI）")
    lines.append("- 原始問題：" + str(meta["question"]))
    lines.append("- 脈絡：" + str(meta["context_chars"]) + " 字元（未包含在本檔）")
    lines.append("- 完成輪次：" + str(status["rounds_completed"]) + " / "
                 + str(status["max_rounds"]))
    if status["converged"]:
        lines.append("- 收斂：全體顧問都表示沒有補充了")
    else:
        lines.append("- 收斂：尚未收斂")
    lines.append("- 格式違規：" + str(status["format_violations"]) + " 次")
    lines.append("- 席次：")
    for seat in meta["seats"]:
        if seat["role"] == "arbiter":
            role_label = "仲裁者"
        else:
            role_label = "顧問"
        seat_line = "- " + seat["seat_id"] + " — " + seat["cli"]
        if seat["model"] is not None:
            seat_line += "：" + seat["model"]
        seat_line += "（" + role_label + "）"
        lines.append("  " + seat_line)
    lines.append("")
    lines.append("> 以下逐字稿由各家 CLI 背後的模型產生，未經任何淨化或改寫。")
    lines.append("")
    lines.append("---")
    for event in events:
        kind = event["kind"]
        data = event["data"]
        if kind == "round_started":
            lines.append("")
            lines.append("## 第 " + str(data["round"]) + " 輪")
        elif kind == "speech":
            lines.append("")
            lines.append("### " + data["seat_id"])
            lines.append("")
            if data["ok"]:
                lines.append(_speech_badge(data))
                lines.append("")
                lines.append(data["text"])
            else:
                lines.append(_render_body(data))
        elif kind == "arbitration_finished":
            record = data["record"]
            lines.append("")
            lines.append("## 仲裁")
            lines.append("")
            lines.append("### " + record["seat_id"]
                         + "（仲裁者 — 不參與輪替、不計入收斂）")
            lines.append("")
            if record["ok"]:
                lines.append(_arbitration_badge(record))
                lines.append("")
                lines.append(record["text"])
            else:
                lines.append(_render_body(record))
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## 用量")
    lines.append("")
    lines.append(
        "總呼叫 " + str(usage["calls"]) + " 次。金額欄位不列入"
        "（council 不呼叫任何模型 API，那些數字是各家 CLI 依 API 定價"
        "換算的參考值）。")
    lines.append("")
    for seat_id in sorted(usage["by_seat"]):
        per = usage["by_seat"][seat_id]
        failed = per.get("failed", 0)
        line = "- " + seat_id + "：calls=" + str(per["calls"])
        if failed:
            line += "，failed=" + str(failed)
        lines.append(line)
        seat_usage = per["usage"]
        if seat_usage:
            flat = _flatten_usage(seat_usage)
            for key in sorted(flat):
                if _is_cost_key(key):
                    continue
                lines.append("  - " + key + "：" + str(flat[key]))
    return "\n".join(lines) + "\n"
