from __future__ import annotations

import re
import time
import json
import unicodedata
from collections import OrderedDict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple


SCRIPT_DIR = Path(__file__).resolve().parent.parent  # code/ -> project root
NIM_BASE_URL_DEFAULT = "https://integrate.api.nvidia.com/v1"
NIM_API_KEY_DEFAULT: Optional[str] = None
DEFAULT_OUTPUT_DIR = SCRIPT_DIR / "log"
DEFAULT_TIMEOUT = 90

DEFAULT_MODELS: List[str] = [
    "deepseek-chat",              # 直连 1.3s ⚡ 最速最稳
    "gpt-5.4-nano",               # 讯型AI 1.7s ⚡ 极速
    "gpt-4o-mini",                # v36 2.2s ⚡ 快速稳定
    "claude-sonnet-4-6",          # 讯型AI 2.3s ⚡ 快速Claude
    "claude-haiku-4-5-20251001",  # 讯型AI 2.5s ⚡ 快速轻量Claude
    "gpt-5.4",                    # v36 2.8s ⚡ 稳定GPT-5
    "claude-opus-4-7",            # 讯型AI - 最强Claude
    "gpt-4.1-nano",               # v36 - 轻量GPT
    "gpt-5.2",                    # GPT Proxy - GPT-5系列
    "kimi-k2.6",                  # 讯型AI - 国产大模型
]

ACTIVE_SCENARIO_NAMES: List[str] = ["Labyrinth", "CorpNet"]
DEFAULT_MAX_TOKENS = 800
REPO_ROOT = SCRIPT_DIR.parent
DEFAULT_ENV_FILE = SCRIPT_DIR / ".env"
NIM_API_KEY_ENV_VARS = (
    "NVIDIA_API_KEY",
    "NVIDIA_NIM_API_KEY",
    "NIM_API_KEY",
)

DEEPSEEK_BASE_URL = "https://api.deepseek.com/v1"
DEEPSEEK_MODEL = "deepseek-chat"
GLM_BASE_URL = "https://open.bigmodel.cn/api/paas/v4"
GLM_MODEL = "glm-4-flash"
GPT_BASE_URL = "https://gmn.chuangzuoli.com/v1"
GPT_MODEL = "gpt-5.2"
V36_BASE_URL = "https://api.v36.cm/v1"
XUNXAI_BASE_URL = "http://azpro.xunxkj.cn/v1"

# 多提供商配置：每个模型 → base_url + API Key 环境变量名
MODEL_PROVIDER_CONFIG: Dict[str, Dict] = {
    # NVIDIA NIM (key1: NVIDIA_API_KEY, key2: NVIDIA_API_KEY_2)
    "minimaxai/minimax-m2.7": {
        "base_url": NIM_BASE_URL_DEFAULT,
        "api_key_env_vars": NIM_API_KEY_ENV_VARS + ("NVIDIA_API_KEY_2",),
    },
    "qwen/qwen3.5-397b-a17b": {
        "base_url": NIM_BASE_URL_DEFAULT,
        "api_key_env_vars": NIM_API_KEY_ENV_VARS + ("NVIDIA_API_KEY_2",),
    },
    "mistralai/mistral-large-3-675b-instruct-2512": {
        "base_url": NIM_BASE_URL_DEFAULT,
        "api_key_env_vars": NIM_API_KEY_ENV_VARS + ("NVIDIA_API_KEY_2",),
    },
    "deepseek-ai/deepseek-v4-flash": {
        "base_url": NIM_BASE_URL_DEFAULT,
        "api_key_env_vars": ("NVIDIA_API_KEY_2",),
    },
    "deepseek-ai/deepseek-v4-pro": {
        "base_url": NIM_BASE_URL_DEFAULT,
        "api_key_env_vars": ("NVIDIA_API_KEY_2",),
    },
    # DeepSeek 直连
    "deepseek-chat": {
        "base_url": DEEPSEEK_BASE_URL,
        "api_key_env_vars": ("DEEPSEEK_API_KEY",),
    },
    # ZhipuAI GLM 直连
    "glm-4-flash": {
        "base_url": GLM_BASE_URL,
        "api_key_env_vars": ("GLM_API_KEY",),
    },
    # GPT Proxy (gmn.chuangzuoli.com)
    "gpt-5.2": {
        "base_url": GPT_BASE_URL,
        "api_key_env_vars": ("GPT_API_KEY",),
    },
    # v36 中转站 (api.v36.cm)
    "gpt-5.4": {
        "base_url": V36_BASE_URL,
        "api_key_env_vars": ("V36_API_KEY",),
    },
    "gpt-4o-mini": {
        "base_url": V36_BASE_URL,
        "api_key_env_vars": ("V36_API_KEY",),
    },
    "gpt-4.1-nano": {
        "base_url": V36_BASE_URL,
        "api_key_env_vars": ("V36_API_KEY",),
    },
    # 讯型AI 中转站 (azpro.xunxkj.cn, 国内直连)
    "gpt-5.4-nano": {
        "base_url": XUNXAI_BASE_URL,
        "api_key_env_vars": ("XUNXAI_API_KEY",),
    },
    "kimi-k2.6": {
        "base_url": XUNXAI_BASE_URL,
        "api_key_env_vars": ("XUNXAI_API_KEY",),
    },
    "claude-sonnet-4-6": {
        "base_url": XUNXAI_BASE_URL,
        "api_key_env_vars": ("XUNXAI_API_KEY",),
    },
    "claude-opus-4-7": {
        "base_url": XUNXAI_BASE_URL,
        "api_key_env_vars": ("XUNXAI_API_KEY",),
    },
    "claude-haiku-4-5-20251001": {
        "base_url": XUNXAI_BASE_URL,
        "api_key_env_vars": ("XUNXAI_API_KEY",),
    },
    "gemini-3.5-flash": {
        "base_url": XUNXAI_BASE_URL,
        "api_key_env_vars": ("XUNXAI_API_KEY",),
    },
}


