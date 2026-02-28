from __future__ import annotations

import json
from dataclasses import dataclass

from db.models import Manual, Server
from services.manual_service import ManualService
from services.server_service import ServerService


@dataclass
class ExportBundle:
    servers: list[dict]
    manuals: list[dict]

    def to_json(self) -> str:
        return json.dumps({"servers": self.servers, "manuals": self.manuals}, ensure_ascii=False, indent=2)


class ExportImportService:
    def __init__(self, server_service: ServerService, manual_service: ManualService) -> None:
        self._server_service = server_service
        self._manual_service = manual_service

    @staticmethod
    def _serialize_server(server: Server, include_secret: bool = False) -> dict:
        payload = {
            "name": server.name,
            "role": server.role.value,
            "provider": server.provider,
            "ip4": server.ip4,
            "ip6": server.ip6,
            "domain": server.domain,
            "ssh_port": server.ssh_port,
            "ssh_user": server.ssh_user,
            "secret_type": server.secret_type.value,
            "tags": [t.tag for t in server.tags],
            "notes": server.notes,
            "is_favorite": server.is_favorite,
            "cpu_load": float(server.cpu_load) if server.cpu_load is not None else None,
            "ram_load": float(server.ram_load) if server.ram_load is not None else None,
            "disk_load": float(server.disk_load) if server.disk_load is not None else None,
            "net_notes": server.net_notes,
        }
        if include_secret:
            payload["secret_encrypted"] = server.secret_encrypted
        return payload

    @staticmethod
    def _serialize_manual(manual: Manual) -> dict:
        return {
            "title": manual.title,
            "category": manual.category.value,
            "tags": [t.tag for t in manual.tags],
            "body_markdown": manual.body_markdown,
        }

    async def export_user_data(self, telegram_id: int, include_secret: bool = False) -> ExportBundle:
        servers, _ = await self._server_service.list_servers(telegram_id, page=1, page_size=1000, scope="all")
        manuals = await self._manual_service.list_manuals(telegram_id)
        return ExportBundle(
            servers=[self._serialize_server(s, include_secret=include_secret) for s in servers],
            manuals=[self._serialize_manual(m) for m in manuals],
        )
