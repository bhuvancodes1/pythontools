from collections import defaultdict
from datetime import datetime, timezone
from typing import Dict, List, Optional
from .aruba_client import ArubaCentralClient
from .models import Device
from .validation import prepare_devices


def chunks(items: List[Device], size: int):
    for i in range(0, len(items), size):
        yield items[i:i + size]


def run_onboarding(payload: Dict, client: Optional[ArubaCentralClient], dry_run: bool = True) -> Dict:
    devices, errors = prepare_devices(payload)
    report = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "dry_run": dry_run,
        "validation_errors": errors,
        "devices": [d.to_dict() for d in devices],
        "batches": [],
        "summary": {},
    }
    if errors:
        report["summary"] = {"status": "VALIDATION_FAILED", "total": len(devices)}
        return report

    batch_size = int(payload.get("global_config", {}).get("batch_size", 25))
    batch_size = max(1, min(batch_size, 100))
    continue_on_error = bool(payload.get("global_config", {}).get("continue_on_error", True))

    if dry_run:
        for d in devices:
            d.inventory_status = "WOULD_ADD"
            d.license_status = "WOULD_ASSIGN"
        report["devices"] = [d.to_dict() for d in devices]
        report["summary"] = {"status": "DRY_RUN_OK", "total": len(devices)}
        return report

    invalid_services = sorted({d.license_service for d in devices if d.license_service.startswith("REPLACE_WITH_")})
    if invalid_services:
        report["validation_errors"] = [f"Replace placeholder license service: {value}" for value in invalid_services]
        report["summary"] = {"status": "VALIDATION_FAILED", "total": len(devices)}
        return report

    if client is None:
        raise ValueError("API client is required when dry_run is false")

    successful: List[Device] = []
    for batch in chunks(devices, batch_size):
        info = {"operation": "inventory_add", "serials": [d.serial for d in batch]}
        try:
            result = client.add_devices([{"mac": d.mac, "serial": d.serial} for d in batch])
            info["result"] = result
            for d in batch:
                d.inventory_status = "ADDED"
                successful.append(d)
        except Exception as exc:
            info["error"] = str(exc)
            for d in batch:
                d.inventory_status = "FAILED"
                d.error = str(exc)
            if not continue_on_error:
                report["batches"].append(info)
                break
        report["batches"].append(info)

    groups = defaultdict(list)
    for d in successful:
        groups[(d.device_type, d.license_service)].append(d)
    for (device_type, service), group in groups.items():
        for batch in chunks(group, batch_size):
            info = {
                "operation": "license_assign", "device_type": device_type,
                "service": service, "serials": [d.serial for d in batch]
            }
            try:
                result = client.assign_subscription([d.serial for d in batch], [service])
                info["result"] = result
                for d in batch:
                    d.license_status = "ASSIGNED"
            except Exception as exc:
                info["error"] = str(exc)
                for d in batch:
                    d.license_status = "FAILED"
                    d.error = str(exc)
            report["batches"].append(info)

    completed = sum(1 for d in devices if d.inventory_status == "ADDED" and d.license_status == "ASSIGNED")
    report["devices"] = [d.to_dict() for d in devices]
    report["summary"] = {
        "status": "COMPLETED" if completed == len(devices) else "PARTIAL_FAILURE",
        "total": len(devices), "completed": completed,
        "failed": len(devices) - completed,
    }
    return report
