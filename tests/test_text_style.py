"""中文台词标点收口。"""

from src.core.text_style import soften_chinese_punctuation


def test_inner_period_becomes_comma() -> None:
    assert (
        soften_chinese_punctuation("不然呢，第一次见面就要我笑脸相迎吗。你也太闲了。")
        == "不然呢，第一次见面就要我笑脸相迎吗，你也太闲了"
    )


def test_nameplate_period_softened() -> None:
    assert soften_chinese_punctuation("四季夏目。就这些。") == "四季夏目，就这些"


def test_question_mark_kept() -> None:
    assert (
        soften_chinese_punctuation("哈？突然说什么。脑袋撞到了？")
        == "哈？突然说什么，脑袋撞到了？"
    )
