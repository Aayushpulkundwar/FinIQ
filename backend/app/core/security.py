import uuid
from datetime import datetime, timedelta
from typing import List, Optional
import jwt
import bcrypt
from fastapi import Depends, HTTPException, status, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession
from loguru import logger

from app.core.config import settings
from app.db.session import get_db
from app.models.user import User, UserRole
from app.repositories.portfolio import PortfolioRepository
from app.core.cache import cache


# Standard Security Schemes
security_scheme = HTTPBearer()


# ── Password Hashing ──────────────────────────────────────────────────────────

def hash_password(password: str) -> str:
    """Hash raw password text using bcrypt."""
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify raw password matches stored bcrypt hash."""
    return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))


# ── JWT Operations ────────────────────────────────────────────────────────────

def create_access_token(user_id: uuid.UUID, role: str, expires_delta: Optional[timedelta] = None) -> str:
    """Generate JWT Access Token containing user metadata."""
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)

    payload = {
        "sub": str(user_id),
        "role": role,
        "exp": expire,
        "type": "access"
    }
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def create_refresh_token(user_id: uuid.UUID, expires_delta: Optional[timedelta] = None) -> str:
    """Generate JWT Refresh Token for credential renewal."""
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(days=7) # Refresh token standard TTL 7 days

    payload = {
        "sub": str(user_id),
        "exp": expire,
        "type": "refresh"
    }
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def decode_token(token: str) -> dict:
    """Decode and validate a JWT token payload."""
    try:
        payload = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token has expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid authorization token")


# ── Security Dependency Injection ─────────────────────────────────────────────

async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security_scheme),
    db: AsyncSession = Depends(get_db)
) -> User:
    """FastAPI Dependency retrieving active User profile from JWT bearer headers."""
    payload = decode_token(credentials.credentials)
    user_id_str = payload.get("sub")
    token_type = payload.get("type")

    if not user_id_str or token_type != "access":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token type credentials")

    repo = PortfolioRepository(db)
    user = await repo.get_user(uuid.UUID(user_id_str))
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User account not found")
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User account is deactivated")

    return user


class RoleChecker:
    """RBAC Dependency asserting the active user role belongs to allowed groups."""
    def __init__(self, allowed_roles: List[UserRole]):
        self.allowed_roles = [r.value if isinstance(r, UserRole) else r for r in allowed_roles]

    def __call__(self, current_user: User = Depends(get_current_user)) -> User:
        user_role = current_user.role.value if isinstance(current_user.role, UserRole) else current_user.role
        if user_role not in self.allowed_roles:
            logger.warning(f"Access denied for user {current_user.id} with role {user_role}. Required: {self.allowed_roles}")
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="User does not have sufficient permissions to execute this request"
            )
        return current_user


# ── Redis Rate Limiting ───────────────────────────────────────────────────────

class RateLimiter:
    """
    FastAPI dependency enforcing dynamic rate limits based on Client IP address.
    """
    def __init__(self, calls: int = 100, period: int = 60):
        self.calls = calls
        self.period = period

    async def __call__(self, request: Request):
        if not cache.enabled or not cache.client:
            # Bypass limit if Redis caching is disabled/offline
            return

        # Extract Client IP from headers
        ip = request.client.host if request.client else "unknown_ip"
        endpoint = request.url.path
        key_hash = cache.hash_key(f"{ip}:{endpoint}")
        redis_key = f"rate_limit:{key_hash}"

        try:
            current = await cache.client.get(redis_key)
            if current is not None:
                current_calls = int(current)
                if current_calls >= self.calls:
                    logger.warning(f"Rate limit exceeded for IP: {ip} on route: {endpoint}")
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail="Rate limit exceeded. Please try again later."
                    )
                await cache.client.incr(redis_key)
            else:
                # Set initial counter with TTL expiration
                await cache.client.set(redis_key, 1, ex=self.period)
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"RateLimiter check failed: {e}")
            # Resiliently pass request if rate-limiter service encounters errors
            return
