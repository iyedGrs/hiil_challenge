"""Idempotent demo seeding (spec/local-dev.md L4, L5, spec/backend.md B8).

Run with ``python -m app.seed_demo``. Seeds two preparers, one reviewer and one
reviewer recipient so the integrated loop can be demonstrated without manual SQL.

Credentials are obviously synthetic and printed to stdout for local use only.
They are development fixtures, not deployable accounts: the deployed environment
must create real accounts with real secrets.

Re-running updates the existing rows in place and never duplicates them.
"""

from __future__ import annotations

import logging
import sys
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.orm import Session as DbSession

from app.db import session_scope
from app.domain.enums import Role
from app.ids import RECIPIENT_PREFIX, USER_PREFIX, new_id
from app.models.user import Recipient, User
from app.security import hash_password

logger = logging.getLogger("app.seed_demo")

#: Shared password for every demo account. Local development only.
DEMO_PASSWORD = "demo-pass-1234"

#: Recipient remit label. Descriptive only: it must not claim official filing,
#: legal acceptance or certification (spec/backend.md B10).
DEMO_RECIPIENT_LABEL = "Demo review desk"
DEMO_RECIPIENT_REMIT = (
    "Synthetic demo reviewer inbox. Receives prepared dossiers for human review only; "
    "no official filing, legal advice or acceptance is implied."
)


@dataclass(frozen=True)
class DemoAccount:
    """One seeded account (spec/local-dev.md L5)."""

    email: str
    display_name: str
    role: Role


DEMO_ACCOUNTS: tuple[DemoAccount, ...] = (
    DemoAccount("preparer1@demo.local", "Demo Preparer One", Role.preparer),
    DemoAccount("preparer2@demo.local", "Demo Preparer Two", Role.preparer),
    DemoAccount("reviewer@demo.local", "Demo Reviewer", Role.reviewer),
)


def upsert_user(db: DbSession, account: DemoAccount, password: str) -> User:
    """Create or refresh ``account``. Matching is by lower-cased email."""
    existing = db.scalar(select(User).where(func.lower(User.email) == account.email.lower()))
    if existing is not None:
        existing.display_name = account.display_name
        existing.role = account.role
        existing.is_active = True
        # Re-hash so a rerun restores the documented demo password.
        existing.password_hash = hash_password(password)
        return existing

    user = User(
        id=new_id(USER_PREFIX),
        email=account.email.lower(),
        display_name=account.display_name,
        role=account.role,
        password_hash=hash_password(password),
        is_active=True,
    )
    db.add(user)
    db.flush()
    return user


def upsert_recipient(db: DbSession, reviewer: User) -> Recipient:
    """Create or refresh the single demo reviewer destination (B9, B10).

    ``GET /api/recipients`` reads these rows, which is why submission targets are
    server-owned and a preparer cannot submit to an arbitrary address.
    """
    existing = db.scalar(
        select(Recipient).where(
            Recipient.reviewer_id == reviewer.id,
            Recipient.label == DEMO_RECIPIENT_LABEL,
        )
    )
    if existing is not None:
        existing.remit = DEMO_RECIPIENT_REMIT
        existing.is_active = True
        return existing

    recipient = Recipient(
        id=new_id(RECIPIENT_PREFIX),
        reviewer_id=reviewer.id,
        label=DEMO_RECIPIENT_LABEL,
        remit=DEMO_RECIPIENT_REMIT,
        is_active=True,
    )
    db.add(recipient)
    db.flush()
    return recipient


def seed(db: DbSession, password: str = DEMO_PASSWORD) -> list[User]:
    """Seed demo accounts and the reviewer recipient. Safe to repeat."""
    users = [upsert_user(db, account, password) for account in DEMO_ACCOUNTS]
    reviewer = next(user for user in users if user.role is Role.reviewer)
    upsert_recipient(db, reviewer)
    return users


def main(argv: list[str] | None = None) -> int:
    """Entry point for ``python -m app.seed_demo`` (spec/local-dev.md L4)."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    del argv  # no command-line options
    with session_scope() as db:
        users = seed(db)

    print("Seeded synthetic demo accounts (local development only):")
    for user in users:
        print(f"  {user.email:<24} role={user.role.value:<9} password={DEMO_PASSWORD}")
    print(f"Reviewer destination: {DEMO_RECIPIENT_LABEL}")
    print("These are fake demo credentials. Do not reuse them anywhere real.")
    return 0


if __name__ == "__main__":  # pragma: no cover - process entry point
    sys.exit(main())
