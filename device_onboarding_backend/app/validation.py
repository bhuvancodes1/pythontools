import re
from collections import Counter, defaultdict
from typing import Dict, List, Tuple
from .models import Device

MAC_RE = re.compile(r"^[0-9a-f]{2}(:[0-9a-f]{2}){5}$")
SWITCH_RE = re.compile(r"^(?P<role>[A-Za-z0-9]+(?:-[A-Za-z0-9]+)*)-(?P<member>[1-9][0-9]*)$")
AP_RE = re.compile(r"^AP(?P<number>[0-9]+)$", re.IGNORECASE)
STORE_ID_RE = re.compile(r"^[A-Za-z]+$")
STORE_NUMBER_RE = re.compile(r"^[0-9]+$")


def normalize_mac(value: str) -> str:
    compact = re.sub(r"[^0-9A-Fa-f]", "", value or "")
    if len(compact) != 12:
        raise ValueError(f"Invalid MAC address: {value}")
    normalized = ":".join(compact[i:i + 2] for i in range(0, 12, 2)).lower()
    if not MAC_RE.fullmatch(normalized):
        raise ValueError(f"Invalid MAC address: {value}")
    return normalized


def prepare_devices(payload: Dict) -> Tuple[List[Device], List[str]]:
    errors: List[str] = []
    store = payload.get("store", {})
    identifier = str(store.get("identifier", "")).strip().upper()
    number = str(store.get("number", "")).strip()
    if not STORE_ID_RE.fullmatch(identifier):
        errors.append("store.identifier must contain letters only")
    if not STORE_NUMBER_RE.fullmatch(number):
        errors.append("store.number must contain digits only")
    prefix = f"{identifier}{number}"
    services = payload.get("global_config", {}).get("license_services", {})

    devices: List[Device] = []
    for index, raw in enumerate(payload.get("devices", []), start=1):
        try:
            name = str(raw["input_name"]).strip().upper()
            dtype = str(raw["device_type"]).strip().lower()
            serial = str(raw["serial"]).strip().upper()
            mac = normalize_mac(str(raw["mac"]))
            if dtype not in {"switch", "iap"}:
                raise ValueError("device_type must be 'switch' or 'iap'")
            if not serial:
                raise ValueError("serial is required")
            service = str(services.get(dtype, "")).strip()
            if not service:
                raise ValueError(f"license service is required for {dtype}")

            device = Device(name, dtype, mac, serial, license_service=service)
            if dtype == "switch":
                match = SWITCH_RE.fullmatch(name)
                if not match:
                    raise ValueError("switch input_name must end with stack member, e.g. M1-ST1-1")
                device.base_role = match.group("role")
                device.stack_member = int(match.group("member"))
                device.generated_name = f"{prefix}-{device.base_role}"
            else:
                match = AP_RE.fullmatch(name)
                if not match:
                    raise ValueError("AP input_name must be AP followed by a number, e.g. AP01")
                ap_number = int(match.group("number"))
                if ap_number < 1:
                    raise ValueError("AP number must be 1 or greater")
                device.base_role = f"AP{ap_number:02d}"
                device.generated_name = f"{prefix}-{device.base_role}"
            device.validation_status = "VALID"
            devices.append(device)
        except (KeyError, ValueError) as exc:
            errors.append(f"devices[{index}]: {exc}")

    mac_counts = Counter(d.mac for d in devices)
    serial_counts = Counter(d.serial for d in devices)
    ap_counts = Counter(d.generated_name for d in devices if d.device_type == "iap")
    for value, count in mac_counts.items():
        if count > 1:
            errors.append(f"Duplicate MAC: {value}")
    for value, count in serial_counts.items():
        if count > 1:
            errors.append(f"Duplicate serial: {value}")
    for value, count in ap_counts.items():
        if count > 1:
            errors.append(f"Duplicate AP name: {value}")

    stacks = defaultdict(list)
    for d in devices:
        if d.device_type == "switch":
            stacks[d.generated_name].append(d)
    for stack_name, members in stacks.items():
        member_ids = [d.stack_member for d in members]
        if len(member_ids) != len(set(member_ids)):
            errors.append(f"Duplicate stack member in {stack_name}")
        if 1 not in member_ids:
            errors.append(f"{stack_name} must include stack member 1")
        expected = list(range(1, max(member_ids) + 1))
        if sorted(member_ids) != expected:
            errors.append(f"{stack_name} members must be consecutive from 1; received {sorted(member_ids)}")
        deployment = "stack" if len(members) > 1 else "standalone"
        for d in members:
            d.deployment_type = deployment
            d.stack_size = len(members)

    if not devices:
        errors.append("At least one valid device is required")
    return devices, errors
