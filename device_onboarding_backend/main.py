import argparse
import json
import os
import sys
from pathlib import Path
from dotenv import load_dotenv
from app.aruba_client import ArubaCentralClient
from app.service import run_onboarding


def load_json(path: str):
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def main():
    parser = argparse.ArgumentParser(description="Validate and onboard Aruba Central devices")
    parser.add_argument("--input", default="config/input.json", help="Input JSON file")
    parser.add_argument("--execute", action="store_true", help="Perform live API calls; otherwise dry-run")
    parser.add_argument("--output", default="onboarding_report.json", help="Report JSON file")
    parser.add_argument("--list-services", choices=["iap", "switch"], help="List available services and exit")
    args = parser.parse_args()

    load_dotenv()
    token = os.getenv("ARUBA_ACCESS_TOKEN", "")
    base_url = os.getenv("ARUBA_BASE_URL", "https://eu-apigw.central.arubanetworks.com")
    timeout = int(os.getenv("REQUEST_TIMEOUT_SECONDS", "30"))
    verify_ssl = os.getenv("VERIFY_SSL", "true").lower() == "true"

    client = None
    if args.execute or args.list_services:
        if not token or token == "replace_with_access_token":
            print("ARUBA_ACCESS_TOKEN is missing. Copy .env.example to .env and add a valid token.", file=sys.stderr)
            return 2
        client = ArubaCentralClient(base_url, token, timeout, verify_ssl)

    if args.list_services:
        print(json.dumps(client.get_license_services(args.list_services), indent=2))
        return 0

    payload = load_json(args.input)
    report = run_onboarding(payload, client, dry_run=not args.execute)
    Path(args.output).write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report["summary"], indent=2))
    print(f"Report written to {args.output}")
    return 1 if report.get("validation_errors") else 0

if __name__ == "__main__":
    raise SystemExit(main())
