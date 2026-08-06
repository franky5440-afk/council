import unittest

from engine import transcript


def make_meta(**overrides):
    meta = {
        "id": "sess-test-1",
        "live": True,
        "busy": False,
        "question": "該不該用 Rust？",
        "context_chars": 3,
        "seats": [
            {"seat_id": "a1", "cli": "opencode",
             "model": "opencode/deepseek-v4-flash-free", "role": "advisor"},
            {"seat_id": "a2", "cli": "claude", "model": None,
             "role": "advisor"},
            {"seat_id": "arb", "cli": "claude", "model": "claude-opus-5",
             "role": "arbiter"},
        ],
        "status": {
            "phase": "awaiting_user",
            "rounds_completed": 1,
            "max_rounds": 5,
            "at_cap": False,
            "can_start_round": False,
            "converged": False,
            "format_violations": 0,
            "usage": {"calls": 0, "total": {}, "by_seat": {}},
        },
    }
    meta.update(overrides)
    return meta


def round_started(seq, round_no):
    return {"seq": seq, "kind": "round_started", "data": {"round": round_no}}


def speech(seq, seat_id, text="發言正文", ok=True, stance="同意", more=False,
           truncated=False, violation=False, error=None, elapsed_s=11.5,
           model_used="opencode/deepseek-v4-flash-free", usage=None):
    return {
        "seq": seq,
        "kind": "speech",
        "data": {
            "seat_id": seat_id,
            "ok": ok,
            "text": text,
            "truncated": truncated,
            "error": error,
            "elapsed_s": elapsed_s,
            "model_used": model_used,
            "usage": usage,
            "stance": stance,
            "more": more,
            "violation": violation,
        },
    }


def arbitration_finished(seq, text="仲裁正文", ok=True, truncated=False,
                         error=None, elapsed_s=90.8,
                         model_used="claude-opus-5", usage=None):
    return {
        "seq": seq,
        "kind": "arbitration_finished",
        "data": {
            "record": {
                "seat_id": "arb",
                "ok": ok,
                "text": text,
                "truncated": truncated,
                "error": error,
                "elapsed_s": elapsed_s,
                "model_used": model_used,
                "usage": usage,
            },
            "status": {},
        },
    }


