import asyncio
import json
from pathlib import Path

from aruba_client import ArubaCentralError, create_aruba_site, extract_site_id
from models import CreateSiteRequest
from site_name_service import build_site_name

INPUT_FILE = Path(__file__).with_name("input.json")

async def main():
    with INPUT_FILE.open("r", encoding="utf-8") as file:
        raw_input = json.load(file)

    request = CreateSiteRequest(**raw_input)
    final_site_name = build_site_name(request)

    payload = {
        "site_name": final_site_name,
        "site_address": request.site_address.model_dump(),
    }

    print(f"Creating Aruba Central site: {final_site_name}")

    try:
        response = await create_aruba_site(payload)
    except ArubaCentralError as exc:
        print(f"FAILED: {exc.message}")
        if exc.response_body:
            print(json.dumps(exc.response_body, indent=2))
        raise SystemExit(1)

    site_id = extract_site_id(response)
    print("SUCCESS: Aruba Central site created.")
    print(f"Site name: {final_site_name}")
    print(f"Site ID: {site_id if site_id else 'Not returned/found in API response'}")
    print("Aruba response:")
    print(json.dumps(response, indent=2))

if __name__ == "__main__":
    asyncio.run(main())
