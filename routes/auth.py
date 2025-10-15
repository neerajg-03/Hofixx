from flask import Blueprint, request, jsonify, render_template, make_response
from flask_jwt_extended import create_access_token, jwt_required, get_jwt_identity, set_access_cookies, unset_jwt_cookies
from werkzeug.utils import secure_filename
import os
from extensions import bcrypt
from models import User, Provider
from bson import ObjectId

auth_bp = Blueprint('auth', __name__)


@auth_bp.get('/login')
def login_page():
    return render_template('login.html')


@auth_bp.get('/signup')
def signup_page():
    return render_template('signup.html')


@auth_bp.post('/signup')
def signup():
    data = request.get_json() or request.form
    name = data.get('name')
    email = data.get('email')
    phone = data.get('phone')
    password = data.get('password')
    role = (data.get('role') or 'user').lower()

    if not all([name, email, password, role]):
        return jsonify({'message': 'Missing fields'}), 400

    if User.objects(email=email).first():
        return jsonify({'message': 'Email already exists'}), 400

    password_hash = bcrypt.generate_password_hash(password).decode('utf-8')
    user = User(name=name, email=email, phone=phone, role=role, password_hash=password_hash)
    user.save()

    if role == 'provider':
        provider = Provider(user=user, skills=['Electrician', 'Plumber'], availability=True)
        provider.save()
        # Update user with provider reference
        user.provider_profile = provider
        user.save()

    token = create_access_token(identity=str(user.id), additional_claims={'role': user.role, 'name': user.name, 'email': user.email})
    response = make_response(jsonify({'access_token': token}))
    set_access_cookies(response, token)
    return response


@auth_bp.post('/login')
def login():
    data = request.get_json() or request.form
    email = data.get('email')
    password = data.get('password')

    if not all([email, password]):
        return jsonify({'message': 'Missing fields'}), 400

    user = User.objects(email=email).first()
    if not user or not bcrypt.check_password_hash(user.password_hash, password):
        return jsonify({'message': 'Invalid credentials'}), 401

    token = create_access_token(identity=str(user.id), additional_claims={'role': user.role, 'name': user.name, 'email': user.email})
    response = make_response(jsonify({'access_token': token}))
    set_access_cookies(response, token)
    return response




@auth_bp.get('/dashboard/provider')
@jwt_required(optional=True)
def dashboard_provider_page():
    return render_template('dashboard_provider.html')


@auth_bp.get('/booking')
@jwt_required(optional=True)
def booking_page():
    return render_template('booking.html')


@auth_bp.get('/tracking/<int:booking_id>')
@jwt_required(optional=True)
def tracking_page(booking_id):
    return render_template('tracking.html', booking_id=booking_id)

@auth_bp.get('/track-provider')
@jwt_required(optional=True)
def track_provider_page():
    return render_template('track_provider.html')

@auth_bp.get('/test-tracking')
def test_tracking_page():
    return render_template('test_tracking.html')

@auth_bp.get('/service-request/<request_id>/quotes')
@jwt_required(optional=True)
def service_request_quotes_page(request_id):
    return render_template('service_request_quotes.html')

@auth_bp.get('/provider/requests')
@jwt_required(optional=True)
def provider_requests_page():
    return render_template('provider_requests.html')

@auth_bp.get('/provider/service-requests')
@jwt_required(optional=True)
def provider_service_requests_page():
    return render_template('provider_service_requests.html')

@auth_bp.get('/create-service-request')
@jwt_required(optional=True)
def create_service_request_page():
    return render_template('create_service_request.html')


@auth_bp.get('/me')
@jwt_required()
def get_current_user():
    """Get current user data"""
    ident = get_jwt_identity()
    user_id = str(ident) if isinstance(ident, str) else str(ident['id'])
    
    try:
        user = User.objects(id=ObjectId(user_id)).first()
        if not user:
            return jsonify({'message': 'User not found'}), 404
        
        user_data = {
            'id': str(user.id),
            'name': user.name,
            'email': user.email,
            'phone': user.phone,
            'role': user.role,
            'rating': user.rating,
            'credits': user.credits,
            'created_at': user.created_at.isoformat() if user.created_at else None,
            'provider_profile': None
        }
        
        # Add provider profile if exists
        if user.provider_profile:
            user_data['provider_profile'] = {
                'id': str(user.provider_profile.id),
                'skills': user.provider_profile.skills,
                'availability': user.provider_profile.availability
            }
        
        return jsonify(user_data)
        
    except Exception as e:
        return jsonify({'message': 'Invalid user ID'}), 400


@auth_bp.get('/profile')
@jwt_required(optional=True)
def profile_page():
    return render_template('profile.html')