class TranscriptTest(unittest.TestCase):
    def test_empty_events_still_renders_metadata(self):
        out = transcript.render_markdown(make_meta(), [])
        self.assertIn("# council 討論逐字稿", out)
        self.assertIn("討論 id：sess-test-1", out)
        self.assertIn("模式：LIVE（真的呼叫過 CLI）", out)
        self.assertIn("原始問題：該不該用 Rust？", out)
        self.assertIn("完成輪次：1 / 5", out)
        self.assertIn("格式違規：0 次", out)

    def test_round_speeches_verbatim(self):
        events = [
            round_started(1, 1),
            speech(2, "a1", text="第一段發言"),
            speech(3, "a2", text="第二段發言"),
            speech(4, "a3", text="第三段發言"),
        ]
        out = transcript.render_markdown(make_meta(), events)
        self.assertIn("## 第 1 輪", out)
        for seat_id in ("a1", "a2", "a3"):
            self.assertIn("### " + seat_id, out)
        for body in ("第一段發言", "第二段發言", "第三段發言"):
            self.assertIn(body, out)
        self.assertIn("立場: 同意", out)
        self.assertIn("補充: 無", out)

    def test_failed_speech_shows_error_no_badge(self):
        events = [
            round_started(1, 1),
            speech(2, "a1", ok=False, error="呼叫失敗", stance=None,
                   more=True),
        ]
        out = transcript.render_markdown(make_meta(), events)
        self.assertIn("未回應：呼叫失敗", out)
        self.assertNotIn("立場:", out)
        self.assertNotIn("補充:", out)

    def test_failed_speech_without_error_just_未回應(self):
        events = [speech(1, "a1", ok=False, error=None, stance=None)]
        out = transcript.render_markdown(make_meta(), events)
        self.assertIn("未回應", out)
        self.assertNotIn("未回應：", out)

    def test_arbitration_record_eight_keys_no_keyerror(self):
        events = [
            round_started(1, 1),
            speech(2, "a1", text="顧問發言"),
            arbitration_finished(3, text="仲裁結論"),
        ]
        out = transcript.render_markdown(make_meta(), events)
        self.assertIn("## 仲裁", out)
        self.assertIn("### arb（仲裁者 — 不參與輪替、不計入收斂）", out)
        self.assertIn("仲裁結論", out)
        self.assertIn("90.8 秒", out)
        self.assertIn("模型：claude-opus-5", out)

    def test_stance_none_omits_stance_badge(self):
        events = [speech(1, "a1", stance=None, more=True)]
        out = transcript.render_markdown(make_meta(), events)
        self.assertNotIn("立場:", out)
        self.assertIn("補充: 有", out)

    def test_model_used_none_and_value(self):
        events = [
            speech(1, "a1", model_used=None),
            speech(2, "a2", model_used="claude-opus-5"),
        ]
        out = transcript.render_markdown(make_meta(), events)
        self.assertIn("模型：未經確認", out)
        self.assertIn("模型：claude-opus-5", out)

    def test_cost_fields_excluded_from_usage(self):
        usage = {
            "cost": 0.313167,
            "total_cost_usd": 0.5,
            "tokens": {"input": 1234, "output": 5678},
        }
        meta = make_meta(status={
            "phase": "awaiting_user",
            "rounds_completed": 1,
            "max_rounds": 5,
            "at_cap": False,
            "can_start_round": False,
            "converged": False,
            "format_violations": 0,
            "usage": {
                "calls": 1,
                "total": {},
                "by_seat": {"a1": {"calls": 1, "usage": usage}},
            },
        })
        out = transcript.render_markdown(meta, [])
        for forbidden in ("cost", "0.313167", "total_cost_usd", "0.5"):
            self.assertNotIn(forbidden, out)
        self.assertIn("tokens.input：1234", out)
        self.assertIn("tokens.output：5678", out)

    def test_markdown_in_speech_preserved_verbatim(self):
        text = ("# 標題\n\n---\n\n```\ncode block\n```\n\n|表格|\n")
        events = [speech(1, "a1", text=text)]
        out = transcript.render_markdown(make_meta(), events)
        self.assertIn(text, out)
        self.assertIn("# 標題", out)
        self.assertIn("|表格|", out)

    def test_unknown_kind_ignored(self):
        events = [
            {"seq": 1, "kind": "unknown_kind", "data": {"x": 1}},
            round_started(2, 1),
            speech(3, "a1", text="正常發言"),
        ]
        out = transcript.render_markdown(make_meta(), events)
        self.assertIn("### a1", out)
        self.assertIn("正常發言", out)

    def test_multiple_arbitrations(self):
        events = [
            arbitration_finished(1, text="第一次仲裁"),
            arbitration_finished(2, text="第二次仲裁"),
        ]
        out = transcript.render_markdown(make_meta(), events)
        self.assertEqual(out.count("## 仲裁"), 2)
        self.assertIn("第一次仲裁", out)
        self.assertIn("第二次仲裁", out)

    def test_seat_usage_none_only_calls_line(self):
        meta = make_meta(status={
            "phase": "awaiting_user",
            "rounds_completed": 0,
            "max_rounds": 5,
            "at_cap": False,
            "can_start_round": True,
            "converged": False,
            "format_violations": 0,
            "usage": {
                "calls": 2,
                "total": {},
                "by_seat": {
                    "a1": {"calls": 1, "usage": None},
                    "a2": {"calls": 1, "usage": {}},
                },
            },
        })
        out = transcript.render_markdown(meta, [])
        self.assertIn("- a1：calls=1\n- a2：calls=1", out)
        self.assertNotIn("  - tokens", out)


if __name__ == "__main__":
    unittest.main()
