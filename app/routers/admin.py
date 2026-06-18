import os
import hmac
from fastapi import APIRouter, HTTPException, Header
from pydantic import BaseModel, field_validator

from app.db.models import User, CreditTransaction

router = APIRouter()


class AddCreditsRequest(BaseModel):
    user_id: str
    amount: int
    description: str = "Manual credit adjustment"

    @field_validator("amount")
    @classmethod
    def amount_must_be_nonzero(cls, v: int) -> int:
        if v == 0:
            raise ValueError("amount must be non-zero")
        return v


@router.post("/admin/credits")
def add_credits(req: AddCreditsRequest, x_admin_key: str | None = Header(default=None)):
    admin_secret = os.getenv("ADMIN_SECRET", "")
    supplied = x_admin_key or ""
    # Timing-safe comparison to prevent secret enumeration
    if not admin_secret or not hmac.compare_digest(supplied.encode(), admin_secret.encode()):
        raise HTTPException(status_code=403, detail="Forbidden")

    user = User.objects(user_id=req.user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    User.objects(user_id=req.user_id).update_one(inc__credits=req.amount)
    CreditTransaction(
        user_id=req.user_id,
        amount=req.amount,
        type="purchase",
        description=req.description,
    ).save()

    user.reload()
    return {"user_id": req.user_id, "credits": user.credits}
