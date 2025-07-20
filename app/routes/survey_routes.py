from fastapi import APIRouter, HTTPException, status, Depends
from typing import List
from motor.motor_asyncio import AsyncIOMotorClient
from bson import ObjectId
from datetime import datetime
from app.models.survey import Survey, SurveyCreate
from app.models.user import User
from app.database import get_collection
from app.auth import get_current_user
from app.services.utils import (
    convert_objectids_to_str,
    is_temp_id,
    update_survey_status,
    validate_conditional_logic,
    get_surveys_collection_dependency,
    get_responses_collection_dependency,
)

router = APIRouter()

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
    survey_data["status"] = update_survey_status(survey_data)

    for q in survey_data["questions"]:
        if not q.get("_id") or is_temp_id(q.get("_id", "")):
            q["_id"] = ObjectId()

    result = await surveys_collection.insert_one(survey_data)
    new_survey = await surveys_collection.find_one({"_id": result.inserted_id})
    return Survey(**convert_objectids_to_str(new_survey))

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

    parent_id = existing.get("parent_id") or existing["_id"]

    latest = await surveys_collection.find({
        "$or": [{"_id": parent_id}, {"parent_id": str(parent_id)}]
    }).sort("version", -1).to_list(1)
    latest_version = latest[0].get("version", 1) if latest else 1

    update_data = survey.model_dump(by_alias=True, exclude=["id", "creator_id", "created_at"])
    update_data["version"] = latest_version + 1
    update_data["parent_id"] = str(parent_id)
    update_data["title"] = f"{survey.title} v{update_data['version']}"
    update_data["status"] = "created"
    update_data["start_date"] = survey.start_date
    update_data["end_date"] = survey.end_date
    update_data["created_at"] = datetime.utcnow()
    update_data["updated_at"] = datetime.utcnow()
    update_data["creator_id"] = current_user.id

    temp_id_map = {}
    new_questions = []
    for q in update_data.get("questions", []):
        if is_temp_id(q.get("_id", "")):
            new_id = ObjectId()
            temp_id_map[q["_id"]] = str(new_id)
            q["_id"] = new_id
        elif not q.get("_id"):
            q["_id"] = ObjectId()
        new_questions.append(q)
    update_data["questions"] = new_questions

    for q in update_data.get("questions", []):
        if q.get("visible_if"):
            ref_id = q["visible_if"].get("question_id")
            if ref_id in temp_id_map:
                q["visible_if"]["question_id"] = temp_id_map[ref_id]

    result = await surveys_collection.insert_one(update_data)
    new_survey = await surveys_collection.find_one({"_id": result.inserted_id})
    return Survey(**convert_objectids_to_str(new_survey))

@router.get("/", response_model=List[Survey])
async def get_surveys(
    current_user: User = Depends(get_current_user),
    surveys_collection: AsyncIOMotorClient = Depends(get_surveys_collection_dependency)
):
    pipeline = [
        {"$match": {"creator_id": current_user.id}},
        {
            "$addFields": {
                "normalized_parent_id": {
                    "$cond": [
                        {
                            "$and": [
                                {"$ne": ["$parent_id", None]},
                                {"$ne": [{"$type": "$parent_id"}, "objectId"]}
                            ]
                        },
                        {"$toObjectId": "$parent_id"},
                        "$parent_id"
                    ]
                }
            }
        },
        {"$sort": {"version": -1}},
        {
            "$group": {
                "_id": {"$ifNull": ["$normalized_parent_id", "$_id"]},
                "latest_survey": {"$first": "$$ROOT"}
            }
        },
        {"$replaceRoot": {"newRoot": "$latest_survey"}},
        {"$unset": "normalized_parent_id"},
        {"$sort": {"created_at": -1}}
    ]

    surveys = await surveys_collection.aggregate(pipeline).to_list(1000)
    latest_surveys = []
    for survey in surveys:
        survey["status"] = update_survey_status(survey)
        await surveys_collection.update_one(
            {"_id": survey["_id"]},
            {"$set": {"status": survey["status"]}}
        )
        latest_surveys.append(Survey(**convert_objectids_to_str(survey)))
    print("Encuestas filtradas:", surveys)
    return latest_surveys

