from fastapi import APIRouter, HTTPException, Request, status, Depends, UploadFile, File
from fastapi.responses import FileResponse, StreamingResponse
from typing import List, Dict, Any
from motor.motor_asyncio import AsyncIOMotorClient
from bson import ObjectId
from datetime import datetime
import uuid
import os
import aiofiles
from app.models.survey import Survey, SurveyCreate, SurveyResponse
from app.models.user import User
from app.database import get_collection
from app.auth import get_current_user
from app.services.survey_stats import compute_survey_statistics
from app.services.pdf_report import generate_pdf_report
import pandas as pd
from io import BytesIO, StringIO


router = APIRouter()

# Directorio para almacenar los logos
UPLOAD_DIR = "uploads/surveys"
os.makedirs(UPLOAD_DIR, exist_ok=True)

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

# ------------------------------
# DEPENDENCIAS
# ------------------------------

async def get_surveys_collection_dependency() -> AsyncIOMotorClient:
    return get_collection("surveys")

async def get_responses_collection_dependency() -> AsyncIOMotorClient:
    return get_collection("survey_responses")

# ------------------------------
# CARGA DE LOGOS
# ------------------------------

@router.post("/upload-logo", status_code=status.HTTP_201_CREATED)
async def upload_logo(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user)
):
    if not file.content_type in ["image/png", "image/jpeg"]:
        raise HTTPException(status_code=400, detail="Solo se permiten archivos PNG o JPEG")
    
    if file.size and file.size > 2 * 1024 * 1024:  # Límite de 2MB
        raise HTTPException(status_code=400, detail="El archivo no debe superar los 2MB")
    
    # Generar nombre único para el archivo
    file_extension = file.filename.split('.')[-1]
    file_name = f"{uuid.uuid4()}.{file_extension}"
    file_path = os.path.join(UPLOAD_DIR, file_name)
    
    # Guardar el archivo
    async with aiofiles.open(file_path, 'wb') as out_file:
        content = await file.read()
        await out_file.write(content)
    
    # Generar URL para el archivo
    logo_url = f"/uploads/surveys/{file_name}"
    
    return {"logo_url": logo_url}

# ------------------------------
# SERVIR ARCHIVOS ESTÁTICOS
# ------------------------------

@router.get("/uploads/surveys/{filename}")
async def serve_logo(filename: str):
    file_path = os.path.join(UPLOAD_DIR, filename)
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="Archivo no encontrado")
    return FileResponse(file_path)

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
    survey_data["status"] = update_survey_status(survey_data)

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
    updated_surveys = []
    for survey in surveys:
        survey["status"] = update_survey_status(survey)
        await surveys_collection.update_one(
            {"_id": survey["_id"]},
            {"$set": {"status": survey["status"]}}
        )
        updated_surveys.append(Survey(**convert_objectids_to_str(survey)))
    return updated_surveys

@router.get("/public", response_model=List[Survey])
async def get_public_surveys(
    surveys_collection: AsyncIOMotorClient = Depends(get_surveys_collection_dependency)
):
    surveys = await surveys_collection.find({"is_public": True}).to_list(1000)
    updated_surveys = []
    for survey in surveys:
        survey["status"] = update_survey_status(survey)
        await surveys_collection.update_one(
            {"_id": survey["_id"]},
            {"$set": {"status": survey["status"]}}
        )
        updated_surveys.append(Survey(**convert_objectids_to_str(survey)))
    return updated_surveys

@router.get("/public/{id}", response_model=Survey)
async def get_public_survey_by_id(
    id: str,
    surveys_collection: AsyncIOMotorClient = Depends(get_surveys_collection_dependency)
):
    if not ObjectId.is_valid(id):
        raise HTTPException(status_code=400, detail="ID inválido")

    survey = await surveys_collection.find_one({"_id": ObjectId(id), "is_public": True})
    if not survey:
        raise HTTPException(status_code=404, detail="Encuesta no encontrada o no es pública")

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

    survey["status"] = update_survey_status(survey)
    await surveys_collection.update_one(
        {"_id": survey["_id"]},
        {"$set": {"status": survey["status"]}}
    )
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
    update_data["status"] = update_survey_status(update_data)

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
    
    # Validar fechas
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
    request: Request,
    current_user: User = Depends(get_current_user),
    surveys_collection=Depends(get_surveys_collection_dependency)
):
    if not ObjectId.is_valid(id):
        raise HTTPException(status_code=400, detail="ID inválido")

    survey = await surveys_collection.find_one({"_id": ObjectId(id)})
    if not survey or str(survey["creator_id"]) != str(current_user.id):
        raise HTTPException(status_code=403, detail="No autorizado")

    survey["status"] = update_survey_status(survey)
    await surveys_collection.update_one(
        {"_id": survey["_id"]},
        {"$set": {"status": survey["status"]}}
    )

    filters = dict(request.query_params)
    filter_pairs = []
    
    i = 0
    while f"filter_qid_{i}" in filters:
        if f"filter_value_{i}" in filters and f"filter_operator_{i}" in filters:
            try:
                value = float(filters[f"filter_value_{i}"])
                filter_pairs.append({
                    "qid": filters[f"filter_qid_{i}"],
                    "value": value,
                    "operator": filters[f"filter_operator_{i}"],
                })
            except ValueError:
                raise HTTPException(status_code=400, detail=f"Valor inválido para el filtro {i}")
        i += 1

    valid_operators = {"equals", "less_than", "greater_than", "less_than_or_equal", "greater_than_or_equal"}
    for f in filter_pairs:
        if f["operator"] not in valid_operators:
            raise HTTPException(status_code=400, detail=f"Operador inválido: {f['operator']}")
        if f["qid"] not in {str(q["_id"]) for q in survey.get("questions", []) if q["type"] == "number_input"}:
            raise HTTPException(status_code=400, detail=f"El filtro para la pregunta {f['qid']} no es de tipo number_input")

    stats = await compute_survey_statistics(id, filter_pairs)
    return stats

