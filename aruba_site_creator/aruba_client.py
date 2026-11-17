import os
from typing import Any
import httpx
from dotenv import load_dotenv

load_dotenv()
ARUBA_BASE_URL = os.getenv("ARUBA_BASE_URL", "https://eu-apigw.central.arubanetworks.com")
ARUBA_ACCESS_TOKEN = os.getenv("ARUBA_ACCESS_TOKEN")
CREATE_SITE_ENDPOINT = "/central/v2/sites"

class ArubaCentralError(Exception):
    def __init__(self, message: str, status_code: int = 500, response_body: Any = None):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.response_body = response_body

def extract_site_id(data: dict):
    keys = ["site_id", "siteId", "id"]
    for key in keys:
        if data.get(key) is not None:
            return str(data[key])
    for obj in [data.get("site"), data.get("data"), data.get("result")]:
        if isinstance(obj, dict):
            for key in keys:
                if obj.get(key) is not None:
                    return str(obj[key])
    return None

async def create_aruba_site(payload: dict) -> dict:
    if not ARUBA_ACCESS_TOKEN:
        raise ArubaCentralError("ARUBA_ACCESS_TOKEN is not configured in the environment.", 500)
    url = f"{ARUBA_BASE_URL.rstrip('/')}{CREATE_SITE_ENDPOINT}"
    headers = {"Authorization": f"Bearer {ARUBA_ACCESS_TOKEN}", "Content-Type": "application/json", "Accept": "application/json"}
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(url, headers=headers, json=payload)
    except httpx.TimeoutException as exc:
        raise ArubaCentralError("Aruba Central API request timed out.", 504) from exc
    except httpx.RequestError as exc:
        raise ArubaCentralError(f"Unable to connect to Aruba Central: {exc}", 502) from exc
    try:
        data = response.json()
    except ValueError:
        data = {"raw_response": response.text}
    if response.status_code not in (200, 201, 202):
        msg = data.get("message") or data.get("error") or "Aruba Central rejected the site creation request."
        raise ArubaCentralError(str(msg), response.status_code, data)
    return data
