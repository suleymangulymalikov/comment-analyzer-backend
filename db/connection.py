import os
from mongoengine import connect, disconnect
from dotenv import load_dotenv

load_dotenv()


def connect_db():
    uri = os.getenv("MONGODB_URI")
    if not uri:
        raise ValueError("MONGODB_URI not found in .env")
    connect(db="comment_analyzer", host=uri)
    print("Connected to MongoDB")


def disconnect_db():
    disconnect()
    print("Disconnected from MongoDB")