from fastapi import APIRouter, HTTPException, status, Depends
from typing import List
from app.services.survey_stats import compute_survey_statistics
from app.models.survey import Survey, SurveyCreate, SurveyResponse
from app.models.user import User 
from app.database import get_collection 
from app.auth import get_current_user 
from motor.motor_asyncio import AsyncIOMotorClient 
from bson import ObjectId 
from datetime import datetime

router = APIRouter()

async def get_surveys_collection_dependency() -> AsyncIOMotorClient:
    return get_collection("surveys")


@router.post("/", response_model=Survey, status_code=status.HTTP_201_CREATED)
async def create_survey(
    survey: SurveyCreate,
    current_user: User = Depends(get_current_user),
    surveys_collection: AsyncIOMotorClient = Depends(get_surveys_collection_dependency)
):
    survey_data = survey.model_dump(by_alias=True)
    survey_data["creator_id"] = current_user.id
    survey_data["created_at"] = datetime.utcnow()
    survey_data["updated_at"] = datetime.utcnow()

    result = await surveys_collection.insert_one(survey_data)
    new_survey = await surveys_collection.find_one({"_id": result.inserted_id})
    return Survey(**new_survey)


@router.get("/", response_model=List[Survey])
async def get_surveys(
    current_user: User = Depends(get_current_user),
    surveys_collection: AsyncIOMotorClient = Depends(get_surveys_collection_dependency)
):
    user_surveys = await surveys_collection.find({"creator_id": current_user.id}).to_list(1000)
    return [Survey(**survey) for survey in user_surveys]

@router.get("/public", response_model=List[Survey], summary="Ver encuestas públicas (no requiere autenticación)")
async def get_public_surveys(
    surveys_collection: AsyncIOMotorClient = Depends(get_surveys_collection_dependency)
):
    public_surveys = await surveys_collection.find({"is_public": True}).to_list(1000)
    return [Survey(**s) for s in public_surveys]

@router.get("/public/{id}", response_model=Survey)
async def get_public_survey_by_id(
    id: str,
    surveys_collection: AsyncIOMotorClient = Depends(get_surveys_collection_dependency)
):
    if not ObjectId.is_valid(id):
        raise HTTPException(status_code=400, detail="Invalid ID format")

    survey = await surveys_collection.find_one({"_id": ObjectId(id), "is_public": True})
    if not survey:
        raise HTTPException(status_code=404, detail="Survey not found or is private")

    return Survey(**survey)


@router.get("/{id}", response_model=Survey)
async def get_survey_by_id(
    id: str,
    current_user: User = Depends(get_current_user),
    surveys_collection: AsyncIOMotorClient = Depends(get_surveys_collection_dependency)
):
    if not ObjectId.is_valid(id):
        raise HTTPException(status_code=400, detail="Invalid ID format")

    survey = await surveys_collection.find_one({"_id": ObjectId(id), "creator_id": current_user.id})
    if not survey:
        raise HTTPException(status_code=404, detail="Survey not found or you don't have permission")
    
    return Survey(**survey)


@router.put("/{id}", response_model=Survey)
async def update_survey(
    id: str,
    survey: Survey,
    current_user: User = Depends(get_current_user),
    surveys_collection: AsyncIOMotorClient = Depends(get_surveys_collection_dependency)
):
    if not ObjectId.is_valid(id):
        raise HTTPException(status_code=400, detail="Invalid ID format")

    existing_survey = await surveys_collection.find_one({"_id": ObjectId(id), "creator_id": current_user.id})
    if not existing_survey:
        raise HTTPException(status_code=404, detail="Survey not found or you don't have permission")

    update_data = survey.model_dump(by_alias=True, exclude_unset=True, exclude=["id", "creator_id", "created_at"])
    update_data["updated_at"] = datetime.utcnow()

    if "questions" in update_data:
        for q in update_data["questions"]:
            if "_id" in q and isinstance(q["_id"], str) and q["_id"].startswith('temp_'):
                del q["_id"]
            if q.get("type") not in ['multiple_choice', 'checkbox_group'] and q.get("options") is not None:
                del q["options"]
            elif q.get("type") in ['multiple_choice', 'checkbox_group'] and (q.get("options") is None or len(q["options"]) == 0):
                q["options"] = []

    result = await surveys_collection.update_one({"_id": ObjectId(id)}, {"$set": update_data})

    if result.modified_count == 1:
        updated_survey = await surveys_collection.find_one({"_id": ObjectId(id)})
        return Survey(**updated_survey)
    
    return Survey(**existing_survey)


@router.delete("/{id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_survey(
    id: str,
    current_user: User = Depends(get_current_user),
    surveys_collection: AsyncIOMotorClient = Depends(get_surveys_collection_dependency)
):
    if not ObjectId.is_valid(id):
        raise HTTPException(status_code=400, detail="Invalid ID format")

    result = await surveys_collection.delete_one({"_id": ObjectId(id), "creator_id": current_user.id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Survey not found or you don't have permission")

@router.post("/{id}/responses", status_code=status.HTTP_201_CREATED)
async def submit_survey_response(
    id: str,
    response_data: dict,
    surveys_collection: AsyncIOMotorClient = Depends(get_surveys_collection_dependency)
):
    if not ObjectId.is_valid(id):
        raise HTTPException(status_code=400, detail="Invalid ID format")

    survey = await surveys_collection.find_one({"_id": ObjectId(id), "is_public": True})
    if not survey:
        raise HTTPException(status_code=404, detail="Survey not found or is private")

    responder_email = response_data.pop("responder_email", None)
    answers = response_data

    if responder_email:
        if not isinstance(responder_email, str) or "@" not in responder_email:
            raise HTTPException(status_code=400, detail="Correo electrónico inválido")

        # ✅ Verifica si ese correo ya respondió esta encuesta
        response_collection = get_collection("survey_responses")
        existing = await response_collection.find_one({
            "survey_id": ObjectId(id),
            "responder_email": responder_email
        })

        if existing:
            raise HTTPException(status_code=400, detail="Este correo ya ha respondido esta encuesta")

    # Guardar la respuesta
    submission = {
        "survey_id": ObjectId(id),
        "responder_email": responder_email,
        "answers": answers,
        "submitted_at": datetime.utcnow()
    }

    await get_collection("survey_responses").insert_one(submission)
    return {"message": "Respuesta registrada con éxito"}

@router.get("/{id}/responses", response_model=List[SurveyResponse])
async def get_survey_responses(
    id: str,
    current_user: User = Depends(get_current_user),
):
    if not ObjectId.is_valid(id):
        raise HTTPException(status_code=400, detail="Invalid survey ID")

    surveys_collection = get_collection("surveys")
    survey = await surveys_collection.find_one({"_id": ObjectId(id)})

    if not survey:
        raise HTTPException(status_code=404, detail="Survey not found")

    # Verifica que el usuario es el creador
    if str(survey["creator_id"]) != str(current_user.id):
        raise HTTPException(status_code=403, detail="No autorizado a ver respuestas de esta encuesta")

    responses_collection = get_collection("survey_responses")
    raw_responses = await responses_collection.find({"survey_id": ObjectId(id)}).to_list(1000)

    return [SurveyResponse(**r) for r in raw_responses]

