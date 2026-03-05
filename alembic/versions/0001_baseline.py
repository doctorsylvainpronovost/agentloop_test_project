"""baseline revision

Revision ID: 0001_baseline
Revises:
Create Date: 2026-03-05 00:00:00.000000

"""

from typing import Sequence
from typing import Union

# revision identifiers, used by Alembic.
revision: str = "0001_baseline"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
