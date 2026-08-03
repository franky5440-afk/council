from .base import detect as _detect

ID = "gemini"
CMD = "gemini"


def detect() -> dict:
    return _detect(CMD, ID)


def ask(prompt: str, timeout_s: int, max_chars: int) -> dict:
    raise NotImplementedError
