"""
Authentication router — user registration and login.

Rate limits:
    - POST /register: 5 requests/minute per IP
    - POST /login:    5 requests/minute per IP
"""
from fastapi import APIRouter, Depends, HTTPException, status, Request
from async_fastapi_jwt_auth import AuthJWT
from sqlalchemy.ext.asyncio import AsyncSession
from schemas import UserCreate, UserLogin
from user_dal import UserDAL
from utils import hash_password, verify_password
from dependencies import get_db, limiter

router = APIRouter(tags=["Authentication"])

_COMMON_ERRORS = {
    429: {"description": "Rate limit exceeded — too many requests from this IP."},
    422: {"description": "Validation error — request body does not match the expected schema."},
}


@router.post(
    "/register",
    status_code=status.HTTP_201_CREATED,
    summary="Register a new user",
    description=(
        "Create a new user account with a chosen role.\n\n"
        "**Roles available:**\n"
        "- `viewer` *(default)* — dashboard summary access only.\n"
        "- `analyst` — read records and view insights.\n"
        "- `admin` — full CRUD and user management.\n\n"
        "Returns a **Bearer JWT** immediately so the user can start making "
        "authenticated requests without a separate login step.\n\n"
        "> ⚠️ Limited to **5 requests per minute** per IP address."
    ),
    response_description="JWT access token and the new user's ID.",
    responses={
        201: {
            "description": "User created successfully.",
            "content": {
                "application/json": {
                    "example": {"access_token": "<jwt>", "user_id": 1}
                }
            },
        },
        400: {"description": "Email address is already registered."},
        **_COMMON_ERRORS,
    },
)
@limiter.limit("5/minute")
async def register(
    request: Request,
    user_data: UserCreate,
    db: AsyncSession = Depends(get_db),
    Authorize: AuthJWT = Depends(),
):
    """
    Register a new user and return an access token.

    Args:
        request (Request): Used by slowapi for rate-limit key extraction.
        user_data (UserCreate): Validated registration payload.
        db (AsyncSession): Injected database session.
        Authorize (AuthJWT): JWT provider.

    Raises:
        HTTPException: 400 if the email is already taken.

    Returns:
        dict: ``access_token`` (JWT) and ``user_id`` of the new account.
    """
    dal = UserDAL(db)
    existing_user = await dal.get_user_by_email(user_data.email)
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered",
        )
    hashed = hash_password(user_data.password)
    new_user = await dal.create_user(
        email=user_data.email,
        hashed_password=hashed,
        role=user_data.role,
    )
    access_token = await Authorize.create_access_token(subject=str(new_user.id))
    return {"access_token": access_token, "user_id": new_user.id}


@router.post(
    "/login",
    summary="Log in and receive a JWT",
    description=(
        "Authenticate with an email and password to receive a **Bearer JWT**.\n\n"
        "The token must be passed in the `Authorization` header for all "
        "protected endpoints:\n"
        "```\nAuthorization: Bearer <token>\n```\n\n"
        "**Failure conditions:**\n"
        "- `401` — wrong email or password.\n"
        "- `403` — account has been deactivated by an admin.\n"
        "- `429` — rate limit exceeded.\n\n"
        "> ⚠️ Limited to **5 requests per minute** per IP address."
    ),
    response_description="JWT access token and the authenticated user's ID.",
    responses={
        200: {
            "description": "Login successful.",
            "content": {
                "application/json": {
                    "example": {"access_token": "<jwt>", "user_id": 1}
                }
            },
        },
        401: {"description": "Invalid email or password."},
        403: {"description": "Account is inactive — contact an administrator."},
        **_COMMON_ERRORS,
    },
)
@limiter.limit("5/minute")
async def login(
    request: Request,
    user_data: UserLogin,
    db: AsyncSession = Depends(get_db),
    Authorize: AuthJWT = Depends(),
):
    """
    Authenticate a user and return a JWT.

    Args:
        request (Request): Used by slowapi for rate-limit key extraction.
        user_data (UserLogin): Email and plaintext password.
        db (AsyncSession): Injected database session.
        Authorize (AuthJWT): JWT provider.

    Raises:
        HTTPException: 401 for invalid credentials, 403 for inactive accounts.

    Returns:
        dict: ``access_token`` (JWT) and ``user_id``.
    """
    dal = UserDAL(db)
    user = await dal.get_user_by_email(user_data.email)

    if not user or not verify_password(user_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is inactive",
        )

    access_token = await Authorize.create_access_token(subject=str(user.id))
    return {"access_token": access_token, "user_id": user.id}
