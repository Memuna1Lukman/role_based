from typing import Optional

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_hostname:str
    database_name: str
    database_username: str
    database_password:str
    database_port: str
    database_url: Optional[str] = None
    secret_key: str
    algorithm: str
    access_token_expire_minutes:int
    refresh_token_expire_days: int = 30
    cookie_secure: bool = False
    allowed_origins: str = "http://localhost:5173,http://localhost:3000"
    model_config = {'env_file': '.env'}






settings = Settings()
