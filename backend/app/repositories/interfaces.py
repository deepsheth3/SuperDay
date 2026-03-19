from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession


class AccountRepository(ABC):
    @abstractmethod
    async def find_by_normalized_name(self, session: AsyncSession, tenant_id: UUID, normalized: str) -> UUID | None: ...

    @abstractmethod
    async def find_by_alias(self, session: AsyncSession, tenant_id: UUID, normalized_alias: str) -> UUID | None: ...


class CommunicationRepository(ABC):
    @abstractmethod
    async def list_candidates(
        self,
        session: AsyncSession,
        tenant_id: UUID,
        account_id: UUID,
        occurred_after: datetime,
        occurred_before: datetime,
        limit: int,
    ) -> list[UUID]: ...


class ActivityRepository(ABC):
    @abstractmethod
    async def recent_activity(
        self, session: AsyncSession, tenant_id: UUID, account_id: UUID, limit: int
    ) -> list[dict]: ...
