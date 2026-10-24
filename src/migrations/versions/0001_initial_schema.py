"""initial schema

Every table from the feature spec, the user_closure triggers, and the AI principal.

Revision ID: 0001
Revises:
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = '0001'
down_revision = None
branch_labels = None
depends_on = None


# user_closure is derived from users.manager_id and never written by application code.
# Self rows (depth 0) are included, so "ancestors of X" and "subtree of X" both include X.
CLOSURE_SQL = """
CREATE FUNCTION user_closure_insert() RETURNS trigger AS $$
BEGIN
    INSERT INTO user_closure (ancestor_id, descendant_id, depth) VALUES (NEW.id, NEW.id, 0);
    IF NEW.manager_id IS NOT NULL THEN
        INSERT INTO user_closure (ancestor_id, descendant_id, depth)
        SELECT ancestor_id, NEW.id, depth + 1 FROM user_closure WHERE descendant_id = NEW.manager_id;
    END IF;
    RETURN NULL;
END $$ LANGUAGE plpgsql;

CREATE FUNCTION user_closure_check_cycle() RETURNS trigger AS $$
BEGIN
    IF NEW.manager_id IS NOT NULL AND EXISTS (
        SELECT 1 FROM user_closure WHERE ancestor_id = NEW.id AND descendant_id = NEW.manager_id
    ) THEN
        RAISE EXCEPTION 'manager cycle: % is in the subtree of %', NEW.manager_id, NEW.id
            USING ERRCODE = 'check_violation';
    END IF;
    RETURN NEW;
END $$ LANGUAGE plpgsql;

-- Moving a user moves their whole subtree: drop every path from the old ancestors into the
-- subtree, then join the new manager's ancestors to every node of the subtree.
CREATE FUNCTION user_closure_move() RETURNS trigger AS $$
BEGIN
    DELETE FROM user_closure c
    USING user_closure sub, user_closure sup
    WHERE sub.ancestor_id = NEW.id
      AND c.descendant_id = sub.descendant_id
      AND sup.descendant_id = NEW.id AND sup.depth > 0
      AND c.ancestor_id = sup.ancestor_id;
    IF NEW.manager_id IS NOT NULL THEN
        INSERT INTO user_closure (ancestor_id, descendant_id, depth)
        SELECT sup.ancestor_id, sub.descendant_id, sup.depth + sub.depth + 1
        FROM user_closure sup, user_closure sub
        WHERE sup.descendant_id = NEW.manager_id AND sub.ancestor_id = NEW.id;
    END IF;
    RETURN NULL;
END $$ LANGUAGE plpgsql;

CREATE TRIGGER users_closure_insert AFTER INSERT ON users
    FOR EACH ROW EXECUTE FUNCTION user_closure_insert();
CREATE TRIGGER users_closure_check_cycle BEFORE UPDATE OF manager_id ON users
    FOR EACH ROW WHEN (OLD.manager_id IS DISTINCT FROM NEW.manager_id)
    EXECUTE FUNCTION user_closure_check_cycle();
CREATE TRIGGER users_closure_move AFTER UPDATE OF manager_id ON users
    FOR EACH ROW WHEN (OLD.manager_id IS DISTINCT FROM NEW.manager_id)
    EXECUTE FUNCTION user_closure_move();
