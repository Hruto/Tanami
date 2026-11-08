"""Request-scoped context (request id and user id).

Held in ``contextvars`` so structlog can attach it to every record and the error
handler can echo it back to the client (TQA 12). Never contains personal data.
"""

from __future__ import annotations

from contextvars import ContextVar

_request_id: ContextVar[str] = ContextVar("request_id", default="")
_user_id: ContextVar[str] = ContextVar("user_id", default="")


def set_request_id(value: str) -> None:
    _request_id.set(value)


def get_request_id() -> str:
    return _request_id.get()


def reset_request_id() -> None:
    _request_id.set("")


def set_user_id(value: str | None) -> None:
    _user_id.set(value or "")


def get_user_id() -> str:
    return _user_id.get()


def reset_user_id() -> None:
    _user_id.set("")
