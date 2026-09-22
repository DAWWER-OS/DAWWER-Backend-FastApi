from typing import Any, List, Optional
from pydantic import BaseModel, ConfigDict, Field


class TokenPayload(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    user_id: str
    role: Optional[str] = None
    roles: List[str] = Field(default_factory=list)
    store_id: Optional[str] = None
    email: Optional[str] = None

    def __getitem__(self, item: str) -> Any:
        try:
            return getattr(self, item)
        except AttributeError:
            raise KeyError(item)

    def get(self, item: str, default: Any = None) -> Any:
        return getattr(self, item, default)

    def is_admin(self) -> bool:
        if self.role and self.role.lower() in ("admin", "superadmin"):
            return True
        return any(r.lower() in ("admin", "superadmin") for r in self.roles)
