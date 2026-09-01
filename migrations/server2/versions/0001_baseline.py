"""Create the Server 2 migration baseline."""

from collections.abc import Sequence

revision: str = "server2_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Reserve the first revision; read-model tables start in W5."""


def downgrade() -> None:
    """Remove no objects because the baseline is intentionally empty."""
