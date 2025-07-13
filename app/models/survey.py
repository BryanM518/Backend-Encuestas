# app/models.py
from pydantic import BaseModel, Field, BeforeValidator, AfterValidator
from typing import Optional, List, Dict, Any, Annotated
from datetime import datetime
from bson import ObjectId

def convert_objectid_to_str(v: Any) -> str:
    return str(v)


ObjectIdStr = Annotated[
    str,
    BeforeValidator(str),
    AfterValidator(lambda v: ObjectId(v)) 
]

class PyObjectId(ObjectId):
    @classmethod
    def __get_validators__(cls):
        yield cls.validate

    @classmethod
    def validate(cls, v, info):
        if not ObjectId.is_valid(v):
            raise ValueError("Invalid ObjectId")
        return ObjectId(v)

    @classmethod
    def __get_pydantic_json_schema__(cls, core_schema, handler):
        field_schema = handler(core_schema)
        field_schema['type'] = 'string'
        return field_schema


class Question(BaseModel):
    id: PyObjectId = Field(default_factory=PyObjectId, alias="_id")
    type: str 
    text: str
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
    title: str
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

    model_config = {
        "populate_by_name": True, 
        "arbitrary_types_allowed": True,
        "json_encoders": {ObjectId: str}, 
        "json_schema_extra": {
            "example": {
                "title": "Encuesta de Clima Laboral",
                "description": "Una encuesta para evaluar el ambiente de trabajo.",
                "questions": [], 
                "status": "created"
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

