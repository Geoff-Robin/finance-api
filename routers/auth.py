"""
Authentication router servicing endpoints for user provisioning and session initialization.
"""
from fastapi import APIRouter, Depends, HTTPException, status, Request
from async_fastapi_jwt_auth import AuthJWT
from sqlalchemy.ext.asyncio import AsyncSession
from schemas import UserCreate, UserLogin
from user_dal import UserDAL
from utils import hash_password, verify_password
from dependencies import get_db, limiter

router = APIRouter(tags=["Authentication"])

@router.post('/register', status_code=status.HTTP_201_CREATED)
@limiter.limit("5/minute")
async def register(
    request: Request,
    user_data: UserCreate,
    db: AsyncSession = Depends(get_db),
    Authorize: AuthJWT = Depends()
):
    """
    Registers a new standard user or admin depending on payload specifications.

    Args:
        request (Request): The incoming request mapped for rate limiting.
        user_data (UserCreate): The schema holding parsed email and raw password.
        db (AsyncSession): Scoped database session chunk.
        Authorize (AuthJWT): Security context.

    Raises:
        HTTPException: Raises 400 if the provided email matches an existing account.

    Returns:
        dict: Yields a newly minted identity access token upon successful persistence.
    """
    dal = UserDAL(db)
    existing_user = await dal.get_user_by_email(user_data.email)
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered"
        )
    hashed = hash_password(user_data.password)
    new_user = await dal.create_user(
        email=user_data.email,
        hashed_password=hashed,
        role=user_data.role
    )
    
    access_token = await Authorize.create_access_token(subject=str(new_user.id))
    return {"access_token": access_token, "user_id": new_user.id}

@router.post("/login")
@limiter.limit("5/minute")
async def login(
    request: Request,
    user_data: UserLogin,
    db: AsyncSession = Depends(get_db),
    Authorize: AuthJWT = Depends()
):
    """
    Grants system authorization to existing legitimate users via JWT emission.

    Args:
        request (Request): Raw incoming request object for limiting tracking.
        user_data (UserLogin): Extracted schema holding the email and raw plaintext payload.
        db (AsyncSession): Database transactional context block.
        Authorize (AuthJWT): Security middleware provider.

    Raises:
        HTTPException: Will emit 401 if credentials are invalid or missing.

    Returns:
        dict: A payload wrapper holding the active access_token spanning the session lifecycle.
    """
    dal = UserDAL(db)
    user = await dal.get_user_by_email(user_data.email)

    if not user or not verify_password(user_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password"
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is inactive"
        )
        
    access_token = await Authorize.create_access_token(subject=str(user.id))
    return {"access_token": access_token, "user_id": user.id}
