#!/usr/bin/env python3
"""Sync helpers between the dashboard issue body and data.json."""
from __future__ import annotations
import argparse, json, re, sys, datetime, pathlib

ENV_ORDER = ["ampm-dev-us", "ampm-qa-us", "ampm-vnv-us", "ampm-perf-us"]
VALID_STATUSES = ("up", "warn", "down")
MARKER = "<!-- AMPM-STATUS-DASHBOARD: do not remove this marker -->"
DATA_FILE = pathlib.Path("data.json")


def default_env() -> dict:
    return {"status": "up", "downtime": False, "remarks": ""}


def load_data() -> dict:
    if DATA_FILE.exists():
        return json.loads(DATA_FILE.read_text())
    return {"updated": "", "envs": {e: default_env() for e in ENV_ORDER}}


def render_body(data: dict) -> str:
    lines = [
        MARKER,
        "",
        f"_Last updated: {data.get('updated', '')}_",
        "",
        "Edit values below and **Update comment** (or just toggle a checkbox) to apply changes to the status page.",
        "",
        "Allowed status values: `up`, `warn`, `down`.",
        "",
    ]
    envs = data.get("envs", {})
    for env in ENV_ORDER:
        e = {**default_env(), **envs.get(env, {})}
        remarks = e["remarks"].strip() or "_none_"
        check = "x" if e["downtime"] else " "
        lines += [
            f"## {env}",
            f"- Status: `{e['status']}`",
            f"- [{check}] Scheduled downtime",
            f"- Remarks: {remarks}",
            "",
        ]
    return "\n".join(lines)


def parse_body(body: str) -> dict:
    envs = {e: default_env() for e in ENV_ORDER}
    # split on "## env-name" headings
    sections = re.split(r"^##\s+", body, flags=re.M)
    for sec in sections[1:]:
        first, *rest = sec.splitlines()
        env = first.strip()
        if env not in ENV_ORDER:
            continue
        text = "\n".join(rest)

        m_status = re.search(r"Status:\s*`?([A-Za-z]+)`?", text)
        status = (m_status.group(1).lower() if m_status else "up")
        if status not in VALID_STATUSES:
            status = "up"

        m_dt = re.search(r"\[([ xX])\]\s*Scheduled\s*downtime", text)
        downtime = bool(m_dt and m_dt.group(1).lower() == "x")

        m_rem = re.search(r"Remarks:\s*(.*)", text)
        remarks = (m_rem.group(1).strip() if m_rem else "")
        if remarks in ("_none_", "*none*", "none", "-"):
            remarks = ""

        envs[env] = {"status": status, "downtime": downtime, "remarks": remarks}
    return envs


def cmd_to_json(args):
    body = pathlib.Path(args.body_file).read_text()
    new_envs = parse_body(body)
    data = load_data()
    if data.get("envs") == new_envs:
        print("no-change")
        return
    data["envs"] = new_envs
    data["updated"] = datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
    DATA_FILE.write_text(json.dumps(data, indent=2) + "\n")
    print("changed")


def cmd_to_issue(args):
    data = load_data()
    body = render_body(data)
    pathlib.Path(args.out).write_text(body)
    print(f"wrote {args.out}")


def main():
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)

    p1 = sub.add_parser("to-json", help="Parse issue body file and update data.json")
    p1.add_argument("body_file")
    p1.set_defaults(func=cmd_to_json)

    p2 = sub.add_parser("to-issue", help="Render issue body from data.json")
    p2.add_argument("--out", default="issue-body.md")
    p2.set_defaults(func=cmd_to_issue)

    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
