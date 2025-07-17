from fastapi import APIRouter, HTTPException, status, Depends
from typing import List, Dict, Any
from app.services.survey_stats import compute_survey_statistics
from app.models.survey import Survey, SurveyCreate, SurveyResponse, Question, VisibleIfCondition
from app.models.user import User 
from app.database import get_collection 
from app.auth import get_current_user 
from motor.motor_asyncio import AsyncIOMotorClient 
from bson import ObjectId 
from datetime import datetime

router = APIRouter()

# ------------------------------
# UTILS
# ------------------------------

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

# ------------------------------
# DEPENDENCIAS
# ------------------------------

async def get_surveys_collection_dependency() -> AsyncIOMotorClient:
    return get_collection("surveys")

async def get_responses_collection_dependency() -> AsyncIOMotorClient:
    return get_collection("survey_responses")

# ------------------------------
# CRUD ENCUESTAS
# ------------------------------

@router.post("/", response_model=Survey, status_code=status.HTTP_201_CREATED)
async def create_survey(
    survey: SurveyCreate,
    current_user: User = Depends(get_current_user),
    surveys_collection: AsyncIOMotorClient = Depends(get_surveys_collection_dependency)
):
    survey_data = survey.model_dump(by_alias=True, exclude_unset=True)
    survey_data["creator_id"] = current_user.id
    survey_data["created_at"] = datetime.utcnow()
    survey_data["updated_at"] = datetime.utcnow()

    for q in survey_data["questions"]:
        if not q.get("_id") or is_temp_id(q.get("_id", "")):
            q["_id"] = ObjectId()

    result = await surveys_collection.insert_one(survey_data)
    new_survey = await surveys_collection.find_one({"_id": result.inserted_id})
    return Survey(**convert_objectids_to_str(new_survey))


@router.get("/", response_model=List[Survey])
async def get_surveys(
    current_user: User = Depends(get_current_user),
    surveys_collection: AsyncIOMotorClient = Depends(get_surveys_collection_dependency)
):
    surveys = await surveys_collection.find({"creator_id": current_user.id}).to_list(1000)
    return [Survey(**convert_objectids_to_str(s)) for s in surveys]


@router.get("/public", response_model=List[Survey])
async def get_public_surveys(
    surveys_collection: AsyncIOMotorClient = Depends(get_surveys_collection_dependency)
):
    surveys = await surveys_collection.find({"is_public": True}).to_list(1000)
    return [Survey(**convert_objectids_to_str(s)) for s in surveys]


@router.get("/public/{id}", response_model=Survey)
async def get_public_survey_by_id(
    id: str,
    surveys_collection: AsyncIOMotorClient = Depends(get_surveys_collection_dependency)
):
    if not ObjectId.is_valid(id):
        raise HTTPException(status_code=400, detail="ID inválido")

    survey = await surveys_collection.find_one({"_id": ObjectId(id), "is_public": True})
    if not survey:
        raise HTTPException(status_code=404, detail="Encuesta no encontrada o privada")

    return Survey(**convert_objectids_to_str(survey))


@router.get("/{id}", response_model=Survey)
async def get_survey_by_id(
    id: str,
    current_user: User = Depends(get_current_user),
    surveys_collection: AsyncIOMotorClient = Depends(get_surveys_collection_dependency)
):
    if not ObjectId.is_valid(id):
        raise HTTPException(status_code=400, detail="ID inválido")

    survey = await surveys_collection.find_one({"_id": ObjectId(id), "creator_id": current_user.id})
    if not survey:
        raise HTTPException(status_code=404, detail="Encuesta no encontrada")

    return Survey(**convert_objectids_to_str(survey))


