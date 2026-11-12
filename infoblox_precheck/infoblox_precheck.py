"""Infoblox store staging pre-check.

Validates engineer-provided VLAN 1/VLAN 2 addressing against Infoblox by
comparing the first three IPv4 octets, and returns every Infoblox network
scope associated with the requested store.

Required .env variables:
    INFOBLOX_BASE_URL=https://your-infoblox-server
    INFOBLOX_WAPI_VERSION=v2.12
    INFOBLOX_USERNAME=your_username
    INFOBLOX_PASSWORD=your_password

Optional .env variables:
    INFOBLOX_NETWORK_VIEW=default
    INFOBLOX_VERIFY_SSL=true
    INFOBLOX_TIMEOUT=30
    INFOBLOX_MAX_RESULTS=1000
"""

from __future__ import annotations

import json
import os
import re
import ssl
import urllib.error
import urllib.parse
import urllib.request
from typing import Any


def load_dotenv(path: str = ".env") -> None:
    """Small .env loader so the function has no third-party dependency."""
    if not os.path.exists(path):
        return
    with open(path, "r", encoding="utf-8") as file:
        for raw_line in file:
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            os.environ.setdefault(key, value)


def env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def first_three_octets(value: str) -> str:
    """Return first three IPv4 octets from host, xx-form, or CIDR string."""
    if not isinstance(value, str):
        raise ValueError("IP/network value must be a string")

    candidate = value.strip().split("/", 1)[0]
    parts = candidate.split(".")
    if len(parts) != 4:
        raise ValueError(f"Invalid IPv4 format: {value}")

    for octet in parts[:3]:
        if not octet.isdigit() or not 0 <= int(octet) <= 255:
            raise ValueError(f"Invalid IPv4 format: {value}")

    last = parts[3].lower()
    if last not in {"x", "xx"}:
        if not last.isdigit() or not 0 <= int(last) <= 255:
            raise ValueError(f"Invalid IPv4 format: {value}")

    return ".".join(parts[:3])


def extattr_value(record: dict[str, Any], name: str) -> str | None:
    value = record.get("extattrs", {}).get(name, {}).get("value")
    return str(value).strip() if value is not None else None


def get_gateway(record: dict[str, Any]) -> str | None:
    for option in record.get("options", []) or []:
        if str(option.get("name", "")).lower() == "routers":
            value = option.get("value")
            return str(value).strip() if value else None
    return None


def get_vlan_role(record: dict[str, Any]) -> str:
    """Determine Primary/Secondary from Subnet Name first, comment second."""
    subnet_name = extattr_value(record, "Subnet Name") or ""
    comment = str(record.get("comment") or "")
    text = f"{subnet_name} {comment}".lower()
    if "secondary" in text:
        return "Secondary"
    return "Primary"


def natural_vlan_key(record: dict[str, Any]) -> tuple[int, str, int]:
    vlan = extattr_value(record, "VLAN") or ""
    match = re.search(r"\d+", vlan)
    number = int(match.group()) if match else 999999
    role_order = 1 if get_vlan_role(record) == "Secondary" else 0
    return number, vlan.lower(), role_order


def get_infoblox_config() -> dict[str, Any]:
    load_dotenv()

    required = [
        "INFOBLOX_BASE_URL",
        "INFOBLOX_WAPI_VERSION",
        "INFOBLOX_USERNAME",
        "INFOBLOX_PASSWORD",
    ]
    missing = [name for name in required if not os.getenv(name)]
    if missing:
        raise RuntimeError(f"Missing required .env value(s): {', '.join(missing)}")

    return {
        "base_url": os.environ["INFOBLOX_BASE_URL"].rstrip("/"),
        "version": os.environ["INFOBLOX_WAPI_VERSION"].strip("/"),
        "username": os.environ["INFOBLOX_USERNAME"],
        "password": os.environ["INFOBLOX_PASSWORD"],
        "network_view": os.getenv("INFOBLOX_NETWORK_VIEW", "default"),
        "verify_ssl": env_bool("INFOBLOX_VERIFY_SSL", True),
        "timeout": int(os.getenv("INFOBLOX_TIMEOUT", "30")),
        "max_results": int(os.getenv("INFOBLOX_MAX_RESULTS", "1000")),
    }


def fetch_store_networks(store_id: str) -> list[dict[str, Any]]:
    """Get network objects from Infoblox and retain only the requested Site EA."""
    config = get_infoblox_config()

    query = urllib.parse.urlencode(
        {
        "*Site": store_id,
        "_return_fields": "network,network_view,comment,extattrs,options",
        "_max_results": config["max_results"],
    }
    )
    url = f'{config["base_url"]}/wapi/{config["version"]}/network?{query}'

    credentials = f'{config["username"]}:{config["password"]}'.encode("utf-8")
    import base64
    auth_header = "Basic " + base64.b64encode(credentials).decode("ascii")

    request = urllib.request.Request(
        url,
        headers={"Authorization": auth_header, "Accept": "application/json"},
        method="GET",
    )

    ssl_context = None
    if not config["verify_ssl"]:
        ssl_context = ssl._create_unverified_context()  # noqa: SLF001

    try:
        with urllib.request.urlopen(
            request, timeout=config["timeout"], context=ssl_context
        ) as response:
            data = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Infoblox API HTTP {exc.code}: {body}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Unable to connect to Infoblox: {exc.reason}") from exc

    if not isinstance(data, list):
        raise RuntimeError("Unexpected Infoblox response: expected a JSON array")

    requested = store_id.strip().upper()
    return [
        item
        for item in data
        if (extattr_value(item, "Site") or "").upper() == requested
        and (
            not config["network_view"]
            or item.get("network_view") == config["network_view"]
        )
    ]


