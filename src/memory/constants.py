"""P2-B 记忆相关常量。禁止把重复数字散落到调用处。"""

from __future__ import annotations

EMBED_DIM = 256
NGRAM_SIZES = (2, 3)
VECTOR_TABLE = "episodes"
EMBED_ID_PREFIX = "ep:"

DEFAULT_RETRIEVE_K = 5
RETRIEVE_K_MIN = 3
RETRIEVE_K_MAX = 8
DEFAULT_STYLE_MAX = 8
SUMMARY_MAX_CHARS = 240
LONG_DIGIT_LEN = 8
RECENT_TURNS_FOR_RETRIEVE = 4

DEFAULT_CHAT_ID = "web:local"
VECTOR_BACKEND_LANCEDB = "lancedb"

STATUS_ACTIVE = "active"
STATUS_PENDING = "pending"
STATUS_ARCHIVED = "archived"
STATUS_CANDIDATE = "candidate"
STATUS_CONFIRMED = "confirmed"
STATUS_REJECTED = "rejected"

SOURCE_EXTRACT = "extract"
SOURCE_GROUP_IMPORT = "group_import"
SOURCE_USER_CMD = "user_cmd"

LAYER_PROFILE = "profile"
LAYER_EPISODE = "episode"
LAYER_STYLE = "style"
EPISODE_LAYERS = frozenset({LAYER_EPISODE, "episodes"})
STYLE_LAYERS = frozenset({LAYER_STYLE})

HIGH_RISK_PREFIXES = ("dislikes.", "rule.", "promise.", "taboo.", "commitment.")
