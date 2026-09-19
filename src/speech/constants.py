"""P3-A TTS 常量。"""

from __future__ import annotations

TTS_TEXT_LANG = "ja"
PROMPT_LANG = "ja"
TTS_MEDIA_TYPE = "wav"
TTS_TEXT_SPLIT_METHOD = "cut0"
TTS_CONNECT_TIMEOUT_S = 2.0
DEFAULT_TTS_TIMEOUT_S = 60.0
DEFAULT_TTS_API_BASE = "http://127.0.0.1:9880"
DEFAULT_REF_DIR = "data/natsume/references"
DEFAULT_CACHE_DIR = "data/tts_cache"
DEFAULT_GPT_WEIGHTS = "data/natsume/weights/natsume-e15.ckpt"
DEFAULT_SOVITS_WEIGHTS = "data/natsume/weights/natsume_e8_s1104.pth"
AUDIO_ID_LEN = 16
WAV_HEADER_SIZE = 44
ERROR_BODY_MAX = 500
SAD_FALLBACK_EMOTION = "neutral"
PROMPTS_FILE = "prompts.json"

EMOTION_REF_FILES = {
    "neutral": ("ref_01.wav", "あ、結構忙しかったわね"),
    "happy": ("ref_02.wav", "今日も一日、お疲れ様"),
    "angry": ("ref_06.wav", "言っとくけど変なことはしないからね"),
    "shy": ("ref_11.wav", "好き、大好き"),
}
