"""SQLAlchemy ORM models matching the v0 schema in soonstone_roadmap.md.

Timestamps stored as ISO 8601 UTC text with a 'Z' suffix (sortable as strings
and compatible with SQLite's datetime() / julianday() functions). JSON arrays
and objects stored as TEXT (application layer serializes/deserializes); SQLite
JSON1 functions are available if needed.
"""
from __future__ import annotations

from sqlalchemy import (
    ForeignKey,
    Index,
    Integer,
    PrimaryKeyConstraint,
    REAL,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from soonstone.db import Base

ISO8601_UTC_NOW = text("(strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))")


class Station(Base):
    __tablename__ = "stations"

    station_id: Mapped[str] = mapped_column(Text, primary_key=True)
    name: Mapped[str | None] = mapped_column(Text, nullable=True)
    latitude: Mapped[float] = mapped_column(REAL, nullable=False)
    longitude: Mapped[float] = mapped_column(REAL, nullable=False)
    elevation_m: Mapped[float | None] = mapped_column(REAL, nullable=True)
    state: Mapped[str | None] = mapped_column(Text, nullable=True)
    station_type: Mapped[str | None] = mapped_column(Text, nullable=True)
    taf_site: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    active: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    first_seen: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=ISO8601_UTC_NOW
    )
    last_seen: Mapped[str | None] = mapped_column(Text, nullable=True)
    nws_forecast_url: Mapped[str | None] = mapped_column(Text, nullable=True)


class Observation(Base):
    __tablename__ = "observations"
    __table_args__ = (
        PrimaryKeyConstraint("station_id", "observed_at", name="pk_observations"),
        Index("idx_obs_observed_at", "observed_at"),
    )

    station_id: Mapped[str] = mapped_column(
        Text, ForeignKey("stations.station_id"), nullable=False
    )
    observed_at: Mapped[str] = mapped_column(Text, nullable=False)
    raw_metar: Mapped[str | None] = mapped_column(Text, nullable=True)
    metar_type: Mapped[str | None] = mapped_column(Text, nullable=True)
    temp_c: Mapped[float | None] = mapped_column(REAL, nullable=True)
    dewpoint_c: Mapped[float | None] = mapped_column(REAL, nullable=True)
    wind_dir_deg: Mapped[int | None] = mapped_column(Integer, nullable=True)
    wind_speed_kt: Mapped[float | None] = mapped_column(REAL, nullable=True)
    wind_gust_kt: Mapped[float | None] = mapped_column(REAL, nullable=True)
    visibility_sm: Mapped[float | None] = mapped_column(REAL, nullable=True)
    altimeter_inhg: Mapped[float | None] = mapped_column(REAL, nullable=True)
    precip_1hr_in: Mapped[float | None] = mapped_column(REAL, nullable=True)
    present_weather: Mapped[str | None] = mapped_column(Text, nullable=True)
    cloud_layers: Mapped[str | None] = mapped_column(Text, nullable=True)
    ceiling_ft: Mapped[int | None] = mapped_column(Integer, nullable=True)
    flight_category: Mapped[str | None] = mapped_column(Text, nullable=True)
    radar_image_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    ingested_at: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=ISO8601_UTC_NOW
    )


class Taf(Base):
    __tablename__ = "tafs"
    __table_args__ = (
        UniqueConstraint(
            "station_id", "issued_at", "amendment_type", name="uq_tafs_issuance"
        ),
        Index("idx_tafs_station_issued", "station_id", "issued_at"),
        Index("idx_tafs_valid_range", "valid_from", "valid_to"),
    )

    taf_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    station_id: Mapped[str] = mapped_column(
        Text, ForeignKey("stations.station_id"), nullable=False
    )
    issued_at: Mapped[str] = mapped_column(Text, nullable=False)
    valid_from: Mapped[str] = mapped_column(Text, nullable=False)
    valid_to: Mapped[str] = mapped_column(Text, nullable=False)
    raw_taf: Mapped[str | None] = mapped_column(Text, nullable=True)
    amendment_type: Mapped[str | None] = mapped_column(Text, nullable=True)
    parse_method: Mapped[str] = mapped_column(
        Text, nullable=False, default="deterministic"
    )
    parse_confidence: Mapped[float | None] = mapped_column(REAL, nullable=True)
    parse_warnings: Mapped[str | None] = mapped_column(Text, nullable=True)
    ingested_at: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=ISO8601_UTC_NOW
    )

    groups: Mapped[list["TafGroup"]] = relationship(
        back_populates="taf", cascade="all, delete-orphan", order_by="TafGroup.group_index"
    )


class TafGroup(Base):
    __tablename__ = "taf_groups"
    __table_args__ = (
        PrimaryKeyConstraint("taf_id", "group_index", name="pk_taf_groups"),
        Index("idx_taf_groups_temporal", "group_from", "group_to"),
    )

    taf_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("tafs.taf_id", ondelete="CASCADE"), nullable=False
    )
    group_index: Mapped[int] = mapped_column(Integer, nullable=False)
    group_type: Mapped[str] = mapped_column(Text, nullable=False)
    group_from: Mapped[str] = mapped_column(Text, nullable=False)
    group_to: Mapped[str] = mapped_column(Text, nullable=False)
    probability_pct: Mapped[int | None] = mapped_column(Integer, nullable=True)
    wind_dir_deg: Mapped[int | None] = mapped_column(Integer, nullable=True)
    wind_speed_kt: Mapped[float | None] = mapped_column(REAL, nullable=True)
    wind_gust_kt: Mapped[float | None] = mapped_column(REAL, nullable=True)
    visibility_sm: Mapped[float | None] = mapped_column(REAL, nullable=True)
    weather: Mapped[str | None] = mapped_column(Text, nullable=True)
    cloud_layers: Mapped[str | None] = mapped_column(Text, nullable=True)
    ceiling_ft: Mapped[int | None] = mapped_column(Integer, nullable=True)
    flight_category: Mapped[str | None] = mapped_column(Text, nullable=True)

    taf: Mapped[Taf] = relationship(back_populates="groups")


class NwsForecast(Base):
    __tablename__ = "nws_forecasts"
    __table_args__ = (
        UniqueConstraint(
            "station_id", "valid_from", "valid_to",
            name="uq_nws_forecasts_period",
        ),
        Index("idx_nws_station_valid", "station_id", "valid_from"),
    )

    nws_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    station_id: Mapped[str] = mapped_column(
        Text, ForeignKey("stations.station_id"), nullable=False
    )
    period_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    valid_from: Mapped[str] = mapped_column(Text, nullable=False)
    valid_to: Mapped[str] = mapped_column(Text, nullable=False)
    temperature_f: Mapped[int | None] = mapped_column(Integer, nullable=True)
    wind_dir: Mapped[str | None] = mapped_column(Text, nullable=True)
    wind_speed: Mapped[str | None] = mapped_column(Text, nullable=True)
    pop_pct: Mapped[int | None] = mapped_column(Integer, nullable=True)
    short_forecast: Mapped[str | None] = mapped_column(Text, nullable=True)
    detailed_forecast: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    ingested_at: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=ISO8601_UTC_NOW
    )
