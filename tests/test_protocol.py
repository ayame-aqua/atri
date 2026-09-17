"""[[natsume]] 尾块解析与降级。"""

from __future__ import annotations

from src.core.protocol import parse


def test_happy_path() -> None:
    raw = '今晚风有点大。\n\n[[natsume]]\n{"emotion":"shy","silent":false,"memory_candidates":[]}'
    parsed = parse(raw)
    assert parsed.visible_text == "今晚风有点大。"
    assert parsed.emotion == "shy"
    assert parsed.silent is False
    assert parsed.parse_ok is True


def test_missing_marker_uses_full_text() -> None:
    parsed = parse("普通回复")
    assert parsed.visible_text == "普通回复"
    assert parsed.emotion == "neutral"
    assert parsed.silent is False
    assert parsed.memory_candidates == []


def test_legacy_emotion_line() -> None:
    parsed = parse("嗯。\n[[emotion:happy]]")
    assert "emotion" not in parsed.visible_text
    assert parsed.emotion == "happy"


def test_bad_json_degrades() -> None:
    raw = "可见\n\n[[natsume]]\n{not-json"
    parsed = parse(raw)
    assert parsed.visible_text == "可见"
    assert parsed.emotion == "neutral"
    assert parsed.parse_ok is False
    assert parsed.log_level == "error"


def test_unknown_emotion_falls_back() -> None:
    raw = '嗨\n\n[[natsume]]\n{"emotion":"excited","silent":false,"memory_candidates":[]}'
    parsed = parse(raw)
    assert parsed.emotion == "neutral"
    assert parsed.parse_ok is True


def test_unknown_keys_ignored() -> None:
    raw = '嗨\n\n[[natsume]]\n{"emotion":"happy","silent":false,"memory_candidates":[],"extra":1}'
    parsed = parse(raw)
    assert parsed.emotion == "happy"
    assert parsed.parse_ok is True
