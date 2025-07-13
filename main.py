# main.py
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.routes import survey_routes

app = FastAPI(
    title="Backend de Plataforma de Encuestas Inteligentes",
    description="API para gestionar encuestas, plantillas y respuestas.",
    version="0.1.0",
)

# Configuración de CORS
origins = [
    "http://localhost:8081",  # La URL donde corre tu frontend de Vue.js
    "http://127.0.0.1:8081",  # Alternativa de localhost
    # Añade aquí cualquier otro origen si tu frontend se despliega en otro lugar
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"], # Permite todos los métodos (GET, POST, PUT, DELETE, etc.)
    allow_headers=["*"], # Permite todas las cabeceras
)

app.include_router(survey_routes.router, prefix="/api/v1", tags=["Encuestas"])

@app.get("/")
async def read_root():
    return {"message": "¡Bienvenido a la API de la Plataforma de Encuestas Inteligentes!"}