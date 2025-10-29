from jose import jwt, JWTError
from datetime import datetime, timedelta
from fastapi import Request, HTTPException, status
from fastapi.responses import JSONResponse
from bson import ObjectId

SECRET_KEY = "SUPER_SECRET_JWT_KEY"  # Replace with env var in production
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60

# --- CREATE TOKEN ---
def create_access_token(data: dict):
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


# --- VERIFY TOKEN DEPENDENCY ---

def verify_token(request: Request):
    """Verify JWT token from the Authorization header."""
    auth_header = request.headers.get("Authorization")
    print("the token",auth_header)

    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authorization header missing or invalid. Use Bearer <token>."
        )

    token = auth_header.split(" ")[1]

    try:
        # Decode and verify the JWT

        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        print("the fdecoded token", payload)
        return payload  # e.g. { "user_id": "...", "user_name": "...", "user_email": "..." }

    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token. Please log in again."
        )
