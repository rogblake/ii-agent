from pydantic import BaseModel


class DatabaseConfig(BaseModel):
    neon_db_api_key: str | None = None
