"""String-backed enum columns that coerce legacy uppercase DB values on read/write."""

from __future__ import annotations

import enum
from typing import Any

from sqlalchemy.types import String, TypeDecorator

# Legacy alias values stored in older rows -> canonical enum value string.
_LEGACY_VALUE_ALIASES: dict[type[enum.Enum], dict[str, str]] = {}


def register_legacy_enum_alias(
    enum_cls: type[enum.Enum], *, legacy_value: str, canonical_value: str
) -> None:
    bucket = _LEGACY_VALUE_ALIASES.setdefault(enum_cls, {})
    bucket[legacy_value.strip().lower()] = canonical_value


def _normalize_key(raw: str) -> str:
    return raw.strip().upper().replace("-", "_").replace(" ", "_")


def coerce_str_enum(enum_cls: type[enum.Enum], raw: Any) -> enum.Enum:
    """Resolve a DB/API string to an enum member (value-first, then legacy member name)."""
    if isinstance(raw, enum_cls):
        return raw
    if raw is None or not str(raw).strip():
        raise LookupError(f"{enum_cls.__name__}: empty value")
    text = str(raw).strip()
    lower = text.lower()
    aliases = _LEGACY_VALUE_ALIASES.get(enum_cls, {})
    if lower in aliases:
        lower = aliases[lower].lower()
    for member in enum_cls:
        if member.value.lower() == lower:
            return member
    name_key = _normalize_key(text)
    if name_key in enum_cls.__members__:
        return enum_cls[name_key]
    raise LookupError(
        f"{lower!r} is not a valid {enum_cls.__name__} value "
        f"(expected one of: {', '.join(m.value for m in enum_cls)})"
    )


class CoercedStrEnumType(TypeDecorator):
    """Persist lowercase enum values; tolerate legacy uppercase member names on read."""

    impl = String
    cache_ok = True

    def __init__(self, enum_cls: type[enum.Enum], *, length: int = 32) -> None:
        self.enum_cls = enum_cls
        self.length = length
        super().__init__(length)

    def process_bind_param(self, value: Any, dialect: Any) -> str | None:
        if value is None:
            return None
        member = coerce_str_enum(self.enum_cls, value)
        return member.value

    def process_result_value(self, value: Any, dialect: Any) -> enum.Enum | None:
        if value is None:
            return None
        return coerce_str_enum(self.enum_cls, value)


def coerced_enum_column(enum_cls: type[enum.Enum], *, length: int = 32) -> CoercedStrEnumType:
    return CoercedStrEnumType(enum_cls, length=length)
