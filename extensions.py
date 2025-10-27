from mongoengine import connect
import os

def init_mongodb():
    """Initialize MongoDB connection"""
    mongodb_uri = os.getenv('MONGODB_URI')
    if not mongodb_uri:
        raise ValueError("MONGODB_URI not found in environment variables")

    # Explicitly set alias and database name
    connect(
        host=mongodb_uri,
        alias="default",
        db="HofixDb",
        connect=False
    )
