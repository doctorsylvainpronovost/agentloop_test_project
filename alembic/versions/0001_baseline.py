"""baseline revision

Revision ID: 0001_baseline
Revises:
Create Date: 2026-03-05 00:00:00.000000

"""

from typing import Sequence
from typing import Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0001_baseline"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "weather_cache",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("lat", sa.Double(), nullable=False),
        sa.Column("lon", sa.Double(), nullable=False),
        sa.Column("units", sa.String(length=16), nullable=False),
        sa.Column("range", sa.String(length=16), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.CheckConstraint("lat BETWEEN -90 AND 90", name="ck_weather_cache_lat_bounds"),
        sa.CheckConstraint("lon BETWEEN -180 AND 180", name="ck_weather_cache_lon_bounds"),
        sa.CheckConstraint(
            "units IN ('metric', 'imperial')",
            name="ck_weather_cache_units_valid",
        ),
        sa.CheckConstraint("range IN ('1d', '3d', '7d')", name="ck_weather_cache_range_valid"),
        sa.CheckConstraint("expires_at > created_at", name="ck_weather_cache_expires_after_created"),
        sa.UniqueConstraint(
            "lat",
            "lon",
            "units",
            "range",
            "created_at",
            name="uq_weather_cache_key_version",
        ),
    )

    op.execute(
        """
        CREATE INDEX ix_weather_cache_lookup_latest
        ON weather_cache (lat, lon, units, range, created_at DESC, expires_at DESC);
        """
    )

    op.execute(
        """
        COMMENT ON TABLE weather_cache IS
        'Cache versions are grouped by (lat, lon, units, range). Multiple versions are allowed over time; uniqueness is enforced at (key + created_at) so freshness ordering remains deterministic.';
        """
    )
    op.execute(
        """
        COMMENT ON CONSTRAINT uq_weather_cache_key_version ON weather_cache IS
        'Enforces one version per composite key at a given created_at timestamp while preserving historical versions.';
        """
    )
    op.execute(
        """
        COMMENT ON INDEX ix_weather_cache_lookup_latest IS
        'Supports cache reads by equality key filters, then latest-first freshness ordering, with expires_at available for TTL filtering.';
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_weather_cache_lookup_latest")
    op.drop_table("weather_cache")
