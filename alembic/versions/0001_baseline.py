"""baseline revision

Revision ID: 0001_baseline
Revises:
Create Date: 2026-03-05 00:00:00.000000

"""

from typing import Sequence
from typing import Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "0001_baseline"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

COORDINATE_PRECISION = 9
COORDINATE_SCALE = 6


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.BigInteger(), primary_key=True, nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("email", name="uq_users_email"),
    )

    op.create_table(
        "saved_locations",
        sa.Column("id", sa.BigInteger(), primary_key=True, nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column(
            "latitude",
            sa.Numeric(precision=COORDINATE_PRECISION, scale=COORDINATE_SCALE),
            nullable=False,
        ),
        sa.Column(
            "longitude",
            sa.Numeric(precision=COORDINATE_PRECISION, scale=COORDINATE_SCALE),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_saved_locations_user_id_users"),
        sa.CheckConstraint(
            "latitude >= -90 AND latitude <= 90",
            name="ck_saved_locations_latitude_range",
        ),
        sa.CheckConstraint(
            "longitude >= -180 AND longitude <= 180",
            name="ck_saved_locations_longitude_range",
        ),
    )

    op.create_index("ix_saved_locations_user_id", "saved_locations", ["user_id"])
    op.create_index("ix_saved_locations_user_id_name", "saved_locations", ["user_id", "name"])


def downgrade() -> None:
    op.drop_index("ix_saved_locations_user_id_name", table_name="saved_locations")
    op.drop_index("ix_saved_locations_user_id", table_name="saved_locations")
    op.drop_table("saved_locations")
    op.drop_table("users")
