from __future__ import annotations

import uuid
from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import joinedload

from db.models import Billing, Server, ServerStatus
from services.schemas import BillingCreateSchema


class BillingService:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def add_billing(self, payload: BillingCreateSchema) -> Billing:
        billing = Billing(
            server_id=uuid.UUID(payload.server_id),
            paid_at=payload.paid_at,
            expires_at=payload.expires_at,
            price_amount=payload.price_amount,
            price_currency=payload.price_currency,
            period=payload.period,
            comment=payload.comment,
        )
        async with self._session_factory() as session:
            session.add(billing)
            await session.commit()
            await session.refresh(billing)
            return billing

    async def list_expiring(self, owner_telegram_id: int, days: int) -> list[tuple[Server, Billing, int]]:
        start_date = date.today()
        end_date = start_date + timedelta(days=days)

        async with self._session_factory() as session:
            rows = await session.execute(
                select(Server, Billing)
                .join(Billing, Billing.server_id == Server.id)
                .where(
                    Server.owner_telegram_id == owner_telegram_id,
                    Server.status == ServerStatus.ACTIVE,
                    Billing.expires_at >= start_date,
                    Billing.expires_at <= end_date,
                )
                .order_by(Billing.expires_at.asc())
            )
            result: list[tuple[Server, Billing, int]] = []
            for server, billing in rows.all():
                delta = (billing.expires_at - start_date).days
                result.append((server, billing, delta))
            return result

    async def list_server_billings(self, owner_telegram_id: int, server_id: str) -> list[Billing]:
        try:
            server_uuid = uuid.UUID(server_id)
        except ValueError:
            return []
        async with self._session_factory() as session:
            server = await session.scalar(select(Server.id).where(Server.id == server_uuid, Server.owner_telegram_id == owner_telegram_id))
            if server is None:
                return []
            rows = await session.scalars(select(Billing).where(Billing.server_id == server_uuid).order_by(Billing.expires_at.desc()))
            return list(rows)

    async def nearest_billing_for_server(self, server_id: uuid.UUID) -> Billing | None:
        async with self._session_factory() as session:
            today = date.today()
            return await session.scalar(
                select(Billing)
                .where(Billing.server_id == server_id, Billing.expires_at >= today)
                .order_by(Billing.expires_at.asc())
            )

    async def monthly_summary(self, owner_telegram_id: int, target_date: date | None = None) -> dict[str, Decimal]:
        current = target_date or date.today()
        month_start = date(current.year, current.month, 1)
        next_month = date(current.year + (1 if current.month == 12 else 0), 1 if current.month == 12 else current.month + 1, 1)

        async with self._session_factory() as session:
            rows = await session.execute(
                select(Billing.price_currency, func.sum(Billing.price_amount))
                .join(Server, Server.id == Billing.server_id)
                .where(
                    Server.owner_telegram_id == owner_telegram_id,
                    Billing.paid_at >= month_start,
                    Billing.paid_at < next_month,
                )
                .group_by(Billing.price_currency)
            )

            result: dict[str, Decimal] = defaultdict(Decimal)
            for currency, amount in rows.all():
                result[str(currency)] = amount
            return dict(result)

    async def due_notifications(self, days_before: list[int]) -> list[tuple[Server, Billing, int]]:
        today = date.today()
        max_days = max(days_before)
        date_limit = today + timedelta(days=max_days)

        async with self._session_factory() as session:
            rows = await session.execute(
                select(Server, Billing)
                .join(Billing, Billing.server_id == Server.id)
                .options(joinedload(Server.tags))
                .where(
                    and_(
                        Server.status == ServerStatus.ACTIVE,
                        Billing.expires_at >= today,
                        Billing.expires_at <= date_limit,
                    )
                )
            )

            result: list[tuple[Server, Billing, int]] = []
            for server, billing in rows.all():
                delta = (billing.expires_at - today).days
                if delta in days_before:
                    result.append((server, billing, delta))
            return result
