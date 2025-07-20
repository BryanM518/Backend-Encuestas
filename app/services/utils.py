from bson import ObjectId
from datetime import datetime
from typing import Dict, Any
from fastapi import HTTPException, status
from app.models.survey import Survey
from app.database import get_collection
from motor.motor_asyncio import AsyncIOMotorClient

def convert_objectids_to_str(data: dict) -> dict:
    """Convierte todos los ObjectId en el documento a strings"""
    def convert_value(v):
        if isinstance(v, ObjectId):
            return str(v)
        if isinstance(v, list):
            return [convert_value(i) for i in v]
        if isinstance(v, dict):
            return {k: convert_value(val) for k, val in v.items()}
        return v
    return convert_value(data)

def is_temp_id(id_str: str) -> bool:
    return isinstance(id_str, str) and id_str.startswith("temp_")

def update_survey_status(survey: dict) -> str:
    """Determina el estado de la encuesta basado en las fechas"""
    now = datetime.utcnow()
    start_date = survey.get("start_date")
    end_date = survey.get("end_date")
    
    if end_date and now > end_date:
        return "closed"
    elif start_date and now >= start_date:
        return "published"
    return "created"

def validate_conditional_logic(survey: Survey, answers: Dict[str, Any]):
    for q in survey.questions:
        if not q.visible_if:
            continue

        qid = str(q.id)
        cond = q.visible_if
        referenced_answer = answers.get(str(cond.question_id))

        should_be_visible = False
        if cond.operator == "equals":
            should_be_visible = str(referenced_answer) == str(cond.value)
        elif cond.operator == "not_equals":
            should_be_visible = str(referenced_answer) != str(cond.value)
        elif cond.operator == "in":
            if isinstance(referenced_answer, list):
                should_be_visible = any(str(item) == str(cond.value) for item in referenced_answer)
            else:
                should_be_visible = str(cond.value) in str(referenced_answer).split(",")
        elif cond.operator == "not_in":
            if isinstance(referenced_answer, list):
                should_be_visible = all(str(item) != str(cond.value) for item in referenced_answer)
            else:
                should_be_visible = str(cond.value) not in str(referenced_answer).split(",")

        if not should_be_visible and qid in answers:
            question_text = q.text[:50] + "..." if len(q.text) > 50 else q.text
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"La pregunta '{question_text}' no debería ser visible según las respuestas proporcionadas"
            )
    
async def get_surveys_collection_dependency() -> AsyncIOMotorClient:
    return get_collection("surveys")

async def get_responses_collection_dependency() -> AsyncIOMotorClient:
    return get_collection("survey_responses")



