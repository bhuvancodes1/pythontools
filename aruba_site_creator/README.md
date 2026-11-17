# Aruba Central Site Creator

FastAPI backend plus a simple input-file test runner for creating staging sites in Aruba Central.

## Configure credentials
Copy `.env.example` to `.env` and set a valid `ARUBA_ACCESS_TOKEN`.

## Test using input.json
1. Edit `input.json` with the store/site details.
2. Install dependencies: `pip install -r requirements.txt`
3. Run: `python create_site_from_input.py`

The script builds the final site name, calls Aruba Central, and prints the returned Site ID and API response.

## FastAPI mode
Run: `uvicorn main:app --reload`

Swagger UI: `http://127.0.0.1:8000/docs`

POST `/api/sites` accepts the same input fields as `input.json`. Later the frontend can send these fields directly instead of using the file.
