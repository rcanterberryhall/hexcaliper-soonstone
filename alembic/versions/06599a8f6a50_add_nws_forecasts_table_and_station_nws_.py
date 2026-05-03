"""add nws_forecasts table and Station.nws_forecast_url column

Revision ID: 06599a8f6a50
Revises: 354ae86c03cd
Create Date: 2026-05-02 22:07:00.472578

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '06599a8f6a50'
down_revision: Union[str, None] = '354ae86c03cd'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("stations") as batch:
        batch.add_column(sa.Column("nws_forecast_url", sa.Text, nullable=True))

    op.create_table(
        "nws_forecasts",
        sa.Column("nws_id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("station_id", sa.Text, sa.ForeignKey("stations.station_id"), nullable=False),
        sa.Column("period_name", sa.Text, nullable=True),
        sa.Column("valid_from", sa.Text, nullable=False),
        sa.Column("valid_to", sa.Text, nullable=False),
        sa.Column("temperature_f", sa.Integer, nullable=True),
        sa.Column("wind_dir", sa.Text, nullable=True),
        sa.Column("wind_speed", sa.Text, nullable=True),
        sa.Column("pop_pct", sa.Integer, nullable=True),
        sa.Column("short_forecast", sa.Text, nullable=True),
        sa.Column("detailed_forecast", sa.Text, nullable=True),
        sa.Column("raw_json", sa.Text, nullable=True),
        sa.Column(
            "ingested_at", sa.Text, nullable=False,
            server_default=sa.text("(strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))"),
        ),
        sa.UniqueConstraint(
            "station_id", "valid_from", "valid_to", name="uq_nws_forecasts_period"
        ),
    )
    op.create_index("idx_nws_station_valid", "nws_forecasts", ["station_id", "valid_from"])


def downgrade() -> None:
    op.drop_index("idx_nws_station_valid", table_name="nws_forecasts")
    op.drop_table("nws_forecasts")
    with op.batch_alter_table("stations") as batch:
        batch.drop_column("nws_forecast_url")
