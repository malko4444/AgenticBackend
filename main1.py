# # main.py
# import os
# import uuid
# import re
# import datetime
# from typing import Optional, List, Dict, Any
# from config.dataBase import get_db  # function now returns db directly

# from dotenv import load_dotenv
# from fastapi import FastAPI, Depends, Body, HTTPException, Query
# from fastapi.middleware.cors import CORSMiddleware
# from fastapi.responses import JSONResponse
# from pydantic import BaseModel
# import httpx

# from utils.utils import verify_token
# from routes import auth_routes

# load_dotenv()

# WEATHER_API_KEY = os.getenv("WEATHER_API_KEY")
# GEMINI_API_KEY = os.getenv("GOOGLE_API_KEY")

# app = FastAPI(title="Climate-Aware Todo Assistant")

# app.add_middleware(
#     CORSMiddleware,
#     allow_origins=["*"],
#     allow_credentials=True,
#     allow_methods=["*"],
#     allow_headers=["*"],
# )

# # get db
# db = get_db()

# # Ensure indexes on startup
# @app.on_event("startup")
# def ensure_indexes():
#     try:
#         db.user_todos.create_index("login_user_id")
#         db.ai_todos.create_index("login_user_id")
#         db.ai_todos.create_index("created_at")
#         print("✅ MongoDB indexes ensured")
#     except Exception as e:
#         print("❌ Failed to ensure indexes:", e)

# # --- Helper: detect language ---
# def detect_language(text: str) -> str:
#     if re.search(r'[\u0600-\u06FF]', text):
#         return "urdu"
#     latin_chars = len(re.findall(r'[A-Za-z]', text))
#     return "english"

# # --- Weather + AQI ---
# async def fetch_weather_and_aqi(city: str) -> Dict[str, Any]:
#     if not WEATHER_API_KEY:
#         return {"error": "WEATHER_API_KEY not configured."}
#     async with httpx.AsyncClient(timeout=10.0) as client:
#         try:
#             geo_resp = await client.get(
#                 f"http://api.openweathermap.org/geo/1.0/direct?q={city}&limit=1&appid={WEATHER_API_KEY}"
#             )
#             geo_resp.raise_for_status()
#             geo_data = geo_resp.json()
#             if not geo_data:
#                 return {"error": f"City '{city}' not found."}
#             lat, lon = geo_data[0]["lat"], geo_data[0]["lon"]

#             weather_resp = await client.get(
#                 f"http://api.openweathermap.org/data/2.5/weather?lat={lat}&lon={lon}&appid={WEATHER_API_KEY}&units=metric"
#             )
#             weather_resp.raise_for_status()
#             weather_data = weather_resp.json()

#             aqi_resp = await client.get(
#                 f"http://api.openweathermap.org/data/2.5/air_pollution?lat={lat}&lon={lon}&appid={WEATHER_API_KEY}"
#             )
#             aqi_resp.raise_for_status()
#             aqi_data = aqi_resp.json()
#         except Exception as e:
#             return {"error": f"Weather/AQI fetch failed: {e}"}

#     condition = weather_data["weather"][0]["description"].capitalize()
#     temp_c = weather_data["main"]["temp"]
#     feelslike_c = weather_data["main"]["feels_like"]
#     aqi = aqi_data["list"][0]["main"]["aqi"]
#     components = aqi_data["list"][0]["components"]
#     pm2_5 = components.get("pm2_5")
#     no2 = components.get("no2")
#     co = components.get("co")

#     return {
#         "city": city,
#         "condition": condition,
#         "temp_c": temp_c,
#         "feelslike_c": feelslike_c,
#         "pm2_5": pm2_5,
#         "no2": no2,
#         "co": co,
#         "aqi": aqi,
#         "raw": {"weather": weather_data, "air_pollution": aqi_data},
#     }

# # --- Climate adaptation logic ---
# def climate_adaptation_suggestion(
#     todo_text: str, planned_time: Optional[str], weather: Dict[str, Any], language: str
# ) -> Dict[str, Any]:
#     aqi_pm25 = float(weather.get("pm2_5", 0))
#     temp_c = weather.get("temp_c")
#     condition = (weather.get("condition") or "").lower()
#     now = datetime.datetime.utcnow()

