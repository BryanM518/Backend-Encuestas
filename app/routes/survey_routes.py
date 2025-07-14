# app/routes/survey_routes.py
from fastapi import APIRouter, HTTPException, status, Depends
from typing import List
from app.models.survey import Survey 
from app.models.user import User 
from app.database import get_collection 
from app.auth import get_current_user 
from motor.motor_asyncio import AsyncIOMotorClient 
from bson import ObjectId 
from datetime import datetime

router = APIRouter()

async def get_surveys_collection_dependency() -> AsyncIOMotorClient:
    """Retorna la colección de 'surveys' de la base de datos."""
    return get_collection("surveys")


@router.post("/", response_model=Survey, status_code=status.HTTP_201_CREATED, summary="Crear una nueva encuesta (Requiere autenticación)")
async def create_survey(
    survey: Survey,
    current_user: User = Depends(get_current_user),
    surveys_collection: AsyncIOMotorClient = Depends(get_surveys_collection_dependency)
):
    survey.creator_id = current_user.id
    
    survey_data = survey.model_dump(by_alias=True, exclude=["id"])

    result = await surveys_collection.insert_one(survey_data)
    
    new_survey = await surveys_collection.find_one({"_id": result.inserted_id})
    return Survey(**new_survey)

@router.get("/", response_model=List[Survey], summary="Obtener todas las encuestas del usuario actual (Requiere autenticación)")
async def get_surveys(
    current_user: User = Depends(get_current_user),
    surveys_collection: AsyncIOMotorClient = Depends(get_surveys_collection_dependency)
):
    user_surveys = await surveys_collection.find({"creator_id": current_user.id}).to_list(1000)
    return [Survey(**survey) for survey in user_surveys]

@router.get("/{id}", response_model=Survey, summary="Obtener una encuesta por ID (Requiere autenticación, solo propias)")
async def get_survey_by_id(
    id: str,
    current_user: User = Depends(get_current_user),
    surveys_collection: AsyncIOMotorClient = Depends(get_surveys_collection_dependency)
):
    if not ObjectId.is_valid(id):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid ID format")

    survey = await surveys_collection.find_one({"_id": ObjectId(id), "creator_id": current_user.id})
    if survey:
        return Survey(**survey)
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Survey not found or you don't have permission")

@router.put("/{id}", response_model=Survey, summary="Actualizar una encuesta (Requiere autenticación, solo propias)")
async def update_survey(
    id: str,
    survey: Survey,
    current_user: User = Depends(get_current_user),
    surveys_collection: AsyncIOMotorClient = Depends(get_surveys_collection_dependency)
):
    if not ObjectId.is_valid(id):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid ID format")

    existing_survey = await surveys_collection.find_one({"_id": ObjectId(id), "creator_id": current_user.id})
    if not existing_survey:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Survey not found or you don't have permission")

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


    result = await surveys_collection.update_one(
        {"_id": ObjectId(id)},
        {"$set": update_data}
    )

    if result.modified_count == 1:
        updated_survey = await surveys_collection.find_one({"_id": ObjectId(id)})
        return Survey(**updated_survey)
    
    return Survey(**existing_survey)


@router.delete("/{id}", status_code=status.HTTP_204_NO_CONTENT, summary="Eliminar una encuesta (Requiere autenticación, solo propias)")
async def delete_survey(
    id: str,
    current_user: User = Depends(get_current_user),
    surveys_collection: AsyncIOMotorClient = Depends(get_surveys_collection_dependency)
):
    if not ObjectId.is_valid(id):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid ID format")

    result = await surveys_collection.delete_one({"_id": ObjectId(id), "creator_id": current_user.id})
    if result.deleted_count == 1:
        return # FastAPI maneja 204 No Content para None o respuesta vacía
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Survey not found or you don't have permission")