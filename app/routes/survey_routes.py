# app/routes/survey_routes.py
from fastapi import APIRouter, HTTPException, status
from typing import List
from datetime import datetime
from bson import ObjectId

from app.database import get_collection
from app.models.survey import Survey, SurveyTemplate, SurveyResponse

router = APIRouter()

surveys_collection = get_collection("surveys")
survey_templates_collection = get_collection("survey_templates")
survey_responses_collection = get_collection("survey_responses")

def serialize_mongo_doc(doc):
    if doc:
        doc["id"] = str(doc["_id"])
        del doc["_id"]
    return doc

# --- Survey Endpoints ---

@router.post("/surveys/", response_model=Survey, status_code=status.HTTP_201_CREATED)
async def create_survey(survey: Survey):
    try:
        survey_to_insert = survey.model_dump(by_alias=True)

        result = await surveys_collection.insert_one(survey_to_insert)
        created_survey = await surveys_collection.find_one({"_id": result.inserted_id})
        if created_survey:
            return Survey(**created_survey)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to retrieve created survey")
    except Exception as e:
        print(f"Error creating survey: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Error creating survey: {e}")

@router.get("/surveys/", response_model=List[Survey])
async def get_all_surveys():
    surveys = []
    async for survey in surveys_collection.find():
        surveys.append(serialize_mongo_doc(survey))
    return surveys

@router.get("/surveys/{survey_id}", response_model=Survey)
async def get_survey(survey_id: str):
    survey = await surveys_collection.find_one({"_id": ObjectId(survey_id)})
    if survey:
        return serialize_mongo_doc(survey)
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Survey not found")

@router.put("/surveys/{survey_id}", response_model=Survey)
async def update_survey(survey_id: str, survey: Survey):
    update_data = survey.model_dump(by_alias=True, exclude_unset=True)
    update_data["updated_at"] = datetime.utcnow()
    result = await surveys_collection.update_one( # Esperar la operación de actualización
        {"_id": ObjectId(survey_id)}, {"$set": update_data}
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Survey not found")
    updated_survey = await surveys_collection.find_one({"_id": ObjectId(survey_id)}) # Esperar la operación de búsqueda
    return serialize_mongo_doc(updated_survey)

@router.delete("/surveys/{survey_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_survey(survey_id: str):
    result = await surveys_collection.delete_one({"_id": ObjectId(survey_id)}) # Esperar la operación de eliminación
    if result.deleted_count == 0:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Survey not found")
    return

@router.post("/survey-templates/", response_model=SurveyTemplate, status_code=status.HTTP_201_CREATED)
async def create_survey_template(template: SurveyTemplate):
    template_dict = template.model_dump(by_alias=True)
    template_dict["_id"] = ObjectId()
    result = await survey_templates_collection.insert_one(template_dict)
    created_template = await survey_templates_collection.find_one({"_id": result.inserted_id})
    return serialize_mongo_doc(created_template)

@router.post("/survey-responses/", response_model=SurveyResponse, status_code=status.HTTP_201_CREATED)
async def submit_survey_response(response: SurveyResponse):
    response_dict = response.model_dump(by_alias=True)
    response_dict["_id"] = ObjectId()
    result = await survey_responses_collection.insert_one(response_dict)
    created_response = await survey_responses_collection.find_one({"_id": result.inserted_id})
    return serialize_mongo_doc(created_response)