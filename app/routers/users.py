from fastapi import APIRouter
from pydantic import BaseModel
from app.db.models import User

router = APIRouter()


class UpsertUserRequest(BaseModel):
    user_id: str
    email: str


@router.post("/users")
def sync_user(req: UpsertUserRequest):
    user = User.objects(user_id=req.user_id).first()
    if not user:
        user = User(user_id=req.user_id, email=req.email)
        user.save()
    return {"user_id": user.user_id, "email": user.email}
