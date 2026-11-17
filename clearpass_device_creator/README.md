# ClearPass Network Device Creator

Creates a new ClearPass network device from a reference device, with a **preview and explicit approval gate** before any write operation.

## Workflow
1. Read a row from `input.csv`.
2. GET the reference network device.
3. Derive the new name, description, IP and attributes.
4. GET each inherited NAD group and calculate the proposed membership while retaining existing members.
5. Print the proposed device POST body and NAD group changes. Save a redacted JSON preview under `previews/`.
6. In normal interactive mode, require the user to type `CREATE`.
7. Re-check that group memberships have not changed since the preview.
8. POST the new device, then PATCH each supported list-format NAD group.

The device POST body intentionally excludes `nad_groups`. Group membership is updated separately, matching the ClearPass 6.11.16 behavior established during testing.

## Setup
Python 3.9+ is recommended.

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

Configure `.env`:
```dotenv
BASE_URL=https://your-clearpass-hostname
ACCESS_TOKEN=your_bearer_token
RADIUS_SECRET=your_radius_secret
TACACS_SECRET=your_tacacs_secret
VERIFY_TLS=true
REQUEST_TIMEOUT=30
```

Do not commit `.env` or share your token/secrets. Keep TLS verification enabled in production.

## Input CSV
Required header and example:
```csv
reference_device_name,new_store_number,new_store_name,vlan20_gateway_ip
JS4545-M1-ST1,TS0001,Test Site name,172.16.1.1
```
Add one row for each device.

## Run safely
First create a preview only:
```bash
python main.py --dry-run
```
This performs GET requests and writes `previews/TS0001-M1-ST1_preview.json`. It does not send POST or PATCH.

Then run interactively:
```bash
python main.py
```
The script displays the proposed device body and each NAD group's current/proposed members. Type exactly `CREATE` to proceed. Any other response cancels the operation for that row.

Use a different CSV:
```bash
python main.py --input another_input.csv
```

`--yes` skips the interactive confirmation and should only be used when an upstream workflow has already presented the preview and obtained explicit approval:
```bash
python main.py --yes
```

Choose another preview directory:
```bash
python main.py --preview-dir review_files
```

## Preview file and credential handling
The preview JSON contains:
- Proposed POST endpoint and request body
- Proposed new device name, IP and attributes
- NAD group name and format
- Existing group members
- Proposed group members and complete PATCH value

RADIUS and TACACS secrets are masked in the terminal and preview JSON. They are loaded from `.env` only when the actual POST payload is sent. Do not log or display the unredacted payload.

## Safeguards and limitations
- Duplicate device names are rejected before creation.
- Existing list-format group members are retained; the new IP is appended only if absent.
- Unsupported NAD group formats are displayed and skipped.
- Before POST, the script re-GETs the groups and aborts if membership changed since the preview. This prevents applying an outdated preview.
- The script does not test whether the derived IP is free. Verify IP availability/reservation before production execution.
- If POST succeeds but a subsequent PATCH fails, the device may already exist. Check ClearPass before retrying.
- Run jobs serially when they affect the same NAD groups. A concurrent update after the final verification and before PATCH is still a possible race; use operational locking if multiple automation workers may update the same group.
- A preview is a proposed change record, not proof that the change was applied. Check the final API responses and ClearPass state.
