"""Initial schema: stations, observations, tafs, taf_groups.

CRITICAL: PRAGMA auto_vacuum = INCREMENTAL must execute BEFORE any CREATE TABLE.
SQLite ignores the pragma on databases that already contain tables; this is the
only safe place to set it.

Revision ID: 0001
Revises:
Create Date: 2026-05-02
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


ISO8601_UTC_NOW = sa.text("(strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))")


def upgrade() -> None:
    # MUST be first — see module docstring.
    op.execute("PRAGMA auto_vacuum = INCREMENTAL")
    # auto_vacuum only takes effect after a VACUUM on a fresh DB.
    op.execute("VACUUM")

    op.create_table(
        "stations",
        sa.Column("station_id", sa.Text, primary_key=True),
        sa.Column("name", sa.Text, nullable=True),
        sa.Column("latitude", sa.REAL, nullable=False),
        sa.Column("longitude", sa.REAL, nullable=False),
        sa.Column("elevation_m", sa.REAL, nullable=True),
        sa.Column("state", sa.Text, nullable=True),
        sa.Column("station_type", sa.Text, nullable=True),
        sa.Column("taf_site", sa.Integer, nullable=False, server_default=sa.text("0")),
        sa.Column("active", sa.Integer, nullable=False, server_default=sa.text("1")),
        sa.Column("first_seen", sa.Text, nullable=False, server_default=ISO8601_UTC_NOW),
        sa.Column("last_seen", sa.Text, nullable=True),
    )

    op.create_table(
        "observations",
        sa.Column("station_id", sa.Text, sa.ForeignKey("stations.station_id"), nullable=False),
        sa.Column("observed_at", sa.Text, nullable=False),
        sa.Column("raw_metar", sa.Text, nullable=False),
        sa.Column("metar_type", sa.Text, nullable=True),
        sa.Column("temp_c", sa.REAL, nullable=True),
        sa.Column("dewpoint_c", sa.REAL, nullable=True),
        sa.Column("wind_dir_deg", sa.Integer, nullable=True),
        sa.Column("wind_speed_kt", sa.REAL, nullable=True),
        sa.Column("wind_gust_kt", sa.REAL, nullable=True),
        sa.Column("visibility_sm", sa.REAL, nullable=True),
        sa.Column("altimeter_inhg", sa.REAL, nullable=True),
        sa.Column("precip_1hr_in", sa.REAL, nullable=True),
        sa.Column("present_weather", sa.Text, nullable=True),
        sa.Column("cloud_layers", sa.Text, nullable=True),
        sa.Column("ceiling_ft", sa.Integer, nullable=True),
        sa.Column("flight_category", sa.Text, nullable=True),
        sa.Column("radar_image_path", sa.Text, nullable=True),
        sa.Column("ingested_at", sa.Text, nullable=False, server_default=ISO8601_UTC_NOW),
        sa.PrimaryKeyConstraint("station_id", "observed_at", name="pk_observations"),
    )
    op.create_index("idx_obs_observed_at", "observations", ["observed_at"])

    op.create_table(
        "tafs",
        sa.Column("taf_id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("station_id", sa.Text, sa.ForeignKey("stations.station_id"), nullable=False),
        sa.Column("issued_at", sa.Text, nullable=False),
        sa.Column("valid_from", sa.Text, nullable=False),
        sa.Column("valid_to", sa.Text, nullable=False),
        sa.Column("raw_taf", sa.Text, nullable=False),
        sa.Column("amendment_type", sa.Text, nullable=True),
        sa.Column(
            "parse_method",
            sa.Text,
            nullable=False,
            server_default=sa.text("'deterministic'"),
        ),
        sa.Column("parse_confidence", sa.REAL, nullable=True),
        sa.Column("parse_warnings", sa.Text, nullable=True),
        sa.Column("ingested_at", sa.Text, nullable=False, server_default=ISO8601_UTC_NOW),
        sa.UniqueConstraint(
            "station_id", "issued_at", "amendment_type", name="uq_tafs_issuance"
        ),
    )
    op.create_index("idx_tafs_station_issued", "tafs", ["station_id", "issued_at"])
    op.create_index("idx_tafs_valid_range", "tafs", ["valid_from", "valid_to"])

    op.create_table(
        "taf_groups",
        sa.Column(
            "taf_id",
            sa.Integer,
            sa.ForeignKey("tafs.taf_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("group_index", sa.Integer, nullable=False),
        sa.Column("group_type", sa.Text, nullable=False),
        sa.Column("group_from", sa.Text, nullable=False),
        sa.Column("group_to", sa.Text, nullable=False),
        sa.Column("probability_pct", sa.Integer, nullable=True),
        sa.Column("wind_dir_deg", sa.Integer, nullable=True),
        sa.Column("wind_speed_kt", sa.REAL, nullable=True),
        sa.Column("wind_gust_kt", sa.REAL, nullable=True),
        sa.Column("visibility_sm", sa.REAL, nullable=True),
        sa.Column("weather", sa.Text, nullable=True),
        sa.Column("cloud_layers", sa.Text, nullable=True),
        sa.Column("ceiling_ft", sa.Integer, nullable=True),
        sa.Column("flight_category", sa.Text, nullable=True),
        sa.PrimaryKeyConstraint("taf_id", "group_index", name="pk_taf_groups"),
    )
    op.create_index(
        "idx_taf_groups_temporal", "taf_groups", ["group_from", "group_to"]
    )


def downgrade() -> None:
    op.drop_index("idx_taf_groups_temporal", table_name="taf_groups")
    op.drop_table("taf_groups")
    op.drop_index("idx_tafs_valid_range", table_name="tafs")
    op.drop_index("idx_tafs_station_issued", table_name="tafs")
    op.drop_table("tafs")
    op.drop_index("idx_obs_observed_at", table_name="observations")
    op.drop_table("observations")
    op.drop_table("stations")