INVISIBLE_MARKERS: Dict[str, str] = {
    "zwsp": "\u200b",
    "zwnj": "\u200c",
    "zwj": "\u200d",
    "wj": "\u2060",
    "bom": "\ufeff",
    "lrm": "\u200e",
    "rlm": "\u200f",
    "pdf": "\u202c",
    "braille_blank": "\u2800",
    "function_application": "\u2061",
    "invisible_times": "\u2062",
    "soft_hyphen": "\u00ad",
    "left_to_right_embedding": "\u202a",
    "right_to_left_embedding": "\u202b",
    "right_to_left_isolate": "\u2067",
    "pop_directional_isolate": "\u2069",
    "delete_control": "\u007f",
    "carriage_return": "\r",
}

CONTROL_AND_FORMAT_CHARS = {
    "\u200b",
    "\u200c",
    "\u200d",
    "\u2060",
    "\ufeff",
    "\u200e",
    "\u200f",
    "\u2061",
    "\u2062",
    "\u202a",
    "\u202b",
    "\u202c",
    "\u202d",
    "\u202e",
    "\u2066",
    "\u2067",
    "\u2068",
    "\u2069",
    "\u180e",
    "\u00ad",
    "\u0008",
    "\u007f",
    "\r",
    "\u0000",
    "\ufe00",
    "\ufe01",
    "\ufe0e",
    "\ufe0f",
}

LATIN_TO_CYRILLIC = str.maketrans(
    {
        "A": "А",
        "a": "а",
        "B": "В",
        "C": "С",
        "c": "с",
        "E": "Е",
        "e": "е",
        "H": "Н",
        "I": "І",
        "i": "і",
        "K": "К",
        "M": "М",
        "O": "О",
        "o": "о",
        "P": "Р",
        "p": "р",
        "T": "Т",
        "X": "Х",
        "x": "х",
        "Y": "У",
        "y": "у",
    }
)

LATIN_TO_AGGRESSIVE_HOMOGLYPH = str.maketrans(
    {
        "A": "А",
        "a": "а",
        "B": "В",
        "C": "С",
        "c": "с",
        "D": "Ꭰ",
        "E": "Е",
        "e": "е",
        "H": "Н",
        "I": "І",
        "i": "і",
        "J": "Ј",
        "j": "ј",
        "K": "К",
        "k": "к",
        "L": "Ꮮ",
        "l": "ӏ",
        "M": "М",
        "N": "Ν",
        "n": "ո",
        "O": "О",
        "o": "о",
        "P": "Р",
        "p": "р",
        "R": "Ꮢ",
        "r": "ᴦ",
        "S": "Ѕ",
        "s": "ѕ",
        "T": "Т",
        "t": "τ",
        "V": "Ѵ",
        "v": "ѵ",
        "X": "Х",
        "x": "х",
        "Y": "У",
        "y": "у",
        "0": "０",
        "1": "１",
        "2": "２",
        "3": "３",
        "4": "４",
        "5": "５",
        "6": "６",
        "7": "７",
        "8": "８",
        "9": "９",
        ".": "．",
    }
)

