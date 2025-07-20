from motor.motor_asyncio import AsyncIOMotorClient
import uuid
from fastapi import APIRouter, status, File, Depends, UploadFile, HTTPException
from fastapi.responses import Response
from app.models.user import User
from app.auth import get_current_user
from app.database import get_collection
from bson import ObjectId
from datetime import datetime

router = APIRouter()

@router.post("/upload-logo", status_code=status.HTTP_201_CREATED)
async def upload_logo(
    file: UploadFile = File(...),
    survey_id: str | None = None,
    current_user: User = Depends(get_current_user),
    files_collection: AsyncIOMotorClient = Depends(lambda: get_collection("files")),
    surveys_collection: AsyncIOMotorClient = Depends(lambda: get_collection("surveys"))
):
    if not file.content_type in ["image/png", "image/jpeg"]:
        raise HTTPException(status_code=400, detail="Solo se permiten archivos PNG o JPEG")
    
    if file.size and file.size > 2 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="El archivo no debe superar los 2MB")
    
    if survey_id:
        if not ObjectId.is_valid(survey_id):
            raise HTTPException(status_code=400, detail="ID de encuesta inválido")
        survey = await surveys_collection.find_one({"_id": ObjectId(survey_id), "creator_id": current_user.id})
        if not survey:
            raise HTTPException(status_code=404, detail="Encuesta no encontrada o no autorizada")

    content = await file.read()
    file_id = str(uuid.uuid4())
    
    file_doc = {
        "_id": file_id,
        "content_type": file.content_type,
        "data": content,
        "creator_id": current_user.id,
        "survey_id": survey_id,
        "created_at": datetime.utcnow()
    }
    await files_collection.insert_one(file_doc)
    
    return {"file_id": file_id}

@router.get("/files/{file_id}")
async def serve_file(
    file_id: str,
    files_collection: AsyncIOMotorClient = Depends(lambda: get_collection("files"))
):
    file_doc = await files_collection.find_one({"_id": file_id})
    if not file_doc:
        raise HTTPException(status_code=404, detail="Archivo no encontrado")
    
    return Response(
        content=file_doc["data"],
        media_type=file_doc["content_type"]
    )