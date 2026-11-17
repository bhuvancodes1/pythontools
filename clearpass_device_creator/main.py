#!/usr/bin/env python3
import argparse
import csv
import ipaddress
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

import requests
from dotenv import load_dotenv

load_dotenv()


def env_required(key):
    value = os.getenv(key, "").strip()
    if not value or value.startswith("CHANGE_ME"):
        raise RuntimeError(f"Please configure {key} in .env")
    return value


def base_url():
    return env_required("BASE_URL").rstrip("/")


def verify_tls():
    return os.getenv("VERIFY_TLS", "true").strip().lower() not in ("false", "0", "no")


def timeout():
    return int(os.getenv("REQUEST_TIMEOUT", "30"))


def api(path):
    return f"{base_url()}/api/{path.lstrip('/')}"


def make_session():
    session = requests.Session()
    session.headers.update({
        "Accept": "application/json",
        "Content-Type": "application/json",
        "Authorization": f"Bearer {env_required('ACCESS_TOKEN')}",
    })
    return session


def call(session, method, url, **kwargs):
    response = session.request(
        method, url, timeout=timeout(), verify=verify_tls(), **kwargs
    )
    if not response.ok:
        try:
            detail = response.json()
        except ValueError:
            detail = response.text
        raise RuntimeError(
            f"{method} {url}: HTTP {response.status_code}: {detail}"
        )
    if not response.text.strip():
        return None
    try:
        return response.json()
    except ValueError as exc:
        raise RuntimeError(f"{method} {url}: response was not JSON") from exc


def get_reference(session, name):
    return call(
        session, "GET",
        api(f"network-device/name/{quote(name, safe='')}")
    )


def make_name(reference_name, new_store_number):
    if "-" not in reference_name:
        raise ValueError(f"Reference device name has no '-': {reference_name}")
    return f"{new_store_number}-{reference_name.split('-', 1)[1]}"


def make_description(description, reference_name, new_store_number):
    old_store_number = reference_name.split("-", 1)[0]
    if old_store_number in description:
        return description.replace(old_store_number, new_store_number, 1)
    print(
        "WARNING: reference store number not found in description; keeping it unchanged.",
        file=sys.stderr,
    )
    return description


def make_ip(reference_ip, gateway_ip):
    reference = ipaddress.IPv4Address(reference_ip)
    gateway = ipaddress.IPv4Address(gateway_ip)
    gateway_octets = str(gateway).split(".")
    reference_last_octet = str(reference).split(".")[-1]
    return str(ipaddress.IPv4Address(
        ".".join(gateway_octets[:3] + [reference_last_octet])
    ))


def build_payload(reference, reference_name, store_number, store_name, gateway_ip):
    for field in ("name", "description", "ip_address"):
        if not reference.get(field):
            raise ValueError(f"Reference response missing '{field}'")

    payload = {
        "name": make_name(reference_name, store_number),
        "description": make_description(
            str(reference["description"]), reference_name, store_number
        ),
        "ip_address": make_ip(str(reference["ip_address"]), gateway_ip),
        "network_addr_type": "IP",
        "radius_secret": env_required("RADIUS_SECRET"),
        "tacacs_secret": env_required("TACACS_SECRET"),
    }

    for field in ("vendor_name", "vendor_id", "coa_capable", "coa_port", "radsec_enabled"):
        if field in reference:
            payload[field] = reference[field]

    reference_attributes = reference.get("attributes") or {}
    attributes = {"Location": store_name}
    for field in ("Site_Schema", "Device Vendor"):
        if field in reference_attributes:
            attributes[field] = reference_attributes[field]
    payload["attributes"] = attributes
    return payload


def device_exists(session, name):
    url = api(f"network-device/name/{quote(name, safe='')}")
    response = session.get(url, timeout=timeout(), verify=verify_tls())
    if response.status_code == 404:
        return False
    if response.ok:
        return True
    try:
        detail = response.json()
    except ValueError:
        detail = response.text
    raise RuntimeError(
        f"Device existence check failed: HTTP {response.status_code}: {detail}"
    )


def parse_group_members(value):
    if value is None or value == "":
        return []
    if isinstance(value, list):
        raw_members = value
    else:
        # ClearPass list-format response in this environment is comma-separated text.
        raw_members = str(value).split(",")
    return [str(member).strip() for member in raw_members if str(member).strip()]


