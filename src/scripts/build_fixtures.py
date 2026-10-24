"""Generate src/fixtures/*.json deterministically (plan.md §3 Day 3).

The output is committed; edit this script, not the JSON. `--check` exits 1 if the committed
files differ from what the script produces (CI runs it).

Planted scenarios (the ones the AI is evaluated on) are written out by hand below and labelled
in expected.json. Filler messages come from template pools that are deliberately *not* tasks.
"""

import argparse
import json
import random
import re
import sys
import uuid
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "fixtures"
NS = uuid.UUID("6f0b6c1e-3a52-4c1e-9a43-0d1f2c7b5e10")
TZ = timezone(timedelta(hours=8))  # company time (Asia/Kuala_Lumpur)
EPOCH = datetime(2026, 10, 1, 9, 0, tzinfo=TZ)  # users, departments and channels exist from here
NOW = datetime(2026, 10, 24, 9, 0, tzinfo=TZ)
WORKDAYS = [d for d in range(12, 24) if datetime(2026, 10, d).weekday() < 5]


def uid(*parts: object) -> str:
    return str(uuid.uuid5(NS, ":".join(map(str, parts))))


def at(day: int, hh: int, mm: int = 0) -> datetime:
    return datetime(2026, 10, day, hh, mm, tzinfo=TZ)


def iso(t: datetime | None) -> str | None:
    return t.astimezone(UTC).isoformat().replace("+00:00", "Z") if t else None


# ---------------------------------------------------------------- org

DEPARTMENTS = ["Engineering", "Design", "Marketing", "Operations", "Finance"]

# key, name, title, department, manager key, role
PEOPLE = [
    ("maya", "Maya Chen", "Chief Executive Officer", "Operations", None, "member"),
    ("omar", "Omar Haddad", "VP of Engineering", "Engineering", "maya", "member"),
    ("carol", "Carol Diaz", "Head of Design", "Design", "maya", "member"),
    ("hannah", "Hannah Weber", "Head of Marketing", "Marketing", "maya", "member"),
    ("rafael", "Rafael Gomez", "Chief Operating Officer", "Operations", "maya", "member"),
    ("sofia", "Sofia Lindqvist", "Chief Financial Officer", "Finance", "maya", "member"),
    ("bob", "Bob Tan", "Frontend Engineer", "Engineering", "omar", "member"),
    ("dana", "Dana Kim", "Staff Engineer", "Engineering", "omar", "member"),
    ("ethan", "Ethan Novak", "Data Engineer", "Engineering", "omar", "member"),
    ("farah", "Farah Aziz", "Backend Engineer", "Engineering", "omar", "member"),
    ("leo", "Leo Martins", "Full-stack Engineer", "Engineering", "omar", "member"),
    ("priya", "Priya Nair", "Backend Engineer", "Engineering", "omar", "member"),
    ("sam", "Sam Okafor", "Site Reliability Engineer", "Engineering", "omar", "member"),
    ("yusuf", "Yusuf Demir", "Mobile Engineer", "Engineering", "omar", "member"),
    ("chloe", "Chloe Martin", "QA Engineer", "Engineering", "omar", "member"),
    ("ivy", "Ivy Laurent", "Product Designer", "Design", "carol", "member"),
    ("noah", "Noah Park", "UX Researcher", "Design", "carol", "member"),
    ("zara", "Zara Ali", "Visual Designer", "Design", "carol", "member"),
    ("elena", "Elena Sokolova", "Product Designer", "Design", "carol", "member"),
    ("alice", "Alice Moreau", "Product Marketing Manager", "Marketing", "hannah", "member"),
    ("ken", "Ken Ito", "Marketing Analyst", "Marketing", "hannah", "member"),
    ("lucia", "Lucia Rossi", "Content Lead", "Marketing", "hannah", "member"),
    ("tom", "Tom Becker", "Events Manager", "Marketing", "hannah", "member"),
    ("ravi", "Ravi Patel", "Growth Marketer", "Marketing", "hannah", "member"),
    ("grace", "Grace Liu", "IT Administrator", "Operations", "rafael", "admin"),
    ("victor", "Victor Hale", "Systems Administrator", "Operations", "rafael", "member"),
    ("nina", "Nina Petrov", "Office Manager", "Operations", "rafael", "member"),
    ("ahmed", "Ahmed Saleh", "Financial Analyst", "Finance", "sofia", "member"),
    ("mei", "Mei Wong", "Accountant", "Finance", "sofia", "member"),
    ("jonas", "Jonas Berg", "Financial Controller", "Finance", "sofia", "member"),
]
U = {p[0]: uid("user", p[0]) for p in PEOPLE}
NAME = {p[0]: p[1] for p in PEOPLE}
DEPT_OF = {p[0]: p[3] for p in PEOPLE}
D = {d: uid("department", d) for d in DEPARTMENTS}


def mention(key: str) -> str:
    """Mention syntax in body_md (contracts/DECISIONS.md #16): a Markdown link with a mention: URL."""
    return f"[@{NAME[key]}](mention:user/{U[key]})"


def dept_mention(dept: str) -> str:
    return f"[@{dept}](mention:department/{D[dept]})"


# ---------------------------------------------------------------- conversations

# key, name, description, public, ai_enabled, creator, members
CHANNELS = [
    ("general", "general", "Company-wide announcements", True, True, "maya", [p[0] for p in PEOPLE]),
    ("random", "random", "Water cooler", True, True, "grace",
     ["bob", "dana", "leo", "ivy", "noah", "alice", "ken", "tom", "grace", "nina", "mei", "sam", "yusuf", "chloe",
      "zara", "ravi"]),
    ("website", "website", "Marketing site and landing pages", True, True, "alice",
     ["omar", "bob", "dana", "leo", "ivy", "noah", "alice", "lucia", "ken"]),
    ("payments", "payments-launch", "Stripe launch, go-live Nov 2", False, True, "sofia",
     ["omar", "farah", "priya", "sam", "sofia", "ahmed", "mei"]),
    ("brand", "brand-refresh", "Q4 brand refresh", True, True, "hannah",
     ["carol", "ivy", "noah", "zara", "elena", "hannah", "ken", "tom"]),
    ("incidents", "incidents", "Production incidents and follow-ups", True, True, "sam",
     ["omar", "dana", "farah", "sam", "yusuf", "leo", "grace", "victor", "chloe"]),
    ("hiring", "hiring", "Hiring pipeline (leads only)", False, False, "maya",
     ["maya", "omar", "carol", "hannah", "rafael", "sofia", "grace"]),
    ("office", "office-ops", "Office, facilities and equipment", True, True, "rafael",
     ["rafael", "nina", "victor", "grace", "jonas", "tom", "maya"]),
]
# Membership periods that closed (point-in-time access, spec 2.7).
LEFT = {("website", "ken"): at(20, 17, 30)}

