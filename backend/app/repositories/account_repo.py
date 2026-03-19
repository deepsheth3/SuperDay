from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.core import Account, AccountAlias
from app.repositories.interfaces import AccountRepository


class SqlAccountRepository(AccountRepository):
    async def find_by_normalized_name(self, session: AsyncSession, tenant_id: UUID, normalized: str) -> UUID | None:
        q = select(Account.account_id).where(
            Account.tenant_id == tenant_id,
            Account.normalized_account_name == normalized,
        ).limit(1)
        r = await session.execute(q)
        row = r.scalar_one_or_none()
        return row

    async def find_by_alias(self, session: AsyncSession, tenant_id: UUID, normalized_alias: str) -> UUID | None:
        q = select(AccountAlias.account_id).where(
            AccountAlias.tenant_id == tenant_id,
            AccountAlias.normalized_alias_text == normalized_alias,
        ).limit(1)
        r = await session.execute(q)
        return r.scalar_one_or_none()
