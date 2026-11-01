
import os
from datetime import datetime, timedelta, timezone

import jwt
from dotenv import load_dotenv
from fastapi import Depends, HTTPException
from fastapi.security import (
    HTTPBearer,
    HTTPAuthorizationCredentials
)
from pwdlib import PasswordHash

from backend.database import get_db_connection


load_dotenv()

password_hash = PasswordHash.recommended()

security = HTTPBearer(auto_error=False)

JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY")
JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60


# ---------------- PASSWORD HASHING ----------------

def hash_password(password: str) -> str:
    return password_hash.hash(password)


def verify_password(password: str, hashed_password: str) -> bool:
    try:
        return password_hash.verify(password, hashed_password)
    except Exception:
        return False


# ---------------- JWT TOKEN GENERATION ----------------

def create_access_token(user: dict) -> str:
    if not JWT_SECRET_KEY:
        raise RuntimeError("JWT_SECRET_KEY is missing from .env")

    expiration = datetime.now(timezone.utc) + timedelta(
        minutes=ACCESS_TOKEN_EXPIRE_MINUTES
    )

    payload = {
        "sub": str(user["user_id"]),
        "email": user["email"],
        "role": user["role"],
        "exp": expiration
    }

    token = jwt.encode(
        payload,
        JWT_SECRET_KEY,
        algorithm=JWT_ALGORITHM
    )

    return token


# ---------------- CURRENT USER AUTHENTICATION ----------------

def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    if credentials is None:
        raise HTTPException(
            status_code=401,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"}
        )

    if not JWT_SECRET_KEY:
        raise HTTPException(
            status_code=500,
            detail="JWT secret is not configured"
        )

    try:
        payload = jwt.decode(
            credentials.credentials,
            JWT_SECRET_KEY,
            algorithms=[JWT_ALGORITHM]
        )

        user_id = int(payload["sub"])

    except (jwt.InvalidTokenError, KeyError, ValueError, TypeError):
        raise HTTPException(
            status_code=401,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"}
        )

    connection = None
    cursor = None

    try:
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)

        cursor.execute(
            """
            SELECT user_id, name, email, role
            FROM users
            WHERE user_id = %s
            """,
            (user_id,)
        )

        user = cursor.fetchone()

        if not user:
            raise HTTPException(
                status_code=401,
                detail="User not found"
            )

        return user

    except HTTPException:
        raise

    except Exception as error:
        print("Authentication database error:", error)

        raise HTTPException(
            status_code=500,
            detail="Unable to verify authenticated user"
        )

    finally:
        if cursor:
            cursor.close()

        if connection:
            connection.close()


# ---------------- ROLE-BASED AUTHORIZATION ----------------

def require_roles(*allowed_roles):

    def role_checker(
        user: dict = Depends(get_current_user)
    ):
        if user["role"] not in allowed_roles:
            raise HTTPException(
                status_code=403,
                detail="You do not have permission to access this resource"
            )

        return user

    return role_checker