"""

DROP_CLOSURE_SQL = """
DROP TRIGGER IF EXISTS users_closure_move ON users;
DROP TRIGGER IF EXISTS users_closure_check_cycle ON users;
DROP TRIGGER IF EXISTS users_closure_insert ON users;
DROP FUNCTION IF EXISTS user_closure_move();
DROP FUNCTION IF EXISTS user_closure_check_cycle();
DROP FUNCTION IF EXISTS user_closure_insert();
"""

# The single AI principal and its event-log cursor exist in every environment, not just seeded ones.
SEED_SQL = """
INSERT INTO ai_agent (name, scopes)
VALUES ('assistant', ARRAY['conversations:read', 'suggestions:create', 'suggestions:status']);
INSERT INTO event_consumers (name, last_event_id) VALUES ('ai', 0);
"""


def upgrade() -> None:
    op.create_table('ai_agent',
    sa.Column('id', sa.Uuid(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('name', sa.Text(), nullable=False),
    sa.Column('scopes', postgresql.ARRAY(sa.Text()), server_default=sa.text("'{}'"), nullable=False),
    sa.Column('active', sa.Boolean(), server_default=sa.text('true'), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_ai_agent')),
    sa.UniqueConstraint('name', name=op.f('uq_ai_agent_name'))
    )
    op.create_table('departments',
    sa.Column('id', sa.Uuid(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('name', sa.Text(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_departments')),
    sa.UniqueConstraint('name', name=op.f('uq_departments_name'))
    )
    op.create_table('event_consumers',
    sa.Column('name', sa.Text(), nullable=False),
    sa.Column('last_event_id', sa.BigInteger(), server_default=sa.text('0'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('name', name=op.f('pk_event_consumers'))
    )
    op.create_table('users',
    sa.Column('id', sa.Uuid(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('email', sa.Text(), nullable=False),
    sa.Column('password_hash', sa.Text(), nullable=False),
    sa.Column('name', sa.Text(), nullable=False),
    sa.Column('job_title', sa.Text(), nullable=True),
    sa.Column('manager_id', sa.Uuid(), nullable=True),
    sa.Column('department_id', sa.Uuid(), nullable=True),
    sa.Column('role', sa.Text(), server_default='member', nullable=False),
    sa.Column('avatar_file_id', sa.Uuid(), nullable=True),
    sa.Column('timezone', sa.Text(), server_default='UTC', nullable=False),
    sa.Column('active', sa.Boolean(), server_default=sa.text('true'), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("role IN ('admin', 'member')", name=op.f('ck_users_role')),
    sa.ForeignKeyConstraint(['department_id'], ['departments.id'], name=op.f('fk_users_department_id_departments')),
    sa.ForeignKeyConstraint(['manager_id'], ['users.id'], name=op.f('fk_users_manager_id_users'), ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_users')),
    sa.UniqueConstraint('email', name=op.f('uq_users_email'))
    )
    op.create_index(op.f('ix_users_department_id'), 'users', ['department_id'], unique=False)
    op.create_index(op.f('ix_users_manager_id'), 'users', ['manager_id'], unique=False)
    op.create_table('conversations',
    sa.Column('id', sa.Uuid(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('kind', sa.Text(), nullable=False),
    sa.Column('name', sa.Text(), nullable=True),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('is_public', sa.Boolean(), server_default=sa.text('false'), nullable=False),
    sa.Column('department_id', sa.Uuid(), nullable=True),
    sa.Column('member_key', sa.Text(), nullable=True),
    sa.Column('ai_enabled', sa.Boolean(), server_default=sa.text('true'), nullable=False),
    sa.Column('last_seq', sa.BigInteger(), server_default=sa.text('0'), nullable=False),
    sa.Column('created_by', sa.Uuid(), nullable=True),
    sa.Column('archived_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("kind IN ('department', 'channel', 'dm')", name=op.f('ck_conversations_kind')),
    sa.ForeignKeyConstraint(['created_by'], ['users.id'], name=op.f('fk_conversations_created_by_users')),
    sa.ForeignKeyConstraint(['department_id'], ['departments.id'], name=op.f('fk_conversations_department_id_departments')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_conversations'))
    )
    op.create_index('uq_conversations_department', 'conversations', ['department_id'], unique=True, postgresql_where=sa.text("kind = 'department'"))
    op.create_index('uq_conversations_dm_member_key', 'conversations', ['member_key'], unique=True, postgresql_where=sa.text("kind = 'dm'"))
    op.create_table('notifications',
    sa.Column('id', sa.Uuid(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('user_id', sa.Uuid(), nullable=False),
    sa.Column('type', sa.Text(), nullable=False),
    sa.Column('ref_type', sa.Text(), nullable=False),
    sa.Column('ref_id', sa.Uuid(), nullable=False),
    sa.Column('read_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("ref_type IN ('message', 'task', 'suggestion')", name=op.f('ck_notifications_ref_type')),
    sa.CheckConstraint("type IN ('mention', 'dm', 'thread_reply', 'task_assigned', 'suggestion')", name=op.f('ck_notifications_type')),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_notifications_user_id_users'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_notifications'))
    )
    op.create_index('ix_notifications_user_unread', 'notifications', ['user_id', 'read_at'], unique=False)
    op.create_table('sessions',
    sa.Column('id', sa.Text(), nullable=False),
    sa.Column('user_id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_sessions_user_id_users'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_sessions'))
    )
    op.create_index(op.f('ix_sessions_user_id'), 'sessions', ['user_id'], unique=False)
    op.create_table('user_closure',
    sa.Column('ancestor_id', sa.Uuid(), nullable=False),
    sa.Column('descendant_id', sa.Uuid(), nullable=False),
    sa.Column('depth', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['ancestor_id'], ['users.id'], name=op.f('fk_user_closure_ancestor_id_users'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['descendant_id'], ['users.id'], name=op.f('fk_user_closure_descendant_id_users'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('ancestor_id', 'descendant_id', name=op.f('pk_user_closure'))
    )
    op.create_index(op.f('ix_user_closure_descendant_id'), 'user_closure', ['descendant_id'], unique=False)
    op.create_table('ai_runs',
    sa.Column('id', sa.Uuid(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('agent_id', sa.Uuid(), nullable=False),
    sa.Column('conversation_id', sa.Uuid(), nullable=False),
    sa.Column('from_event_id', sa.BigInteger(), nullable=False),
    sa.Column('to_event_id', sa.BigInteger(), nullable=False),
    sa.Column('started_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('finished_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('status', sa.Text(), server_default='running', nullable=False),
    sa.Column('error', sa.Text(), nullable=True),
    sa.CheckConstraint("status IN ('running', 'succeeded', 'failed')", name=op.f('ck_ai_runs_status')),
    sa.ForeignKeyConstraint(['agent_id'], ['ai_agent.id'], name=op.f('fk_ai_runs_agent_id_ai_agent')),
    sa.ForeignKeyConstraint(['conversation_id'], ['conversations.id'], name=op.f('fk_ai_runs_conversation_id_conversations')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_ai_runs'))
    )
    op.create_index(op.f('ix_ai_runs_conversation_id'), 'ai_runs', ['conversation_id'], unique=False)
    op.create_table('channel_read_cursors',
    sa.Column('user_id', sa.Uuid(), nullable=False),
    sa.Column('conversation_id', sa.Uuid(), nullable=False),
    sa.Column('last_read_seq', sa.BigInteger(), server_default=sa.text('0'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['conversation_id'], ['conversations.id'], name=op.f('fk_channel_read_cursors_conversation_id_conversations'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_channel_read_cursors_user_id_users'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('user_id', 'conversation_id', name=op.f('pk_channel_read_cursors'))
    )
    op.create_table('conversation_members',
    sa.Column('id', sa.Uuid(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('conversation_id', sa.Uuid(), nullable=False),
    sa.Column('user_id', sa.Uuid(), nullable=False),
    sa.Column('joined_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('left_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('role', sa.Text(), server_default='member', nullable=False),
    sa.Column('muted', sa.Boolean(), server_default=sa.text('false'), nullable=False),
    sa.Column('ai_opt_in', sa.Boolean(), server_default=sa.text('false'), nullable=False),
    sa.CheckConstraint("role IN ('owner', 'member')", name=op.f('ck_conversation_members_role')),
    sa.ForeignKeyConstraint(['conversation_id'], ['conversations.id'], name=op.f('fk_conversation_members_conversation_id_conversations'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_conversation_members_user_id_users')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_conversation_members'))
    )
    op.create_index('ix_conversation_members_user_id', 'conversation_members', ['user_id'], unique=False)
    op.create_index('uq_conversation_members_open', 'conversation_members', ['conversation_id', 'user_id'], unique=True, postgresql_where=sa.text('left_at IS NULL'))
    op.create_table('events',
    sa.Column('id', sa.BigInteger(), sa.Identity(always=False), nullable=False),
    sa.Column('type', sa.Text(), nullable=False),
    sa.Column('conversation_id', sa.Uuid(), nullable=True),
    sa.Column('actor_id', sa.Uuid(), nullable=True),
    sa.Column('subject_type', sa.Text(), nullable=False),
    sa.Column('subject_id', sa.Uuid(), nullable=False),
    sa.Column('payload', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['actor_id'], ['users.id'], name=op.f('fk_events_actor_id_users')),
    sa.ForeignKeyConstraint(['conversation_id'], ['conversations.id'], name=op.f('fk_events_conversation_id_conversations')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_events'))
    )
    op.create_index('ix_events_conversation_id_id', 'events', ['conversation_id', 'id'], unique=False)
    op.create_table('messages',
    sa.Column('id', sa.Uuid(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('conversation_id', sa.Uuid(), nullable=False),
    sa.Column('author_id', sa.Uuid(), nullable=False),
    sa.Column('parent_id', sa.Uuid(), nullable=True),
    sa.Column('seq', sa.BigInteger(), nullable=False),
    sa.Column('body_md', sa.Text(), nullable=False),
    sa.Column('client_id', sa.Uuid(), nullable=True),
    sa.Column('reply_count', sa.Integer(), server_default=sa.text('0'), nullable=False),
    sa.Column('last_reply_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('edited_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('tsv', postgresql.TSVECTOR(), sa.Computed("to_tsvector('english', coalesce(body_md, ''))", persisted=True), nullable=False),
    sa.ForeignKeyConstraint(['author_id'], ['users.id'], name=op.f('fk_messages_author_id_users')),
    sa.ForeignKeyConstraint(['conversation_id'], ['conversations.id'], name=op.f('fk_messages_conversation_id_conversations'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['parent_id'], ['messages.id'], name=op.f('fk_messages_parent_id_messages')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_messages')),
    sa.UniqueConstraint('author_id', 'client_id', name=op.f('uq_messages_author_id_client_id')),
    sa.UniqueConstraint('conversation_id', 'seq', name=op.f('uq_messages_conversation_id_seq'))
    )
    op.create_index('ix_messages_parent_id', 'messages', ['parent_id'], unique=False)
    op.create_index('ix_messages_tsv', 'messages', ['tsv'], unique=False, postgresql_using='gin')
    op.create_table('tasks',
    sa.Column('id', sa.Uuid(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('assignee_id', sa.Uuid(), nullable=False),
    sa.Column('created_by', sa.Uuid(), nullable=False),
    sa.Column('created_by_ai', sa.Boolean(), server_default=sa.text('false'), nullable=False),
    sa.Column('source_conversation_id', sa.Uuid(), nullable=False),
    sa.Column('project', sa.Text(), nullable=True),
    sa.Column('title', sa.Text(), nullable=False),
    sa.Column('description_md', sa.Text(), server_default='', nullable=False),
    sa.Column('status', sa.Text(), server_default='open', nullable=False),
    sa.Column('priority', sa.Text(), server_default='normal', nullable=False),
    sa.Column('due_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
    sa.CheckConstraint("priority IN ('low', 'normal', 'high', 'urgent')", name=op.f('ck_tasks_priority')),
    sa.CheckConstraint("status IN ('open', 'in_progress', 'done', 'cancelled')", name=op.f('ck_tasks_status')),
    sa.ForeignKeyConstraint(['assignee_id'], ['users.id'], name=op.f('fk_tasks_assignee_id_users')),
    sa.ForeignKeyConstraint(['created_by'], ['users.id'], name=op.f('fk_tasks_created_by_users')),
    sa.ForeignKeyConstraint(['source_conversation_id'], ['conversations.id'], name=op.f('fk_tasks_source_conversation_id_conversations')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_tasks'))
    )
    op.create_index(op.f('ix_tasks_assignee_id'), 'tasks', ['assignee_id'], unique=False)
    op.create_index(op.f('ix_tasks_project'), 'tasks', ['project'], unique=False)
    op.create_index(op.f('ix_tasks_source_conversation_id'), 'tasks', ['source_conversation_id'], unique=False)
    op.create_index(op.f('ix_tasks_status'), 'tasks', ['status'], unique=False)
    op.create_table('ai_proposals',
    sa.Column('id', sa.Uuid(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('run_id', sa.Uuid(), nullable=True),
    sa.Column('conversation_id', sa.Uuid(), nullable=False),
    sa.Column('kind', sa.Text(), nullable=False),
    sa.Column('payload', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('confidence', sa.Float(), nullable=True),
    sa.Column('status', sa.Text(), server_default='pending', nullable=False),
    sa.Column('applied_task_id', sa.Uuid(), nullable=True),
    sa.Column('decided_by', sa.Uuid(), nullable=True),
    sa.Column('decided_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('expires_at', sa.DateTime(timezone=True), server_default=sa.text("now() + interval '7 days'"), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("kind IN ('task', 'status_change')", name=op.f('ck_ai_proposals_kind')),
    sa.CheckConstraint("status IN ('pending', 'accepted', 'modified', 'rejected', 'expired')", name=op.f('ck_ai_proposals_status')),
    sa.ForeignKeyConstraint(['applied_task_id'], ['tasks.id'], name=op.f('fk_ai_proposals_applied_task_id_tasks')),
    sa.ForeignKeyConstraint(['conversation_id'], ['conversations.id'], name=op.f('fk_ai_proposals_conversation_id_conversations')),
    sa.ForeignKeyConstraint(['decided_by'], ['users.id'], name=op.f('fk_ai_proposals_decided_by_users')),
    sa.ForeignKeyConstraint(['run_id'], ['ai_runs.id'], name=op.f('fk_ai_proposals_run_id_ai_runs')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_ai_proposals'))
    )
    op.create_index('ix_ai_proposals_conversation_status', 'ai_proposals', ['conversation_id', 'status'], unique=False)
    op.create_table('ai_tool_calls',
    sa.Column('id', sa.Uuid(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('run_id', sa.Uuid(), nullable=False),
    sa.Column('tool_name', sa.Text(), nullable=False),
    sa.Column('arguments', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('scope_check', sa.Boolean(), nullable=False),
    sa.Column('result', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('status', sa.Text(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("status IN ('executed', 'denied', 'failed', 'stubbed')", name=op.f('ck_ai_tool_calls_status')),
    sa.ForeignKeyConstraint(['run_id'], ['ai_runs.id'], name=op.f('fk_ai_tool_calls_run_id_ai_runs')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_ai_tool_calls'))
    )
    op.create_index(op.f('ix_ai_tool_calls_run_id'), 'ai_tool_calls', ['run_id'], unique=False)
    op.create_table('files',
    sa.Column('id', sa.Uuid(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('uploader_id', sa.Uuid(), nullable=False),
    sa.Column('conversation_id', sa.Uuid(), nullable=True),
    sa.Column('message_id', sa.Uuid(), nullable=True),
    sa.Column('kind', sa.Text(), server_default='file', nullable=False),
    sa.Column('name', sa.Text(), nullable=False),
    sa.Column('mime', sa.Text(), nullable=False),
    sa.Column('size', sa.BigInteger(), nullable=False),
    sa.Column('storage_key', sa.Text(), nullable=False),
    sa.Column('language', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("kind IN ('file', 'image', 'snippet', 'avatar')", name=op.f('ck_files_kind')),
    sa.ForeignKeyConstraint(['conversation_id'], ['conversations.id'], name=op.f('fk_files_conversation_id_conversations')),
    sa.ForeignKeyConstraint(['message_id'], ['messages.id'], name=op.f('fk_files_message_id_messages'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['uploader_id'], ['users.id'], name=op.f('fk_files_uploader_id_users')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_files')),
    sa.UniqueConstraint('storage_key', name=op.f('uq_files_storage_key'))
    )
    op.create_index(op.f('ix_files_conversation_id'), 'files', ['conversation_id'], unique=False)
    op.create_index(op.f('ix_files_message_id'), 'files', ['message_id'], unique=False)
    # users <-> files is a cycle, so this FK is added once both tables exist.
    op.create_foreign_key(op.f('fk_users_avatar_file_id_files'), 'users', 'files', ['avatar_file_id'], ['id'], ondelete='SET NULL')
    op.create_table('message_edits',
    sa.Column('id', sa.Uuid(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('message_id', sa.Uuid(), nullable=False),
    sa.Column('prior_body_md', sa.Text(), nullable=False),
    sa.Column('edited_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['message_id'], ['messages.id'], name=op.f('fk_message_edits_message_id_messages'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_message_edits'))
    )
    op.create_index(op.f('ix_message_edits_message_id'), 'message_edits', ['message_id'], unique=False)
    op.create_table('message_mentions',
    sa.Column('id', sa.Uuid(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('message_id', sa.Uuid(), nullable=False),
    sa.Column('kind', sa.Text(), nullable=False),
    sa.Column('user_id', sa.Uuid(), nullable=True),
    sa.Column('department_id', sa.Uuid(), nullable=True),
    sa.CheckConstraint("kind IN ('user', 'department', 'channel', 'here')", name=op.f('ck_message_mentions_kind')),
    sa.ForeignKeyConstraint(['department_id'], ['departments.id'], name=op.f('fk_message_mentions_department_id_departments')),
    sa.ForeignKeyConstraint(['message_id'], ['messages.id'], name=op.f('fk_message_mentions_message_id_messages'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_message_mentions_user_id_users')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_message_mentions'))
    )
    op.create_index(op.f('ix_message_mentions_message_id'), 'message_mentions', ['message_id'], unique=False)
    op.create_index('ix_message_mentions_user_id', 'message_mentions', ['user_id'], unique=False)
    op.create_table('message_refs',
    sa.Column('id', sa.Uuid(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('message_id', sa.Uuid(), nullable=False),
    sa.Column('target_type', sa.Text(), nullable=False),
    sa.Column('target_id', sa.Uuid(), nullable=False),
    sa.CheckConstraint("target_type IN ('message', 'channel', 'task')", name=op.f('ck_message_refs_target_type')),
    sa.ForeignKeyConstraint(['message_id'], ['messages.id'], name=op.f('fk_message_refs_message_id_messages'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_message_refs'))
    )
    op.create_index(op.f('ix_message_refs_message_id'), 'message_refs', ['message_id'], unique=False)
    op.create_index('ix_message_refs_target', 'message_refs', ['target_type', 'target_id'], unique=False)
    op.create_table('reactions',
    sa.Column('message_id', sa.Uuid(), nullable=False),
    sa.Column('user_id', sa.Uuid(), nullable=False),
    sa.Column('emoji', sa.Text(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['message_id'], ['messages.id'], name=op.f('fk_reactions_message_id_messages'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_reactions_user_id_users')),
    sa.PrimaryKeyConstraint('message_id', 'user_id', 'emoji', name=op.f('pk_reactions'))
    )
    op.create_table('task_history',
    sa.Column('id', sa.Uuid(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('task_id', sa.Uuid(), nullable=False),
    sa.Column('actor_id', sa.Uuid(), nullable=False),
    sa.Column('field', sa.Text(), nullable=False),
    sa.Column('old_value', sa.Text(), nullable=True),
    sa.Column('new_value', sa.Text(), nullable=True),
    sa.Column('changed_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['actor_id'], ['users.id'], name=op.f('fk_task_history_actor_id_users')),
    sa.ForeignKeyConstraint(['task_id'], ['tasks.id'], name=op.f('fk_task_history_task_id_tasks'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_task_history'))
    )
    op.create_index(op.f('ix_task_history_task_id'), 'task_history', ['task_id'], unique=False)
    op.create_table('task_sources',
    sa.Column('task_id', sa.Uuid(), nullable=False),
    sa.Column('message_id', sa.Uuid(), nullable=False),
    sa.ForeignKeyConstraint(['message_id'], ['messages.id'], name=op.f('fk_task_sources_message_id_messages')),
    sa.ForeignKeyConstraint(['task_id'], ['tasks.id'], name=op.f('fk_task_sources_task_id_tasks'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('task_id', 'message_id', name=op.f('pk_task_sources'))
    )
    op.create_index(op.f('ix_task_sources_message_id'), 'task_sources', ['message_id'], unique=False)
    op.execute(CLOSURE_SQL)
    op.execute(SEED_SQL)


def downgrade() -> None:
    op.execute(DROP_CLOSURE_SQL)
    op.drop_constraint(op.f('fk_users_avatar_file_id_files'), 'users', type_='foreignkey')
    op.drop_index(op.f('ix_task_sources_message_id'), table_name='task_sources')
    op.drop_table('task_sources')
    op.drop_index(op.f('ix_task_history_task_id'), table_name='task_history')
    op.drop_table('task_history')
    op.drop_table('reactions')
    op.drop_index('ix_message_refs_target', table_name='message_refs')
    op.drop_index(op.f('ix_message_refs_message_id'), table_name='message_refs')
    op.drop_table('message_refs')
    op.drop_index('ix_message_mentions_user_id', table_name='message_mentions')
    op.drop_index(op.f('ix_message_mentions_message_id'), table_name='message_mentions')
    op.drop_table('message_mentions')
    op.drop_index(op.f('ix_message_edits_message_id'), table_name='message_edits')
    op.drop_table('message_edits')
    op.drop_index(op.f('ix_files_message_id'), table_name='files')
    op.drop_index(op.f('ix_files_conversation_id'), table_name='files')
    op.drop_table('files')
    op.drop_index(op.f('ix_ai_tool_calls_run_id'), table_name='ai_tool_calls')
    op.drop_table('ai_tool_calls')
    op.drop_index('ix_ai_proposals_conversation_status', table_name='ai_proposals')
    op.drop_table('ai_proposals')
    op.drop_index(op.f('ix_tasks_status'), table_name='tasks')
    op.drop_index(op.f('ix_tasks_source_conversation_id'), table_name='tasks')
    op.drop_index(op.f('ix_tasks_project'), table_name='tasks')
    op.drop_index(op.f('ix_tasks_assignee_id'), table_name='tasks')
    op.drop_table('tasks')
    op.drop_index('ix_messages_tsv', table_name='messages', postgresql_using='gin')
    op.drop_index('ix_messages_parent_id', table_name='messages')
    op.drop_table('messages')
    op.drop_index('ix_events_conversation_id_id', table_name='events')
    op.drop_table('events')
    op.drop_index('uq_conversation_members_open', table_name='conversation_members', postgresql_where=sa.text('left_at IS NULL'))
    op.drop_index('ix_conversation_members_user_id', table_name='conversation_members')
    op.drop_table('conversation_members')
    op.drop_table('channel_read_cursors')
    op.drop_index(op.f('ix_ai_runs_conversation_id'), table_name='ai_runs')
    op.drop_table('ai_runs')
    op.drop_index(op.f('ix_user_closure_descendant_id'), table_name='user_closure')
    op.drop_table('user_closure')
    op.drop_index(op.f('ix_sessions_user_id'), table_name='sessions')
    op.drop_table('sessions')
    op.drop_index('ix_notifications_user_unread', table_name='notifications')
    op.drop_table('notifications')
    op.drop_index('uq_conversations_dm_member_key', table_name='conversations', postgresql_where=sa.text("kind = 'dm'"))
    op.drop_index('uq_conversations_department', table_name='conversations', postgresql_where=sa.text("kind = 'department'"))
    op.drop_table('conversations')
    op.drop_index(op.f('ix_users_manager_id'), table_name='users')
    op.drop_index(op.f('ix_users_department_id'), table_name='users')
    op.drop_table('users')
    op.drop_table('event_consumers')
    op.drop_table('departments')
    op.drop_table('ai_agent')
