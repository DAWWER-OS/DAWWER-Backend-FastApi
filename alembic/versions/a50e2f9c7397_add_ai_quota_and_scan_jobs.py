"""add_ai_quota_and_scan_jobs

Revision ID: a50e2f9c7397
Revises: 
Create Date: 2026-10-09 18:07:44.613400

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'a50e2f9c7397'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema: Add store quota fields and create scan_jobs audit table."""
    # 1. Add quota fields to stores with non-null server defaults to prevent temporary NULL states
    op.add_column(
        'stores',
        sa.Column(
            'ai_scans_limit',
            sa.Integer(),
            nullable=False,
            server_default=sa.text('30'),
        ),
    )
    op.add_column(
        'stores',
        sa.Column(
            'ai_scans_used',
            sa.Integer(),
            nullable=False,
            server_default=sa.text('0'),
        ),
    )
    op.add_column(
        'stores',
        sa.Column(
            'ai_scans_reset_at',
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now() + interval '30 days'"),
        ),
    )

    # 2. Create scan_jobs audit and tracking table
    op.create_table(
        'scan_jobs',
        sa.Column(
            'id',
            postgresql.UUID(as_uuid=False),
            nullable=False,
            server_default=sa.text('gen_random_uuid()'),
        ),
        sa.Column(
            'store_id',
            postgresql.UUID(as_uuid=False),
            nullable=False,
        ),
        sa.Column(
            'status',
            sa.String(length=32),
            nullable=False,
            server_default=sa.text("'PENDING'"),
        ),
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text('now()'),
        ),
        sa.Column(
            'updated_at',
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text('now()'),
        ),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('refunded_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('heartbeat_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('lease_owner', sa.String(length=255), nullable=True),
        sa.Column('quota_period_reset_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('failure_reason', sa.String(length=255), nullable=True),
        sa.Column('error_details', sa.Text(), nullable=True),
        sa.Column('idempotency_key', sa.String(length=255), nullable=True),
        sa.Column('shelf_job_id', sa.String(length=64), nullable=True),
        sa.Column(
            'extracted_drafts_count',
            sa.Integer(),
            nullable=False,
            server_default=sa.text('0'),
        ),
        sa.ForeignKeyConstraint(
            ['store_id'],
            ['stores.id'],
            name='fk_scan_jobs_store_id',
            ondelete='CASCADE',
        ),
        sa.PrimaryKeyConstraint('id', name='pk_scan_jobs'),
        sa.CheckConstraint(
            "status IN ('PENDING', 'PROCESSING', 'COMPLETED', 'FAILED', 'REFUNDED')",
            name='ck_scan_jobs_status',
        ),
    )

    # 3. Create indexes on scan_jobs
    op.create_index('ix_scan_jobs_id', 'scan_jobs', ['id'], unique=False)
    op.create_index('ix_scan_jobs_store_id', 'scan_jobs', ['store_id'], unique=False)
    op.create_index('ix_scan_jobs_status', 'scan_jobs', ['status'], unique=False)
    op.create_index('ix_scan_jobs_created_at', 'scan_jobs', ['created_at'], unique=False)
    op.create_index('ix_scan_jobs_heartbeat_at', 'scan_jobs', ['heartbeat_at'], unique=False)
    op.create_index('ix_scan_jobs_idempotency_key', 'scan_jobs', ['idempotency_key'], unique=False)
    op.create_index(
        'ix_scan_jobs_stale_lookup',
        'scan_jobs',
        ['status', 'heartbeat_at', 'created_at'],
        unique=False,
    )
    op.create_index(
        'ix_scan_jobs_store_idempotency',
        'scan_jobs',
        ['store_id', 'idempotency_key'],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema: Drop scan_jobs table and quota fields from stores."""
    # 1. Drop scan_jobs indexes and table
    op.drop_index('ix_scan_jobs_store_idempotency', table_name='scan_jobs')
    op.drop_index('ix_scan_jobs_stale_lookup', table_name='scan_jobs')
    op.drop_index('ix_scan_jobs_idempotency_key', table_name='scan_jobs')
    op.drop_index('ix_scan_jobs_heartbeat_at', table_name='scan_jobs')
    op.drop_index('ix_scan_jobs_created_at', table_name='scan_jobs')
    op.drop_index('ix_scan_jobs_status', table_name='scan_jobs')
    op.drop_index('ix_scan_jobs_store_id', table_name='scan_jobs')
    op.drop_index('ix_scan_jobs_id', table_name='scan_jobs')
    op.drop_table('scan_jobs')

    # 2. Drop quota columns from stores
    op.drop_column('stores', 'ai_scans_reset_at')
    op.drop_column('stores', 'ai_scans_used')
    op.drop_column('stores', 'ai_scans_limit')
