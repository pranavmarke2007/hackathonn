
from pymongo import MongoClient

client = MongoClient("mongodb+srv://pranavmarke66_db_user:G9Zy2vXLHTBXYftM@cluster0.ny5xzbo.mongodb.net/?appName=Cluster0")
db = client["ai_scheduler"]

emails_collection = db["emails"]

# optional but recommended
emails_collection.create_index("mail_id", unique=True)