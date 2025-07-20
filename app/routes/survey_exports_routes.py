from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse, StreamingResponse
from typing import List
from app.models.user import User
from app.models.survey import SurveyResponse
from app.database import get_collection
from app.auth import get_current_user
from bson import ObjectId
from app.services.survey_stats import compute_survey_statistics
from app.services.pdf_report import generate_pdf_report
import os
from datetime import datetime
import pandas as pd
from io import BytesIO, StringIO
from motor.motor_asyncio import AsyncIOMotorClient
from app.services.utils import (
    convert_objectids_to_str,
    is_temp_id,
    update_survey_status,
    validate_conditional_logic,
    get_surveys_collection_dependency,
    get_responses_collection_dependency,
)

router = APIRouter()

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