# DM pairs with (ai_opt_in a, ai_opt_in b). Pair 0 is the one-sided opt-in case.
DMS = [
    ("alice", "bob", True, False),
    ("dana", "omar", True, True),
    ("ken", "hannah", True, True),
    ("ivy", "carol", False, False),
    ("leo", "dana", False, False),
    ("sofia", "mei", True, True),
    ("grace", "victor", False, False),
    ("tom", "nina", False, False),
    ("maya", "rafael", False, False),
    ("priya", "farah", False, False),
    ("noah", "zara", True, False),
    ("sam", "yusuf", False, False),
    ("lucia", "alice", False, False),
    ("omar", "maya", False, False),
    ("jonas", "ahmed", False, False),
]

C: dict[str, str] = {}
MEMBERS: dict[str, list[str]] = {}
for d in DEPARTMENTS:
    C[d.lower()] = uid("conversation", "department", d)
    MEMBERS[d.lower()] = [p[0] for p in PEOPLE if p[3] == d]
for ch in CHANNELS:
    C[ch[0]] = uid("conversation", "channel", ch[0])
    MEMBERS[ch[0]] = ch[6]
for a, b, _, _ in DMS:
    C[f"dm:{a}:{b}"] = uid("conversation", "dm", a, b)
    MEMBERS[f"dm:{a}:{b}"] = [a, b]


def link(conv: str, msg: str | None = None) -> str:
    return f"/c/{C[conv]}/m/{msg}" if msg else f"/c/{C[conv]}"


# ---------------------------------------------------------------- messages

MESSAGES: list[dict] = []
EXPECTED: list[dict] = []
BY_KEY: dict[str, dict] = {}


def msg(key, conv, author, body, t, parent=None, **extra) -> dict:
    """A planted message. `key` names it for tasks, suggestions and expected.json."""
    assert author in MEMBERS[conv], f"{author} not in {conv}"
    m = {
        "id": uid("message", key),
        "conversation_key": conv,
        "author": author,
        "parent_key": parent,
        "body_md": body,
        "created_at": t,
        "also_in_channel": False,
        "reactions": [],
        "file_ids": [],
        "edits": [],
        "edited_at": None,
        "deleted_at": None,
        **extra,
    }
    MESSAGES.append(m)
    BY_KEY[key] = m
    return m


def expect(case: str, key: str, tool: str | None, note: str, trigger: str = "message", **expected) -> None:
    EXPECTED.append({
        "case": case,
        "message_id": BY_KEY[key]["id"],
        "trigger": trigger,
        "expected_tool": tool,
        "expected": expected,
        "note": note,
    })


# --- history: asks from the first week that already became tasks (H*)
HISTORY = [
    # key, conv, author, assignee, body, title, project, status, accepted from suggestion?
    ("h1", "engineering", "omar", "dana", 12, 10,
     f"{mention('dana')} please own the Postgres 17 upgrade plan — dry run on staging first.",
     "Plan the Postgres 17 upgrade", "infra", "in_progress", False),
    ("h2", "engineering", "omar", "farah", 12, 11,
     f"{mention('farah')} can you set up an error-budget dashboard in Grafana for the API?",
     "Set up error-budget dashboard in Grafana", "infra", "done", True),
    ("h3", "payments", "sofia", "ahmed", 12, 14,
     f"{mention('ahmed')} please draft the fee schedule for the launch so we can review it Thursday.",
     "Draft the launch fee schedule", "payments", "done", False),
    ("h4", "payments", "omar", "priya", 13, 10,
     f"{mention('priya')} please get the Stripe webhooks integrated in the billing service by the 20th.",
     "Integrate Stripe webhooks in billing service", "payments", "in_progress", False),
    ("h5", "brand", "hannah", "carol", 13, 15,
     f"{mention('carol')} could your team deliver three logo directions by next Wednesday?",
     "Deliver three logo directions", "brand-refresh", "done", True),
    ("h6", "marketing", "hannah", "ken", 13, 16,
     f"{mention('ken')} please prepare the October campaign performance report.",
     "Prepare October campaign report", None, "open", False),
    ("h7", "design", "carol", "zara", 14, 10,
     f"{mention('zara')} can you audit the icon set for contrast against WCAG AA?",
     "Audit icon set for WCAG AA contrast", "brand-refresh", "open", False),
    ("h8", "office", "rafael", "victor", 14, 11,
     f"{mention('victor')} please get three quotes for the new standing desks.",
     "Get quotes for standing desks", "office", "in_progress", False),
    ("h9", "finance", "sofia", "jonas", 14, 14,
     f"{mention('jonas')} please close out the September accruals before Friday.",
     "Close September accruals", "month-end", "done", False),
    ("h10", "incidents", "grace", "victor", 15, 9,
     f"{mention('victor')} can you update the DNS records for the docs subdomain? The old CNAME still points "
     "at the legacy host.",
     "Update DNS records for docs subdomain", "infra", "open", False),
    ("h12", "general", "maya", "grace", 15, 10,
     f"{mention('grace')} please roll out the new password manager to everyone by the end of the month.",
     "Roll out the password manager company-wide", "security", "in_progress", False),
    ("h13", "dm:dana:omar", "dana", "omar", 15, 16,
     "Could you approve my conference budget for KubeCon? The request is in the finance portal.",
     "Approve Dana's KubeCon budget", None, "open", False),
    ("h14", "engineering", "dana", "leo", 16, 10,
     f"{mention('leo')} can you review PR #482 (rate limiter) today?",
     "Review PR #482 (rate limiter)", "infra", "done", False),
]
for key, conv, author, _assignee, day, hh, body, *_ in HISTORY:
    msg(key, conv, author, body, at(day, hh, 5))

