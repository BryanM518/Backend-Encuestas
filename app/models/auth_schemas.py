from pydantic import BaseModel, Field, EmailStr
from typing import Optional

class UserCreate(BaseModel):
    """Modelo para crear un nuevo usuario (registro)."""
    username: str = Field(..., min_length=3, max_length=50)
    email: EmailStr
    password: str = Field(..., min_length=8) # La contraseña en texto plano para el registro

    model_config = {
        "json_schema_extra": {
            "example": {
                "username": "newuser",
                "email": "newuser@example.com",
                "password": "strongpassword123",
            }
        },
    }

class UserLogin(BaseModel):
    """Modelo para la autenticación de usuario (login)."""
    username: str
    password: str

    model_config = {
        "json_schema_extra": {
            "example": {
                "username": "testuser",
                "password": "mypassword",
            }
        },
    }

class Token(BaseModel):
    """Modelo para la respuesta del token JWT."""
    access_token: str
    token_type: str = "bearer"

    model_config = {
        "json_schema_extra": {
            "example": {
                "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
                "token_type": "bearer",
            }
        },
    }