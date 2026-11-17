# Aruba Central Device Onboarding Backend

Python backend logic for:

1. Validating store and device input.
2. Generating switch and AP names.
3. Detecting standalone switches and stacks.
4. Adding devices to Aruba Central inventory using MAC and serial.
5. Mapping `switch` and `iap` devices to separate license services.
6. Assigning subscriptions in batches.
7. Writing a JSON execution report.

## Security first

Do not put an Aruba access token in Python or `input.json`. Copy `.env.example` to `.env` and add a newly generated token. Any token previously pasted into chat, email, source control, or documentation should be revoked and rotated.

## Setup

```bash
python -m venv .venv
```

Windows PowerShell:

```powershell
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
```

Linux/macOS:

```bash
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Edit `.env` and `config/input.json`.

## Check available license services

```bash
python main.py --list-services switch
python main.py --list-services iap
```

Copy the required service identifiers into `global_config.license_services` in `config/input.json`.

## Dry run

Dry run is the default and makes no API calls:

```bash
python main.py --input config/input.json --output onboarding_report.json
```

## Execute live onboarding

```bash
python main.py --input config/input.json --execute --output onboarding_report.json
```

## Input naming

- `M1-ST1-1` becomes logical name `JS5354-M1-ST1`, member 1.
- If only member 1 exists, it is classified as standalone.
- If members 1 and 2 exist, both use logical name `JS5354-M1-ST1` and are classified as a two-member stack.
- `AP1` or `AP01` becomes `JS5354-AP01`.

## Important limitation

The supplied inventory and licensing APIs do not set the final Aruba hostname. `generated_name` is prepared and reported for a later group/template/device-variable workflow.

## Tests

```bash
pytest -q
```