msg("h1r", "engineering", "dana", "On it. I'll write up the plan in the infra doc.", at(12, 10, 20), parent="h1")
msg("h4r", "payments", "priya", "Webhook handler is in review, signature checks done.", at(19, 15, 40), parent="h4")
msg("h14r", "engineering", "leo", "Approved with two nits 👍", at(16, 14, 10), parent="h14")

# The direct-manager exception: Omar assigns his report Priya, who is not in #website (spec 2.7).
msg("h11", "website", "omar",
    f"{mention('priya')} isn't in here, but Priya — please run a Lighthouse audit on the new landing page this "
    "week. I'll add you as the assignee directly.", at(15, 11, 0))

# --- P1: a clear ask, accepted as a task, later closed by "done, shipped it"
msg("p1", "website", "alice",
    f"{mention('bob')} can you fix the broken signup button on the pricing page before Thursday's launch? "
    "It throws a 500 on submit.", at(19, 10, 12))
msg("p1r1", "website", "bob", "On it — looks like the CSRF token isn't passed through on that form.",
    at(19, 10, 31), parent="p1")
msg("p1r2", "website", "bob", "Done, shipped it. Fix is live on prod 🚀", at(21, 16, 2), parent="p1",
    also_in_channel=True)
expect("clear_ask", "p1", "propose_task", "Explicit @mention, clear action and deadline.",
       assignee_id=U["bob"], due_at="2026-10-22", already_tracked_by="task:t1")
expect("closes_task", "p1r2", "propose_status_change", "'Done, shipped it' in the thread of the task's source.",
       task_id=uid("task", "t1"), new_status="done")

# --- P2: sounds like a task but isn't
msg("p2", "website", "lucia", "We should really redo the whole homepage someday, it feels so 2019 😅",
    at(19, 11, 40))
expect("not_a_task", "p2", "no_action", "Wishful 'someday', no owner, no commitment. The AI proposed it once "
       "and it was rejected (suggestion s9).")
msg("p2b", "random", "noah", "Someone should really fix the coffee machine on 3 lol", at(20, 9, 15))
expect("not_a_task_joke", "p2b", "no_action", "Joke in #random.")
msg("p2c", "incidents", "sam", "FYI I already rotated the API keys last night, nothing else needed.",
    at(20, 9, 50))
expect("past_action", "p2c", "no_action", "Reports something already done.")
msg("p2d", "office", "tom", "Does anyone know when the office closes on Friday?", at(22, 15, 0))
expect("question", "p2d", "no_action", "A question, not a request for work.")

# --- P3: mentions a non-member
msg("p3", "website", "ivy",
    f"{mention('ethan')} could you update the analytics snippet on the landing page? The GA4 tag is outdated.",
    at(20, 14, 20))
expect("non_member", "p3", "propose_task", "Ethan is not a member of #website; card must show the non-member "
       "state.", assignee_id=U["ethan"], assignee_is_member=False, already_tracked_by="suggestion:s5")

# --- P5: DM where only one side opted in -> the AI must not read it
msg("p5", "dm:alice:bob", "alice", "Bob, can you send me the Q3 traffic numbers by tomorrow?", at(20, 16, 0))
expect("dm_one_sided_opt_in", "p5", None, "Bob has not opted in; ai_can_read is false, the event is skipped.",
       skipped="ai_cannot_read")

# --- P6: DM where both opted in
msg("p6", "dm:dana:omar", "omar",
    "Dana, please put together the on-call rota for November and share it in #engineering by Wednesday.",
    at(21, 9, 30))
expect("dm_opted_in", "p6", "propose_task", "Both opted in; task spawned in the DM.", assignee_id=U["dana"],
       due_at="2026-10-28", already_tracked_by="suggestion:s8")

# --- P7: @department mention
msg("p7", "brand", "hannah",
    f"{dept_mention('Design')} we need the new logo exported as SVG and PNG for the press kit by Oct 28.",
    at(21, 11, 0))
expect("department_mention", "p7", "propose_task", "Department mention; resolve within Design, members of the "
       "channel preferred.", assignee_in=[U[k] for k in ("carol", "ivy", "noah", "zara", "elena")],
       due_at="2026-10-28", project="brand-refresh")

# --- P8: named person without an @mention
msg("p8", "payments", "sofia",
    "Mei, could you reconcile the Stripe payouts against the ledger for September? Need it for the board pack.",
    at(21, 14, 30))
expect("name_match", "p8", "propose_task", "Named in text, no @mention; project already exists.",
       assignee_id=U["mei"], project="payments", already_tracked_by="suggestion:s6")

# --- P9: "someone from design"
msg("p9", "website", "leo", "Can someone from design mock up the empty state for the new dashboard?",
    at(21, 15, 10))
expect("someone_from_department", "p9", "propose_task", "Narrow to Design members in the channel.",
       assignee_in=[U["ivy"], U["noah"]], already_tracked_by="suggestion:s7")

# --- P10: task with a code block
msg("p10", "incidents", "farah",
    f"{mention('sam')} the nightly export job is failing with this — can you take a look today?\n\n"
    "```python\nTraceback (most recent call last):\n  File \"export.py\", line 88, in run\n"
    "    rows = fetch_batch(cursor, size=BATCH)\npsycopg.errors.QueryCanceled: canceling statement due to "
    "statement timeout\n```", at(22, 9, 5))
msg("p10r", "incidents", "sam", "Bumped the statement timeout for that role and re-ran it. Green now.",
    at(22, 11, 40), parent="p10")
expect("task_with_code", "p10", "propose_task", "Ask with a code block; already turned into a task manually.",
       assignee_id=U["sam"], due_at="2026-10-22", already_tracked_by="task:t_p10")

