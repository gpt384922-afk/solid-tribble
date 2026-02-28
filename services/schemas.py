from __future__ import annotations

import ipaddress
import re
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from db.models import ManualCategory, SecretType, ServerRole


class ServerCreateSchema(BaseModel):
    owner_telegram_id: int
    name: str = Field(min_length=1, max_length=100)
    role: ServerRole
    provider: str = Field(min_length=1, max_length=100)
    ip4: str
    ip6: str | None = None
    domain: str | None = None
    ssh_port: int = Field(default=22, ge=1, le=65535)
    ssh_user: str = Field(min_length=1, max_length=100)
    secret_type: SecretType = SecretType.NONE
    secret_value: str | None = None
    tags: list[str] = Field(default_factory=list)
    notes: str = ""

    @field_validator("ip4")
    @classmethod
    def validate_ip4(cls, value: str) -> str:
        ip = ipaddress.ip_address(value.strip())
        if ip.version != 4:
            raise ValueError("Требуется IPv4")
        return value.strip()

    @field_validator("ip6")
    @classmethod
    def validate_ip6(cls, value: str | None) -> str | None:
        if not value:
            return None
        ip = ipaddress.ip_address(value.strip())
        if ip.version != 6:
            raise ValueError("Требуется IPv6")
        return value.strip()

    @field_validator("domain")
    @classmethod
    def validate_domain(cls, value: str | None) -> str | None:
        if not value:
            return None
        domain = value.strip().lower()
        if len(domain) > 255 or "." not in domain:
            raise ValueError("Некорректный домен")
        return domain

    @field_validator("tags")
    @classmethod
    def normalize_tags(cls, value: list[str]) -> list[str]:
        seen: set[str] = set()
        result: list[str] = []
        for raw in value:
            tag = raw.strip().lower()
            if not tag or tag in seen:
                continue
            seen.add(tag)
            result.append(tag)
        return result

    @field_validator("secret_value")
    @classmethod
    def validate_secret_value(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        return value or None


class BillingCreateSchema(BaseModel):
    server_id: str
    paid_at: date
    expires_at: date
    price_amount: Decimal
    price_currency: str = Field(default="RUB", min_length=3, max_length=10)
    period: str = Field(default="1m", min_length=1, max_length=20)
    comment: str | None = None

    @field_validator("price_amount", mode="before")
    @classmethod
    def parse_amount(cls, value: str | float | Decimal) -> Decimal:
        if isinstance(value, Decimal):
            amount = value
        else:
            try:
                amount = Decimal(str(value).replace(",", "."))
            except InvalidOperation as exc:
                raise ValueError("Сумма должна быть числом") from exc
        if amount < 0:
            raise ValueError("Сумма не может быть отрицательной")
        return amount

    @field_validator("price_currency")
    @classmethod
    def normalize_currency(cls, value: str) -> str:
        return value.strip().upper()

    @field_validator("expires_at")
    @classmethod
    def validate_dates(cls, value: date, info) -> date:
        paid_at = info.data.get("paid_at")
        if paid_at and value < paid_at:
            raise ValueError("Дата истечения не может быть раньше даты оплаты")
        return value


class ManualCreateSchema(BaseModel):
    owner_telegram_id: int
    title: str = Field(min_length=1, max_length=200)
    category: ManualCategory = ManualCategory.OTHER
    tags: list[str] = Field(default_factory=list)
    body_markdown: str = Field(min_length=1)

    @field_validator("tags")
    @classmethod
    def normalize_tags(cls, value: list[str]) -> list[str]:
        return ServerCreateSchema.normalize_tags(value)


ROLE_MAP: dict[str, ServerRole] = {
    "bridge": ServerRole.BRIDGE,
    "xray-edge": ServerRole.XRAY_EDGE,
    "panel": ServerRole.PANEL,
    "db": ServerRole.DB,
    "test": ServerRole.TEST,
    "other": ServerRole.OTHER,
}

MANUAL_CATEGORY_MAP: dict[str, ManualCategory] = {
    "install": ManualCategory.INSTALL,
    "troubleshoot": ManualCategory.TROUBLESHOOT,
    "upgrade": ManualCategory.UPGRADE,
    "other": ManualCategory.OTHER,
}

SECRET_TYPE_MAP: dict[str, SecretType] = {
    "password": SecretType.PASSWORD,
    "private_key": SecretType.PRIVATE_KEY,
    "none": SecretType.NONE,
}


def parse_tags_input(raw: str) -> list[str]:
    if not raw.strip():
        return []
    parts = re.split(r"[,\s]+", raw.strip())
    return [p for p in parts if p]


def parse_manual_commands(markdown_text: str) -> list[str]:
    pattern = re.compile(r"```(?:[a-zA-Z0-9_+-]*)\n(.*?)```", re.DOTALL)
    return [m.strip() for m in pattern.findall(markdown_text) if m.strip()]


SearchScope = Literal["all", "expiring_7"]
