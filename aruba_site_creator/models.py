from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field, model_validator

class SiteIdentifier(str, Enum):
    SAINSBURYS = "JS"
    ARGOS = "AR"
    DEPOT = "DP"
    IC = "IC"
    BC = "BC"

class SiteAddress(BaseModel):
    address: str = Field(..., min_length=1)
    city: str = Field(..., min_length=1)
    state: str = Field(..., min_length=1)
    country: str = Field(default="United Kingdom", min_length=1)
    zipcode: str = Field(..., min_length=1)

class CreateSiteRequest(BaseModel):
    store_identifier: Optional[SiteIdentifier] = None
    store_number: Optional[str] = None
    store_name: Optional[str] = None
    site_name: Optional[str] = None
    add_pre_staging_tag: bool = True
    region: Optional[str] = None
    site_address: SiteAddress

    @model_validator(mode="after")
    def validate_site_name_inputs(self):
        direct = bool(self.site_name and self.site_name.strip())
        generated = all([self.store_identifier, self.store_number and self.store_number.strip(), self.store_name and self.store_name.strip()])
        if direct and generated:
            raise ValueError("Provide either site_name directly or store_identifier, store_number and store_name.")
        if not direct and not generated:
            raise ValueError("Provide site_name directly, or all of store_identifier, store_number and store_name.")
        return self

class CreateSiteResponse(BaseModel):
    success: bool
    message: str
    site_name: str
    site_id: Optional[str] = None
    aruba_response: Optional[dict] = None
