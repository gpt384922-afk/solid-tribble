from __future__ import annotations

import uuid
from typing import Iterable

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import joinedload

from crypto.secrets import SecretCipher
from db.models import Billing, SecretType, Server, ServerStatus, ServerTag
from services.schemas import SearchScope, ServerCreateSchema


class ServerService:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession], cipher: SecretCipher) -> None:
        self._session_factory = session_factory
        self._cipher = cipher

    async def create_server(self, payload: ServerCreateSchema) -> Server:
        encrypted_secret = None
        if payload.secret_type != SecretType.NONE and payload.secret_value:
            encrypted_secret = self._cipher.encrypt(payload.secret_value)

        server = Server(
            owner_telegram_id=payload.owner_telegram_id,
            name=payload.name,
            role=payload.role,
            provider=payload.provider,
            ip4=payload.ip4,
            ip6=payload.ip6,
            domain=payload.domain,
            ssh_port=payload.ssh_port,
            ssh_user=payload.ssh_user,
            secret_type=payload.secret_type,
            secret_encrypted=encrypted_secret,
            notes=payload.notes,
            tags=[ServerTag(tag=t) for t in payload.tags],
        )
        async with self._session_factory() as session:
            session.add(server)
            await session.commit()
            await session.refresh(server)
            return server

    async def list_servers(
        self,
        owner_telegram_id: int,
        page: int = 1,
        page_size: int = 5,
        scope: SearchScope = "all",
        search: str | None = None,
        role: str | None = None,
        provider: str | None = None,
        tag: str | None = None,
    ) -> tuple[list[Server], int]:
        offset = (max(page, 1) - 1) * page_size
        conditions = [Server.owner_telegram_id == owner_telegram_id]

        if scope == "active":
            conditions.append(Server.status == ServerStatus.ACTIVE)
        elif scope == "archived":
            conditions.append(Server.status == ServerStatus.ARCHIVED)

        if role:
            conditions.append(Server.role == role)
        if provider:
            conditions.append(Server.provider.ilike(f"%{provider}%"))

        if search:
            query = f"%{search}%"
            conditions.append(
                or_(
                    Server.name.ilike(query),
                    Server.ip4.ilike(query),
                    Server.provider.ilike(query),
                    Server.notes.ilike(query),
                )
            )

        base = select(Server).where(and_(*conditions)).options(joinedload(Server.tags)).order_by(Server.is_favorite.desc(), Server.name)

        if tag:
            base = base.join(ServerTag).where(ServerTag.tag == tag.lower())

        if scope == "expiring_7":
            sub = (
                select(Billing.server_id, func.min(Billing.expires_at).label("nearest_expires"))
                .where(Billing.expires_at >= func.current_date())
                .group_by(Billing.server_id)
                .subquery()
            )
            base = (
                base.join(sub, sub.c.server_id == Server.id)
                .where(func.date_part("day", sub.c.nearest_expires - func.current_date()) <= 7)
                .where(func.date_part("day", sub.c.nearest_expires - func.current_date()) >= 0)
            )

        count_query = select(func.count()).select_from(base.order_by(None).subquery())

        async with self._session_factory() as session:
            total = int(await session.scalar(count_query) or 0)
            servers = await session.scalars(base.offset(offset).limit(page_size))
            result = list(servers.unique().all())
            return result, total

    async def get_server(self, owner_telegram_id: int, server_id: str) -> Server | None:
        try:
            uid = uuid.UUID(server_id)
        except ValueError:
            return None

        async with self._session_factory() as session:
            server = await session.scalar(
                select(Server)
                .where(Server.id == uid, Server.owner_telegram_id == owner_telegram_id)
                .options(joinedload(Server.tags), joinedload(Server.billings))
            )
            return server

    async def get_server_any_owner(self, server_id: str) -> Server | None:
        try:
            uid = uuid.UUID(server_id)
        except ValueError:
            return None
        async with self._session_factory() as session:
            return await session.scalar(select(Server).where(Server.id == uid).options(joinedload(Server.tags), joinedload(Server.billings)))

    async def toggle_archive(self, owner_telegram_id: int, server_id: str) -> Server | None:
        try:
            server_uuid = uuid.UUID(server_id)
        except ValueError:
            return None
        async with self._session_factory() as session:
            server = await session.scalar(select(Server).where(Server.id == server_uuid, Server.owner_telegram_id == owner_telegram_id))
            if server is None:
                return None
            server.status = ServerStatus.ARCHIVED if server.status == ServerStatus.ACTIVE else ServerStatus.ACTIVE
            await session.commit()
            await session.refresh(server)
            return server

    async def toggle_favorite(self, owner_telegram_id: int, server_id: str) -> Server | None:
        try:
            server_uuid = uuid.UUID(server_id)
        except ValueError:
            return None
        async with self._session_factory() as session:
            server = await session.scalar(select(Server).where(Server.id == server_uuid, Server.owner_telegram_id == owner_telegram_id))
            if server is None:
                return None
            server.is_favorite = not server.is_favorite
            await session.commit()
            await session.refresh(server)
            return server

    async def update_server_notes_and_load(
        self,
        owner_telegram_id: int,
        server_id: str,
        notes: str,
        cpu_load: float | None,
        ram_load: float | None,
        disk_load: float | None,
        net_notes: str | None,
    ) -> bool:
        try:
            server_uuid = uuid.UUID(server_id)
        except ValueError:
            return False
        async with self._session_factory() as session:
            server = await session.scalar(select(Server).where(Server.id == server_uuid, Server.owner_telegram_id == owner_telegram_id))
            if server is None:
                return False
            server.notes = notes
            server.cpu_load = cpu_load
            server.ram_load = ram_load
            server.disk_load = disk_load
            server.net_notes = net_notes
            await session.commit()
            return True

    async def reveal_secret(self, owner_telegram_id: int, server_id: str) -> str | None:
        try:
            server_uuid = uuid.UUID(server_id)
        except ValueError:
            return None
        async with self._session_factory() as session:
            server = await session.scalar(select(Server).where(Server.id == server_uuid, Server.owner_telegram_id == owner_telegram_id))
            if server is None or not server.secret_encrypted:
                return None
            return self._cipher.decrypt(server.secret_encrypted)

    @staticmethod
    def tags_as_text(tags: Iterable[ServerTag]) -> str:
        result = [f"#{item.tag}" for item in tags]
        return ", ".join(result) if result else "-"

    @staticmethod
    def build_copy_block(server: Server) -> str:
        domain = server.domain or "-"
        return (
            f"IP: {server.ip4}\n"
            f"SSH: ssh {server.ssh_user}@{server.ip4} -p {server.ssh_port}\n"
            f"Домен: {domain}"
        )
