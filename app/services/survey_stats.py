from typing import Dict, Any
from bson import ObjectId
from collections import Counter
from statistics import mean, median
from app.database import get_collection
import re


def compute_histogram(values: list[float], bin_size: int = 10) -> Dict[str, int]:
    """Genera un histograma agrupando valores en intervalos."""
    hist = {}
    for v in values:
        try:
            bin_label = f"{int(v // bin_size) * bin_size}-{(int(v // bin_size) + 1) * bin_size - 1}"
            hist[bin_label] = hist.get(bin_label, 0) + 1
        except (ValueError, TypeError):
            pass
    return hist


def compute_word_cloud(texts: list[str], stopwords: set[str] = None) -> list[dict]:
    """Genera una nube de palabras con las palabras más frecuentes."""
    word_freq = Counter()
    stopwords = stopwords or {
        'el', 'la', 'los', 'las', 'de', 'y', 'en', 'que', 'por', 'para', 'con',
        'un', 'una', 'es', 'no', 'sí', 'al', 'lo', 'como', 'más', 'pero', 'sus'
    }
    for text in texts:
        words = re.findall(r"\b\w{3,}\b", text.lower())
        for word in words:
            if word not in stopwords:
                word_freq[word] += 1
    return [{"word": word, "count": count} for word, count in word_freq.most_common(20)]


async def compute_survey_statistics(survey_id: str, filter_pairs: list[dict] = None) -> Dict[str, Any]:
    if not ObjectId.is_valid(survey_id):
        raise ValueError("ID de encuesta inválido")

    surveys_collection = get_collection("surveys")
    responses_collection = get_collection("survey_responses")

    survey = await surveys_collection.find_one({"_id": ObjectId(survey_id)})
    if not survey:
        raise ValueError("Encuesta no encontrada")

    # Construir query con múltiples filtros
    query = {"survey_id": ObjectId(survey_id)}
    if filter_pairs:
        for filter_pair in filter_pairs:
            qid = filter_pair.get("qid")
            value = filter_pair.get("value")
            operator = filter_pair.get("operator", "equals")
            question_type = filter_pair.get("type")

            if question_type == "number_input":
                mongo_operator = {
                    "equals": "$eq",
                    "less_than": "$lt",
                    "greater_than": "$gt",
                    "less_than_or_equal": "$lte",
                    "greater_than_or_equal": "$gte"
                }.get(operator, "$eq")
                query[f"answers.{qid}"] = {mongo_operator: value}
            elif question_type == "multiple_choice":
                query[f"answers.{qid}"] = value
            elif question_type == "checkbox_group":
                query[f"answers.{qid}"] = {"$in": [value]}

    print("🟡 Query de filtro:", query)
    responses = await responses_collection.find(query).to_list(1000)

    stats = {}

    for question in survey.get("questions", []):
        qid_str = str(question["_id"])
        stats[qid_str] = {
            "text": question["text"],
            "type": question["type"],
            "options": {},
            "responses": []
        }

    for response in responses:
        for raw_qid, answer in response.get("answers", {}).items():
            qid = str(raw_qid)
            if qid not in stats:
                continue

            q_stats = stats[qid]
            q_type = q_stats["type"]

            if q_type in ["multiple_choice", "satisfaction_scale", "number_input"]:
                key = str(answer)
                q_stats["options"][key] = q_stats["options"].get(key, 0) + 1
                if q_type == "number_input":
                    try:
                        q_stats["responses"].append(float(answer))
                    except:
                        pass

            elif q_type == "checkbox_group":
                if isinstance(answer, list):
                    for opt in answer:
                        key = str(opt)
                        q_stats["options"][key] = q_stats["options"].get(key, 0) + 1

            elif q_type == "text_input":
                q_stats["responses"].append(str(answer))

    # Calcular métricas adicionales
    for qid, q in stats.items():
        if q["type"] == "number_input" and q["responses"]:
            try:
                q["avg"] = round(mean(q["responses"]), 2)
                q["median"] = round(median(q["responses"]), 2)
                q["min"] = min(q["responses"])
                q["max"] = max(q["responses"])
                q["histogram"] = compute_histogram(q["responses"])
            except:
                pass
        elif q["type"] == "text_input" and q["responses"]:
            q["word_cloud"] = compute_word_cloud(q["responses"])

    return stats