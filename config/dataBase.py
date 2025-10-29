# config/dataBase.py
import os
from pymongo import MongoClient
from dotenv import load_dotenv

load_dotenv()

MONGO_URI = os.getenv("MONGODB_URI", "mongodb://localhost:27017/")

try:
    # initialize client immediately
    client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
    client.admin.command("ping")  # quick ping to confirm connection
    db = client["AgentAssistance"]  # select database
    print("✅ Connected to MongoDB successfully by zuabir shezad")
except Exception as e:
    print("❌ Failed to connect to MongoDB:", e)
    raise

# Optional helper to get db (just in case)
def get_db():
    return db
