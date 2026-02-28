from datetime import date

import pytest
from pydantic import ValidationError

from db.models import ServerRole, SecretType
from services.schemas import BillingCreateSchema, ServerCreateSchema


def test_server_schema_valid() -> None:
    payload = ServerCreateSchema(
        owner_telegram_id=1,
        name="node-1",
        role=ServerRole.BRIDGE,
        provider="hetzner",
        ip4="1.1.1.1",
        ssh_port=22,
        ssh_user="root",
        secret_type=SecretType.PASSWORD,
        secret_value="pass",
        tags=["prod", "eu"],
        notes="ok",
    )
    assert payload.ip4 == "1.1.1.1"


def test_server_schema_invalid_ip() -> None:
    with pytest.raises(ValidationError):
        ServerCreateSchema(
            owner_telegram_id=1,
            name="node-1",
            role=ServerRole.BRIDGE,
            provider="hetzner",
            ip4="not_an_ip",
            ssh_port=22,
            ssh_user="root",
            secret_type=SecretType.NONE,
        )


def test_billing_dates_validation() -> None:
    with pytest.raises(ValidationError):
        BillingCreateSchema(
            server_id="00000000-0000-0000-0000-000000000001",
            paid_at=date(2026, 2, 10),
            expires_at=date(2026, 2, 1),
            price_amount="100",
            price_currency="RUB",
            period="1m",
        )