@router.put("/{id}", response_model=Survey)
async def update_survey(
    id: str,
    survey: Survey,
    current_user: User = Depends(get_current_user),
    surveys_collection: AsyncIOMotorClient = Depends(get_surveys_collection_dependency)
):
    if not ObjectId.is_valid(id):
        raise HTTPException(status_code=400, detail="ID inválido")

    existing = await surveys_collection.find_one({"_id": ObjectId(id), "creator_id": current_user.id})
    if not existing:
        raise HTTPException(status_code=404, detail="Encuesta no encontrada")

    update_data = survey.model_dump(by_alias=True, exclude=["id", "creator_id", "created_at"])
    update_data["updated_at"] = datetime.utcnow()

    temp_id_map = {}
    for q in update_data.get("questions", []):
        if is_temp_id(q.get("_id", "")):
            new_id = ObjectId()
            temp_id_map[q["_id"]] = str(new_id)
            q["_id"] = new_id
        elif not q.get("_id"):
            q["_id"] = ObjectId()

    for q in update_data.get("questions", []):
        if q.get("visible_if"):
            ref_id = q["visible_if"].get("question_id")
            if ref_id in temp_id_map:
                q["visible_if"]["question_id"] = temp_id_map[ref_id]

    await surveys_collection.update_one({"_id": ObjectId(id)}, {"$set": update_data})
    updated = await surveys_collection.find_one({"_id": ObjectId(id)})
    return Survey(**convert_objectids_to_str(updated))


@router.delete("/{id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_survey(
    id: str,
    current_user: User = Depends(get_current_user),
    surveys_collection: AsyncIOMotorClient = Depends(get_surveys_collection_dependency)
):
    if not ObjectId.is_valid(id):
        raise HTTPException(status_code=400, detail="ID inválido")

    result = await surveys_collection.delete_one({"_id": ObjectId(id), "creator_id": current_user.id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Encuesta no encontrada")

# ------------------------------
# RESPONDER ENCUESTA
# ------------------------------

@router.post("/{id}/responses", status_code=status.HTTP_201_CREATED)
async def submit_survey_response(
    id: str,
    response_data: dict,
    surveys_collection: AsyncIOMotorClient = Depends(get_surveys_collection_dependency)
):
    print("Datos recibidos:", response_data)
    if not ObjectId.is_valid(id):
        raise HTTPException(status_code=400, detail="ID inválido")

    doc = await surveys_collection.find_one({"_id": ObjectId(id), "is_public": True})
    if not doc:
        raise HTTPException(status_code=404, detail="Encuesta no encontrada o privada")

    survey = Survey(**convert_objectids_to_str(doc))
    responder_email = response_data.pop("responder_email", None)
    answers = response_data

    if responder_email:
        if not isinstance(responder_email, str) or "@" not in responder_email:
            raise HTTPException(status_code=400, detail="Correo inválido")

        responses_collection = get_collection("survey_responses")
        existing = await responses_collection.find_one({
            "survey_id": ObjectId(id),
            "responder_email": responder_email
        })
        if existing:
            raise HTTPException(status_code=400, detail="Este correo ya ha respondido")

    validate_conditional_logic(survey, answers)

    submission = {
        "survey_id": ObjectId(id),
        "responder_email": responder_email,
        "answers": answers,
        "submitted_at": datetime.utcnow()
    }

    result = await get_collection("survey_responses").insert_one(submission)
    return {"message": "Respuesta registrada", "response_id": str(result.inserted_id)}

# ------------------------------
# ESTADÍSTICAS Y RESPUESTAS
# ------------------------------

@router.get("/{id}/responses", response_model=List[SurveyResponse])
async def get_survey_responses(
    id: str,
    current_user: User = Depends(get_current_user),
    responses_collection: AsyncIOMotorClient = Depends(get_responses_collection_dependency)
):
    if not ObjectId.is_valid(id):
        raise HTTPException(status_code=400, detail="ID inválido")

    survey = await get_collection("surveys").find_one({"_id": ObjectId(id)})
    if not survey or str(survey["creator_id"]) != str(current_user.id):
        raise HTTPException(status_code=403, detail="No autorizado")

    responses = await responses_collection.find({"survey_id": ObjectId(id)}).to_list(1000)
    return [SurveyResponse(**convert_objectids_to_str(r)) for r in responses]


@router.get("/{id}/stats")
async def get_survey_stats(
    id: str,
    current_user: User = Depends(get_current_user),
    surveys_collection: AsyncIOMotorClient = Depends(get_surveys_collection_dependency)
):
    if not ObjectId.is_valid(id):
        raise HTTPException(status_code=400, detail="ID inválido")

    survey = await surveys_collection.find_one({"_id": ObjectId(id)})
    if not survey or str(survey["creator_id"]) != str(current_user.id):
        raise HTTPException(status_code=403, detail="No autorizado")

    stats = await compute_survey_statistics(id)
    return stats