@router.get("/public", response_model=List[Survey])
async def get_public_surveys(
    surveys_collection: AsyncIOMotorClient = Depends(get_surveys_collection_dependency)
):
    pipeline = [
        {
            "$addFields": {
                "normalized_parent_id": {
                    "$cond": [
                        {
                            "$and": [
                                {"$ne": ["$parent_id", None]},
                                {"$ne": [{"$type": "$parent_id"}, "objectId"]}
                            ]
                        },
                        {"$toObjectId": "$parent_id"},
                        "$parent_id"
                    ]
                }
            }
        },
        {"$sort": {"version": -1}},
        {
            "$group": {
                "_id": {"$ifNull": ["$normalized_parent_id", "$_id"]},
                "latest_survey": {"$first": "$$ROOT"}
            }
        },
        {"$replaceRoot": {"newRoot": "$latest_survey"}},
        {"$unset": "normalized_parent_id"},
        {"$match": {"status": "published"}},
        {"$sort": {"created_at": -1}}
    ]

    surveys = await surveys_collection.aggregate(pipeline).to_list(1000)
    latest_surveys = []
    for survey in surveys:
        survey["status"] = update_survey_status(survey)
        await surveys_collection.update_one(
            {"_id": survey["_id"]},
            {"$set": {"status": survey["status"]}}
        )
        latest_surveys.append(Survey(**convert_objectids_to_str(survey)))
    return latest_surveys

@router.get("/public/{id}", response_model=Survey)
async def get_public_survey_by_id(
    id: str,
    surveys_collection: AsyncIOMotorClient = Depends(get_surveys_collection_dependency)
):
    if not ObjectId.is_valid(id):
        raise HTTPException(status_code=400, detail="ID inválido")

    # Usar un pipeline de agregación para obtener la versión más reciente de la encuesta
    pipeline = [
        {
            "$match": {
                "$or": [
                    {"_id": ObjectId(id)},
                    {"parent_id": id}
                ],
                "is_public": True
            }
        },
        {
            "$addFields": {
                "normalized_parent_id": {
                    "$cond": [
                        {
                            "$and": [
                                {"$ne": ["$parent_id", None]},
                                {"$ne": [{"$type": "$parent_id"}, "objectId"]}
                            ]
                        },
                        {"$toObjectId": "$parent_id"},
                        "$parent_id"
                    ]
                }
            }
        },
        {"$sort": {"version": -1}},
        {
            "$group": {
                "_id": {"$ifNull": ["$normalized_parent_id", "$_id"]},
                "latest_survey": {"$first": "$$ROOT"}
            }
        },
        {"$replaceRoot": {"newRoot": "$latest_survey"}},
        {"$unset": "normalized_parent_id"}
    ]

    surveys = await surveys_collection.aggregate(pipeline).to_list(1)
    if not surveys:
        raise HTTPException(status_code=404, detail="Encuesta no encontrada o no es pública")

    survey = surveys[0]
    print("Survey before serialization:", survey)  # Depuración: Imprimir documento crudo
    survey["status"] = update_survey_status(survey)
    await surveys_collection.update_one(
        {"_id": survey["_id"]},
        {"$set": {"status": survey["status"]}}
    )

    if survey["status"] == "created" and survey.get("start_date"):
        raise HTTPException(
            status_code=400,
            detail=f"Esta encuesta no está disponible aún. Abre el {datetime.fromisoformat(survey['start_date'].replace('Z', '+00:00')).strftime('%d de %B de %Y, %H:%M')}."
        )
    elif survey["status"] == "closed" and survey.get("end_date"):
        raise HTTPException(
            status_code=400,
            detail=f"Esta encuesta ha finalizado. Cerró el {datetime.fromisoformat(survey['end_date'].replace('Z', '+00:00')).strftime('%d de %B de %Y, %H:%M')}."
        )

    serialized_survey = Survey(**convert_objectids_to_str(survey))
    print("Survey after serialization:", serialized_survey.model_dump())  # Depuración: Imprimir documento serializado
    return serialized_survey

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

    survey["status"] = update_survey_status(survey)
    await surveys_collection.update_one(
        {"_id": survey["_id"]},
        {"$set": {"status": survey["status"]}}
    )
    return Survey(**convert_objectids_to_str(survey))

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

