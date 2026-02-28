from __future__ import annotations

import enum
import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db.base import Base


class ServerRole(str, enum.Enum):
    BRIDGE = "bridge"
    XRAY_EDGE = "xray-edge"
    PANEL = "panel"
    DB = "db"
    TEST = "test"
    OTHER = "other"


class SecretType(str, enum.Enum):
    PASSWORD = "password"
    PRIVATE_KEY = "private_key"
    NONE = "none"


class ManualCategory(str, enum.Enum):
    INSTALL = "install"
    TROUBLESHOOT = "troubleshoot"
    UPGRADE = "upgrade"
    OTHER = "other"


class AccessUser(Base):
    __tablename__ = "access_users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AppSetting(Base):
    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    value: Mapped[str] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class Server(Base):
    __tablename__ = "servers"
    __table_args__ = (
        UniqueConstraint("owner_telegram_id", "name", name="uq_server_owner_name"),
        Index("ix_servers_owner_name", "owner_telegram_id", "name"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    owner_telegram_id: Mapped[int] = mapped_column(BigInteger, index=True)
    name: Mapped[str] = mapped_column(String(100))
    role: Mapped[ServerRole] = mapped_column(Enum(ServerRole, name="server_role_enum"))
    provider: Mapped[str] = mapped_column(String(100), default="")
    ip4: Mapped[str] = mapped_column(String(45))
    ip6: Mapped[str | None] = mapped_column(String(100), nullable=True)
    domain: Mapped[str | None] = mapped_column(String(255), nullable=True)
    ssh_port: Mapped[int] = mapped_column(Integer, default=22)
    ssh_user: Mapped[str] = mapped_column(String(100))
    secret_type: Mapped[SecretType] = mapped_column(Enum(SecretType, name="secret_type_enum"), default=SecretType.NONE)
    secret_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    notes: Mapped[str] = mapped_column(Text, default="")
    is_favorite: Mapped[bool] = mapped_column(Boolean, default=False)
    cpu_load: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)
    ram_load: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)
    disk_load: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)
    net_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    tags: Mapped[list[ServerTag]] = relationship(back_populates="server", cascade="all, delete-orphan")
    billings: Mapped[list[Billing]] = relationship(back_populates="server", cascade="all, delete-orphan")


class ServerTag(Base):
    __tablename__ = "server_tags"
    __table_args__ = (UniqueConstraint("server_id", "tag", name="uq_server_tag"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    server_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("servers.id", ondelete="CASCADE"))
    tag: Mapped[str] = mapped_column(String(50), index=True)

    server: Mapped[Server] = relationship(back_populates="tags")


class Billing(Base):
    __tablename__ = "billings"
    __table_args__ = (
        Index("ix_billings_expires_at", "expires_at"),
        CheckConstraint("price_amount >= 0", name="ck_billings_price_non_negative"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    server_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("servers.id", ondelete="CASCADE"))
    paid_at: Mapped[date] = mapped_column(Date)
    expires_at: Mapped[date] = mapped_column(Date)
    price_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    price_currency: Mapped[str] = mapped_column(String(10), default="RUB")
    period: Mapped[str] = mapped_column(String(20), default="1m")
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    server: Mapped[Server] = relationship(back_populates="billings")


class Manual(Base):
    __tablename__ = "manuals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    owner_telegram_id: Mapped[int] = mapped_column(BigInteger, index=True)
    title: Mapped[str] = mapped_column(String(200), index=True)
    category: Mapped[ManualCategory] = mapped_column(Enum(ManualCategory, name="manual_category_enum"), default=ManualCategory.OTHER)
    body_markdown: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    tags: Mapped[list[ManualTag]] = relationship(back_populates="manual", cascade="all, delete-orphan")


class ManualTag(Base):
    __tablename__ = "manual_tags"
    __table_args__ = (UniqueConstraint("manual_id", "tag", name="uq_manual_tag"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    manual_id: Mapped[int] = mapped_column(Integer, ForeignKey("manuals.id", ondelete="CASCADE"))
    tag: Mapped[str] = mapped_column(String(50), index=True)

    manual: Mapped[Manual] = relationship(back_populates="tags")


class SchemaVersion(Base):
    __tablename__ = "schema_version"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    version: Mapped[int] = mapped_column(Integer, default=1, unique=True)
    applied_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