# --- P11: code block, not a task
msg("p11", "engineering", "leo",
    "Here's the query I used for the retention numbers, in case it helps anyone:\n\n```sql\n"
    "SELECT date_trunc('week', created_at) AS week, count(DISTINCT user_id)\nFROM sessions\n"
    "GROUP BY 1 ORDER BY 1;\n```", at(20, 13, 0))
expect("code_not_a_task", "p11", "no_action", "Sharing a snippet.")

# --- P12: a ✅ reaction closes a task (on h10's source message)
BY_KEY["h10"]["reactions"].append({"user": "victor", "emoji": "✅", "created_at": at(22, 17, 20)})
expect("reaction_closes_task", "h10", "propose_status_change", "Assignee reacted ✅ to the task's source message.",
       trigger="reaction:✅", task_id=uid("task", "h10"), new_status="done")

# --- P13–P15: stub tools
msg("p13", "dm:ken:hannah", "ken", "Hi Hannah, I'd like to take Nov 3–5 off for a family thing, is that ok?",
    at(21, 10, 0))
expect("leave_request", "p13", "request_leave", "Stub tool; scope not granted by default -> denied.",
       start_date="2026-11-03", end_date="2026-11-05")
msg("p14", "office", "tom", "I paid €84.50 for the client lunch on Tuesday, how do I get that reimbursed?",
    at(22, 12, 30))
expect("expense_claim", "p14", "submit_claim", "Stub tool.", amount=84.5, currency="EUR")
msg("p15", "brand", "carol", "Let's get Hannah, Ivy and Ken together for 30 min on Monday to review the "
    "moodboards.", at(22, 16, 0))
expect("meeting", "p15", "schedule_meeting", "Stub tool.",
       attendee_ids=[U["hannah"], U["ivy"], U["ken"]], duration_minutes=30)

# --- P19: a channel with the AI switched off
msg("p19", "hiring", "maya", "Rafael, please schedule the final interviews for the senior backend role next week.",
    at(21, 9, 0))
expect("ai_disabled_channel", "p19", None, "#hiring has ai_enabled = false.", skipped="ai_cannot_read")

# --- P20: a former member's message (Ken left #website on the 20th)
msg("p20", "website", "ken", "Pushed the new meta descriptions for the blog pages.", at(14, 15, 0))

# --- P21: two tasks in one message
msg("p21", "marketing", "hannah",
    f"Two things for this week: {mention('alice')} please finalise the newsletter copy by Wednesday, and "
    f"{mention('tom')} book the venue for the November meetup.", at(19, 9, 20))
expect("two_tasks", "p21", "propose_task", "Two propose_task calls from one message.",
       calls=[{"assignee_id": U["alice"], "due_at": "2026-10-21"}, {"assignee_id": U["tom"]}],
       already_tracked_by="task:t_p21a,task:t_p21b")

# --- P22: an edited message (the edit turns it into a task)
msg("p22", "website", "alice",
    f"{mention('lucia')} can you check the SEO meta tags on the blog by Friday?", at(21, 10, 0),
    edited_at=at(21, 10, 4), edits=[{"prior_body_md": "Can someone check the SEO tags?", "edited_at": at(21, 10, 4)}])
expect("edited_into_task", "p22", "propose_task", "message.updated with prior_body_md; the edit names Lucia.",
       trigger="message.updated", assignee_id=U["lucia"], due_at="2026-10-23")

# --- P23: a deleted message
msg("p23", "random", "ken", "oops wrong channel", at(22, 10, 0), deleted_at=at(22, 10, 1))

# --- P24: an ask inside a thread, accepted with modifications
msg("p24p", "engineering", "omar", "Release 2.4 planning thread 🧵", at(20, 10, 0))
msg("p24", "engineering", "dana", f"{mention('leo')} can you write the migration notes for 2.4?", at(20, 10, 15),
    parent="p24p")
expect("thread_ask", "p24", "propose_task", "Ask inside a thread; context is the thread.", assignee_id=U["leo"],
       already_tracked_by="task:t_p24")

# --- P26: a self-commitment
msg("p26", "engineering", "bob", "I'll take care of updating the README for the deploy script.", at(21, 11, 30))
expect("self_commitment", "p26", "propose_task", "The author commits to a task for themselves.",
       assignee_id=U["bob"], already_tracked_by="task:t_p26")

# --- S10's source: an observation that was proposed and expired
msg("s10src", "marketing", "ken", "The email template still uses the old brand colours.", at(12, 15, 0))
expect("observation", "s10src", "no_action", "An observation with no ask; its suggestion expired untouched.")

# --- links, files, snippets
msg("lnk1", "engineering", "dana", f"Context for Thursday's release: {link('website', BY_KEY['p1']['id'])}",
    at(19, 13, 0))
msg("lnk2", "random", "grace", f"Interview loop details are here: {link('hiring')} (leads only, sorry!)",
    at(20, 11, 0))
msg("lnk3", "engineering", "omar", f"Tracking the signup fix here: /t/{uid('task', 't1')}", at(19, 16, 0))

FILES = [
    {"key": "f1", "conv": "payments", "uploader": "mei", "kind": "file", "name": "september_payouts.csv",
     "mime": "text/csv", "language": None,
     "content": "payout_id,date,amount,currency,status\npo_1001,2026-09-03,12850.00,USD,paid\n"
                "po_1002,2026-09-10,9734.20,USD,paid\npo_1003,2026-09-17,15002.75,USD,paid\n"
                "po_1004,2026-09-24,11120.40,USD,in_transit\n"},
    {"key": "f2", "conv": "engineering", "uploader": "leo", "kind": "snippet", "name": "rate_limiter.py",
     "mime": "text/x-python", "language": "python",
     "content": "import time\n\n\nclass TokenBucket:\n    def __init__(self, rate: float, capacity: int):\n"
                "        self.rate, self.capacity = rate, capacity\n        self.tokens = capacity\n"
                "        self.updated = time.monotonic()\n\n    def allow(self) -> bool:\n"
                "        now = time.monotonic()\n"
                "        self.tokens = min(self.capacity, self.tokens + (now - self.updated) * self.rate)\n"
                "        self.updated = now\n        if self.tokens >= 1:\n            self.tokens -= 1\n"
                "            return True\n        return False\n"},
    {"key": "f3", "conv": "website", "uploader": "ivy", "kind": "image", "name": "hero-v2.png", "mime": "image/png",
     "language": None,
     # 1x1 transparent PNG
     "content_b64": "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="},
]
msg("f1m", "payments", "mei", "Here's the raw payout export for September 📎", at(21, 15, 0))
msg("f2m", "engineering", "leo", "Snippet of the token bucket from PR #482 for reference", at(16, 15, 0))
msg("f3m", "website", "ivy", "Hero image v2 for the landing page", at(19, 12, 0))
for f, m in zip(FILES, ("f1m", "f2m", "f3m"), strict=True):
    f["message_key"] = m
    BY_KEY[m]["file_ids"].append(uid("file", f["key"]))