@router.post("/{id}/responses", status_code=status.HTTP_201_CREATED)
async def submit_survey_response(
    id: str,
    response_data: dict,
    surveys_collection: AsyncIOMotorClient = Depends(get_surveys_collection_dependency),
    responses_collection: AsyncIOMotorClient = Depends(get_responses_collection_dependency)
):
    print("Datos recibidos:", response_data)
    if not ObjectId.is_valid(id):
        raise HTTPException(status_code=400, detail="ID inválido")

    doc = await surveys_collection.find_one({"_id": ObjectId(id)})
    if not doc:
        raise HTTPException(status_code=404, detail="Encuesta no encontrada")

    survey = Survey(**convert_objectids_to_str(doc))
    now = datetime.utcnow()
    if survey.start_date and now < survey.start_date:
        raise HTTPException(
            status_code=400,
            detail=f"Esta encuesta no está disponible aún. Abre el {survey.start_date.strftime('%d de %B de %Y, %H:%M')}."
        )
    if survey.end_date and now > survey.end_date:
        raise HTTPException(
            status_code=400,
            detail=f"Esta encuesta ha finalizado. Cerró el {survey.end_date.strftime('%d de %B de %Y, %H:%M')}."
        )

    responder_email = response_data.pop("responder_email", None)
    answers = response_data

    if responder_email:
        if not isinstance(responder_email, str) or "@" not in responder_email:
            raise HTTPException(status_code=400, detail="Correo inválido")

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

    result = await responses_collection.insert_one(submission)
    return {"message": "Respuesta registrada", "response_id": str(result.inserted_id)}

@router.post("/{survey_id}/clone", response_model=Survey)
async def clone_survey_version(
    survey_id: str,
    current_user: User = Depends(get_current_user),
    surveys_collection=Depends(get_surveys_collection_dependency)
):
    if not ObjectId.is_valid(survey_id):
        raise HTTPException(status_code=400, detail="ID inválido")

    original = await surveys_collection.find_one({"_id": ObjectId(survey_id)})
    if not original or str(original["creator_id"]) != str(current_user.id):
        raise HTTPException(status_code=403, detail="No autorizado para duplicar esta encuesta")

    parent_id = original.get("parent_id") or original["_id"]

    latest = await surveys_collection.find({
        "$or": [{"_id": parent_id}, {"parent_id": str(parent_id)}]
    }).sort("version", -1).to_list(1)
    latest_version = latest[0].get("version", 1) if latest else 1

    new_survey = original.copy()
    new_survey.pop("_id", None)
    new_survey["version"] = latest_version + 1
    new_survey["parent_id"] = str(parent_id)
    new_survey["title"] = f"{original['title']} v{new_survey['version']}"
    new_survey["status"] = "created"
    new_survey["start_date"] = original.get("start_date")
    new_survey["end_date"] = original.get("end_date")
    new_survey["created_at"] = datetime.utcnow()
    new_survey["updated_at"] = datetime.utcnow()

    new_questions = []
    for q in new_survey.get("questions", []):
        q["_id"] = ObjectId()
        new_questions.append(q)
    new_survey["questions"] = new_questions

    result = await surveys_collection.insert_one(new_survey)
    new_survey["_id"] = result.inserted_id

    print(Survey(**convert_objectids_to_str(new_survey)))
    return Survey(**convert_objectids_to_str(new_survey))

@router.get("/{survey_id}/versions", response_model=List[Survey])
async def get_survey_versions(survey_id: str):
    collection = get_collection("surveys")

    base_survey = await collection.find_one({"_id": ObjectId(survey_id)})
    if not base_survey:
        raise HTTPException(status_code=404, detail="Encuesta no encontrada")

    parent_id = base_survey.get("parent_id", base_survey["_id"])

    cursor = collection.find({
        "$or": [
            {"_id": parent_id},
            {"parent_id": parent_id}
        ]
    }).sort("version", 1)

    raw_surveys = await cursor.to_list(length=100)

    surveys = [Survey(**convert_objectids_to_str(s)) for s in raw_surveys]
    print(surveys)

    return surveys
