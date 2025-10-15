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
    mongodb_uri = os.getenv('MONGODB_URI', 'mongodb://localhost:27017/hofix')
    connect(host=mongodb_uri)

