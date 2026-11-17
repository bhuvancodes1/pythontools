from dataclasses import dataclass, asdict
from typing import Optional

@dataclass
class Device:
    input_name: str
    device_type: str
    mac: str
    serial: str
    generated_name: str = ""
    base_role: str = ""
    stack_member: Optional[int] = None
    deployment_type: str = "standalone"
    stack_size: int = 1
    license_service: str = ""
    validation_status: str = "PENDING"
    inventory_status: str = "NOT_STARTED"
    license_status: str = "NOT_STARTED"
    error: Optional[str] = None

    def to_dict(self):
        return asdict(self)