# ---------------------------------------------------------------- filler (never tasks)

POOLS = {
    "general": [
        "Morning everyone ☀️", "Reminder: all-hands is at 4pm today in the big room and on the call.",
        "Happy Friday all!", "The kitchen got a new espresso machine 🎉", "Thanks everyone for a great week.",
        "Slides from today's lunch & learn are in the shared drive.",
        "Parking lot B is closed tomorrow for resurfacing.", "Great job on the release, everyone 👏",
        "Office wifi is back to normal now.", "Welcome to our two new interns starting Monday 👋",
        "Q3 results recap is posted in the wiki.", "Friendly reminder that Monday is the team photo day 📸",
    ],
    "random": [
        "Anyone watching the match tonight?", "Best ramen spot near the office? 🍜",
        "My cat walked over my keyboard and sent half an email 😂", "That's hilarious", "Weekend plans, anyone?",
        "lol", "Has anyone tried the new bakery downstairs?", "TIL octopuses have three hearts 🐙",
        "The sunset from the 12th floor right now 🌇", "Rainy day again ☔", "Bring back the Friday donuts",
        "Who left the Lego set in meeting room 4? It's amazing",
    ],
    "engineering": [
        "Deployed api v2.3.1 to staging, all green ✅", "CI is green again.",
        "Merged the logging refactor, thanks for the reviews.",
        "Nice write-up on Postgres partial indexes: https://www.postgresql.org/docs/current/indexes-partial.html",
        "Standup notes are in the doc.", "The flaky checkout test seems fixed after the retry change.",
        "Staging DB was restored from last night's snapshot.", "Load test results look good: p95 at 180 ms.",
        "Dependabot PRs for this week are merged.", "Tech talk on Thursday is about our search indexing.",
    ],
    "design": [
        "Pushed the updated components to the Figma library.", "The new icon set is looking sharp.",
        "Moodboard v2 is up in the brand file.", "Thanks for the feedback on the onboarding flow!",
        "Usability sessions went well today, notes are in Dovetail.", "Design crit moved to 3pm today.",
    ],
    "marketing": [
        "Newsletter open rate was 41% this week 📈", "The webinar had 230 sign-ups.",
        "Blog post on the release is live.", "Social calendar for next week is drafted.",
        "Paid campaign CPC dropped 12% after the creative refresh.", "Case study with Acme is published 🎉",
    ],
    "operations": [
        "Fire drill is scheduled for Thursday at 10am.", "New badges have arrived at reception.",
        "The cleaning crew comes in at 6pm today.", "Third-floor printer is fixed.",
        "Laptop refresh batch arrived; IT is imaging them this week.",
    ],
    "finance": [
        "Month-end close is on track.", "Expense policy doc is updated in the wiki.",
        "October invoices have gone out.", "Audit fieldwork starts in two weeks.",
        "Cash runway model updated with September actuals.",
    ],
    "website": [
        "New hero image looks great.", "Staging site is updated with the latest copy.",
        "Lighthouse score went from 71 to 88 after image compression 🎉", "Pricing page copy is approved.",
        "The A/B test on the CTA colour is running.", "Favicon is updated on staging too.",
        "Cookie banner copy got legal's thumbs up.", "Mobile nav looks much better after yesterday's tweak.",
        "Page weight is down to 1.2 MB on the landing page.", "Customer logos strip is live.",
    ],
    "payments": [
        "Sandbox webhooks are flowing now.", "Finance sign-off on the fee schedule is done.",
        "PCI questionnaire submitted.", "Refund flow tested end to end in sandbox.", "Go-live checklist is 80% green.",
        "Stripe account review came back clean.", "Payout schedule confirmed as weekly.",
        "Test cards for all three currencies pass.", "Dispute webhook is wired to the alerts channel.",
    ],
    "brand": [
        "Typography options are in the deck.", "Colour palette v3 is in Figma.",
        "The agency loved direction B.", "Updated the brand voice doc with the new examples.",
        "Illustration style references are in the board.", "Direction B tested best with customers.",
        "Swag mock-ups with the new logo look fun 🧢", "Photography guidelines draft is in the folder.",
    ],
    "incidents": [
        "Resolved: elevated error rate on /api/search, root cause was a cache stampede.",
        "Monitoring: latency is back to normal.", "Postmortem for Tuesday's outage is published.",
        "Alert noise is down 40% after the threshold tuning.", "Status page updated.",
        "Resolved: queue backlog cleared after the worker restart.", "Disk usage alert on db-2 was a false alarm.",
        "Error rates are flat after the deploy.", "Monitoring: CDN hit rate back to 96%.",
    ],
    "hiring": [
        "Great candidate today for the design role.", "Offer accepted for the data analyst role 🎉",
        "Pipeline review notes are in the hiring doc.", "Two strong referrals for the SRE opening.",
        "The design take-home got great reviews from the panel.", "Headcount plan for Q1 is in the deck.",
    ],
    "office": [
        "The new chairs arrive on Wednesday.", "Meeting room 2 screen is replaced.",
        "Plant delivery came in, they look great 🪴", "Visitor Wi-Fi password rotated, it's on the board.",
        "Lockers on 4 are all assigned now.", "Air-con on the west side is back to normal.",
        "Bike racks got two more spots.",
    ],
    "dm": [
        "Thanks!", "Sounds good 👍", "Got it, thanks for the heads up.", "See you at the all-hands.",
        "Coffee later?", "Haha yes", "Nice work today.", "Thanks for covering earlier.", "Enjoy your weekend!",
        "That meeting ran long 😅",
    ],
}
REPLIES = ["👍", "Thanks!", "Nice", "Agreed", "Makes sense", "Good catch", "Love it", "+1", "🙌", "Ha, true"]
EMOJI = ["👍", "🎉", "😂", "👀", "🙌", "❤️"]
FILLER_COUNTS = {
    "general": 40, "random": 40, "website": 25, "payments": 20, "brand": 20, "incidents": 22, "hiring": 12,
    "office": 15, "engineering": 30, "design": 15, "marketing": 15, "operations": 10, "finance": 12,
}


