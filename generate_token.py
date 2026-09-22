import argparse
import datetime
import jwt
from app.core.config import settings
from app.core.security import DOTNET_NAME_IDENTIFIER_CLAIM, DOTNET_ROLE_CLAIM


def generate_token(
    user_id: str = "7742a091-aca8-4e81-9d10-ffb04e49019c",
    role: str = "Admin",
    email: str = "admin@dawwer.com",
    store_id: str | None = None,
    days_valid: int = 365,
) -> str:
    now = datetime.datetime.now(datetime.timezone.utc)
    exp = now + datetime.timedelta(days=days_valid)

    payload = {
        "sub": user_id,
        DOTNET_NAME_IDENTIFIER_CLAIM: user_id,
        "role": role,
        DOTNET_ROLE_CLAIM: role,
        "email": email,
        "iss": settings.JWT_ISSUER,
        "aud": settings.JWT_AUDIENCE,
        "exp": int(exp.timestamp()),
        "iat": int(now.timestamp()),
    }
    if store_id:
        payload["store_id"] = store_id

    return jwt.encode(
        payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate a test JWT token")
    parser.add_argument(
        "--user-id", default="7742a091-aca8-4e81-9d10-ffb04e49019c", help="User ID (UUID)"
    )
    parser.add_argument("--role", default="Admin", help="Role (Admin, User, etc.)")
    parser.add_argument("--email", default="admin@dawwer.com", help="User email")
    parser.add_argument("--store-id", default=None, help="Store ID (optional)")
    parser.add_argument("--days", type=int, default=365, help="Validity in days")

    args = parser.parse_args()
    token = generate_token(
        user_id=args.user_id,
        role=args.role,
        email=args.email,
        store_id=args.store_id,
        days_valid=args.days,
    )
    print("\n--- Generated JWT Token ---")
    print(token)
    print("\nToken details:")
    print(f"User ID: {args.user_id}")
    print(f"Role   : {args.role}")
    print(f"Email  : {args.email}")
    print(f"Expiry : {args.days} days")
