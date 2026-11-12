# Infoblox Store Staging Pre-check

This folder contains the initial Store Staging pre-check function.

## What it does

1. Reads store ID, VLAN1 and VLAN2 from `input.json`.
2. Connects to Infoblox using Basic Authentication from `.env`.
3. Retrieves Infoblox network objects with `network`, `network_view`, `comment`, `extattrs`, and `options`.
4. Filters results using `extattrs.Site.value == store_id`.
5. Validates VLAN1 against VLAN1 Primary only.
6. Validates VLAN2 against VLAN2.
7. VLAN validation compares the first three IP octets.
8. Displays all returned network scopes for the requested store.
9. Reads gateways dynamically from the DHCP `routers` option.
10. Marks a scope `Present - Gateway option missing` when there is no router option.
11. Writes the result to `output.json`.

## Folder structure

```text
infoblox_precheck/
├── .env
├── .gitignore
├── README.md
├── input.json
├── infoblox_precheck.py
├── requirements.txt
└── run.py
```

## Configuration

Edit `.env`:

```env
INFOBLOX_BASE_URL=https://your-infoblox-server
INFOBLOX_WAPI_VERSION=v2.12
INFOBLOX_USERNAME=your_username
INFOBLOX_PASSWORD=your_password
INFOBLOX_NETWORK_VIEW=default
INFOBLOX_VERIFY_SSL=true
INFOBLOX_TIMEOUT=30
INFOBLOX_MAX_RESULTS=1000
```

Keep `.env` private. It is intentionally included in `.gitignore`.

## Runtime input

Edit `input.json` before running:

```json
{
  "store_id": "JS5285",
  "vlan1_ip": "10.189.248.xx",
  "vlan2_ip": "10.201.248.xx"
}
```

The VLAN IP values can use `xx` or an actual last octet. Validation uses the first three octets either way.

## Run

Requires Python 3.10 or newer.

From this folder:

```bash
python run.py
```

The program prints the result and creates `output.json`.

## Later application integration

The UI/API can directly import:

```python
from infoblox_precheck import run_infoblox_precheck
```

and call:

```python
result = run_infoblox_precheck(
    store_id="JS5285",
    vlan1_ip="10.189.248.xx",
    vlan2_ip="10.201.248.xx"
)
```

This keeps the Infoblox validation logic separate from the future FastAPI/React application layer.