def pool_for(conv: str) -> list[str]:
    return POOLS["dm"] if conv.startswith("dm:") else POOLS[conv]


def active_members(conv: str, t: datetime) -> list[str]:
    return [k for k in MEMBERS[conv] if not ((conv, k) in LEFT and LEFT[(conv, k)] <= t)]


def add_filler(rng: random.Random) -> None:
    decks: dict[str, list[str]] = {}

    def draw(conv: str) -> str:
        """Shuffled deck per conversation, so repeats only happen once a pool is used up."""
        if not decks.get(conv):
            decks[conv] = rng.sample(pool_for(conv), k=len(pool_for(conv)))
        return decks[conv].pop()

    counts = dict(FILLER_COUNTS)
    for a, b, _, _ in DMS:
        counts[f"dm:{a}:{b}"] = 4
    for conv, n in counts.items():
        top: list[dict] = []
        for i in range(n):
            t = at(rng.choice(WORKDAYS), rng.randint(9, 17), rng.randint(0, 59))
            parent = None
            if top and rng.random() < 0.15:
                parent = rng.choice(top[-5:])
                t = parent["created_at"] + timedelta(minutes=rng.randint(5, 180))
                if t > NOW:
                    parent, t = None, at(rng.choice(WORKDAYS), rng.randint(9, 17), rng.randint(0, 59))
            author = rng.choice(active_members(conv, t))
            body = rng.choice(REPLIES) if parent else draw(conv)
            m = {
                "id": uid("message", "filler", conv, i), "conversation_key": conv, "author": author,
                "parent_key": parent["key"] if parent else None, "body_md": body, "created_at": t,
                "also_in_channel": False, "reactions": [], "file_ids": [], "edits": [], "edited_at": None,
                "deleted_at": None, "key": f"filler:{conv}:{i}",
            }
            if rng.random() < 0.25:
                for who in rng.sample(active_members(conv, t), k=min(len(MEMBERS[conv]), rng.randint(1, 3))):
                    m["reactions"].append({"user": who, "emoji": rng.choice(EMOJI),
                                           "created_at": t + timedelta(minutes=rng.randint(1, 90))})
            MESSAGES.append(m)
            BY_KEY[m["key"]] = m
            if not parent:
                top.append(m)


# ---------------------------------------------------------------- tasks & suggestions

def due(day: int) -> datetime:
    return at(day, 18, 0)


TASKS: list[dict] = []


def task(key, source_keys, assignee, created_by, title, *, project=None, status="open", priority="normal",
         due_at=None, created_by_ai=False, description="", created_offset=15) -> None:
    src = BY_KEY[source_keys[0]]
    created = src["created_at"] + timedelta(minutes=created_offset)
    TASKS.append({
        "id": uid("task", key), "key": key, "title": title, "description_md": description,
        "assignee": assignee, "created_by": created_by, "created_by_ai": created_by_ai,
        "source_conversation_key": src["conversation_key"], "project": project, "status": status,
        "priority": priority, "due_at": due_at, "created_at": created,
        "source_message_keys": source_keys,
    })


for key, _conv, author, assignee, day, _hh, _body, title, project, status, from_ai in HISTORY:
    task(key, [key], assignee, author, title, project=project, status=status, created_by_ai=from_ai,
         due_at=due(day + 7) if status != "done" else None)
task("h11", ["h11"], "priya", "omar", "Run a Lighthouse audit on the new landing page", project="website",
     due_at=due(23), description="Copied from the source message because the assignee is not a member of "
     "#website (spec 2.7):\n\n> Priya — please run a Lighthouse audit on the new landing page this week.")
task("t1", ["p1"], "bob", "alice", "Fix the signup button 500 on the pricing page", project="website",
     status="in_progress", priority="high", due_at=due(22), created_by_ai=True, created_offset=3)
task("t_p10", ["p10"], "sam", "farah", "Fix the failing nightly export job", project="infra", status="done",
     priority="high", due_at=due(22), created_offset=2)
task("t_p21a", ["p21"], "alice", "hannah", "Finalise newsletter copy", project="newsletter", due_at=due(21))
task("t_p21b", ["p21"], "tom", "hannah", "Book the venue for the November meetup", project="meetup")
task("t_p24", ["p24"], "leo", "omar", "Write the 2.4 migration notes", project="release-2.4", created_by_ai=True,
     due_at=due(23), created_offset=40)
task("t_p26", ["p26"], "bob", "bob", "Update the deploy script README", project="infra", priority="low")

STATUS_PATH = {"open": [], "in_progress": ["in_progress"], "done": ["in_progress", "done"]}

SUGGESTIONS: list[dict] = []


def suggestion(key, source_keys, kind, payload, status, *, confidence, decided_by=None, applied=None,
               created_offset=2, decided_offset=10) -> None:
    src = BY_KEY[source_keys[0]]
    created = src["created_at"] + timedelta(minutes=created_offset)
    decided = created + timedelta(minutes=decided_offset) if status not in ("pending", "expired") else None
    if status == "expired":
        decided = created + timedelta(days=7)
    payload = {**payload, "source_message_ids": [BY_KEY[k]["id"] for k in source_keys]}
    SUGGESTIONS.append({
        "id": uid("suggestion", key), "conversation_key": src["conversation_key"], "kind": kind,
        "payload": payload, "confidence": confidence, "status": status,
        "applied_task_id": uid("task", applied) if applied else None, "decided_by": decided_by,
        "decided_at": decided, "created_at": created, "expires_at": created + timedelta(days=7),
    })


