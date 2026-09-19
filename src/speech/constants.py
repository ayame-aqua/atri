"""P3 语音常量。P3-A TTS；P3-B ASR。"""

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

DEFAULT_ASR_MODEL = "sensevoice-small"
SENSEVOICE_MODEL_ID = "iic/SenseVoiceSmall"
SENSEVOICE_LANGUAGE = "zn"
ASR_WAV_RATE = 16000
WHISPER_FALLBACK_SIZE = "small"
ASR_MODEL_PREFIX = "faster-whisper-"
ASR_LANGUAGE = "zh"
ASR_NO_SPEECH_MAX = 0.6
ASR_MIN_AUDIO_BYTES = 2000
ASR_MAX_AUDIO_BYTES = 3 * 1024 * 1024
ASR_MIN_TEXT_CHARS = 2
ASR_BEAM_SIZE = 1
UNCLEAR_REPLY = "没听清"
USER_AUDIO_TYPE = "user_audio"
USER_TRANSCRIPT_TYPE = "user_transcript"
VAD_LEVEL_TYPE = "vad_level"
STATUS_UNCLEAR = "unclear"

EMOTION_REF_FILES = {
    "neutral": ("ref_01.wav", "あ、結構忙しかったわね"),
    "happy": ("ref_02.wav", "今日も一日、お疲れ様"),
    "angry": ("ref_06.wav", "言っとくけど変なことはしないからね"),
    "shy": ("ref_11.wav", "好き、大好き"),
}
