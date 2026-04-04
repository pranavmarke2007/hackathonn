import os
from dotenv import load_dotenv
from pymongo import MongoClient

load_dotenv()

client = MongoClient(os.getenv("MONGO_URI"))
db = client["pranavmarke"]   # 👈 your DB name here

emails_collection = db["emails"]