def proposal(title, assignee, conv, *, description="", project=None, due_at=None) -> dict:
    return {
        "title": title, "description_md": description, "assignee_id": U[assignee] if assignee else None,
        "assignee_is_member": bool(assignee) and assignee in MEMBERS[conv], "project": project,
        "due_at": iso(due_at),
    }


suggestion("s1", ["p1"], "task", proposal("Fix the signup button 500 on the pricing page", "bob", "website",
           project="website", due_at=due(22)), "accepted", confidence=0.93, decided_by="alice", applied="t1",
           decided_offset=1)
suggestion("s2", ["p24"], "task", proposal("Write migration notes", "leo", "engineering"), "modified",
           confidence=0.88, decided_by="omar", applied="t_p24", decided_offset=38)
suggestion("s3", ["h5"], "task", proposal("Deliver three logo directions", "carol", "brand",
           project="brand-refresh"), "accepted", confidence=0.9, decided_by="hannah", applied="h5")
suggestion("s4", ["h2"], "task", proposal("Set up error-budget dashboard in Grafana", "farah", "engineering",
           project="infra"), "accepted", confidence=0.86, decided_by="omar", applied="h2")
suggestion("s5", ["p3"], "task", proposal("Update the GA4 analytics snippet on the landing page", "ethan", "website",
           project="website"), "pending", confidence=0.84)
suggestion("s6", ["p8"], "task", proposal("Reconcile September Stripe payouts against the ledger", "mei", "payments",
           project="payments"), "pending", confidence=0.91)
suggestion("s7", ["p9"], "task", proposal("Mock up the dashboard empty state", "ivy", "website"), "pending",
           confidence=0.62)
suggestion("s8", ["p6"], "task", proposal("Prepare the November on-call rota", "dana", "dm:dana:omar",
           due_at=due(28)), "pending", confidence=0.89)
suggestion("s9", ["p2"], "task", proposal("Redesign the homepage", None, "website"), "rejected", confidence=0.31,
           decided_by="lucia", decided_offset=25)
suggestion("s10", ["s10src"], "task", proposal("Update brand colours in the email template", "ken", "marketing"),
           "expired", confidence=0.45)
suggestion("s11", ["p1r2"], "status_change", {"task_id": uid("task", "t1"), "new_status": "done"}, "pending",
           confidence=0.95)


# ---------------------------------------------------------------- assembly

MENTION_RE = re.compile(r"\[@[^\]]+\]\(mention:(user|department)/([0-9a-f-]{36})\)")
REF_RE = re.compile(r"/c/([0-9a-f-]{36})(?:/m/([0-9a-f-]{36}))?|/t/([0-9a-f-]{36})")


def extract(body: str) -> tuple[list[dict], list[dict]]:
    mentions = [
        {"kind": k, "user_id": i if k == "user" else None, "department_id": i if k == "department" else None}
        for k, i in MENTION_RE.findall(body)
    ]
    mentions += [{"kind": w, "user_id": None, "department_id": None} for w in ("channel", "here") if f"@{w}" in body]
    refs = []
    for conv, message, task_id in REF_RE.findall(body):
        if task_id:
            refs.append({"target_type": "task", "target_id": task_id})
        elif message:
            refs.append({"target_type": "message", "target_id": message})
        else:
            refs.append({"target_type": "channel", "target_id": conv})
    return mentions, refs


