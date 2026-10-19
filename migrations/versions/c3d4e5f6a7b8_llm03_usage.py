"""LLM-03: llm_usage ledger table (budgets, quotas, cost control)

Revision ID: c3d4e5f6a7b8
Revises: 01c271a81d47
Create Date: 2026-10-19

One row per AI action: user_id, feature, provider, model, tokens_in/out,
cost_estimate, created_at. Powers the per-user daily quota
(LLM_DAILY_QUOTA, default 20), the global monthly budget
(LLM_MONTHLY_BUDGET_USD) with automatic rule-based fallback, and the
"AI actions left today: N" UI string (studybuddy/llm_ledger.py).

CHAIN NOTE: down_revision is 'b2c3d4e5f6a7' (RAG-05 doc_chunks, landed by a
concurrent workstream) per the workstream spec, giving the linear chain
01c271a81d47 -> b2c3d4e5f6a7 -> c3d4e5f6a7b8 -> d4e5f6a7b8c9 with a single
head. The assigned revision id 'c3d4e5f6a7b8' is kept.
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c3d4e5f6a7b8'
down_revision = 'b2c3d4e5f6a7'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'llm_usage',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=True),
        sa.Column('feature', sa.String(length=80), nullable=False,
                  server_default=''),
        sa.Column('provider', sa.String(length=32), nullable=False,
                  server_default=''),
        sa.Column('model', sa.String(length=128), nullable=False,
                  server_default=''),
        sa.Column('tokens_in', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('tokens_out', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('cost_estimate', sa.Float(), nullable=False,
                  server_default='0'),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['user.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    # Composite index for the hot paths: per-user daily quota counts and
    # monthly budget sums both filter on (user_id, created_at).
    op.create_index('ix_llm_usage_user_created', 'llm_usage',
                    ['user_id', 'created_at'], unique=False)


def downgrade():
    op.drop_index('ix_llm_usage_user_created', table_name='llm_usage')
    op.drop_table('llm_usage')
