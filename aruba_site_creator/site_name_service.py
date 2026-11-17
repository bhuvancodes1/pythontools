import re
from models import CreateSiteRequest

PRE_STAGING_TAG = "Pre Staging not in Live"

def clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()

def clean_site_name(site_name: str) -> str:
    site_name = clean_text(site_name)
    suffix = re.compile(rf"\s*-\s*{re.escape(PRE_STAGING_TAG)}\s*$", re.IGNORECASE)
    return suffix.sub("", site_name).strip()

def validate_store_number(store_number: str) -> str:
    value = clean_text(store_number)
    if not value.isdigit():
        raise ValueError("Store number must contain digits only.")
    if len(value) > 4:
        raise ValueError("Store number cannot contain more than four digits.")
    return value.zfill(4)

def build_site_name(request: CreateSiteRequest) -> str:
    if request.site_name:
        base = clean_site_name(request.site_name)
    else:
        base = f"{request.store_identifier.value}{validate_store_number(request.store_number)} {clean_text(request.store_name)}"
    return f"{base} - {PRE_STAGING_TAG}" if request.add_pre_staging_tag else base
