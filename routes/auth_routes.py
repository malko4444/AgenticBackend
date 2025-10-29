from fastapi import APIRouter, HTTPException, status, Response, Depends
from pydantic import BaseModel, EmailStr
from config.dataBase import db
from passlib.context import CryptContext
from bson import ObjectId
from utils.utils import create_access_token, verify_token
import bcrypt
print(bcrypt.__version__)


print("debugger123", db.users.find_one({"email": "zubairdsds@exsdsadample.com"}))
auth_router = APIRouter()
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")




# ---------- SCHEMAS ----------
class SignupModel(BaseModel):
    name: str
    email: EmailStr
    password: str

class LoginModel(BaseModel):
    email: EmailStr
    password: str

# ---------- SIGNUP ----------
@auth_router.post("/signup")
def signup_user(user: SignupModel, response: Response):
    print("the section block",user.name)
    existing_user = db.users.find_one({"email": user.email})
    print("the user in the db", existing_user)
    if existing_user:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email already registered")

    hashed_password = pwd_context.hash(user.password)
    print("hashPassword", hashed_password)

    new_user = {
        "name": user.name,
        "email": user.email,
        "password": hashed_password
    }

    result = db.users.insert_one(new_user)
    user_id = str(result.inserted_id)

    token_data = {
        "user_id": user_id,
        "user_name": user.name,
        "user_email": user.email
    }

    token = create_access_token(token_data)
    response.set_cookie(key="access_token", value=token, httponly=True)

    return {
        "message": "User registered successfully",
        "token": token,
        "user": token_data
    }

# ---------- LOGIN ----------
@auth_router.post("/login")
def login_user(user: LoginModel, response: Response):
    print("debugger",db.users.find_one({"email": "zubairdsds@exsdsadample.com"}))
    
    db_user = db.users.find_one({"email": user.email})
    if not db_user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    if not pwd_context.verify(user.password, db_user["password"]):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid password")

    token_data = {
        "user_id": str(db_user["_id"]),
        "user_name": db_user["name"],
        "user_email": db_user["email"]
    }

    token = create_access_token(token_data)
    response.set_cookie(key="access_token", value=token, httponly=True)

    return {
        "message": "Login successful",
        "token": token,
        "user": token_data
    }

# ---------- PROFILE (Protected Route) ----------
@auth_router.get("/profile")
def profile(user_from_token=Depends(verify_token)):
    return {
        "message": "User profile fetched successfully",
        "user": user_from_token
    }
