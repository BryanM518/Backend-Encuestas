from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.database import connect_to_mongo, close_mongo_connection
from app.routes import survey_routes, auth_routes, survey_response_routes, survey_invitations_routes

app = FastAPI(
    title="API de Encuestas Inteligentes",
    description="Backend para la creación y gestión de encuestas inteligentes.",
    version="0.1.0",
)

# Configuración de CORS
origins = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:8000",
    "http://127.0.0.1:8000",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"]
)

# Eventos de conexión a la base de datos
@app.on_event("startup")
async def startup_event():
    await connect_to_mongo()

@app.on_event("shutdown")
async def shutdown_event():
    await close_mongo_connection()

# Rutas con prefijos corregidos
app.include_router(survey_routes.router, tags=["Surveys"], prefix="/api/survey_api/surveys")
app.include_router(auth_routes.router, tags=["Auth"], prefix="/api/survey_api/auth")
app.include_router(survey_response_routes.router, tags=["Survey Responses"], prefix="/api/survey_api")
app.include_router(survey_invitations_routes.router, tags=["Survey Invitations"], prefix="/api/survey_api/invitations")

@app.get("/", tags=["Root"])
async def read_root():
    return {"message": "Bienvenido a la API de Encuestas Inteligentes"}