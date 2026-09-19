"""相处状态：三轴数字调语气，不改人设、不改 emotion。"""

from __future__ import annotations

from dataclasses import dataclass

from src.memory.constants import (
    DEFAULT_MOOD_DECAY_PER_HOUR,
    MOOD_ENERGY_MAX,
    MOOD_ENERGY_MIN,
    MOOD_UNIT_MAX,
    MOOD_UNIT_MIN,
)

PRAISE_MARKERS: tuple[str, ...] = (
    "谢谢",
    "感谢",
    "喜欢你",
    "爱你",
    "好棒",
    "真棒",
    "辛苦",
    "可爱",
    "好看",
)
ORDER_MARKERS: tuple[str, ...] = (
    "去给我",
    "你给我",
    "快点",
    "马上做",
    "命令你",
    "闭嘴",
    "给我做",
)
CARE_MARKERS: tuple[str, ...] = ("吃饭", "早点睡", "休息", "加衣服", "别熬夜")


@dataclass(frozen=True)
class MoodState:
    energy: float
    irritation: float
    affection: float


def clamp_mood(energy: float, irritation: float, affection: float) -> MoodState:
    return MoodState(
        energy=_clamp(energy, MOOD_ENERGY_MIN, MOOD_ENERGY_MAX),
        irritation=_clamp(irritation, MOOD_UNIT_MIN, MOOD_UNIT_MAX),
        affection=_clamp(affection, MOOD_UNIT_MIN, MOOD_UNIT_MAX),
    )


def decay_mood(
    state: MoodState, hours: float, per_hour: float = DEFAULT_MOOD_DECAY_PER_HOUR
) -> MoodState:
    if hours <= 0 or per_hour <= 0:
        return state
    step = per_hour * hours
    energy = _toward_zero(state.energy, step)
    irritation = _toward_zero(state.irritation, step)
    affection = _toward_zero(state.affection, step)
    return clamp_mood(energy, irritation, affection)


def mood_delta_from_text(text: str) -> MoodState:
    raw = (text or "").strip()
    energy = 0.0
    irritation = 0.0
    affection = 0.0
    if any(marker in raw for marker in PRAISE_MARKERS):
        affection += 0.08
        irritation -= 0.04
        energy += 0.02
    if any(marker in raw for marker in ORDER_MARKERS):
        irritation += 0.1
        affection -= 0.04
        energy -= 0.03
    if any(marker in raw for marker in CARE_MARKERS):
        affection += 0.03
        energy += 0.02
    return clamp_mood(energy, irritation, affection)


def mood_block(state: MoodState) -> str:
    return (
        "相处状态（不是此刻对话，只调话量和冷热，不要改她是谁，不要改 emotion）："
        f"精力{_level(state.energy, low='偏低', mid='平常', high='还行')}，"
        f"亲近{_level(state.affection, low='一般', mid='还在', high='偏高')}，"
        f"别扭{_level(state.irritation, low='不高', mid='有一点', high='偏高')}。"
        f"{_advice(state)}"
    )


def _advice(state: MoodState) -> str:
    if state.irritation >= 0.55:
        return "话短一点、更冷一点，仍是夏目。"
    if state.affection >= 0.55 and state.energy >= 0:
        return "可以略松一点，仍保持清冷，不要热情轰炸。"
    if state.energy <= -0.4:
        return "话少一点，不要演精神。"
    return "按人设正常说。"


def _level(value: float, *, low: str, mid: str, high: str) -> str:
    if value >= 0.55:
        return high
    if value <= 0.25:
        return low
    return mid


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, float(value)))


def _toward_zero(value: float, step: float) -> float:
    if value > 0:
        return max(0.0, value - step)
    if value < 0:
        return min(0.0, value + step)
    return 0.0
