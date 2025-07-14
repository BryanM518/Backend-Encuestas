# app/models/survey.py
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime
from bson import ObjectId
from enum import Enum
from .object_id_utils import PyObjectId


class QuestionType(str, Enum):
    TEXT_INPUT = "text_input"
    MULTIPLE_CHOICE = "multiple_choice"
    SATISFACTION_SCALE = "satisfaction_scale"
    NUMBER_INPUT = "number_input"
    CHECKBOX_GROUP = "checkbox_group"

class Question(BaseModel):
    id: PyObjectId = Field(default_factory=PyObjectId, alias="_id")
    type: str
    text: str = Field(..., min_length=1)
    options: Optional[List[str]] = None
    is_required: bool = False

    model_config = {
        "populate_by_name": True,
        "arbitrary_types_allowed": True,
        "json_encoders": {ObjectId: str},
        "json_schema_extra": {
            "example": {
                "type": "text_input",
                "text": "¿Cuál es tu sugerencia?",
                "is_required": True
            }
        }
    }


class Survey(BaseModel):
    id: PyObjectId = Field(default_factory=PyObjectId, alias="_id")
    title: str = Field(..., min_length=3, max_length=100)
    description: Optional[str] = None
    questions: List[Question] = []
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    status: str = "created"
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    brand_color: Optional[str] = None
    brand_logo_url: Optional[str] = None
    brand_font: Optional[str] = None
    creator_id: PyObjectId = Field(...)

    model_config = {
        "populate_by_name": True,
        "arbitrary_types_allowed": True,
        "json_encoders": {ObjectId: str},
        "json_schema_extra": {
            "example": {
                "title": "Encuesta de Clima Laboral",
                "description": "Una encuesta para evaluar el ambiente de trabajo.",
                "questions": [],
                "status": "created",
                "creator_id": "60c728ef69d7a2b2c8e1e3e4"
            }
        }
    }

class SurveyTemplate(BaseModel):
    id: PyObjectId = Field(default_factory=PyObjectId, alias="_id")
    name: str
    description: Optional[str] = None
    survey_data: Survey
    created_at: datetime = Field(default_factory=datetime.utcnow)

    model_config = {
        "populate_by_name": True,
        "arbitrary_types_allowed": True,
        "json_encoders": {ObjectId: str}
    }

class SurveyResponse(BaseModel):
    id: PyObjectId = Field(default_factory=PyObjectId, alias="_id")
    survey_id: PyObjectId
    responder_id: Optional[str] = None
    answers: Dict[str, Any]
    submitted_at: datetime = Field(default_factory=datetime.utcnow)

    model_config = {
        "populate_by_name": True,
        "arbitrary_types_allowed": True,
        "json_encoders": {ObjectId: str}
    }