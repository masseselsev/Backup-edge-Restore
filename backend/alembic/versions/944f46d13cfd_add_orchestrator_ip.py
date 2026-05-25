"""add orchestrator ip to settings

Revision ID: 944f46d13cfd
Revises: db382becdc57
Create Date: 2026-05-25 11:35:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '944f46d13cfd'
down_revision: Union[str, None] = 'db382becdc57'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('settings', sa.Column('orchestrator_ip', sa.String(), nullable=False, server_default=''))


def downgrade() -> None:
    op.drop_column('settings', 'orchestrator_ip')
