"""Establish the empty database migration baseline.

Revision ID: 0001_database_baseline
Revises:
Create Date: 2026-07-17
"""

from collections.abc import Sequence

revision: str = "0001_database_baseline"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Establish the baseline without creating business tables."""


def downgrade() -> None:
    """Revert the empty baseline without dropping business data."""
