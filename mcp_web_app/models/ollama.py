from typing import List, Dict, Any, Optional
from pydantic import BaseModel

class OllamaTagDetail(BaseModel):
    name: str
    modified_at: str # Example: "2023-11-20T15:03:04.601790754-08:00"
    size: int # Example: 4109866330
    digest: str
    details: Optional[Dict[str, Any]] = None

class OllamaTagsResponse(BaseModel):
    models: List[OllamaTagDetail]

class OllamaModelListResponse(BaseModel):
    success: bool
    message: Optional[str] = None
    models: Optional[List[str]] = None
    details: Optional[str] = None 