def get_group(session, group_name):
    url = api(f"network-device-group/name/{quote(group_name, safe='')}")
    return url, call(session, "GET", url)


def prepare_group_plans(session, group_names, new_ip):
    """Read each group and calculate the proposed value without changing ClearPass."""
    plans = []
    for group_name in group_names:
        url, group = get_group(session, str(group_name))
        group_format = str(group.get("group_format", "")).lower()
        plan = {
            "name": str(group_name),
            "url": url,
            "group_format": group.get("group_format", ""),
            "status": "pending",
            "current_members": [],
            "proposed_members": [],
            "current_value": group.get("value"),
            "proposed_value": None,
        }

        if group_format != "list":
            plan["status"] = "skipped_unsupported_format"
            plans.append(plan)
            continue

        current_members = parse_group_members(group.get("value"))
        proposed_members = list(current_members)
        if new_ip in proposed_members:
            plan["status"] = "already_present"
        else:
            proposed_members.append(new_ip)

        plan["current_members"] = current_members
        plan["proposed_members"] = proposed_members
        plan["proposed_value"] = ", ".join(proposed_members)
        plans.append(plan)
    return plans


def show_preview(payload, group_plans, preview_path):
    """Print and save a reviewable preview. Secrets are masked in the saved/displayed copy."""
    safe_payload = dict(payload)
    for secret_field in ("radius_secret", "tacacs_secret"):
        if safe_payload.get(secret_field):
            safe_payload[secret_field] = "******** (configured in .env; not stored in preview)"

    safe_groups = []
    for plan in group_plans:
        safe_groups.append({
            "group_name": plan["name"],
            "group_format": plan["group_format"],
            "status": plan["status"],
            "current_members": plan["current_members"],
            "proposed_members": plan["proposed_members"],
            "current_value": plan["current_value"],
            "proposed_value": plan["proposed_value"],
        })

    preview = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "action": "Create ClearPass network device and update inherited NAD groups",
        "device_post": {
            "method": "POST",
            "endpoint": "/api/network-device",
            "request_body": safe_payload,
            "note": "nad_groups is intentionally omitted from the device POST body.",
        },
        "nad_group_updates": safe_groups,
        "security_note": "RADIUS and TACACS secrets are masked and are not written to this preview file.",
    }
    preview_path = Path(preview_path)
    preview_path.parent.mkdir(parents=True, exist_ok=True)
    preview_path.write_text(json.dumps(preview, indent=2), encoding="utf-8")

    print("\n" + "=" * 72)
    print("PREVIEW - REVIEW BEFORE MAKING CHANGES IN CLEARPASS")
    print("=" * 72)
    print("\nDEVICE POST REQUEST")
    print("POST /api/network-device")
    print(json.dumps(safe_payload, indent=2))
    print("\nNAD GROUP CHANGES")
    if not safe_groups:
        print("No NAD groups were returned by the reference device.")
    for group in safe_groups:
        print(f"\nGroup: {group['group_name']}")
        print(f"Status: {group['status']}")
        if group["status"] in ("pending", "already_present"):
            print(f"Current members : {group['current_members']}")
            print(f"Proposed members: {group['proposed_members']}")
            print(f"PATCH value     : {group['proposed_value']}")
        elif group["status"] == "skipped_unsupported_format":
            print(f"Unsupported group format: {group['group_format']} (will not be modified)")
    print(f"\nPreview saved to: {preview_path.resolve()}")
    print("Secrets are masked in the preview file and terminal output.")
    print("=" * 72)
    return preview_path


def confirm_changes(device_name, auto_approve=False):
    if auto_approve:
        print("--yes supplied: approval prompt skipped.")
        return True
    if not sys.stdin.isatty():
        raise RuntimeError(
            "Interactive approval is unavailable. Run in a terminal, or use --yes "
            "only when approval has already been obtained by your calling workflow."
        )
    answer = input(
        f"\nTo create '{device_name}' and update the listed NAD groups, "
        "type CREATE to proceed (anything else cancels): "
    ).strip()
    return answer == "CREATE"


