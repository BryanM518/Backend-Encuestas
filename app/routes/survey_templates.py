from fastapi import APIRouter, Depends, HTTPException, status
from motor.motor_asyncio import AsyncIOMotorDatabase
from bson import ObjectId
from datetime import datetime
from typing import Union, Dict, Any
from app.services.utils import get_surveys_collection_dependency, convert_objectids_to_str
from app.auth import get_current_user
from app.models.survey import SurveyTemplate
from pydantic import ValidationError

router = APIRouter(
    prefix="/api/survey_api",
    tags=["templates"],
    responses={404: {"description": "Not found"}}
)

# @router.get("/surveys/load/{survey_id}")
# async def load_survey(
#     survey_id: str,
#     db: AsyncIOMotorDatabase = Depends(get_surveys_collection_dependency)
# ):
#     """
#     Endpoint para cargar una encuesta por su ID sin filtrar por creator_id.
#     Usado específicamente para cargar encuestas recién creadas desde plantillas en el editor.
#     """
#     try:
#         if not ObjectId.is_valid(survey_id):
#             print(f"Invalid survey_id format: {survey_id}")
#             raise HTTPException(
#                 status_code=status.HTTP_400_BAD_REQUEST,
#                 detail="ID de encuesta inválido"
#             )

#         print(f"Fetching survey with ID: {survey_id}")
#         survey = await db.find_one({"_id": ObjectId(survey_id), "is_template": False})
#         if not survey:
#             print(f"Survey not found for ID: {survey_id}")
#             raise HTTPException(
#                 status_code=status.HTTP_404_NOT_FOUND,
#                 detail="Encuesta no encontrada"
#             )

#         survey_data = convert_objectids_to_str(survey)
#         print(f"Survey data returned: {survey_data}")

#         return survey_data
#     except HTTPException as he:
#         print(f"HTTP Exception: {he.status_code} - {he.detail}")
#         raise he
#     except Exception as e:
#         print(f"Unexpected error fetching survey: {e}")
#         raise HTTPException(
#             status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
#             detail="Error interno al obtener la encuesta"
#         )

@router.get("/templates")
async def get_templates(db: AsyncIOMotorDatabase = Depends(get_surveys_collection_dependency)):
    """
    Lista todas las plantillas disponibles (encuestas con is_template: true).
    """
    print("Received request for /api/survey_api/templates")
    try:
        # Pipeline de agregación para manejar parent_id y obtener plantillas
        pipeline = [
            {"$match": {"is_template": True}},
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
            {"$sort": {"version": -1}},  # Obtener la versión más reciente
            {
                "$group": {
                    "_id": {"$ifNull": ["$normalized_parent_id", "$_id"]},
                    "latest_template": {"$first": "$$ROOT"}
                }
            },
            {"$replaceRoot": {"newRoot": "$latest_template"}},
            {"$unset": "normalized_parent_id"},
            {"$sort": {"created_at": -1}}  # Ordenar por fecha de creación
        ]

        templates = await db.aggregate(pipeline).to_list(1000)
        print(f"Found {len(templates)} templates in database: {[str(t['_id']) for t in templates]}")
        if not templates:
            print("Returning empty list as no templates found")
            return []
        
        valid_templates = []
        for template in templates:
            try:
                # Convertir ObjectId y validar con SurveyTemplate
                template_data = convert_objectids_to_str(template)
                survey = SurveyTemplate(**template_data)
                valid_templates.append(survey.dict())
                print(f"Valid template added: {template_data['_id']}")
            except ValidationError as e:
                print(f"Validation error for template {template.get('_id')}: {e}")
                print(f"Template data: {template_data}")
                continue
            except Exception as e:
                print(f"Unexpected error processing template {template.get('_id')}: {e}")
                continue
        print(f"Returning {len(valid_templates)} valid templates")
        return valid_templates
    except Exception as e:
        print(f"Error fetching templates: {e}")
        raise HTTPException(status_code=500, detail="Error interno al obtener plantillas")

