from typing import Optional
from pydantic import BaseModel


class TokenPayload(BaseModel):
    user_id: str
    role: Optional[str] = None
    store_id: Optional[str] = None
