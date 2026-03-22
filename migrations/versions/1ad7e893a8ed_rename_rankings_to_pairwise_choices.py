"""rename rankings to pairwise_choices

Revision ID: 1ad7e893a8ed
Revises: 93883a4e94c6
Create Date: 2026-03-21 16:11:12.428601

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '1ad7e893a8ed'
down_revision: Union[str, Sequence[str], None] = '93883a4e94c6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Rename rankings column to pairwise_choices."""
    op.alter_column('ballots', 'rankings', new_column_name='pairwise_choices')


def downgrade() -> None:
    """Rename pairwise_choices column back to rankings."""
    op.alter_column('ballots', 'pairwise_choices', new_column_name='rankings')
