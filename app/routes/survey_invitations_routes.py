from fastapi import APIRouter, HTTPException, status, Depends
from app.models.survey import SurveyAccessToken
from app.database import get_collection
from app.models.user import User
from app.auth import get_current_user
from motor.motor_asyncio import AsyncIOMotorClient
from bson import ObjectId
from datetime import datetime, timedelta

router = APIRouter()

# Dependencia para la colección de tokens
def get_token_collection() -> AsyncIOMotorClient:
    return get_collection("survey_access_tokens")

# Dependencia para la colección de encuestas
def get_surveys_collection() -> AsyncIOMotorClient:
    return get_collection("surveys")

@router.post(
    "/generate-access-link/{survey_id}",
    summary="Generar enlace de invitación"
)
async def generate_invite(
    survey_id: str,
    current_user: User = Depends(get_current_user),
    token_collection=Depends(get_token_collection)
):
    # Definimos validez de 7 días
    expires = datetime.utcnow() + timedelta(days=7)
    token = SurveyAccessToken(
        survey_id=survey_id,
        expires_at=expires
    )
    await token_collection.insert_one(token.model_dump())
    return {"token_id": str(token.id)}

@router.get(
    "/access/{token_id}",
    summary="Verificar token de acceso y devolver encuesta"
)
async def verify_invitation_token(
    token_id: str,
    token_collection = Depends(get_token_collection),
    surveys_collection = Depends(get_surveys_collection)
):
    # 1) Recuperar token
    token = await token_collection.find_one({"id": token_id})
    if not token:
        raise HTTPException(status_code=404, detail="Token no encontrado")
    if token.get("is_used"):
        raise HTTPException(status_code=403, detail="Enlace ya usado")
    if token.get("expires_at") and datetime.utcnow() > token["expires_at"]:
        raise HTTPException(status_code=403, detail="Enlace expirado")

    # 2) Marcar como usado
    await token_collection.update_one({"id": token_id}, {"$set": {"is_used": True}})

    # 3) Recuperar encuesta
    survey = await surveys_collection.find_one({"_id": ObjectId(token["survey_id"])})
    if not survey:
        raise HTTPException(status_code=404, detail="Encuesta no encontrada")

    # 4) Convertir todos los ObjectId a string
    def oid_to_str(obj):
        if isinstance(obj, ObjectId):
            return str(obj)
        if isinstance(obj, list):
            return [oid_to_str(v) for v in obj]
        if isinstance(obj, dict):
            return {k: oid_to_str(v) for k, v in obj.items()}
        return obj

    return oid_to_str(survey)
