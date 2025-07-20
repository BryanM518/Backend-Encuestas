from fastapi import APIRouter, Depends, HTTPException
from motor.motor_asyncio import AsyncIOMotorDatabase
from bson import ObjectId
from datetime import datetime
from app.database import get_collection
from app.auth import get_current_user
from app.models.survey import Survey

router = APIRouter(
    prefix="/api/survey_api",
    tags=["templates"],
    responses={404: {"description": "Not found"}}
)

@router.get("/templates")
async def get_templates(db: AsyncIOMotorDatabase = Depends(get_collection)):
    """
    Lista todas las plantillas disponibles (encuestas con is_template: true).
    """
    templates = await db.surveys.find({"is_template": True}).to_list(None)
    if not templates:
        return []
    return [Survey(**t).dict() for t in templates]

@router.post("/surveys/from_template/{template_id}")
async def create_survey_from_template(
    template_id: str,
    user_id: str = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_collection)
):
    """
    Crea una nueva encuesta basada en una plantilla, asignando el creator_id del usuario autenticado.
    """
    try:
        template = await db.surveys.find_one({"_id": ObjectId(template_id), "is_template": True})
        if not template:
            raise HTTPException(status_code=404, detail="Plantilla no encontrada")
        
        new_survey = {
            **template,
            "_id": ObjectId(),
            "creator_id": ObjectId(user_id),
            "is_template": False,
            "status": "created",
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow()
        }
        
        # Copiar preguntas y asignar nuevos IDs
        if "questions" in new_survey:
            new_survey["questions"] = [
                {**q, "_id": ObjectId()} for q in new_survey["questions"]
            ]
        
        result = await db.surveys.insert_one(new_survey)
        return {"survey_id": str(result.inserted_id)}
    except ValueError:
        raise HTTPException(status_code=400, detail="ID de plantilla inválido")