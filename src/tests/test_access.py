"""One test per access rule (plan.md §4.2), against the seeded fixtures."""

from datetime import UTC, datetime

from sqlalchemy import update
from sqlalchemy.orm import Session

from api.access import ai_can_read, can_access, can_assign, can_see, is_member, is_superior
from api.models import Conversation, ConversationMember, Message, Task, User
from tests.conftest import ids, requires_db

pytestmark = requires_db


def user(s: Session, key: str) -> User:
    return s.get(User, ids.user(key))


def conv(s: Session, key: str) -> Conversation:
    return s.get(Conversation, ids.conv(key))


# ---------------------------------------------------------------- can_access (1.5)

def test_public_channel_is_readable_by_a_non_member(session: Session) -> None:
    assert not is_member(session, user(session, "sofia"), conv(session, "website"))
    assert can_access(session, user(session, "sofia"), conv(session, "website"))


def test_private_channel_is_members_only(session: Session) -> None:
    assert can_access(session, user(session, "mei"), conv(session, "payments"))
    assert not can_access(session, user(session, "bob"), conv(session, "payments"))


def test_dm_is_members_only(session: Session) -> None:
    assert can_access(session, user(session, "alice"), conv(session, "dm:alice:bob"))
    assert not can_access(session, user(session, "dana"), conv(session, "dm:alice:bob"))


def test_department_channel_is_members_only(session: Session) -> None:
    assert can_access(session, user(session, "bob"), conv(session, "engineering"))
    assert not can_access(session, user(session, "alice"), conv(session, "engineering"))


def test_being_a_superior_grants_no_conversation_access(session: Session) -> None:
    maya, alice_bob = user(session, "maya"), conv(session, "dm:alice:bob")
    assert is_superior(session, maya, user(session, "alice"))
    assert not can_access(session, maya, alice_bob)


def test_inactive_users_have_no_access(session: Session) -> None:
    bob = user(session, "bob")
    bob.active = False
    assert not can_access(session, bob, conv(session, "website"))


def test_former_member_keeps_only_what_was_posted_before_they_left(session: Session) -> None:
    """Ken left #website on 20 Oct (2.7). #website is public, so make it private to test membership alone."""
    website = conv(session, "website")
    website.is_public = False
    ken = user(session, "ken")
    before = session.get(Message, ids.message("p20"))  # 14 Oct
    after = session.get(Message, ids.message("p22"))  # 21 Oct
    assert not can_access(session, ken, website)
    assert can_access(session, ken, website, at=before.created_at)
    assert not can_access(session, ken, website, at=after.created_at)


def test_current_member_reads_history_from_before_they_joined(session: Session) -> None:
    website = conv(session, "website")
    website.is_public = False
    session.execute(update(ConversationMember).where(
        ConversationMember.conversation_id == website.id, ConversationMember.user_id == ids.user("bob"),
    ).values(joined_at=datetime(2026, 10, 22, tzinfo=UTC)))
    early = session.get(Message, ids.message("h11"))  # 15 Oct
    assert can_access(session, user(session, "bob"), website, at=early.created_at)


def test_is_member_at_a_point_in_time(session: Session) -> None:
    website, ken = conv(session, "website"), user(session, "ken")
    assert is_member(session, ken, website, at=datetime(2026, 10, 14, tzinfo=UTC))
    assert not is_member(session, ken, website, at=datetime(2026, 10, 21, tzinfo=UTC))
    assert not is_member(session, ken, website)


# ---------------------------------------------------------------- can_see (2.3)

def test_assignee_sees_their_task(session: Session) -> None:
    task = session.get(Task, ids.task("h11"))  # Priya, spawned in #website which she's not in
    assert can_see(session, user(session, "priya"), task)


def test_superior_sees_a_subordinates_task(session: Session) -> None:
    task = session.get(Task, ids.task("h13"))  # assigned to Omar, spawned in the Dana–Omar DM
    assert can_see(session, user(session, "maya"), task)


def test_department_colleague_sees_the_task(session: Session) -> None:
    task = session.get(Task, ids.task("h11"))  # Priya is in Engineering
    assert can_see(session, user(session, "chloe"), task)


def test_source_conversation_member_sees_the_task(session: Session) -> None:
    task = session.get(Task, ids.task("t1"))  # Bob (Engineering), spawned in #website
    assert can_see(session, user(session, "lucia"), task)  # Marketing, member of #website


def test_unrelated_user_cannot_see_the_task(session: Session) -> None:
    task = session.get(Task, ids.task("h3"))  # Ahmed (Finance), in private #payments-launch
    assert not can_see(session, user(session, "ivy"), task)


# ---------------------------------------------------------------- can_assign (2.7)

def test_member_can_assign_member(session: Session) -> None:
    assert can_assign(session, user(session, "alice"), user(session, "bob"), conv(session, "website"))


def test_member_cannot_assign_a_non_member(session: Session) -> None:
    assert not can_assign(session, user(session, "ivy"), user(session, "ethan"), conv(session, "website"))


def test_direct_manager_can_assign_a_non_member_report(session: Session) -> None:
    assert can_assign(session, user(session, "omar"), user(session, "priya"), conv(session, "website"))


def test_indirect_superior_gets_no_exception(session: Session) -> None:
    brand = conv(session, "brand")  # Maya is not in #brand-refresh; make her a member to isolate the rule
    session.add(ConversationMember(conversation_id=brand.id, user_id=ids.user("maya")))
    session.flush()
    assert is_superior(session, user(session, "maya"), user(session, "priya"))
    assert not can_assign(session, user(session, "maya"), user(session, "priya"), brand)


def test_assigner_must_be_a_member(session: Session) -> None:
    assert not can_assign(session, user(session, "sofia"), user(session, "bob"), conv(session, "website"))


def test_former_member_cannot_be_assigned(session: Session) -> None:
    assert not can_assign(session, user(session, "alice"), user(session, "ken"), conv(session, "website"))


# ---------------------------------------------------------------- ai_can_read (3.5)

def test_ai_reads_channels_with_the_switch_on(session: Session) -> None:
    assert ai_can_read(session, conv(session, "website"))
    assert not ai_can_read(session, conv(session, "hiring"))


def test_ai_reads_a_dm_only_with_both_opt_ins(session: Session) -> None:
    assert ai_can_read(session, conv(session, "dm:dana:omar"))
    assert not ai_can_read(session, conv(session, "dm:alice:bob"))  # one-sided
    assert not ai_can_read(session, conv(session, "dm:ivy:carol"))  # neither