#     suggested_time = None
#     reason = []
#     advice_lines: List[str] = []

#     if aqi_pm25 >= 100:
#         reason.append("high_aqi")
#         advice_lines.append({
#             "english": "Air quality is poor. Avoid outdoor activities — prefer indoor alternatives or a mask.",
#             "urdu": "ہوا کی آلودگی زیادہ ہے۔ باہر کے کام سے گریز کریں — اندر کریں یا ماسک پہنیں۔"
#         }[language])
#         suggested_time = (now + datetime.timedelta(days=1)).replace(hour=6, minute=0).isoformat()

#     if temp_c >= 37:
#         reason.append("heat_wave")
#         advice_lines.append({
#             "english": "Temperatures are high. Move outdoor tasks earlier or indoors.",
#             "urdu": "درجہ حرارت بہت زیادہ ہے۔ باہر کے کام صبح جلد کریں یا انہیں اندر منتقل کریں۔"
#         }[language])
#         if not suggested_time:
#             suggested_time = (now + datetime.timedelta(days=1)).replace(hour=7, minute=0).isoformat()

#     if any(k in condition for k in ["storm", "thunder", "rain", "shower", "snow", "sleet"]):
#         reason.append("storm_or_rain")
#         advice_lines.append({
#             "english": "Rain or storm expected. Consider indoor alternatives.",
#             "urdu": "بارش یا طوفان متوقع ہے۔ باہر کے کام منتقل کریں یا انہیں آن لائن کریں۔"
#         }[language])
#         if not suggested_time:
#             suggested_time = None

#     if not advice_lines:
#         advice_lines.append({
#             "english": "Conditions look fine. Scheduled as requested.",
#             "urdu": "موسم مناسب لگ رہا ہے۔ آپ کی خواہش کے مطابق شیڈیول کیا جا رہا ہے۔"
#         }[language])

#     paragraph = " ".join(advice_lines)
#     summary = {"english": f"AI suggestion: {paragraph}", "urdu": f"AI مشورہ: {paragraph}"}[language]

#     return {"advice_text": summary, "suggested_time": suggested_time, "reason": reason, "raw_advice": paragraph}

# # --- DB helpers ---
# def save_user_todo_to_db(user_id, language, text, planned_time, metadata):
#     item = {
#         "login_user_id": user_id,
#         "language": language,
#         "text": text,
#         "planned_time": planned_time,
#         "status": "pending",
#         "metadata": metadata,
#         "created_at": datetime.datetime.utcnow()
#     }
#     res = db.user_todos.insert_one(item)
#     item["_id"] = str(res.inserted_id)
#     return item

# def save_ai_todo_to_db(user_id, language, advice_text, suggested_time, reason, related_user_todo_id=None):
#     item = {
#         "login_user_id": user_id,
#         "language": language,
#         "advice_text": advice_text,
#         "suggested_time": suggested_time,
#         "reason": reason,
#         "related_user_todo_id": related_user_todo_id,
#         "created_at": datetime.datetime.utcnow()
#     }
#     res = db.ai_todos.insert_one(item)
#     item["_id"] = str(res.inserted_id)
#     return item

# # --- Request models ---
# class ChatRequest(BaseModel):
#     text: str

   
# def extract_time_and_city(text: str):
#     """Simple regex-based extraction for time and city from text"""
#     # Example: "at 5 pm" or "at 17:00"
#     time_pattern = r"(?:at\s+)?(\d{1,2}(?::\d{2})?\s*(?:am|pm|AM|PM)?)"
#     city_pattern = r"in\s+([A-Z][a-zA-Z]+)"

#     time_match = re.search(time_pattern, text)
#     city_match = re.search(city_pattern, text)
#     print("the city pattern",city)

#     planned_time = time_match.group(1) if time_match else None
#     city = city_match.group(1) if city_match else None
#     print("city",city)

