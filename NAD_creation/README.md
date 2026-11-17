# ClearPass Network Device Creator

Creates a new ClearPass device using an existing device as a reference.

## Workflow
1. GET reference device details.
2. Derive the new name by replacing the first hyphen-delimited token with the new store number.
3. Replace the old store number in the description when it is present.
4. Build the new IP using the first three octets of the VLAN 20 gateway and the last octet of the reference device IP.
5. POST the new device. The POST body intentionally excludes `nad_groups` for ClearPass 6.11.16.
6. For each `nad_groups` entry on the reference device, GET that group and append the new device IP to its existing list-format value using PATCH. Existing members are retained and duplicates are avoided.

## Setup
Use Python 3.9+.

Windows PowerShell:
```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Linux/macOS:
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Edit `.env`:
- `BASE_URL`: ClearPass hostname/base URL, without `/api`
- `ACCESS_TOKEN`: API bearer token
- `RADIUS_SECRET`: RADIUS secret for the new device
- `TACACS_SECRET`: TACACS secret for the new device
- `VERIFY_TLS=true`: keep enabled for production
- `REQUEST_TIMEOUT=30`

Never commit `.env` or share your access token/secrets.

## Input CSV
Required columns:
```csv
reference_device_name,new_store_number,new_store_name,vlan20_gateway_ip
JS4545-M1-ST1,TS0001,Test Site name,172.16.1.1
```
Add one row per device to create.

## Run
First inspect the planned work:
```bash
python main.py --dry-run
```
Then execute:
```bash
python main.py
```
For another CSV:
```bash
python main.py --input another_input.csv --dry-run
python main.py --input another_input.csv
```

## Safeguards / notes
- Refuses to POST if the derived device name already exists.
- Preserves existing list-group members and avoids adding the same IP twice.
- Only list-format NAD groups are updated; other formats are skipped and reported.
- If POST succeeds but a group PATCH fails, the device may already have been created. Check ClearPass before retrying.
- The generated IP must be checked for availability/reservation in the target VLAN before production use.
- Copies vendor name/ID, CoA settings, RadSec setting, `Site_Schema`, and `Device Vendor` when available on the reference. Sets `Location` to the new store name.
- Group membership updates GET the current value then PATCH the complete combined value. Concurrent updates to the same group could race; serialize runs for the same group.
