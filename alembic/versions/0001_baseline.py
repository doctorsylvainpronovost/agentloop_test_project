"""baseline revision

Revision ID: 0001_baseline
Revises:
Create Date: 2026-03-05 00:00:00.000000

This baseline migration creates the PostgreSQL schema used by the FastAPI
weather API and includes concise schema-level documentation for cache usage.
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
        "users",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), primary_key=True),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("email", name="uq_users_email"),
        comment="Application users; owner entity for saved locations and cache preferences.",
    )

    op.create_table(
        "saved_locations",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), primary_key=True),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("location_name", sa.String(length=128), nullable=False),
        sa.Column("country_code", sa.String(length=2), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE", name="fk_saved_locations_user_id_users"),
        sa.UniqueConstraint("user_id", "location_name", "country_code", name="uq_saved_locations_user_scope"),
        comment="User-curated places to quickly re-request weather for repeat locations.",
    )

    op.create_table(
        "weather_cache",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), primary_key=True),
        sa.Column("location_name", sa.String(length=128), nullable=False),
        sa.Column("units", sa.String(length=16), nullable=False),
        sa.Column("forecast_date", sa.Date(), nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.UniqueConstraint(
            "location_name",
            "units",
            "forecast_date",
            "fetched_at",
            name="uq_weather_cache_version",
        ),
        comment=(
            "Weather response cache. Composite uniqueness on "
            "(location_name, units, forecast_date, fetched_at) keeps versioned fetches "
            "while preventing duplicate snapshots for the same fetch timestamp."
        ),
    )

    op.create_index(
        "ix_weather_cache_lookup",
        "weather_cache",
        ["location_name", "units", "forecast_date", "expires_at", sa.text("fetched_at DESC")],
        unique=False,
        postgresql_using="btree",
    )

    # Latest non-expired cache retrieval pattern used by application queries:
    # SELECT payload, fetched_at, expires_at
    # FROM weather_cache
    # WHERE location_name = :location_name
    #   AND units = :units
    #   AND forecast_date = :forecast_date
    #   AND expires_at > NOW()
    # ORDER BY fetched_at DESC
    # LIMIT 1;


def downgrade() -> None:
    op.drop_index("ix_weather_cache_lookup", table_name="weather_cache")
    op.drop_table("weather_cache")
    op.drop_table("saved_locations")
    op.drop_table("users")
