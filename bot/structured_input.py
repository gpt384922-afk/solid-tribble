from __future__ import annotations

import re
from dataclasses import dataclass

from services.schemas import MANUAL_CATEGORY_MAP, ManualCreateSchema, parse_tags_input


class StructuredInputError(Exception):
    def __init__(self, errors: list[str]) -> None:
        self.errors = errors
        super().__init__("\n".join(errors))


@dataclass
class ParsedManualInput:
    manual: ManualCreateSchema


ADD_MANUAL_TEMPLATE = """Заполните шаблон и отправьте одним сообщением:

Название:
Категория:
Теги:
Текст (markdown):
"""


def _normalize_key(key: str) -> str:
    return re.sub(r"\s+", " ", key.strip().lower())


def _parse_labeled_text(text: str, aliases: dict[str, list[str]]) -> dict[str, str]:
    alias_to_field: dict[str, str] = {}
    for field, keys in aliases.items():
        for key in keys:
            alias_to_field[_normalize_key(key)] = field

    result: dict[str, str] = {}
    current_field: str | None = None

    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        if ":" in line:
            key_part, value_part = line.split(":", maxsplit=1)
            field = alias_to_field.get(_normalize_key(key_part))
            if field:
                result[field] = value_part.strip()
                current_field = field
                continue

        if current_field:
            prev = result.get(current_field, "")
            result[current_field] = f"{prev}\n{line}".strip("\n")
        elif line.strip():
            continue

    return result


def _optional(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    if cleaned in {"", "-", "—"}:
        return None
    return cleaned


def _require(field_value: str | None, label: str, errors: list[str]) -> str:
    value = _optional(field_value)
    if not value:
        errors.append(f"Поле «{label}» обязательно для заполнения.")
        return ""
    return value


def parse_manual_input(text: str, user_id: int) -> ParsedManualInput:
    aliases = {
        "title": ["Название"],
        "category": ["Категория"],
        "tags": ["Теги"],
        "body": ["Текст (markdown)", "Текст"],
    }
    values = _parse_labeled_text(text, aliases)
    errors: list[str] = []

    title = _require(values.get("title"), "Название", errors)
    category_raw = _require(values.get("category"), "Категория", errors).lower()
    if category_raw and category_raw not in MANUAL_CATEGORY_MAP:
        errors.append("Поле «Категория» должно быть: install/troubleshoot/upgrade/other.")
    body = _require(values.get("body"), "Текст (markdown)", errors)
    tags_raw = _optional(values.get("tags")) or ""

    if errors:
        raise StructuredInputError(errors)

    manual = ManualCreateSchema(
        owner_telegram_id=user_id,
        title=title,
        category=MANUAL_CATEGORY_MAP[category_raw],
        tags=parse_tags_input(tags_raw),
        body_markdown=body,
    )
    return ParsedManualInput(manual=manual)
