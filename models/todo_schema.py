from pydantic import BaseModel
from typing import Optional

class TodoSchema(BaseModel):
    user_id: str
    task: str
    status: Optional[str] = "pending"
