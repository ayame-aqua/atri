"""世界书触发。"""

from src.core.lore import keyed_lore, trailing_system


def test_keyed_lore_skips_unrelated() -> None:
    assert keyed_lore("你好呀") == ""


def test_keyed_lore_school_scene() -> None:
    text = keyed_lore("你应该就是我的新同桌了吧")
    assert "大学" in text
    assert "高中" in text


def test_trailing_always_has_post_history() -> None:
    text = trailing_system("怎么称呼诶")
    assert "实际" in text
    assert "同桌" not in text
