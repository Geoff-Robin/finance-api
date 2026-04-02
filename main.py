from fastapi import FastAPI, Depends
from fastapi_jwt_auth import AuthJWT
from dotenv import load_dotenv

load_dotenv()

app: FastAPI = FastAPI()

@AuthJWT.load_config
def get_config():
    return {
        "authjwt_secret_key": os["JWT_SECRET_KEY"]
    }
