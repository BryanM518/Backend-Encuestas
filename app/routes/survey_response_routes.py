from fastapi import APIRouter, HTTPException, status, Depends
from app.database import get_collection
from app.auth import get_current_user
from app.models.user import User
from app.models.survey import SurveyResponse, Survey
from motor.motor_asyncio import AsyncIOMotorClient
from bson import ObjectId
from datetime import datetime
from typing import List, Dict, Any

router = APIRouter()

# ----------------------
# UTILIDAD GENERAL
# ----------------------
def convert_objectids_to_str(data: Any) -> Any:
    if isinstance(data, dict):
        return {k: convert_objectids_to_str(v) for k, v in data.items()}
    elif isinstance(data, list):
        return [convert_objectids_to_str(i) for i in data]
    elif isinstance(data, ObjectId):
        return str(data)
    return data

# ----------------------
# DEPENDENCIAS
# ----------------------
async def get_survey_collection():
    return get_collection("surveys")

async def get_response_collection():
    return get_collection("survey_responses")


# ----------------------
# ENVIAR RESPUESTA (PÚBLICO)
# ----------------------
@router.post(
    "/surveys/{survey_id}/responses",
    status_code=status.HTTP_201_CREATED,
    summary="Enviar respuestas a una encuesta (público)"
)
async def submit_response(
    survey_id: str,
    answers: Dict[str, Any],  # JSON plano: {"question_id": respuesta}
    surveys_collection=Depends(get_survey_collection),
    responses_collection=Depends(get_response_collection)
):
    if not ObjectId.is_valid(survey_id):
        raise HTTPException(status_code=400, detail="ID de encuesta inválido")

    survey = await surveys_collection.find_one({"_id": ObjectId(survey_id)})
    if not survey:
        raise HTTPException(status_code=404, detail="Encuesta no encontrada")

    response_doc = {
        "survey_id": ObjectId(survey_id),
        "answers": answers,
        "submitted_at": datetime.utcnow()
    }

    result = await responses_collection.insert_one(response_doc)
    return {
        "message": "Respuestas enviadas correctamente",
        "response_id": str(result.inserted_id)
    }


# ----------------------
# OBTENER RESPUESTAS (AUTENTICADO)
# ----------------------
@router.get(
    "/surveys/{survey_id}/responses",
    response_model=List[SurveyResponse],
    summary="Obtener respuestas de mi encuesta (requiere autenticación)"
)
async def get_survey_responses(
    survey_id: str,
    current_user: User = Depends(get_current_user),
    surveys_collection=Depends(get_survey_collection),
    responses_collection=Depends(get_response_collection)
):
    if not ObjectId.is_valid(survey_id):
        raise HTTPException(status_code=400, detail="ID de encuesta inválido")

    survey = await surveys_collection.find_one({"_id": ObjectId(survey_id)})
    if not survey:
        raise HTTPException(status_code=404, detail="Encuesta no encontrada")

    if str(survey["creator_id"]) != str(current_user.id):
        raise HTTPException(status_code=403, detail="No tienes permiso para ver estas respuestas")

    responses = await responses_collection.find({"survey_id": ObjectId(survey_id)}).to_list(length=1000)

    return [SurveyResponse(**convert_objectids_to_str(r)) for r in responses]
