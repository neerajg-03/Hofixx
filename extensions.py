from flask_jwt_extended import JWTManager
from flask_bcrypt import Bcrypt
from flask_socketio import SocketIO
from mongoengine import connect
import os

jwt = JWTManager()
bcrypt = Bcrypt()
socketio = SocketIO(cors_allowed_origins="*")

def init_mongodb():
    """Initialize MongoDB connection"""
    # Use MongoDB Atlas connection string if provided
    mongodb_uri = os.getenv(
        'MONGODB_URI',
        'mongodb://localhost:27017/hofix'  # fallback for local development
    )

    db_name = os.getenv('MONGODB_DB_NAME', 'hofix')  # can override if needed

    connect(
        db=db_name,
        host=mongodb_uri,
        alias='default'
    )
