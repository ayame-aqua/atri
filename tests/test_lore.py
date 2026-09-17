"""世界书只保留常驻场景，不再按关键词打补丁。"""

from src.core.lore import trailing_system


def test_trailing_is_generic() -> None:
    text = trailing_system("有没有菜单")
    assert "发消息" in text
    assert "吧台" not in text
    assert "同桌" not in text
