from collections import Counter
from typing import List, Dict, Any
from bson import ObjectId

def compute_survey_statistics(survey: dict, responses: List[dict]) -> List[Dict[str, Any]]:
    questions = survey.get("questions", [])
    stats = []

    for question in questions:
        qid = str(question["_id"])
        qtext = question["text"]
        qtype = question["type"]

        data = {
            "question_id": qid,
            "text": qtext,
            "type": qtype,
        }

        # Obtener respuestas para esta pregunta
        all_answers = [
            resp["answers"].get(qid)
            for resp in responses
            if qid in resp["answers"]
        ]

        if qtype == "multiple_choice":
            data["distribution"] = dict(Counter(all_answers))

        elif qtype == "checkbox_group":
            flat = []
            for ans in all_answers:
                if isinstance(ans, list):
                    flat.extend(ans)
            data["distribution"] = dict(Counter(flat))

        elif qtype == "satisfaction_scale":
            numeric = [int(a) for a in all_answers if str(a).isdigit()]
            data["average"] = round(sum(numeric) / len(numeric), 2) if numeric else 0
            data["counts"] = dict(Counter(map(str, numeric)))

        elif qtype == "number_input":
            numeric = [float(a) for a in all_answers if isinstance(a, (int, float, str)) and str(a).replace('.', '', 1).isdigit()]
            if numeric:
                data["average"] = round(sum(numeric) / len(numeric), 2)
                data["min"] = min(numeric)
                data["max"] = max(numeric)
            else:
                data["average"] = data["min"] = data["max"] = None

        elif qtype == "text_input":
            data["responses"] = all_answers

        stats.append(data)

    return stats
