from motor.motor_asyncio import AsyncIOMotorClient
from app.config import settings

client: AsyncIOMotorClient = None
db = None 

async def connect_to_mongo():
    global client, db
    try:
        client = AsyncIOMotorClient(settings.MONGO_DETAILS)
        db = client.get_database("surveys_db")
        await db["users"].create_index("username", unique=True)
        await db["users"].create_index("email", unique=True)
        print("Conectado a la base de datos de MongoDB!")
    except Exception as e:
        print(f"Error al conectar a MongoDB: {e}")

async def close_mongo_connection():
    global client
    if client:
        client.close()
        print("Desconectado de la base de datos de MongoDB.")

def get_collection(collection_name: str):
    global db
    if db is None:
        raise Exception("Database not initialized. Call connect_to_mongo() first via FastAPI startup event.")
    return db[collection_name]