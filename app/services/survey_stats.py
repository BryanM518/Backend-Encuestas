from typing import Dict, Any
from bson import ObjectId
from app.database import get_collection

async def compute_survey_statistics(survey_id: str) -> Dict[str, Any]:
    if not ObjectId.is_valid(survey_id):
        raise ValueError("ID de encuesta inválido")

    surveys_collection = get_collection("surveys")
    responses_collection = get_collection("survey_responses")

    # Obtener encuesta
    survey = await surveys_collection.find_one({"_id": ObjectId(survey_id)})
    if not survey:
        raise ValueError("Encuesta no encontrada")

    # Obtener respuestas
    responses = await responses_collection.find({"survey_id": ObjectId(survey_id)}).to_list(1000)

    stats = {}

    # Inicializar estadísticas por pregunta
    for question in survey.get("questions", []):
        qid_str = str(question["_id"])  # ✅ Convertimos a string para usarlo como clave
        stats[qid_str] = {
            "text": question["text"],
            "type": question["type"],
            "options": {},       # Para preguntas con opciones
            "responses": []      # Para texto libre u otros valores
        }

    # Contar respuestas
    for response in responses:
        for raw_qid, answer in response.get("answers", {}).items():
            qid = str(raw_qid)  # ✅ Convertimos también aquí

            if qid not in stats:
                continue  # Pregunta eliminada o no registrada

            q_stats = stats[qid]
            q_type = q_stats["type"]

            if q_type in ["multiple_choice", "satisfaction_scale", "number_input"]:
                q_stats["options"][str(answer)] = q_stats["options"].get(str(answer), 0) + 1

            elif q_type == "checkbox_group":
                if isinstance(answer, list):
                    for opt in answer:
                        q_stats["options"][str(opt)] = q_stats["options"].get(str(opt), 0) + 1

            elif q_type == "text_input":
                q_stats["responses"].append(str(answer))

    return stats
