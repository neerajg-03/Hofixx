"""
Firebase Authentication Routes
Handles Google OAuth and Phone OTP authentication via Firebase
"""

from flask import Blueprint, request, jsonify, session
from flask_jwt_extended import create_access_token, jwt_required, get_jwt_identity
import firebase_admin
from firebase_admin import credentials, auth
import os
from models import User
import json

firebase_auth_bp = Blueprint('firebase_auth', __name__)

# Initialize Firebase Admin SDK
def init_firebase():
    """Initialize Firebase Admin SDK"""
    try:
        # Check if Firebase is already initialized
        if not firebase_admin._apps:
            # Try to get service account key from environment
            service_account_path = os.getenv('FIREBASE_SERVICE_ACCOUNT_PATH')
            
            if service_account_path and os.path.exists(service_account_path):
                # Use service account file
                cred = credentials.Certificate(service_account_path)
                firebase_admin.initialize_app(cred)
            else:
                # Use default credentials (for production with proper setup)
                firebase_admin.initialize_app()
                
        return True
    except Exception as e:
        print(f"Firebase initialization error: {e}")
        return False

# Initialize Firebase on module load
firebase_initialized = init_firebase()

@firebase_auth_bp.route('/api/firebase/verify-token', methods=['POST'])
def verify_firebase_token():
    """Verify Firebase ID token and create/update user"""
    try:
        data = request.get_json()
        id_token = data.get('idToken')
        
        if not id_token:
            return jsonify({'error': 'No ID token provided'}), 400
        
        if not firebase_initialized:
            return jsonify({'error': 'Firebase not initialized'}), 500
        
        # Verify the Firebase ID token
        decoded_token = auth.verify_id_token(id_token)
        uid = decoded_token['uid']
        
        # Get user info from Firebase
        user_record = auth.get_user(uid)
        
        # Extract user information
        email = user_record.email
        phone = user_record.phone_number
        name = user_record.display_name or 'User'
        photo_url = user_record.photo_url
        
        # Check if user exists in our database
        user = None
        
        # Try to find by email first
        if email:
            user = User.objects(email=email).first()
        
        # If not found by email, try by phone
        if not user and phone:
            user = User.objects(phone=phone).first()
        
        # If not found by phone, try by Firebase UID
        if not user:
            user = User.objects(firebase_uid=uid).first()
        
        # Create new user if doesn't exist
        if not user:
            user = User(
                firebase_uid=uid,
                name=name,
                email=email,
                phone=phone,
                profile_picture=photo_url,
                role='user'  # Default role
            )
            user.save()
            print(f"Created new user: {name} ({email or phone})")
        else:
            # Update existing user with Firebase info
            user.firebase_uid = uid
            if name and not user.name:
                user.name = name
            if email and not user.email:
                user.email = email
            if phone and not user.phone:
                user.phone = phone
            if photo_url and not user.profile_picture:
                user.profile_picture = photo_url
            user.save()
            print(f"Updated existing user: {name} ({email or phone})")
        
        # Create JWT token for our app
        access_token = create_access_token(identity=str(user.id))
        
        return jsonify({
            'success': True,
            'access_token': access_token,
            'user': {
                'id': str(user.id),
                'name': user.name,
                'email': user.email,
                'phone': user.phone,
                'role': user.role,
                'profile_picture': user.profile_picture
            }
        })
        
    except auth.InvalidIdTokenError:
        return jsonify({'error': 'Invalid Firebase token'}), 401
    except Exception as e:
        print(f"Firebase token verification error: {e}")
        return jsonify({'error': 'Token verification failed'}), 500

@firebase_auth_bp.route('/api/firebase/send-otp', methods=['POST'])
def send_otp():
    """Send OTP to phone number (handled by Firebase on frontend)"""
    try:
        data = request.get_json()
        phone_number = data.get('phoneNumber')
        
        if not phone_number:
            return jsonify({'error': 'Phone number required'}), 400
        
        # Firebase handles OTP sending on the frontend
        # This endpoint is just for logging/analytics
        print(f"OTP requested for: {phone_number}")
        
        return jsonify({
            'success': True,
            'message': 'OTP will be sent via Firebase'
        })
        
    except Exception as e:
        print(f"Send OTP error: {e}")
        return jsonify({'error': 'Failed to send OTP'}), 500

@firebase_auth_bp.route('/api/firebase/verify-phone', methods=['POST'])
def verify_phone():
    """Verify phone number OTP (handled by Firebase on frontend)"""
    try:
        data = request.get_json()
        verification_id = data.get('verificationId')
        otp_code = data.get('otpCode')
        
        if not verification_id or not otp_code:
            return jsonify({'error': 'Verification ID and OTP code required'}), 400
        
        # Firebase handles phone verification on the frontend
        # This endpoint is just for logging/analytics
        print(f"Phone verification attempted: {verification_id}")
        
        return jsonify({
            'success': True,
            'message': 'Phone verification handled by Firebase'
        })
        
    except Exception as e:
        print(f"Phone verification error: {e}")
        return jsonify({'error': 'Phone verification failed'}), 500

@firebase_auth_bp.route('/api/firebase/config', methods=['GET'])
def get_firebase_config():
    """Get Firebase configuration for frontend"""
    try:
        config = {
            'apiKey': os.getenv('FIREBASE_API_KEY'),
            'authDomain': os.getenv('FIREBASE_AUTH_DOMAIN'),
            'projectId': os.getenv('FIREBASE_PROJECT_ID'),
            'storageBucket': os.getenv('FIREBASE_STORAGE_BUCKET'),
            'messagingSenderId': os.getenv('FIREBASE_MESSAGING_SENDER_ID'),
            'appId': os.getenv('FIREBASE_APP_ID')
        }
        
        # Check if all required config is present
        missing_config = [key for key, value in config.items() if not value]
        
        if missing_config:
            return jsonify({
                'error': f'Missing Firebase configuration: {", ".join(missing_config)}'
            }), 500
        
        return jsonify(config)
        
    except Exception as e:
        print(f"Firebase config error: {e}")
        return jsonify({'error': 'Failed to get Firebase configuration'}), 500

@firebase_auth_bp.route('/api/firebase/status', methods=['GET'])
def firebase_status():
    """Check Firebase initialization status"""
    return jsonify({
        'initialized': firebase_initialized,
        'message': 'Firebase is ready' if firebase_initialized else 'Firebase not initialized'
    })



