@router.get("/{id}/final-report", response_class=FileResponse)
async def get_final_report(
    id: str,
    current_user: User = Depends(get_current_user),
    surveys_collection=Depends(get_surveys_collection_dependency),
    responses_collection=Depends(get_responses_collection_dependency)
):
    if not ObjectId.is_valid(id):
        raise HTTPException(status_code=400, detail="ID inválido")

    survey = await surveys_collection.find_one({"_id": ObjectId(id)})
    if not survey or str(survey["creator_id"]) != str(current_user.id):
        raise HTTPException(status_code=403, detail="No autorizado")

    survey["status"] = update_survey_status(survey)

    from app.services.survey_stats import compute_survey_statistics
    stats = await compute_survey_statistics(id, [])

    # 🔁 Convertir el dict a una lista para el template
    formatted_stats = []
    for qid, q in stats.items():
        question_summary = {
            "question": q["text"],
            "type": q["type"],
            "data": q.get("options", {}),
            "total": sum(q.get("options", {}).values())
        }

        if q["type"] == "number_input" and q.get("responses"):
            question_summary.update({
                "avg": q.get("avg"),
                "median": q.get("median"),
                "min": q.get("min"),
                "max": q.get("max")
            })
        elif q["type"] == "text_input" and "word_cloud" in q:
            word_data = {w["word"]: w["count"] for w in q["word_cloud"]}
            question_summary["data"] = word_data
            question_summary["total"] = sum(word_data.values())

        formatted_stats.append(question_summary)

    # 📝 Generar PDF
    os.makedirs("reports", exist_ok=True)
    filename = f"reports/survey_report_{id}.pdf"
    generate_pdf_report(survey, formatted_stats, filename)

    # 📄 Devolver archivo PDF
    response = FileResponse(
        filename,
        media_type="application/pdf",
        filename=f"Informe_{survey['title'].replace(' ', '_')}.pdf"
    )
    response.headers["Access-Control-Allow-Origin"] = "*"
    return response

def format_date(date_val):
    try:
        if isinstance(date_val, datetime):
            return date_val.strftime("%Y-%m-%d %H:%M")
        if isinstance(date_val, str):
            dt = datetime.fromisoformat(date_val.replace("Z", "+00:00"))
            return dt.strftime("%Y-%m-%d %H:%M")
    except Exception:
        return ""
    return ""

@router.get("/{id}/export", response_class=StreamingResponse)
async def export_survey_data(
    id: str,
    format: str = "csv",  # "csv" o "xlsx"
    current_user: User = Depends(get_current_user),
    surveys_collection=Depends(get_surveys_collection_dependency),
    responses_collection=Depends(get_responses_collection_dependency)
):
    if not ObjectId.is_valid(id):
        raise HTTPException(status_code=400, detail="ID inválido")

    survey = await surveys_collection.find_one({"_id": ObjectId(id)})
    if not survey or str(survey["creator_id"]) != str(current_user.id):
        raise HTTPException(status_code=403, detail="No autorizado")

    responses = await responses_collection.find({"survey_id": ObjectId(id)}).to_list(1000)
    if not responses:
        raise HTTPException(status_code=404, detail="No hay respuestas para exportar")

    rows = []
    for res in responses:
        row = {
            "_id": str(res.get("_id", "")),
            "Email": res.get("responder_email", ""),
            "Fecha de envío": format_date(res.get("submitted_at"))
        }
        for q in survey.get("questions", []):
            qid = str(q["_id"])
            qtext = q["text"]
            answer = res.get("answers", {}).get(qid, "")
            if isinstance(answer, list):
                row[qtext] = ", ".join(map(str, answer))
            else:
                row[qtext] = str(answer)
        rows.append(row)

    df = pd.DataFrame(rows)

    if format == "xlsx":
        output = BytesIO()
        with pd.ExcelWriter(output, engine="openpyxl") as writer:
            df.to_excel(writer, index=False, sheet_name="Respuestas")
        output.seek(0)
        return StreamingResponse(
            output,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f"attachment; filename=encuesta_{id}.xlsx"}
        )

    else:
        output = StringIO()
        df.to_csv(output, index=False)
        output.seek(0)
        return StreamingResponse(
            output,
            media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename=encuesta_{id}.csv"}
        )