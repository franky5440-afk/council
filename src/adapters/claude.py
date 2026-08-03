from .base import detect as _detect

ID = "claude"
CMD = "claude"


def detect() -> dict:
    return _detect(CMD, ID)


def ask(prompt: str, model: str | None, timeout_s: int, max_chars: int) -> dict:
    raise NotImplementedError
