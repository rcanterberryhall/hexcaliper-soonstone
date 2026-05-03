"""allow null raw_metar and raw_taf for prune

Revision ID: 354ae86c03cd
Revises: 0001
Create Date: 2026-05-02 20:08:34.609232

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '354ae86c03cd'
down_revision: Union[str, None] = '0001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("observations") as batch:
        batch.alter_column("raw_metar", existing_type=sa.Text(), nullable=True)
    with op.batch_alter_table("tafs") as batch:
        batch.alter_column("raw_taf", existing_type=sa.Text(), nullable=True)


def downgrade() -> None:
    with op.batch_alter_table("tafs") as batch:
        batch.alter_column("raw_taf", existing_type=sa.Text(), nullable=False)
    with op.batch_alter_table("observations") as batch:
        batch.alter_column("raw_metar", existing_type=sa.Text(), nullable=False)
