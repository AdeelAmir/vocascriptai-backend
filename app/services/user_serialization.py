from app.models.subscription import Subscription
from app.models.user import User
from app.schemas.user import UserResponse
from app.services.subscriptions import subscription_values


def build_user_response(user: User, subscription: Subscription | None) -> UserResponse:
    return UserResponse.model_validate(
        {
            "id": user.id,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "email": user.email,
            "role": user.role,
            "is_verified": user.is_verified,
            "is_active": user.is_active,
            "created_at": user.created_at,
            **subscription_values(subscription),
        }
    )

