from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date

from services.schemas import (
    MANUAL_CATEGORY_MAP,
    ROLE_MAP,
    SECRET_TYPE_MAP,
    ManualCreateSchema,
    ServerCreateSchema,
    parse_tags_input,
)


class StructuredInputError(Exception):
    def __init__(self, errors: list[str]) -> None:
        self.errors = errors
        super().__init__("\n".join(errors))


@dataclass
class BillingDraft:
    paid_at: date
    expires_at: date
    amount: str
    currency: str
    period: str
    comment: str | None = None


@dataclass
class ParsedServerInput:
    server: ServerCreateSchema
    billing: BillingDraft


@dataclass
class ParsedManualInput:
    manual: ManualCreateSchema


ADD_SERVER_TEMPLATE = """Заполните шаблон и отправьте одним сообщением:

Название:
Роль:
Провайдер:
IPv4:
IPv6:
Домен:
SSH порт:
SSH пользователь:
Тип секрета (password/private_key/none):
Секрет:
Теги (через запятую):
Заметки:
Дата оплаты (YYYY-MM-DD):
Дата истечения (YYYY-MM-DD):
Сумма:
Валюта:
Период:
"""

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
            # Игнорируем лишние строки до первого поля, чтобы не ломать UX.
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


def parse_server_input(text: str, user_id: int) -> ParsedServerInput:
    aliases = {
        "name": ["Название"],
        "role": ["Роль"],
        "provider": ["Провайдер"],
        "ip4": ["IPv4"],
        "ip6": ["IPv6"],
        "domain": ["Домен"],
        "ssh_port": ["SSH порт"],
        "ssh_user": ["SSH пользователь"],
        "secret_type": ["Тип секрета (password/private_key/none)", "Тип секрета"],
        "secret_value": ["Секрет"],
        "tags": ["Теги (через запятую)", "Теги"],
        "notes": ["Заметки"],
        "paid_at": ["Дата оплаты (YYYY-MM-DD)", "Дата оплаты"],
        "expires_at": ["Дата истечения (YYYY-MM-DD)", "Дата истечения"],
        "amount": ["Сумма"],
        "currency": ["Валюта"],
        "period": ["Период"],
    }
    values = _parse_labeled_text(text, aliases)
    errors: list[str] = []

    name = _require(values.get("name"), "Название", errors)
    role_raw = _require(values.get("role"), "Роль", errors).lower()
    provider = _require(values.get("provider"), "Провайдер", errors)
    ip4 = _require(values.get("ip4"), "IPv4", errors)
    ssh_user = _require(values.get("ssh_user"), "SSH пользователь", errors)
    ssh_port_raw = _require(values.get("ssh_port"), "SSH порт", errors)
    secret_type_raw = _require(values.get("secret_type"), "Тип секрета", errors).lower()

    if role_raw and role_raw not in ROLE_MAP:
        errors.append("Поле «Роль» должно быть: bridge/xray-edge/panel/db/test/other.")
    if secret_type_raw and secret_type_raw not in SECRET_TYPE_MAP:
        errors.append("Поле «Тип секрета» должно быть: password/private_key/none.")

    secret_value = _optional(values.get("secret_value"))
    if secret_type_raw in {"password", "private_key"} and not secret_value:
        errors.append("Для выбранного типа секрета поле «Секрет» обязательно.")

    paid_at = _require(values.get("paid_at"), "Дата оплаты", errors)
    expires_at = _require(values.get("expires_at"), "Дата истечения", errors)
    amount = _require(values.get("amount"), "Сумма", errors)
    currency = _require(values.get("currency"), "Валюта", errors)
    period = _require(values.get("period"), "Период", errors)

    if errors:
        raise StructuredInputError(errors)

    try:
        ssh_port = int(ssh_port_raw)
    except ValueError as exc:
        raise StructuredInputError(["Поле «SSH порт» должно быть числом."]) from exc

    try:
        paid_at_date = date.fromisoformat(paid_at)
    except ValueError as exc:
        raise StructuredInputError(["Поле «Дата оплаты» должно быть в формате YYYY-MM-DD."]) from exc
    try:
        expires_at_date = date.fromisoformat(expires_at)
    except ValueError as exc:
        raise StructuredInputError(["Поле «Дата истечения» должно быть в формате YYYY-MM-DD."]) from exc

    tags_raw = _optional(values.get("tags")) or ""
    notes = _optional(values.get("notes")) or ""
    parsed = ServerCreateSchema(
        owner_telegram_id=user_id,
        name=name,
        role=ROLE_MAP[role_raw],
        provider=provider,
        ip4=ip4,
        ip6=_optional(values.get("ip6")),
        domain=_optional(values.get("domain")),
        ssh_port=ssh_port,
        ssh_user=ssh_user,
        secret_type=SECRET_TYPE_MAP[secret_type_raw],
        secret_value=secret_value,
        tags=parse_tags_input(tags_raw),
        notes=notes,
    )

    return ParsedServerInput(
        server=parsed,
        billing=BillingDraft(
            paid_at=paid_at_date,
            expires_at=expires_at_date,
            amount=amount,
            currency=currency,
            period=period,
        ),
    )


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