#     return planned_time, city

# # --------------------------
# # Helper to serialize datetime in todos
# # --------------------------
# def serialize_todo(todo: dict) -> dict:
#     """Return a copy of todo with datetime converted to ISO string."""
#     todo_copy = todo.copy()
#     if todo_copy.get("created_at") and isinstance(todo_copy["created_at"], datetime.datetime):
#         todo_copy["created_at"] = todo_copy["created_at"].isoformat()
#     # if related fields may contain datetime, handle here
#     return todo_copy


# # --- Endpoints ---
# # --------------------------
# # Chat endpoint
# # --------------------------
# @app.post("/chat")
# async def chat_endpoint(payload: ChatRequest = Body(...), user_from_token=Depends(verify_token)):
#     user_id = user_from_token.get("user_id")
#     if not user_id:
#         raise HTTPException(status_code=401, detail="Unauthorized")

#     text = payload.text.strip()
#     if not text:
#         return JSONResponse(status_code=200, content={"reply": "Please tell me what your task is."})

#     # Extract time and city from paragraph
#     planned_time, city = extract_time_and_city(text)
#     city = city or "Karachi"

#     # Handle missing time
#     if not planned_time and "add it" not in text.lower():
#         return JSONResponse(
#             status_code=200,
#             content={"reply": "Please provide the time for your task, or say 'just add it' if you want to skip the time."}
#         )

#     # Fetch weather info
#     weather = await fetch_weather_and_aqi(city)
#     language = "english"

#     # Apply AI adaptation
#     adaptation = climate_adaptation_suggestion(text, planned_time, weather, language)

#     # Save todo (skip time if user said “just add it”)
#     metadata = {"city_used": city, "weather_snapshot": weather}
#     user_todo = save_user_todo_to_db(
#         user_id=user_id,
#         language=language,
#         text=text,
#         planned_time=planned_time if planned_time else None,
#         metadata=metadata
#     )

#     # Save AI advice
#     ai_todo = save_ai_todo_to_db(
#         user_id=user_id,
#         language=language,
#         advice_text=adaptation["advice_text"],
#         suggested_time=adaptation["suggested_time"],
#         reason=adaptation["reason"],
#         related_user_todo_id=user_todo["_id"]
#     )

#     # Compose conversational reply
#     response_text = (
#         f"I've added your task: '{text}'.\n"
#         f"Suggested time: {adaptation['suggested_time']}.\n"
#         f"Weather in {city}: {weather.get('condition')} at {weather.get('temp_c')}°C.\n"
#         f"AI advice: {adaptation['advice_text']}"
#     )

#     return JSONResponse(status_code=200, content={"reply": response_text})

# @app.get("/user_todos")
# def get_user_todos(user_from_token=Depends(verify_token)):
#     user_id = user_from_token.get("user_id")
#     if not user_id:
#         raise HTTPException(status_code=401)
#     items = []
#     for doc in db.user_todos.find({"login_user_id": user_id}).sort("created_at", -1):
#         doc["_id"] = str(doc["_id"])
#         if doc.get("created_at"):
#             doc["created_at"] = doc["created_at"].isoformat()
#         items.append(doc)
#     return {"status": "success", "data": items}

# @app.get("/ai_todos")
# def get_ai_todos(user_from_token=Depends(verify_token)):
#     user_id = user_from_token.get("user_id")
#     if not user_id:
#         raise HTTPException(status_code=401)
#     items = []
#     for doc in db.ai_todos.find({"login_user_id": user_id}).sort("created_at", -1):
#         doc["_id"] = str(doc["_id"])
#         if doc.get("created_at"):
#             doc["created_at"] = doc["created_at"].isoformat()
#         items.append(doc)
#     return {"status": "success", "data": items}

# # include auth routes
# app.include_router(auth_routes.auth_router, prefix="/auth", tags=["Auth"])

# @app.get("/")
# def health():
#     return {"message": "Climate-Aware Todo Assistant - running"}

# if __name__ == "__main__":
#     import uvicorn
#     uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
