import json
from infoblox_precheck import run_infoblox_precheck

INPUT_FILE = "input.json"
OUTPUT_FILE = "output.json"


def main():
    with open(INPUT_FILE, "r", encoding="utf-8") as file:
        inputs = json.load(file)

    required = ["store_id", "vlan1_ip", "vlan2_ip"]
    missing = [key for key in required if not inputs.get(key)]
    if missing:
        raise ValueError(f"Missing required input(s): {', '.join(missing)}")

    result = run_infoblox_precheck(
        store_id=inputs["store_id"],
        vlan1_ip=inputs["vlan1_ip"],
        vlan2_ip=inputs["vlan2_ip"],
    )

    with open(OUTPUT_FILE, "w", encoding="utf-8") as file:
        json.dump(result, file, indent=2)

    print(json.dumps(result, indent=2))
    print(f"\nResult saved to {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