def build() -> dict[str, object]:
    rng = random.Random(2026)
    add_filler(rng)

    # seq per conversation in time order; parents always precede replies
    seqs: dict[str, int] = {}
    for m in sorted(MESSAGES, key=lambda m: (m["created_at"], m["id"])):
        seqs[m["conversation_key"]] = seqs.get(m["conversation_key"], 0) + 1
        m["seq"] = seqs[m["conversation_key"]]
        if m["parent_key"]:
            assert BY_KEY[m["parent_key"]]["created_at"] < m["created_at"], m["id"]

    messages = []
    for m in sorted(MESSAGES, key=lambda m: (m["created_at"], m["id"])):
        mentions, refs = extract(m["body_md"])
        messages.append({
            "id": m["id"], "conversation_id": C[m["conversation_key"]], "author_id": U[m["author"]],
            "parent_id": BY_KEY[m["parent_key"]]["id"] if m["parent_key"] else None, "seq": m["seq"],
            "body_md": m["body_md"], "also_in_channel": m["also_in_channel"], "created_at": iso(m["created_at"]),
            "edited_at": iso(m["edited_at"]), "deleted_at": iso(m["deleted_at"]),
            "mentions": mentions, "refs": refs, "file_ids": m["file_ids"],
            "edits": [{"prior_body_md": e["prior_body_md"], "edited_at": iso(e["edited_at"])} for e in m["edits"]],
            "reactions": [{"user_id": U[r["user"]], "emoji": r["emoji"], "created_at": iso(r["created_at"])}
                          for r in m["reactions"]],
        })

    conversations = []
    for d in DEPARTMENTS:
        k = d.lower()
        conversations.append({
            "id": C[k], "kind": "department", "name": k, "description": f"{d} department", "is_public": False,
            "department_id": D[d], "ai_enabled": True, "created_by": None, "created_at": iso(EPOCH),
            "members": [{"user_id": U[u], "role": "member", "joined_at": iso(EPOCH), "left_at": None,
                         "ai_opt_in": False} for u in MEMBERS[k]],
        })
    for key, name, desc, public, ai, creator, members in CHANNELS:
        conversations.append({
            "id": C[key], "kind": "channel", "name": name, "description": desc, "is_public": public,
            "department_id": None, "ai_enabled": ai, "created_by": U[creator], "created_at": iso(EPOCH),
            "members": [{"user_id": U[u], "role": "owner" if u == creator else "member", "joined_at": iso(EPOCH),
                         "left_at": iso(LEFT.get((key, u))), "ai_opt_in": False} for u in members],
        })
    for a, b, opt_a, opt_b in DMS:
        conversations.append({
            "id": C[f"dm:{a}:{b}"], "kind": "dm", "name": None, "description": None, "is_public": False,
            "department_id": None, "ai_enabled": True, "created_by": U[a], "created_at": iso(EPOCH),
            "members": [
                {"user_id": U[a], "role": "member", "joined_at": iso(EPOCH), "left_at": None, "ai_opt_in": opt_a},
                {"user_id": U[b], "role": "member", "joined_at": iso(EPOCH), "left_at": None, "ai_opt_in": opt_b},
            ],
        })

    tasks = []
    for t in TASKS:
        history, when = [], t["created_at"]
        for new in STATUS_PATH.get(t["status"], []):
            when = when + timedelta(hours=rng.randint(2, 30))
            when = min(when, NOW - timedelta(hours=1))
            old = history[-1]["new_value"] if history else "open"
            history.append({"actor_id": U[t["assignee"]], "field": "status", "old_value": old, "new_value": new,
                            "changed_at": iso(when)})
        if t["key"] == "t_p10":  # picked up at once, closed by the reply in its thread
            history[0]["changed_at"] = iso(t["created_at"] + timedelta(minutes=10))
            history[-1]["changed_at"] = iso(BY_KEY["p10r"]["created_at"])
        tasks.append({
            "id": t["id"], "title": t["title"], "description_md": t["description_md"],
            "assignee_id": U[t["assignee"]], "created_by": U[t["created_by"]], "created_by_ai": t["created_by_ai"],
            "source_conversation_id": C[t["source_conversation_key"]], "project": t["project"],
            "status": t["status"], "priority": t["priority"], "due_at": iso(t["due_at"]),
            "created_at": iso(t["created_at"]),
            "completed_at": history[-1]["changed_at"] if t["status"] == "done" else None,
            "source_message_ids": [BY_KEY[k]["id"] for k in t["source_message_keys"]],
            "history": history,
        })

    suggestions = [{
        "id": s["id"], "conversation_id": C[s["conversation_key"]], "kind": s["kind"], "payload": s["payload"],
        "confidence": s["confidence"], "status": s["status"], "applied_task_id": s["applied_task_id"],
        "decided_by": U[s["decided_by"]] if s["decided_by"] else None, "decided_at": iso(s["decided_at"]),
        "created_at": iso(s["created_at"]), "expires_at": iso(s["expires_at"]),
    } for s in SUGGESTIONS]

    files = [{
        "id": uid("file", f["key"]), "uploader_id": U[f["uploader"]], "conversation_id": C[f["conv"]],
        "message_id": BY_KEY[f["message_key"]]["id"], "kind": f["kind"], "name": f["name"], "mime": f["mime"],
        "language": f["language"], "storage_key": f"fixtures/{uid('file', f['key'])}/{f['name']}",
        "created_at": iso(BY_KEY[f["message_key"]]["created_at"] - timedelta(seconds=30)),
        **({"content": f["content"]} if "content" in f else {"content_b64": f["content_b64"]}),
    } for f in FILES]

    # notifications: user mentions and task assignments; anything before the 23rd is read
    notifications = []
    for m in messages:
        for mn in m["mentions"]:
            if mn["kind"] == "user" and mn["user_id"] != m["author_id"]:
                notifications.append({"user_id": mn["user_id"], "type": "mention", "ref_type": "message",
                                      "ref_id": m["id"], "created_at": m["created_at"]})
    for t in tasks:
        if t["assignee_id"] != t["created_by"]:
            notifications.append({"user_id": t["assignee_id"], "type": "task_assigned", "ref_type": "task",
                                  "ref_id": t["id"], "created_at": t["created_at"]})
    for n in notifications:
        n["id"] = uid("notification", n["user_id"], n["ref_id"], n["type"])
        n["read_at"] = n["created_at"] if n["created_at"] < iso(at(23, 0)) else None

    # read cursors: most people are caught up, some are behind (unread badges)
    last_seq = {C[k]: v for k, v in seqs.items()}
    read_cursors = []
    for c in conversations:
        top = last_seq.get(c["id"], 0)
        for mem in c["members"]:
            if mem["left_at"]:
                continue
            behind = rng.choice([0, 0, 0, 1, 2, 5, 12])
            read_cursors.append({"user_id": mem["user_id"], "conversation_id": c["id"],
                                 "last_read_seq": max(0, top - behind)})

    users = [{
        "id": U[k], "email": f"{name.lower().replace(' ', '.')}@example.com", "name": name, "job_title": title,
        "department_id": D[dept], "manager_id": U[mgr] if mgr else None, "role": role,
        "timezone": "Asia/Kuala_Lumpur", "created_at": iso(EPOCH),
    } for k, name, title, dept, mgr, role in PEOPLE]

    expected = {
        "description": "Labels for the AI eval harness. Messages in AI-readable conversations that are not listed "
                       "here expect no_action. `already_tracked_by` means a task or suggestion already covers it, "
                       "so after dedupe the worker should create nothing new.",
        "default_tool": "no_action",
        "cases": EXPECTED,
    }

    return {
        "departments.json": [{"id": D[d], "name": d, "created_at": iso(EPOCH)} for d in DEPARTMENTS],
        "users.json": users,
        "conversations.json": conversations,
        "messages.json": messages,
        "files.json": files,
        "tasks.json": tasks,
        "suggestions.json": suggestions,
        "notifications.json": sorted(notifications, key=lambda n: n["created_at"]),
        "read_cursors.json": read_cursors,
        "expected.json": expected,
    }


def render(data: object) -> str:
    return json.dumps(data, indent=2, ensure_ascii=False) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="fail if the committed fixtures are stale")
    args = parser.parse_args()

    out = {name: render(data) for name, data in build().items()}
    if args.check:
        stale = [n for n, text in out.items() if not (OUT / n).exists() or (OUT / n).read_text() != text]
        if stale:
            sys.exit(f"stale fixtures (run scripts/build_fixtures.py): {', '.join(stale)}")
        return
    for name, text in out.items():
        (OUT / name).write_text(text)
        data = json.loads(text)
        print(f"{name}: {len(data) if isinstance(data, list) else len(data['cases'])}")


if __name__ == "__main__":
    main()
