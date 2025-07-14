from fastapi import APIRouter, HTTPException, status, Depends
from fastapi.security import OAuth2PasswordRequestForm
from app.models.user import User, UserCreate, UserResponse
from app.models.auth_schemas import Token
from app.auth import get_password_hash, verify_password, create_access_token, get_current_user
from app.database import get_collection
from datetime import datetime, timedelta
from bson import ObjectId
from app.config import settings

router = APIRouter()

@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register_user(user_data: UserCreate):
    users_collection = get_collection("users")

    existing_user = await users_collection.find_one({
        "$or": [{"username": user_data.username}, {"email": user_data.email}]
    })
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username or email already registered"
        )

    # Hashear y preparar datos
    hashed_password = get_password_hash(user_data.password)
    user_in_db = {
        "username": user_data.username,
        "email": user_data.email,
        "password_hash": hashed_password,
        "is_active": True,
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow()
    }

    result = await users_collection.insert_one(user_in_db)
    new_user = await users_collection.find_one({"_id": result.inserted_id})

    return UserResponse(**new_user)  # <-- Esto ahora sí valida correctamente


@router.post("/token", response_model=Token)
async def login_for_access_token(form_data: OAuth2PasswordRequestForm = Depends()):
    users_collection = get_collection("users")
    user_db = await users_collection.find_one({"username": form_data.username})
    if not user_db or not verify_password(form_data.password, user_db["password_hash"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": str(user_db["_id"])},
        expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer"}

@router.get("/me", response_model=UserResponse)
async def read_users_me(current_user: User = Depends(get_current_user)):
    return UserResponse.model_validate(current_user.model_dump(by_alias=True))
