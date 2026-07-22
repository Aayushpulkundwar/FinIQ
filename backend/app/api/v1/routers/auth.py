import uuid
from datetime import timedelta
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession


from app.db.session import get_db
from app.repositories.portfolio import PortfolioRepository
from app.schemas.user import UserRegister, UserLogin, TokenResponse, RefreshRequest, TokenRefreshResponse, UserOut
from app.core.security import (
    hash_password, verify_password, create_access_token, create_refresh_token, decode_token
)


router = APIRouter()


@router.post("/register", response_model=UserOut, status_code=status.HTTP_201_CREATED)
async def register(obj_in: UserRegister, db: AsyncSession = Depends(get_db)) -> UserOut:
    """
    Registers a new platform user with safe hashed password storage.
    """
    repo = PortfolioRepository(db)
    
    # 1. Enforce unique emails
    existing = await repo.get_user_by_email(obj_in.email)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A user account with this email address already exists."
        )

    # 2. Hash password & insert record
    user_data = {
        "email": obj_in.email,
        "hashed_password": hash_password(obj_in.password),
        "role": obj_in.role
    }
    
    user = await repo.create_user(user_data)
    await db.commit()
    
    # Log audit event
    await repo.log_audit(
        action="user_registration",
        details=f"Email: {user.email}, Role: {user.role.value}",
        user_id=user.id
    )
    await db.commit()

    return user


@router.post("/login", response_model=TokenResponse)
async def login(credentials: UserLogin, db: AsyncSession = Depends(get_db)) -> TokenResponse:
    """
    Authenticates user credentials and generates access/refresh tokens.
    """
    repo = PortfolioRepository(db)
    
    # 1. Fetch user by email
    user = await repo.get_user_by_email(credentials.email)
    if not user or not verify_password(credentials.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email address or password combination."
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This user account has been deactivated."
        )

    # 2. Generate security tokens
    access = create_access_token(user.id, user.role.value)
    refresh = create_refresh_token(user.id)

    # Log security audit event
    await repo.log_audit(
        action="user_login",
        details=f"Successful login for: {user.email}",
        user_id=user.id
    )
    await db.commit()

    return TokenResponse(
        access_token=access,
        refresh_token=refresh,
        role=user.role.value
    )


@router.post("/refresh", response_model=TokenRefreshResponse)
async def refresh_token(payload: RefreshRequest, db: AsyncSession = Depends(get_db)) -> TokenRefreshResponse:
    """
    Generates a new access token using a valid, non-expired refresh token.
    """
    repo = PortfolioRepository(db)
    
    # 1. Decode refresh token
    decoded = decode_token(payload.refresh_token)
    user_id_str = decoded.get("sub")
    token_type = decoded.get("type")

    if not user_id_str or token_type != "refresh":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token type provided."
        )

    # 2. Fetch and assert user active status
    user = await repo.get_user(uuid.UUID(user_id_str))

    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User account not found")
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User account has been deactivated")

    # 3. Renew access token
    new_access = create_access_token(user.id, user.role.value)
    return TokenRefreshResponse(access_token=new_access)