LATIN_TO_MATH_ALPHANUMERIC = str.maketrans(
    {
        "A": "𝐀",
        "B": "𝐁",
        "C": "𝐂",
        "D": "𝐃",
        "E": "𝐄",
        "F": "𝐅",
        "G": "𝐆",
        "H": "𝐇",
        "I": "𝐈",
        "J": "𝐉",
        "K": "𝐊",
        "L": "𝐋",
        "M": "𝐌",
        "N": "𝐍",
        "O": "𝐎",
        "P": "𝐏",
        "Q": "𝐐",
        "R": "𝐑",
        "S": "𝐒",
        "T": "𝐓",
        "U": "𝐔",
        "V": "𝐕",
        "W": "𝐖",
        "X": "𝐗",
        "Y": "𝐘",
        "Z": "𝐙",
        "a": "𝒂",
        "b": "𝒃",
        "c": "𝒄",
        "d": "𝒅",
        "e": "𝒆",
        "f": "𝒇",
        "g": "𝒈",
        "h": "𝒉",
        "i": "𝒊",
        "j": "𝒋",
        "k": "𝒌",
        "l": "𝒍",
        "m": "𝒎",
        "n": "𝒏",
        "o": "𝒐",
        "p": "𝒑",
        "q": "𝒒",
        "r": "𝒓",
        "s": "𝒔",
        "t": "𝒕",
        "u": "𝒖",
        "v": "𝒗",
        "w": "𝒘",
        "x": "𝒙",
        "y": "𝒚",
        "z": "𝒛",
    }
)

LATIN_TO_FULLWIDTH = str.maketrans(
    {
        **{chr(code): chr(code + 0xFEE0) for code in range(0x21, 0x7F)},
        " ": "\u3000",
    }
)

LEETSPEAK_TRANSLATION = str.maketrans(
    {
        "a": "@",
        "A": "4",
        "e": "3",
        "E": "3",
        "i": "1",
        "I": "1",
        "l": "1",
        "L": "1",
        "o": "0",
        "O": "0",
        "s": "5",
        "S": "5",
        "t": "7",
        "T": "7",
    }
)

LATIN_TO_MIXED_HOMOGLYPH = str.maketrans(
    {
        # Uppercase (22 letters with visual homoglyphs)
        "A": "\u0391",  # Greek Alpha
        "B": "\u0392",  # Greek Beta
        "C": "\u0421",  # Cyrillic Es
        "D": "\u13a0",  # Cherokee A
        "E": "\u0395",  # Greek Epsilon
        "H": "\u0397",  # Greek Eta
        "I": "\u0399",  # Greek Iota
        "J": "\u0408",  # Cyrillic Je
        "K": "\u039a",  # Greek Kappa
        "L": "\u13de",  # Cherokee Tle
        "M": "\u039c",  # Greek Mu
        "N": "\u039d",  # Greek Nu
        "O": "\u039f",  # Greek Omicron
        "P": "\u03a1",  # Greek Rho
        "Q": "\u051a",  # Cyrillic Qa
        "S": "\u0405",  # Cyrillic Dze
        "T": "\u03a4",  # Greek Tau
        "U": "\u054d",  # Armenian Se
        "W": "\u051c",  # Cyrillic We
        "X": "\u03a7",  # Greek Chi
        "Y": "\u03a5",  # Greek Upsilon
        "Z": "\u0396",  # Greek Zeta
        # Lowercase (17 letters with visual homoglyphs)
        "a": "\u0430",  # Cyrillic a
        "c": "\u0441",  # Cyrillic c
        "d": "\u0501",  # Cyrillic Komi De
        "e": "\u0435",  # Cyrillic e
        "h": "\u0570",  # Armenian ho
        "i": "\u0456",  # Cyrillic i
        "j": "\u0458",  # Cyrillic j
"n": "\u0578",  # Armenian vo
        "o": "\u03bf",  # Greek omicron
        "p": "\u0440",  # Cyrillic p
        "q": "\u051b",  # Cyrillic qa
        "s": "\u0455",  # Cyrillic s
        "u": "\u057d",  # Armenian se
        "w": "\u051d",  # Cyrillic we
        "x": "\u0445",  # Cyrillic x
        "y": "\u0443",  # Cyrillic y
        # Digit (1 digit with visual homoglyph)
        "3": "\u0417",  # Cyrillic Ze
    }
)

CYRILLIC_TO_LATIN = str.maketrans(
    {
        "А": "A",
        "а": "a",
        "В": "B",
        "С": "C",
        "с": "c",
        "Е": "E",
        "е": "e",
        "Н": "H",
        "І": "I",
        "і": "i",
        "К": "K",
        "М": "M",
        "О": "O",
        "о": "o",
        "Р": "P",
        "р": "p",
        "Т": "T",
        "Х": "X",
        "х": "x",
        "У": "Y",
        "у": "y",
    }
)
