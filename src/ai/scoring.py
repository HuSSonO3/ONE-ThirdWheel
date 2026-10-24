"""Argument-aware evaluation. Labels stay here, outside prompts and model clients."""

from collections import Counter


def arguments_match(expected: dict, record: dict, users: list[dict]) -> bool:
    actual = record["result"]["output"].get("proposal", record["arguments"])
    for field in ("assignee_id", "assignee_is_member", "project", "task_id", "new_status",
                  "start_date", "end_date", "amount", "currency", "duration_minutes"):
        if field in expected and actual.get(field) != expected[field]:
            return False
    if expected.get("assignee_in") and actual.get("assignee_id") not in expected["assignee_in"]:
        return False
    if expected.get("due_at") and str(actual.get("due_at", ""))[:10] != expected["due_at"]:
        return False
    if expected.get("attendee_ids"):
        resolved = set()
        for hint in actual.get("attendee_hints", []):
            matches = [u["id"] for u in users if hint.strip("@ ").casefold() in (
                u["name"].casefold(), u["name"].split()[0].casefold(), u["id"])]
            if len(matches) != 1:
                return False
            resolved.add(matches[0])
        if resolved != set(expected["attendee_ids"]):
            return False
    return True


class Scores:
    def __init__(self):
        self.tp = self.fp = self.fn = 0
        self.tool_correct = self.argument_correct = self.labelled = 0
        self.choices: Counter[str] = Counter()
        self.rows: list[dict] = []

    def observe(self, label: dict | None, calls: list[dict], users: list[dict], *, skipped=False):
        expected_tool = label["expected_tool"] if label else "no_action"
        self.choices.update(c["tool_name"] for c in calls)
        expected_args = label.get("expected", {}) if label else {}
        expected_calls = expected_args.get("calls", [expected_args]) if expected_tool == "propose_task" else []
        predicted = [c for c in calls if c["tool_name"] == "propose_task"]
        # One-to-one match: two calls for one correct assignee cannot cover two planted tasks.
        remaining = list(predicted)
        matched = 0
        for args in expected_calls:
            match = next((c for c in remaining if c["status"] == "executed"
                          and not c["result"]["output"].get("rolled_back") and
                          arguments_match(args, c, users)), None)
            if match:
                matched += 1
                remaining.remove(match)
        self.tp += matched
        self.fp += len(predicted) - matched
        self.fn += len(expected_calls) - matched
        if not label:
            return
        self.labelled += 1
        correct_tool = (skipped and expected_tool is None) or (
            not skipped and expected_tool is not None and
            len([c for c in calls if c["tool_name"] == expected_tool]) == (len(expected_calls) or 1))
        correct_args = correct_tool and all(c["status"] != "failed" for c in calls) and (
            skipped or (expected_tool == "propose_task" and matched == len(expected_calls)) or
            (expected_tool != "propose_task" and any(
                arguments_match(expected_args, c, users) for c in calls if c["tool_name"] == expected_tool)))
        self.tool_correct += bool(correct_tool)
        self.argument_correct += bool(correct_args)
        row = {"case": label["case"], "expected": expected_tool,
               "actual": [c["tool_name"] + ":" + c["status"] for c in calls],
               "arguments_correct": bool(correct_args), "skipped": skipped}
        self.rows.append(row)

    def report(self):
        return {"task_precision": self.tp / (self.tp + self.fp) if self.tp + self.fp else 0.0,
                "task_recall": self.tp / (self.tp + self.fn) if self.tp + self.fn else 0.0,
                "labelled_tool_accuracy": self.tool_correct / self.labelled if self.labelled else 0.0,
                "labelled_argument_accuracy": self.argument_correct / self.labelled if self.labelled else 0.0,
                "tool_choices": dict(self.choices), "cases": self.rows}
