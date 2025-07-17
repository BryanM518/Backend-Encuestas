from pydantic import BaseModel, Field, field_validator, model_validator
from typing import Optional, List, Dict, Any, Literal, Union
from datetime import datetime
from bson import ObjectId
from enum import Enum
from .object_id_utils import PyObjectId
from pydantic_core import core_schema
import uuid

class PyObjectIdStr(str):
    @classmethod
    def __get_pydantic_core_schema__(cls, _source_type, _handler):
        return core_schema.no_info_after_validator_function(
            cls.validate,
            core_schema.str_schema(),
            serialization=core_schema.to_string_ser_schema(),
        )

    @classmethod
    def validate(cls, v):
        if isinstance(v, ObjectId):
            return str(v)
        if isinstance(v, str):
            try:
                # Solo validar si no es un ID temporal
                if not v.startswith('temp_'):
                    ObjectId(v)
                return v
            except:
                # Permitir strings vacíos para casos de condiciones no establecidas
                if v == "":
                    return v
                raise ValueError("Invalid ObjectId format")
        raise ValueError("Invalid ObjectId format")

class VisibleIfCondition(BaseModel):
    question_id: PyObjectIdStr = Field(
        "",  # Valor por defecto string vacío
        description="ID de la pregunta de referencia"
    )
    operator: Literal["equals", "not_equals", "in", "not_in"] = "equals"
    value: Any = Field(
        ...,
        description="Valor esperado para la condición"
    )

    model_config = {
        "populate_by_name": True,
        "arbitrary_types_allowed": True,
        "json_encoders": {ObjectId: str},
    }

    @field_validator('value')
    def value_must_be_string_or_list(cls, v):
        if isinstance(v, list):
            return v
        return str(v)

class QuestionType(str, Enum):
    TEXT_INPUT = "text_input"
    MULTIPLE_CHOICE = "multiple_choice"
    SATISFACTION_SCALE = "satisfaction_scale"
    NUMBER_INPUT = "number_input"
    CHECKBOX_GROUP = "checkbox_group"

class Question(BaseModel):
    id: PyObjectIdStr = Field(
        default_factory=PyObjectIdStr, 
        alias="_id",
        description="ID único de la pregunta"
    )
    type: QuestionType
    text: str = Field(..., min_length=1, max_length=500)
    options: Optional[List[str]] = Field(
        None, 
        description="Opciones para preguntas de opción múltiple o checkbox"
    )
    is_required: bool = False
    visible_if: Optional[VisibleIfCondition] = None

    model_config = {
        "populate_by_name": True,
        "arbitrary_types_allowed": True,
        "json_encoders": {ObjectId: str},
    }

    @model_validator(mode='after')
    def validate_question(self):
        if self.type in [QuestionType.MULTIPLE_CHOICE, QuestionType.CHECKBOX_GROUP]:
            if not self.options or len(self.options) == 0:
                raise ValueError("Las preguntas de opción múltiple o checkbox deben tener opciones")
        elif self.options is not None:
            self.options = None
        
        return self

class SurveyBase(BaseModel):
    title: str = Field(..., min_length=3, max_length=100)
    description: Optional[str] = Field(None, max_length=500)
    questions: List[Question] = []
    is_public: bool = False

class SurveyCreate(SurveyBase):
    pass

class Survey(SurveyBase):
    id: PyObjectIdStr = Field(default_factory=PyObjectIdStr, alias="_id")
    creator_id: PyObjectIdStr
    created_at: datetime
    updated_at: datetime
    status: str = "created"

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
                "creator_id": "60c728ef69d7a2b2c8e1e3e4",
                "created_at": "2023-01-01T00:00:00Z",
                "updated_at": "2023-01-01T00:00:00Z",
                "is_public": False
            }
        }
    }

class SurveyResponseBase(BaseModel):
    survey_id: PyObjectIdStr
    responder_email: Optional[str] = None
    answers: Dict[str, Any]

    @field_validator('responder_email')
    def validate_email(cls, v):
        if v is None:
            return v
        if "@" not in v:
            raise ValueError("Formato de correo electrónico inválido")
        return v

class SurveyResponse(SurveyResponseBase):
    id: PyObjectIdStr = Field(default_factory=PyObjectIdStr, alias="_id")
    submitted_at: datetime

    model_config = {
        "populate_by_name": True,
        "arbitrary_types_allowed": True,
        "json_encoders": {ObjectId: str},
    }

class SurveyAccessToken(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    survey_id: str
    email: Optional[str] = None  # Puedes eliminarlo si no lo usas
    created_at: datetime = Field(default_factory=datetime.utcnow)
    expires_at: Optional[datetime] = None
    is_used: bool = False