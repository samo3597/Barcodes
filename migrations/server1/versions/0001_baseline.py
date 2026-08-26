"""Create the Server 1 migration baseline."""

from collections.abc import Sequence

revision: str = "server1_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Reserve the first revision; domain tables start in W2."""


def downgrade() -> None:
    """Remove no objects because the baseline is intentionally empty."""
