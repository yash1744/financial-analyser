"""Orchestrates the Plaid Link flow: PlaidService + repositories + cipher.

PlaidService talks to Plaid; this service owns persistence and the
business rules around connecting an institution.
"""

import logging
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.tracing import traced_span
from app.models.enums import PlaidItemStatus
from app.models.plaid_item import PlaidItem
from app.models.user import User
from app.repositories.plaid_item import PlaidItemRepository
from app.repositories.user import UserRepository
from app.schemas.plaid import LinkTokenResult
from app.services.exceptions import ConflictError, NotFoundError
from app.services.plaid import PlaidService
from app.utils.crypto import TokenCipher

logger = logging.getLogger(__name__)


class PlaidLinkService:
    def __init__(
        self,
        session: AsyncSession,
        plaid: PlaidService,
        cipher: TokenCipher,
    ) -> None:
        self.session = session
        self.plaid = plaid
        self.cipher = cipher
        self.users = UserRepository(session)
        self.items = PlaidItemRepository(session)

    async def _require_user(self, user_id: uuid.UUID) -> User:
        user = await self.users.get(user_id)
        if user is None:
            raise NotFoundError(f"user {user_id} does not exist")
        return user

    async def create_link_token(self, user_id: uuid.UUID) -> LinkTokenResult:
        user = await self._require_user(user_id)
        return await self.plaid.create_link_token(user.id)

    async def exchange_public_token(self, user_id: uuid.UUID, public_token: str) -> PlaidItem:
        """Exchange Link's public_token and persist the connected item.

        Update-mode re-links (Plaid keeps the same item_id) update the
        stored token in place; an item connected by a different user is
        rejected. A *fresh* Link session for an institution the user
        already has an active connection to is rejected too — Plaid mints
        a new item_id per session (in production as much as in sandbox),
        so without this check every re-link would duplicate the bank and
        its transactions.
        """
        with traced_span(
            "plaid.link.exchange_public_token", {"user.id": str(user_id)}
        ) as span:
            user = await self._require_user(user_id)

            exchanged = await self.plaid.exchange_public_token(public_token)
            # Also validates the fresh access token and yields institution info
            snapshot = await self.plaid.get_accounts(exchanged.access_token)
            institution_id = snapshot.item.get("institution_id")
            institution_name = snapshot.item.get("institution_name")
            if institution_id:
                span.set_attribute("institution_id", institution_id)

            encrypted = self.cipher.encrypt(exchanged.access_token)

            item = await self.items.get_by_plaid_item_id(exchanged.item_id)
            if item is not None:
                if item.user_id != user.id:
                    raise ConflictError("this institution connection belongs to another user")
                item.access_token_encrypted = encrypted
                item.institution_id = institution_id or item.institution_id
                item.institution_name = institution_name or item.institution_name
                item.status = PlaidItemStatus.ACTIVE
                span.set_attribute("outcome", "relinked")
                logger.info("Re-linked plaid item %s for user %s", exchanged.item_id, user.id)
            else:
                await self._reject_duplicate_institution(
                    user, exchanged.access_token, institution_id, institution_name
                )
                item = await self.items.create(
                    user_id=user.id,
                    plaid_item_id=exchanged.item_id,
                    access_token_encrypted=encrypted,
                    institution_id=institution_id,
                    institution_name=institution_name,
                )
                span.set_attribute("outcome", "created")
                logger.info("Linked new plaid item %s for user %s", exchanged.item_id, user.id)

            await self.session.commit()
            await self.session.refresh(item)
            return item

    async def _reject_duplicate_institution(
        self,
        user: User,
        new_access_token: str,
        institution_id: str | None,
        institution_name: str | None,
    ) -> None:
        """409 when the user already has an active item for this
        institution. Broken connections (login_required/error/disconnected)
        don't block: a fresh link is the recovery path — the stale item is
        retired so it stops being synced."""
        if not institution_id:
            return
        same_bank = await self.items.list_by_user_and_institution(
            user.id, institution_id
        )
        if any(i.status == PlaidItemStatus.ACTIVE for i in same_bank):
            # Release the just-created Plaid item so it doesn't linger
            # (and bill) — best-effort, the rejection stands regardless
            try:
                await self.plaid.remove_item(new_access_token)
            except Exception:
                logger.warning(
                    "could not remove duplicate plaid item at Plaid", exc_info=True
                )
            raise ConflictError(
                f"{institution_name or 'This bank'} is already connected"
            )
        for stale in same_bank:
            if stale.status != PlaidItemStatus.DISCONNECTED:
                stale.status = PlaidItemStatus.DISCONNECTED
                logger.info(
                    "Retiring stale plaid item %s (replaced by a fresh link)",
                    stale.plaid_item_id,
                )