def find_validation_network(
    records: list[dict[str, Any]], vlan: str, primary_only: bool = False
) -> dict[str, Any] | None:
    candidates = [r for r in records if extattr_value(r, "VLAN") == vlan]
    if primary_only:
        candidates = [r for r in candidates if get_vlan_role(r) == "Primary"]
    return sorted(candidates, key=natural_vlan_key)[0] if candidates else None


def validate_engineer_ip(
    vlan: str,
    engineer_ip: str,
    record: dict[str, Any] | None,
) -> dict[str, Any]:
    if record is None:
        return {
            "vlan": vlan,
            "engineer_provided": engineer_ip,
            "infoblox_network": None,
            "gateway": None,
            "result": "FAIL",
            "message": f"VLAN{vlan} scope not found in Infoblox for requested store",
        }

    network = str(record.get("network") or "")
    engineer_prefix = first_three_octets(engineer_ip)
    infoblox_prefix = first_three_octets(network)
    passed = engineer_prefix == infoblox_prefix

    return {
        "vlan": vlan,
        "engineer_provided": engineer_ip,
        "infoblox_network": network,
        "gateway": get_gateway(record),
        "result": "PASS" if passed else "FAIL",
        "message": (
            f"First three octets match: {engineer_prefix}"
            if passed
            else f"First three octets do not match: engineer={engineer_prefix}, "
            f"Infoblox={infoblox_prefix}"
        ),
    }


def build_vlan_configuration(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []

    for record in sorted(records, key=natural_vlan_key):
        vlan = extattr_value(record, "VLAN") or "Unknown"
        role = get_vlan_role(record)
        gateway = get_gateway(record)
        comment = str(record.get("comment") or "")
        subnet_name = extattr_value(record, "Subnet Name")

        rows.append(
            {
                "vlan": vlan,
                "role": role,
                "description": comment or subnet_name or f"VLAN{vlan} {role}",
                "network": record.get("network"),
                "gateway": gateway,
                "network_view": record.get("network_view"),
                "status": (
                    "Present" if gateway else "Present - Gateway option missing"
                ),
            }
        )

    return rows


def run_infoblox_precheck(
    store_id: str,
    vlan1_ip: str,
    vlan2_ip: str,
) -> dict[str, Any]:
    """Run Store Staging Step 1 Infoblox pre-check."""
    if not store_id.strip():
        raise ValueError("store_id is required")

    # Validate engineer input before calling Infoblox.
    first_three_octets(vlan1_ip)
    first_three_octets(vlan2_ip)

    records = fetch_store_networks(store_id)
    if not records:
        return {
            "store_id": store_id,
            "precheck_status": "FAIL",
            "summary": f"No Infoblox network scopes found for store {store_id}",
            "address_validation": [],
            "vlan_configuration": [],
        }

    # Requirement: VLAN1 must use Primary only. VLAN2 is matched by VLAN EA.
    vlan1_record = find_validation_network(records, "1", primary_only=True)
    vlan2_record = find_validation_network(records, "2", primary_only=False)

    validations = [
        validate_engineer_ip("1", vlan1_ip, vlan1_record),
        validate_engineer_ip("2", vlan2_ip, vlan2_record),
    ]

    overall_pass = all(item["result"] == "PASS" for item in validations)

    return {
        "store_id": store_id,
        "precheck_status": "PASS" if overall_pass else "FAIL",
        "summary": (
            "The VLAN1 and VLAN2 addressing supplied for staging matches "
            "the corresponding Infoblox network scopes."
            if overall_pass
            else "One or more staging VLAN addresses do not match the "
            "corresponding Infoblox network scopes."
        ),
        "address_validation": validations,
        "vlan_configuration": build_vlan_configuration(records),
    }


if __name__ == "__main__":
    # Temporary CLI runner. Later the application can call run_infoblox_precheck()
    # directly from FastAPI/Flask without changing the core validation logic.
    store = input("Store ID (example JS5285): ").strip()
    vlan1 = input("Engineer VLAN1 IP (example 10.189.248.xx): ").strip()
    vlan2 = input("Engineer VLAN2 IP (example 10.201.248.xx): ").strip()

    try:
        result = run_infoblox_precheck(store, vlan1, vlan2)
        print(json.dumps(result, indent=2))
    except Exception as exc:
        print(json.dumps({"precheck_status": "ERROR", "error": str(exc)}, indent=2))
