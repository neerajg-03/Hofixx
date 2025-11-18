from flask import Blueprint, request, jsonify, redirect, url_for, session, current_app
from flask_jwt_extended import create_access_token
from google.oauth2 import id_token
from google.auth.transport import requests
import os
import pyotp
import qrcode
import io
import base64
from models import User
from datetime import datetime, timedelta
import random
import string

oauth_bp = Blueprint('oauth', __name__)

# Store OTPs temporarily (in production, use Redis)
otp_storage = {}

@oauth_bp.route('/auth/google', methods=['POST'])
def google_auth():
    """Handle Google OAuth authentication"""
    try:
        data = request.get_json()
        token = data.get('token')
        
        if not token:
            return jsonify({'error': 'Google token is required'}), 400
        
        # Verify the Google token
        try:
            idinfo = id_token.verify_oauth2_token(
                token, 
                requests.Request(), 
                os.getenv('GOOGLE_CLIENT_ID')
            )
            
            # Extract user information
            google_id = idinfo['sub']
            email = idinfo['email']
            name = idinfo.get('name', '')
            picture = idinfo.get('picture', '')
            
        except ValueError as e:
            print(f"Google token verification failed: {str(e)}")
            return jsonify({'error': 'Invalid Google token'}), 400
        
        # Check if user exists
        user = User.objects(email=email).first()
        
        if user:
            # User exists, log them in
            access_token = create_access_token(identity=str(user.id))
            return jsonify({
                'message': 'Login successful',
                'access_token': access_token,
                'user': {
                    'id': str(user.id),
                    'name': user.name,
                    'email': user.email,
                    'role': user.role,
                    'avatar': user.avatar_path or picture
                }
            }), 200
        else:
            # Create new user
            user = User(
                name=name,
                email=email,
                role='user',
                avatar_path=picture,
                password_hash='',  # No password for OAuth users
                google_id=google_id
            )
            user.save()
            
            access_token = create_access_token(identity=str(user.id))
            return jsonify({
                'message': 'Account created and logged in successfully',
                'access_token': access_token,
                'user': {
                    'id': str(user.id),
                    'name': user.name,
                    'email': user.email,
                    'role': user.role,
                    'avatar': user.avatar_path
                }
            }), 201
            
    except Exception as e:
        print(f"Google OAuth error: {str(e)}")
        return jsonify({'error': 'Authentication failed'}), 500

@oauth_bp.route('/auth/otp/send', methods=['POST'])
def send_otp():
    """Send OTP to phone number"""
    try:
        data = request.get_json()
        phone = data.get('phone')
        
        if not phone:
            return jsonify({'error': 'Phone number is required'}), 400
        
        # Generate 6-digit OTP
        otp = ''.join(random.choices(string.digits, k=6))
        
        # Store OTP with expiration (5 minutes)
        otp_storage[phone] = {
            'otp': otp,
            'expires': datetime.now() + timedelta(minutes=5),
            'attempts': 0
        }
        
        # Note: SMS is now handled by Firebase on the frontend
        # This endpoint is kept for backward compatibility
        print(f"OTP for {phone}: {otp} (SMS handled by Firebase)")
        
        return jsonify({
            'message': 'OTP sent successfully',
            'phone': phone
        }), 200
        
    except Exception as e:
        print(f"OTP send error: {str(e)}")
        return jsonify({'error': 'Failed to send OTP'}), 500

@oauth_bp.route('/auth/otp/verify', methods=['POST'])
def verify_otp():
    """Verify OTP and login/register user"""
    try:
        data = request.get_json()
        phone = data.get('phone')
        otp = data.get('otp')
        name = data.get('name', '')
        
        if not phone or not otp:
            return jsonify({'error': 'Phone number and OTP are required'}), 400
        
        # Check if OTP exists and is not expired
        if phone not in otp_storage:
            return jsonify({'error': 'OTP not found or expired'}), 400
        
        stored_data = otp_storage[phone]
        
        # Check expiration
        if datetime.now() > stored_data['expires']:
            del otp_storage[phone]
            return jsonify({'error': 'OTP expired'}), 400
        
        # Check attempts
        if stored_data['attempts'] >= 3:
            del otp_storage[phone]
            return jsonify({'error': 'Too many attempts'}), 400
        
        # Verify OTP
        if stored_data['otp'] != otp:
            stored_data['attempts'] += 1
            return jsonify({'error': 'Invalid OTP'}), 400
        
        # OTP is valid, clean up
        del otp_storage[phone]
        
        # Check if user exists
        user = User.objects(phone=phone).first()
        
        if user:
            # User exists, log them in
            access_token = create_access_token(identity=str(user.id))
            return jsonify({
                'message': 'Login successful',
                'access_token': access_token,
                'user': {
                    'id': str(user.id),
                    'name': user.name,
                    'email': user.email,
                    'phone': user.phone,
                    'role': user.role,
                    'avatar': user.avatar_path
                }
            }), 200
        else:
            # Create new user
            if not name:
                return jsonify({'error': 'Name is required for new users'}), 400
            
            user = User(
                name=name,
                phone=phone,
                role='user',
                password_hash='',  # No password for OTP users
                email=''  # Will be set later if needed
            )
            user.save()
            
            access_token = create_access_token(identity=str(user.id))
            return jsonify({
                'message': 'Account created and logged in successfully',
                'access_token': access_token,
                'user': {
                    'id': str(user.id),
                    'name': user.name,
                    'email': user.email,
                    'phone': user.phone,
                    'role': user.role,
                    'avatar': user.avatar_path
                }
            }), 201
            
    except Exception as e:
        print(f"OTP verification error: {str(e)}")
        return jsonify({'error': 'OTP verification failed'}), 500

@oauth_bp.route('/auth/otp/resend', methods=['POST'])
def resend_otp():
    """Resend OTP to phone number"""
    try:
        data = request.get_json()
        phone = data.get('phone')
        
        if not phone:
            return jsonify({'error': 'Phone number is required'}), 400
        
        # Generate new OTP
        otp = ''.join(random.choices(string.digits, k=6))
        
        # Store new OTP
        otp_storage[phone] = {
            'otp': otp,
            'expires': datetime.now() + timedelta(minutes=5),
            'attempts': 0
        }
        
        # Note: SMS is now handled by Firebase on the frontend
        # This endpoint is kept for backward compatibility
        print(f"New OTP for {phone}: {otp} (SMS handled by Firebase)")
        
        return jsonify({
            'message': 'OTP resent successfully',
            'phone': phone
        }), 200
        
    except Exception as e:
        print(f"OTP resend error: {str(e)}")
        return jsonify({'error': 'Failed to resend OTP'}), 500

