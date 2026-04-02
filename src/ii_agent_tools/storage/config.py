from typing import Literal, Optional
from pydantic import BaseModel


class StorageConfig(BaseModel):
    storage_provider: Literal["gcs"] = "gcs"
    gcs_bucket_name: Optional[str] = None
    gcs_project_id: Optional[str] = None