@router.post("/templates")
async def create_template(
    template: SurveyTemplate,
    user_id: str = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_surveys_collection_dependency)
):
    """
    Crea una nueva plantilla en la base de datos usando el modelo SurveyTemplate.
    """
    print("Received request to create template")
    try:
        # Convertir el modelo SurveyTemplate a un diccionario y preparar los datos
        template_data = template.dict(by_alias=True)
        template_data["_id"] = ObjectId()
        template_data["is_template"] = True
        template_data["creator_id"] = ObjectId(user_id) if user_id and ObjectId.is_valid(user_id) else None
        template_data["created_at"] = datetime.utcnow() if not template_data.get("created_at") else template_data["created_at"]
        template_data["updated_at"] = datetime.utcnow() if not template_data.get("updated_at") else template_data["updated_at"]
        template_data["status"] = template_data.get("status", "published")
        template_data["parent_id"] = ObjectId(template_data["parent_id"]) if template_data.get("parent_id") and ObjectId.is_valid(template_data["parent_id"]) else None

        # Mapear IDs de preguntas para asegurar que sean ObjectId válidos
        temp_id_map = {}
        new_questions = []
        for q in template_data.get("questions", []):
            old_id = str(q.get("_id"))
            new_id = ObjectId()
            temp_id_map[old_id] = str(new_id)
            q["_id"] = new_id
            new_questions.append(q)
        
        # Actualizar visible_if con nuevos IDs
        for q in new_questions:
            if q.get("visible_if"):
                ref_id = q["visible_if"].get("question_id")
                if ref_id in temp_id_map:
                    q["visible_if"]["question_id"] = temp_id_map[ref_id]
        
        template_data["questions"] = new_questions

        # Log antes de la inserción
        print(f"Attempting to insert template with ID: {template_data['_id']} into collection: surveys")
        print(f"Template data: {template_data}")

        # Insertar la plantilla en la base de datos
        result = await db.insert_one(template_data)
        print(f"Template created with ID: {result.inserted_id}")

        # Verificar que el documento se insertó
        inserted_doc = await db.find_one({"_id": result.inserted_id})
        if inserted_doc:
            print(f"Verified: Template with ID {result.inserted_id} found in database")
        else:
            print(f"Error: Template with ID {result.inserted_id} not found after insertion")

        return {"template_id": str(result.inserted_id)}
    except ValidationError as e:
        print(f"Error de validación al crear plantilla: {e}")
        raise HTTPException(status_code=422, detail=f"Datos de plantilla inválidos: {e}")
    except Exception as e:
        print(f"Error al crear plantilla: {e}")
        raise HTTPException(status_code=500, detail="Error interno al crear la plantilla")

@router.post("/surveys/from_template/{template_id}")
async def create_survey_from_template(
    template_id: str,
    current_user: Union[str, Dict[str, Any]] = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_surveys_collection_dependency)
):
    print(f"Received request to create survey from template with template_id: {template_id}")
    try:
        # Extract user_id
        user_id = None
        if isinstance(current_user, str):
            user_id = current_user
        elif isinstance(current_user, dict) and "id" in current_user:
            user_id = str(current_user["id"])
        elif hasattr(current_user, "id"):
            user_id = str(current_user.id)
        else:
            print("No valid user_id found in current_user")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="No se proporcionó un usuario autenticado válido. Por favor, inicia sesión."
            )

        print(f"Extracted User ID: {user_id}")

        # Validate user_id
        if not user_id:
            print("User_id is None or empty")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="No se proporcionó un usuario autenticado. Por favor, inicia sesión."
            )
        if not ObjectId.is_valid(user_id):
            print(f"Invalid user_id format: {user_id}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="ID de usuario inválido: formato no válido"
            )

        # Validate template_id
        if not ObjectId.is_valid(template_id):
            print(f"Invalid template_id format: {template_id}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="ID de plantilla inválido"
            )

        # Fetch the template
        template = await db.find_one({"_id": ObjectId(template_id), "is_template": True})
        if not template:
            print(f"Template not found for ID: {template_id}")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Plantilla no encontrada"
            )

        print(f"Template data: {template}")

        # Ensure questions are copied
        if not template.get("questions"):
            print(f"Warning: Template {template_id} has no questions")
            template["questions"] = []

        # Validate the template with SurveyTemplate model
        try:
            template_data = convert_objectids_to_str(template)
            if template_data.get("parent_id") and not ObjectId.is_valid(template_data["parent_id"]):
                template_data["parent_id"] = None
            SurveyTemplate(**template_data)
        except ValidationError as e:
            print(f"Template validation failed: {e}")
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Plantilla inválida: {e}"
            )

        # Create new survey from template
        new_survey = {
            **template,
            "_id": ObjectId(),
            "creator_id": ObjectId(user_id),
            "is_template": False,
            "status": "created",
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
            "version": 1,
            "parent_id": None
        }

        # Map question IDs for conditional logic
        temp_id_map = {}
        new_questions = []
        for q in new_survey.get("questions", []):
            old_id = str(q.get("_id"))
            new_id = ObjectId()
            temp_id_map[old_id] = str(new_id)
            q["_id"] = new_id
            new_questions.append(q)

        # Update visible_if with new IDs
        for q in new_questions:
            if q.get("visible_if"):
                ref_id = q["visible_if"].get("question_id")
                if ref_id in temp_id_map:
                    q["visible_if"]["question_id"] = temp_id_map[ref_id]

        new_survey["questions"] = new_questions
        print(f"New survey data before insertion: {new_survey}")

        # Insert the new survey
        print(f"Inserting new survey with ID: {new_survey['_id']}")
        result = await db.insert_one(new_survey)
        print(f"Survey created from template with ID: {result.inserted_id}")

        # Fetch the created survey to return full data
        created_survey = await db.find_one({"_id": result.inserted_id})
        if not created_survey:
            raise HTTPException(status_code=404, detail="Encuesta creada no encontrada")

        survey_data = convert_objectids_to_str(created_survey)
        survey_data["isFromTemplate"] = True  # Agregar indicador para el frontend
        print(f"Returning survey data: {survey_data}")

        return survey_data
    except HTTPException as he:
        print(f"HTTP Exception: {he.status_code} - {he.detail}")
        raise he
    except ValidationError as ve:
        print(f"Pydantic Validation Error: {ve}")
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Error de validación: {ve}"
        )
    except Exception as e:
        print(f"Unexpected error creating survey from template: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error interno al crear la encuesta"
        )