from motor.motor_asyncio import AsyncIOMotorClient
import os
from dotenv import load_dotenv

load_dotenv()

MONGO_DETAILS = os.getenv("MONGO_DETAILS")

if not MONGO_DETAILS:
    raise ValueError("La variable de entorno MONGO_DETAILS no está configurada.")

client = AsyncIOMotorClient(MONGO_DETAILS)

database = client.smart_surveys_db

def get_collection(collection_name: str):
    return database[collection_name]