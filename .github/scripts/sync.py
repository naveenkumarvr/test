#!/usr/bin/env python3
"""
Sync helpers for the AMPM status page.

Two responsibilities:
  1. regen-template : Regenerate .github/ISSUE_TEMPLATE/update-status.yml
                      so dropdowns/inputs default to current data.json values.
  2. apply-form     : Parse a submitted issue body (from the form) and update
                      data.json.
"""
from __future__ import annotations
import argparse, json, re, datetime, pathlib, sys

ENV_ORDER = ["ampm-dev-us", "ampm-qa-us", "ampm-vnv-us", "ampm-perf-us"]
STATUS_OPTIONS = ["up", "warn", "down"]
DOWNTIME_OPTIONS = ["\"No\"", "\"Yes\""]
DOWNTIME_LABELS = ["No", "Yes"]

ROOT = pathlib.Path(__file__).resolve().parents[2]
DATA_FILE = ROOT / "data.json"
TEMPLATE_FILE = ROOT / ".github" / "ISSUE_TEMPLATE" / "update-status.yml"


def default_env() -> dict:
    return {"status": "up", "downtime": False, "remarks": ""}


def load_data() -> dict:
    if DATA_FILE.exists():
        return json.loads(DATA_FILE.read_text())
    return {"updated": "", "envs": {e: default_env() for e in ENV_ORDER}}


# ─────────────────────────────────────────────────────────────────────────────
# 1. Regenerate the issue form template
# ─────────────────────────────────────────────────────────────────────────────

def yaml_escape(s: str) -> str:
    """Quote a string for safe inclusion in a YAML double-quoted scalar."""
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


def render_template(data: dict) -> str:
    envs = data.get("envs", {})
    updated = data.get("updated", "")

    status_emoji = {"up": "🟢 Up", "warn": "🟠 Not Stable", "down": "🔴 Down"}

    table_rows = []
    for env in ENV_ORDER:
        e = {**default_env(), **envs.get(env, {})}
        status_cell = status_emoji.get(e["status"], e["status"])
        downtime_cell = "✅ Yes" if e["downtime"] else "—"
        remarks_cell = e["remarks"].replace("|", "\\|") if e["remarks"] else "—"
        table_rows.append(f"        | `{env}` | {status_cell} | {downtime_cell} | {remarks_cell} |")

    lines = [
        "name: Update environment status",
        "description: Edit the values below to update the AMPM status page.",
        'title: "Status update"',
        "labels: [\"status-update\"]",
        "body:",
        "  - type: markdown",
        "    attributes:",
        "      value: |",
        "        ### 📊 Current status",
        "",
        "        | Environment | Status | Scheduled Downtime | Remarks |",
        "        | --- | --- | --- | --- |",
        *table_rows,
        "",
        f"        _Snapshot: {updated or 'n/a'}_",
        "",
        "        ---",
        "",
        "        **Values below are pre-filled with the current state.** Change whatever you need",
        "        and click **Submit new issue**. A workflow will update `data.json` and this page,",
        "        then close the issue.",
    ]

    for env in ENV_ORDER:
        e = {**default_env(), **envs.get(env, {})}
        status_default = STATUS_OPTIONS.index(e["status"]) if e["status"] in STATUS_OPTIONS else 0
        downtime_default = 1 if e["downtime"] else 0
        remarks = e["remarks"] or ""

        lines += [
            "",
            f"  # ── {env} ──",
            "  - type: dropdown",
            f"    id: {env}-status",
            "    attributes:",
            f"      label: {env} — Status",
            "      options:",
            *[f"        - {opt}" for opt in STATUS_OPTIONS],
            f"      default: {status_default}",
            "    validations:",
            "      required: true",
            "",
            "  - type: dropdown",
            f"    id: {env}-downtime",
            "    attributes:",
            f"      label: {env} — Scheduled downtime",
            "      options:",
            *[f"        - {opt}" for opt in DOWNTIME_OPTIONS],
            f"      default: {downtime_default}",
            "    validations:",
            "      required: true",
            "",
            "  - type: input",
            f"    id: {env}-remarks",
            "    attributes:",
            f"      label: {env} — Remarks",
            "      placeholder: optional note",
        ]
        if remarks:
            lines.append(f"      value: {yaml_escape(remarks)}")

    return "\n".join(lines) + "\n"


def cmd_regen_template(_args):
    data = load_data()
    new = render_template(data)
    if TEMPLATE_FILE.exists() and TEMPLATE_FILE.read_text() == new:
        print("no-change")
        return
    TEMPLATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    TEMPLATE_FILE.write_text(new)
    print("changed")


# ─────────────────────────────────────────────────────────────────────────────
# 2. Apply submitted issue form body to data.json
# ─────────────────────────────────────────────────────────────────────────────

# Issue Forms render submissions as:
#   ### <label>
#   <blank line>
#   <value or "_No response_">
#   <blank line>
HEADING_RE = re.compile(r"^###\s+(.+?)\s*$", re.M)


def parse_form_body(body: str) -> dict:
    """Parse a submitted issue-form body. Returns {env: {status, downtime, remarks}}."""
    # Build {label: value} map
    fields: dict[str, str] = {}
    matches = list(HEADING_RE.finditer(body))
    for i, m in enumerate(matches):
        label = m.group(1).strip()
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(body)
        value = body[start:end].strip()
        if value in ("_No response_", "*No response*"):
            value = ""
        fields[label] = value

    envs: dict[str, dict] = {}
    for env in ENV_ORDER:
        status_label   = f"{env} — Status"
        downtime_label = f"{env} — Scheduled downtime"
        remarks_label  = f"{env} — Remarks"

        status = fields.get(status_label, "up").strip().lower()
        if status not in STATUS_OPTIONS:
            status = "up"

        downtime = fields.get(downtime_label, "No").strip().lower() == "yes"
        remarks = fields.get(remarks_label, "").strip()

        envs[env] = {"status": status, "downtime": downtime, "remarks": remarks}
    return envs


def cmd_apply_form(args):
    body = pathlib.Path(args.body_file).read_text()
    new_envs = parse_form_body(body)
    data = load_data()
    if data.get("envs") == new_envs:
        print("no-change")
        return
    data["envs"] = new_envs
    data["updated"] = datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
    DATA_FILE.write_text(json.dumps(data, indent=2) + "\n")
    print("changed")


# ─────────────────────────────────────────────────────────────────────────────

def main():
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)

    p1 = sub.add_parser("regen-template", help="Rewrite issue-form YAML with current defaults.")
    p1.set_defaults(func=cmd_regen_template)

    p2 = sub.add_parser("apply-form", help="Parse submitted form body and update data.json.")
    p2.add_argument("body_file")
    p2.set_defaults(func=cmd_apply_form)

    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
