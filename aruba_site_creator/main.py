from fastapi import FastAPI, HTTPException
from aruba_client import ArubaCentralError, create_aruba_site, extract_site_id
from models import CreateSiteRequest, CreateSiteResponse
from site_name_service import build_site_name

app = FastAPI(title="Aruba Central Site Creator", version="1.0.0")

@app.get("/health")
async def health_check():
    return {"success": True, "message": "Aruba site creator backend is running."}

@app.post("/api/sites", response_model=CreateSiteResponse)
async def create_site(request: CreateSiteRequest):
    try:
        final_site_name = build_site_name(request)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    payload = {"site_name": final_site_name, "site_address": request.site_address.model_dump()}
    try:
        aruba_response = await create_aruba_site(payload)
    except ArubaCentralError as exc:
        raise HTTPException(status_code=exc.status_code, detail={"success": False, "message": exc.message, "site_name": final_site_name, "aruba_response": exc.response_body}) from exc
    site_id = extract_site_id(aruba_response)
    message = f"Site '{final_site_name}' was created successfully in Aruba Central."
    if site_id:
        message += f" Site ID: {site_id}"
    else:
        message += " Site ID was not found in the API response."
    return CreateSiteResponse(success=True, message=message, site_name=final_site_name, site_id=site_id, aruba_response=aruba_response)