def verify_group_snapshots(session, group_plans):
    """Abort before device creation if a group changed after the preview was prepared."""
    for plan in group_plans:
        if plan["status"] not in ("pending", "already_present"):
            continue
        _, latest = get_group(session, plan["name"])
        latest_members = parse_group_members(latest.get("value"))
        if latest_members != plan["current_members"]:
            raise RuntimeError(
                f"NAD group '{plan['name']}' changed after preview. No device was created. "
                "Generate a fresh preview and review it again."
            )


def apply_group_plan(session, plan):
    if plan["status"] == "already_present":
        return f"UNCHANGED {plan['name']}: new device IP is already a member."
    if plan["status"] == "skipped_unsupported_format":
        return f"SKIPPED {plan['name']}: unsupported group format '{plan['group_format']}'."

    body = {
        "group_format": plan["group_format"],
        "value": plan["proposed_value"],
    }
    call(session, "PATCH", plan["url"], json=body)
    return f"UPDATED {plan['name']}: added {plan['proposed_members'][-1]}."


def process(session, row, dry_run=False, auto_approve=False, preview_dir="previews"):
    reference_name = row["reference_device_name"].strip()
    store_number = row["new_store_number"].strip()
    store_name = row["new_store_name"].strip()
    gateway = row["vlan20_gateway_ip"].strip()
    if not all((reference_name, store_number, store_name, gateway)):
        raise ValueError("A required input CSV field is empty.")

    reference = get_reference(session, reference_name)
    payload = build_payload(reference, reference_name, store_number, store_name, gateway)
    new_name = payload["name"]
    new_ip = payload["ip_address"]
    group_names = reference.get("nad_groups") or []

    print(f"Reference device: {reference_name}")
    print(f"Proposed device : {new_name}")
    print(f"Proposed IP     : {new_ip}")

    if device_exists(session, new_name):
        raise RuntimeError(f"Device '{new_name}' already exists; refusing duplicate POST.")

    group_plans = prepare_group_plans(session, group_names, new_ip)
    safe_filename = re.sub(r"[^A-Za-z0-9_.-]+", "_", new_name)
    preview_path = Path(preview_dir) / f"{safe_filename}_preview.json"
    show_preview(payload, group_plans, preview_path)

    if dry_run:
        print("DRY RUN: preview created. No POST or PATCH requests were sent.")
        return

    if not confirm_changes(new_name, auto_approve=auto_approve):
        print("CANCELLED: no POST or PATCH requests were sent.")
        return

    # Ensure the groups still match what the user approved before creating the device.
    verify_group_snapshots(session, group_plans)

    created = call(session, "POST", api("network-device"), json=payload)
    print("\nDEVICE CREATED:")
    print(json.dumps(created, indent=2) if created is not None else "ClearPass returned an empty response.")

    # ClearPass 6.11.16 workflow: add NAD membership separately after device creation.
    for plan in group_plans:
        print(apply_group_plan(session, plan))


def read_rows(path):
    required = {
        "reference_device_name", "new_store_number",
        "new_store_name", "vlan20_gateway_ip"
    }
    with open(path, newline="", encoding="utf-8-sig") as input_file:
        reader = csv.DictReader(input_file)
        missing = required - set(reader.fieldnames or [])
        if missing:
            raise ValueError("Missing CSV columns: " + ", ".join(sorted(missing)))
        return list(reader)


def main():
    parser = argparse.ArgumentParser(
        description="Create ClearPass devices with a preview and approval step."
    )
    parser.add_argument("-i", "--input", default="input.csv", help="Input CSV file.")
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Generate and save previews; do not send POST/PATCH requests."
    )
    parser.add_argument(
        "--yes", action="store_true",
        help="Skip interactive confirmation. Use only after approval in the calling workflow."
    )
    parser.add_argument(
        "--preview-dir", default="previews",
        help="Directory where redacted preview JSON files are saved."
    )
    args = parser.parse_args()

    session = make_session()
    rows = read_rows(args.input)
    failures = 0
    for number, row in enumerate(rows, 1):
        print(f"\n===== Input row {number} =====")
        try:
            process(
                session, row,
                dry_run=args.dry_run,
                auto_approve=args.yes,
                preview_dir=args.preview_dir,
            )
        except Exception as exc:
            failures += 1
            print(f"ERROR: {exc}", file=sys.stderr)

    print(f"\nCompleted: {len(rows) - failures} succeeded; {failures} failed.")
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
