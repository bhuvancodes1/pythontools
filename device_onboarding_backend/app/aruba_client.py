from typing import Dict, List, Optional
import requests

class ArubaCentralClient:
    def __init__(self, base_url: str, token: str, timeout: int = 30, verify_ssl: bool = True):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.verify_ssl = verify_ssl
        self.session = requests.Session()
        self.session.headers.update({
            "accept": "application/json",
            "authorization": f"Bearer {token}",
            "content-type": "application/json",
        })

    def _request(self, method: str, path: str, **kwargs) -> Dict:
        response = self.session.request(
            method, f"{self.base_url}{path}", timeout=self.timeout,
            verify=self.verify_ssl, **kwargs
        )
        try:
            body = response.json()
        except ValueError:
            body = {"raw": response.text}
        if not response.ok:
            raise RuntimeError(f"HTTP {response.status_code}: {body}")
        return {"status_code": response.status_code, "body": body}

    def get_license_services(self, device_type: str) -> Dict:
        if device_type not in {"iap", "switch"}:
            raise ValueError("device_type must be 'iap' or 'switch'")
        return self._request("GET", "/platform/licensing/v1/services/config", params={"device_type": device_type})

    def add_devices(self, devices: List[Dict[str, str]]) -> Dict:
        payload = [{"mac": d["mac"], "serial": d["serial"]} for d in devices]
        return self._request("POST", "/platform/device_inventory/v1/devices", json=payload)

    def assign_subscription(self, serials: List[str], services: List[str]) -> Dict:
        return self._request("POST", "/platform/licensing/v1/subscriptions/assign", json={
            "serials": serials,
            "services": services,
        })
