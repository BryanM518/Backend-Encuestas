from motor.motor_asyncio import AsyncIOMotorClient
from app.config import settings

client: AsyncIOMotorClient = None
db = None

async def connect_to_mongo():
    global client, db
    try:
        client = AsyncIOMotorClient(settings.MONGO_DETAILS)
        db = client.get_database("surveys_db")

        # Índices únicos para usuarios
        await db["users"].create_index("username", unique=True)
        await db["users"].create_index("email", unique=True)

        # Opcional: índice para tokens si quieres evitar duplicados o acelerar búsquedas
        await db["survey_access_tokens"].create_index("id", unique=True)

        print("✅ Conectado a MongoDB con éxito.")
    except Exception as e:
        print(f"Error al conectar a MongoDB: {e}")

async def close_mongo_connection():
    global client
    if client:
        client.close()
        print("🔌 Desconectado de MongoDB.")

def get_collection(collection_name: str):
    global db
    if db is None:
        raise Exception("La base de datos no está inicializada. Asegúrate de que `connect_to_mongo()` fue llamado en el evento `startup` de FastAPI.")
    return db[collection_name]
