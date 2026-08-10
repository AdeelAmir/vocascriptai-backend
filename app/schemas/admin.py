import uuid
from datetime import datetime
from pydantic import BaseModel, ConfigDict

class AdminLogin(BaseModel):
    email: str
    password: str
    
class AdminResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    first_name: str
    last_name: str
    email: str
    role: int
    is_active: bool
    created_at: datetime

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"

class AdminLoginResponse(BaseModel):
    admin: AdminResponse
    token: TokenResponse
