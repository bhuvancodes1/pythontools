#!/usr/bin/env python3
import argparse
import csv
import ipaddress
import os
import sys
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
    s = requests.Session()
    s.headers.update({
        "Accept": "application/json",
        "Content-Type": "application/json",
        "Authorization": f"Bearer {env_required('ACCESS_TOKEN')}",
    })
    return s


def call(s, method, url, **kwargs):
    r = s.request(method, url, timeout=timeout(), verify=verify_tls(), **kwargs)
    if not r.ok:
        try:
            detail = r.json()
        except ValueError:
            detail = r.text
        raise RuntimeError(f"{method} {url}: HTTP {r.status_code}: {detail}")
    if not r.text.strip():
        return None
    try:
        return r.json()
    except ValueError as exc:
        raise RuntimeError(f"{method} {url}: response was not JSON") from exc


def get_reference(s, name):
    return call(s, "GET", api(f"network-device/name/{quote(name, safe='')}"))


def make_name(reference_name, new_store_number):
    if "-" not in reference_name:
        raise ValueError(f"Reference device name has no '-': {reference_name}")
    return f"{new_store_number}-{reference_name.split('-', 1)[1]}"


def make_description(description, reference_name, new_store_number):
    old_store_number = reference_name.split("-", 1)[0]
    if old_store_number in description:
        return description.replace(old_store_number, new_store_number, 1)
    print("WARNING: reference store number not found in description; keeping it unchanged.",
          file=sys.stderr)
    return description


def make_ip(reference_ip, gateway_ip):
    old_ip = ipaddress.IPv4Address(reference_ip)
    gateway = ipaddress.IPv4Address(gateway_ip)
    octets = str(gateway).split(".")
    return str(ipaddress.IPv4Address(".".join(octets[:3] + [str(old_ip).split(".")[-1]])))


def build_payload(ref, ref_name, store_number, store_name, gateway_ip):
    for field in ("name", "description", "ip_address"):
        if not ref.get(field):
            raise ValueError(f"Reference response missing '{field}'")

    payload = {
        "name": make_name(ref_name, store_number),
        "description": make_description(str(ref["description"]), ref_name, store_number),
        "ip_address": make_ip(str(ref["ip_address"]), gateway_ip),
        "network_addr_type": "IP",
        "radius_secret": env_required("RADIUS_SECRET"),
        "tacacs_secret": env_required("TACACS_SECRET"),
    }

    for field in ("vendor_name", "vendor_id", "coa_capable", "coa_port", "radsec_enabled"):
        if field in ref:
            payload[field] = ref[field]

    ref_attrs = ref.get("attributes") or {}
    attrs = {"Location": store_name}
    for field in ("Site_Schema", "Device Vendor"):
        if field in ref_attrs:
            attrs[field] = ref_attrs[field]
    payload["attributes"] = attrs
    return payload



def exists(s, name):
    url = api(f"network-device/name/{quote(name, safe='')}")
    r = s.get(url, timeout=timeout(), verify=verify_tls())
    if r.status_code == 404:
        return False
    if r.ok:
        return True
    try:
        detail = r.json()
    except ValueError:
        detail = r.text
    raise RuntimeError(f"Device existence check failed: HTTP {r.status_code}: {detail}")


def update_group_add_ip(s, group_name, new_ip, dry_run=False):
    url = api(f"network-device-group/name/{quote(group_name, safe='')}")
    group = call(s, "GET", url)
    group_format = str(group.get("group_format", "")).lower()

    if group_format != "list":
        return f"SKIPPED {group_name}: group format is '{group_format}', not 'list'."

    value = group.get("value") or ""
    if isinstance(value, list):
        members = [str(x).strip() for x in value if str(x).strip()]
    else:
        members = [x.strip() for x in str(value).split(",") if x.strip()]

    if new_ip in members:
        return f"UNCHANGED {group_name}: {new_ip} already exists."

    members.append(new_ip)
    updated_value = ", ".join(members)
    if dry_run:
        return f"DRY RUN {group_name}: would set value to '{updated_value}'."

    body = {"group_format": group.get("group_format", "list"), "value": updated_value}
    call(s, "PATCH", url, json=body)
    return f"UPDATED {group_name}: added {new_ip}."


def process(s, row, dry_run=False):
    ref_name = row["reference_device_name"].strip()
    store_number = row["new_store_number"].strip()
    store_name = row["new_store_name"].strip()
    gateway = row["vlan20_gateway_ip"].strip()
    if not all((ref_name, store_number, store_name, gateway)):
        raise ValueError("A required input CSV field is empty.")

    ref = get_reference(s, ref_name)
    payload = build_payload(ref, ref_name, store_number, store_name, gateway)
    new_name, new_ip = payload["name"], payload["ip_address"]
    groups = ref.get("nad_groups") or []

    print(f"Reference : {ref_name}")
    print(f"New name  : {new_name}")
    print(f"New IP    : {new_ip}")
    print(f"Groups    : {groups}")
    print("POST body :", payload)

    if exists(s, new_name):
        raise RuntimeError(f"Device '{new_name}' already exists; refusing duplicate POST.")

    if dry_run:
        print("DRY RUN: no POST or PATCH sent.")
        for group in groups:
            print(update_group_add_ip(s, str(group), new_ip, dry_run=True))
        return

    created = call(s, "POST", api("network-device"), json=payload)
    print("DEVICE CREATED:", created)

    # ClearPass 6.11.16: do not send nad_groups in the network-device POST.
    # Append the new device IP to each inherited list-format group separately.
    for group in groups:
        print(update_group_add_ip(s, str(group), new_ip))


def read_rows(path):
    required = {"reference_device_name", "new_store_number", "new_store_name", "vlan20_gateway_ip"}
    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        missing = required - set(reader.fieldnames or [])
        if missing:
            raise ValueError("Missing CSV columns: " + ", ".join(sorted(missing)))
        return list(reader)


def main():
    parser = argparse.ArgumentParser(description="Create ClearPass devices from a reference device.")
    parser.add_argument("-i", "--input", default="input.csv")
    parser.add_argument("--dry-run", action="store_true",
                        help="GET and show planned changes without POST/PATCH.")
    args = parser.parse_args()

    s = make_session()
    rows = read_rows(args.input)
    failures = 0
    for number, row in enumerate(rows, 1):
        print(f"\n===== Input row {number} =====")
        try:
            process(s, row, args.dry_run)
        except Exception as exc:
            failures += 1
            print(f"ERROR: {exc}", file=sys.stderr)

    print(f"\nCompleted: {len(rows) - failures} succeeded; {failures} failed.")
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
