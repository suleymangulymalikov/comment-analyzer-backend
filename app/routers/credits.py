from fastapi import APIRouter, HTTPException, Header

from app.db.models import User, CreditTransaction

router = APIRouter()


@router.get("/credits")
def get_credits(x_user_id: str | None = Header(default=None)):
    if not x_user_id:
        raise HTTPException(status_code=401, detail="Missing x-user-id header")

    user = User.objects(user_id=x_user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    transactions = CreditTransaction.objects(user_id=x_user_id).order_by("-created_at").limit(10)

    return {
        "balance": user.credits,
        "transactions": [
            {
                "amount": t.amount,
                "type": t.type,
                "description": t.description,
                "created_at": t.created_at,
            }
            for t in transactions
        ],
    }