@auth_bp.get('/admin/services')
@jwt_required(optional=True)
def admin_services_page():
    return render_template('admin_services.html')


@auth_bp.get('/me')
@jwt_required()
def get_me():
    ident = get_jwt_identity()
    user_id = str(ident) if isinstance(ident, str) else str(ident.get('id') or ident)
    user = User.objects(id=user_id).first()
    if not user:
        return jsonify({'message': 'User not found'}), 404
    return jsonify({
        'id': str(user.id),
        'name': user.name,
        'email': user.email,
        'phone': user.phone,
        'role': user.role,
        'address': user.address,
        'latitude': user.latitude,
        'longitude': user.longitude,
        'avatar_url': (request.url_root.rstrip('/') + '/' + os.path.join('static', user.avatar_path).replace('\\','/')) if user.avatar_path else None,
        'credits': user.credits or 0,
        'rating': user.rating or 0
    })


@auth_bp.post('/profile/update')
@jwt_required()
def update_profile():
    ident = get_jwt_identity()
    user_id = str(ident) if isinstance(ident, str) else str(ident.get('id') or ident)
    user = User.objects(id=user_id).first()
    if not user:
        return jsonify({'message': 'User not found'}), 404

    data = request.get_json() or {}
    name = data.get('name')
    email = data.get('email')
    phone = data.get('phone')
    if email and User.objects(email=email, id__ne=user.id).first():
        return jsonify({'message': 'Email already in use'}), 400
    if name: user.name = name
    if email: user.email = email
    if phone: user.phone = phone
    user.save()
    return jsonify({'message': 'Profile updated'})


@auth_bp.post('/profile/password')
@jwt_required()
def change_password():
    ident = get_jwt_identity()
    user_id = str(ident) if isinstance(ident, str) else str(ident.get('id') or ident)
    user = User.objects(id=user_id).first()
    if not user:
        return jsonify({'message': 'User not found'}), 404
    data = request.get_json() or {}
    current = data.get('current_password')
    new = data.get('new_password')
    if not current or not new:
        return jsonify({'message': 'Missing fields'}), 400
    if not bcrypt.check_password_hash(user.password_hash, current):
        return jsonify({'message': 'Current password incorrect'}), 400
    user.password_hash = bcrypt.generate_password_hash(new).decode('utf-8')
    user.save()
    return jsonify({'message': 'Password changed'})


@auth_bp.post('/profile/avatar')
@jwt_required()
def upload_avatar():
    ident = get_jwt_identity()
    user_id = str(ident) if isinstance(ident, str) else str(ident.get('id') or ident)
    user = User.objects(id=user_id).first()
    if not user:
        return jsonify({'message': 'User not found'}), 404
    if 'avatar' not in request.files:
        return jsonify({'message': 'No file provided'}), 400
    file = request.files['avatar']
    if not file or not file.filename:
        return jsonify({'message': 'Invalid file'}), 400
    filename = secure_filename(file.filename)
    upload_dir = os.path.join('static', 'images', 'avatars')
    os.makedirs(upload_dir, exist_ok=True)
    path = os.path.join(upload_dir, filename)
    file.save(path)
    user.avatar_path = os.path.join('images', 'avatars', filename).replace('\\','/')
    user.save()
    return jsonify({'message': 'Avatar uploaded', 'avatar_url': request.url_root.rstrip('/') + '/' + os.path.join('static', user.avatar_path).replace('\\','/')})


@auth_bp.post('/profile/location')
@jwt_required()
def update_location():
    ident = get_jwt_identity()
    user_id = str(ident) if isinstance(ident, str) else str(ident.get('id') or ident)
    user = User.objects(id=user_id).first()
    if not user:
        return jsonify({'message': 'User not found'}), 404
    
    data = request.get_json() or {}
    latitude = data.get('lat')
    longitude = data.get('lon')
    address = data.get('address')
    
    if latitude is not None:
        user.latitude = float(latitude)
    if longitude is not None:
        user.longitude = float(longitude)
    if address:
        user.address = address
    
    user.save()
    
    # If user is a provider, also update provider location
    if user.provider_profile:
        try:
            from extensions import socketio
            socketio.emit('provider_location', {
                'user_id': str(user.id),
                'name': user.name,
                'lat': user.latitude,
                'lon': user.longitude,
                'address': user.address,
                'rating': user.rating
            })
        except Exception:
            pass
    
    return jsonify({'message': 'Location updated', 'address': user.address})


@auth_bp.post('/logout')
def logout():
    """Logout user and clear cookies"""
    response = make_response(jsonify({'message': 'Logged out successfully'}))
    unset_jwt_cookies(response)
    return response
