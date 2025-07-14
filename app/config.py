import os
from dotenv import load_dotenv

load_dotenv()

class Settings:
    MONGO_DETAILS: str = os.getenv("MONGO_DETAILS", "mongodb://localhost:27017")
    SECRET_KEY: str = os.getenv("SECRET_KEY", "172267a64730654723814623cf89dd310a2c36bbaf1aca860a0242e92883ec43")
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", 30))

settings = Settings()