from flask import Blueprint, request, jsonify, render_template, make_response, redirect, url_for
from flask_jwt_extended import create_access_token, jwt_required, get_jwt_identity, set_access_cookies, unset_jwt_cookies
from werkzeug.utils import secure_filename
import os
from extensions import bcrypt
from models import User, Provider
from bson import ObjectId
import uuid

auth_bp = Blueprint('auth', __name__)


@auth_bp.get('/login')
def login_page():
    google_client_id = os.getenv('GOOGLE_CLIENT_ID', 'YOUR_GOOGLE_CLIENT_ID')
    return render_template('login.html', google_client_id=google_client_id)


@auth_bp.get('/signup')
def signup_page():
    google_client_id = os.getenv('GOOGLE_CLIENT_ID', 'YOUR_GOOGLE_CLIENT_ID')
    return render_template('signup.html', google_client_id=google_client_id)

@auth_bp.get('/test-google')
def test_google_auth():
    return render_template('test_google_auth.html')

@auth_bp.get('/test-client-id')
def test_client_id():
    return render_template('test_client_id.html')

@auth_bp.get('/auth/google')
def google_auth_redirect():
    """Alternative Google authentication route"""
    from urllib.parse import urlencode
    import os
    
    # Google OAuth parameters
    client_id = os.getenv('GOOGLE_CLIENT_ID', '695218588985-pg6cfc385ddagv1np90b3uietqsg5hvc.apps.googleusercontent.com')
    redirect_uri = request.url_root + 'auth/google/callback'
    scope = 'openid email profile'
    state = 'random_state_string'  # In production, use a secure random string
    
    # Build Google OAuth URL
    params = {
        'client_id': client_id,
        'redirect_uri': redirect_uri,
        'scope': scope,
        'response_type': 'code',
        'state': state
    }
    
    google_auth_url = f"https://accounts.google.com/o/oauth2/v2/auth?{urlencode(params)}"
    
    return f'''
    <!DOCTYPE html>
    <html>
    <head>
        <title>Redirecting to Google...</title>
        <style>
            body {{
                font-family: Arial, sans-serif;
                text-align: center;
                padding: 50px;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                color: white;
            }}
            .container {{
                background: rgba(255, 255, 255, 0.1);
                padding: 30px;
                border-radius: 15px;
                max-width: 400px;
                margin: 0 auto;
            }}
            .spinner {{
                border: 4px solid #f3f3f3;
                border-top: 4px solid #3498db;
                border-radius: 50%;
                width: 40px;
                height: 40px;
                animation: spin 2s linear infinite;
                margin: 20px auto;
            }}
            @keyframes spin {{
                0% {{ transform: rotate(0deg); }}
                100% {{ transform: rotate(360deg); }}
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <h2>Redirecting to Google...</h2>
            <div class="spinner"></div>
            <p>Please wait while we redirect you to Google for authentication.</p>
            <p>If you are not redirected automatically, <a href="{google_auth_url}" style="color: #fff; text-decoration: underline;">click here</a>.</p>
        </div>
        <script>
            // Redirect to Google OAuth
            window.location.href = "{google_auth_url}";
        </script>
    </body>
    </html>
    '''

@auth_bp.get('/auth/google/callback')
def google_auth_callback():
    """Handle Google OAuth callback"""
    code = request.args.get('code')
    state = request.args.get('state')
    error = request.args.get('error')
    
    if error:
        return f'''
        <!DOCTYPE html>
        <html>
        <head>
            <title>Authentication Error</title>
            <style>
                body {{ font-family: Arial, sans-serif; text-align: center; padding: 50px; background: #f8f9fa; }}
                .error {{ background: #f8d7da; color: #721c24; padding: 20px; border-radius: 10px; max-width: 400px; margin: 0 auto; }}
            </style>
        </head>
        <body>
            <div class="error">
                <h3>Authentication Error</h3>
                <p>Error: {error}</p>
                <a href="/login" style="color: #721c24;">Back to Login</a>
            </div>
        </body>
        </html>
        ''', 400
    
    if not code:
        return '''
        <!DOCTYPE html>
        <html>
        <head>
            <title>Authentication Error</title>
            <style>
                body { font-family: Arial, sans-serif; text-align: center; padding: 50px; background: #f8f9fa; }
                .error { background: #f8d7da; color: #721c24; padding: 20px; border-radius: 10px; max-width: 400px; margin: 0 auto; }
            </style>
        </head>
        <body>
            <div class="error">
                <h3>Authentication Error</h3>
                <p>No authorization code received from Google.</p>
                <a href="/login" style="color: #721c24;">Back to Login</a>
            </div>
        </body>
        </html>
        ''', 400
    
    try:
        # Exchange authorization code for access token
        import requests
        
        client_id = os.getenv('GOOGLE_CLIENT_ID', '1033624663631-bm5caule4l7cdpcp7cdgcqoe7p214afu.apps.googleusercontent.com')
        client_secret = os.getenv('GOOGLE_CLIENT_SECRET')
        if not client_secret:
            return f'''
            <!DOCTYPE html>
            <html>
            <head>
                <title>Configuration Error</title>
                <style>
                    body {{ font-family: Arial, sans-serif; text-align: center; padding: 50px; background: #f8f9fa; }}
                    .error {{ background: #fff3cd; color: #856404; padding: 20px; border-radius: 10px; max-width: 500px; margin: 0 auto; }}
                </style>
            </head>
            <body>
                <div class="error">
                    <h3>Google OAuth Configuration Missing</h3>
                    <p>Please set the <code>GOOGLE_CLIENT_SECRET</code> environment variable.</p>
                    <p><strong>Steps to fix:</strong></p>
                    <ol style="text-align: left;">
                        <li>Go to <a href="https://console.cloud.google.com/" target="_blank">Google Cloud Console</a></li>
                        <li>Create OAuth 2.0 credentials</li>
                        <li>Set environment variable: <code>GOOGLE_CLIENT_SECRET=your_secret_here</code></li>
                    </ol>
                    <a href="/login" style="color: #856404;">Back to Login</a>
                </div>
            </body>
            </html>
            ''', 500
        redirect_uri = request.url_root + 'auth/google/callback'
        
        # Exchange code for tokens
        token_url = 'https://oauth2.googleapis.com/token'
        token_data = {
            'client_id': client_id,
            'client_secret': client_secret,
            'code': code,
            'grant_type': 'authorization_code',
            'redirect_uri': redirect_uri
        }
        
        token_response = requests.post(token_url, data=token_data)
        token_response.raise_for_status()
        tokens = token_response.json()
        
        # Get user info from Google
        user_info_url = f"https://www.googleapis.com/oauth2/v2/userinfo?access_token={tokens['access_token']}"
        user_response = requests.get(user_info_url)
        user_response.raise_for_status()
        user_info = user_response.json()
        
        # Extract user information
        google_id = user_info['id']
        email = user_info['email']
        name = user_info.get('name', '')
        picture = user_info.get('picture', '')
        
        # Check if user exists
        user = User.objects(email=email).first()
        
        if user:
            # User exists, update Google ID if not set
            if not user.google_id:
                user.google_id = google_id
                user.save()
        else:
            # Create new user
            user = User(
                name=name,
                email=email,
                role='user',
                avatar_path=picture,
                password_hash='',  # No password for OAuth users
                google_id=google_id
                # phone field is optional and not set for OAuth users
            )
            user.save()
        
        # Create JWT token
        token = create_access_token(identity=str(user.id), additional_claims={
            'role': user.role, 
            'name': user.name, 
            'email': user.email
        })
        
        # Set JWT cookie and redirect based on role
        if user.role == 'admin':
            redirect_url = '/admin'
        elif user.role == 'provider':
            redirect_url = '/dashboard-provider'
        else:
            redirect_url = f'/dashboard/user/new?token={token}'
        
        response = make_response(redirect(redirect_url))
        set_access_cookies(response, token)
        return response
        
    except Exception as e:
        print(f"Google OAuth callback error: {str(e)}")
        return f'''
        <!DOCTYPE html>
        <html>
        <head>
            <title>Authentication Error</title>
            <style>
                body {{ font-family: Arial, sans-serif; text-align: center; padding: 50px; background: #f8f9fa; }}
                .error {{ background: #f8d7da; color: #721c24; padding: 20px; border-radius: 10px; max-width: 400px; margin: 0 auto; }}
            </style>
        </head>
        <body>
            <div class="error">
                <h3>Authentication Error</h3>
                <p>Failed to complete Google authentication: {str(e)}</p>
                <a href="/login" style="color: #721c24;">Back to Login</a>
            </div>
        </body>
        </html>
        ''', 500


@auth_bp.post('/signup')
def signup():
    data = request.get_json() or request.form
    name = data.get('name')
    email = data.get('email')
    phone = data.get('phone')
    password = data.get('password')
    role = (data.get('role') or 'user').lower()
    phone_verified = str(data.get('phone_verified') or '').lower() in ('true', '1', 'yes')

    if not all([name, email, password, role]):
        return jsonify({'message': 'Missing required fields'}), 400

    # Phone is optional, but if provided, we can mark it as verified
    if User.objects(email=email).first():
        return jsonify({'message': 'Email already exists'}), 400

    password_hash = bcrypt.generate_password_hash(password).decode('utf-8')
    user = User(name=name, email=email, phone=phone if phone else None, role=role, password_hash=password_hash, phone_verified=phone_verified if phone else False)
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


@auth_bp.get('/api/user/profile')
@jwt_required()
def get_user_profile_api():
    """API endpoint used by frontend to fetch the logged-in user's profile"""
    try:
        ident = get_jwt_identity()
        # Handle different JWT identity formats
        if isinstance(ident, dict):
            user_id = str(ident.get('id') or ident.get('user_id') or ident)
        elif isinstance(ident, str):
            user_id = str(ident)
        else:
            user_id = str(ident)

        try:
            user = User.objects(id=ObjectId(user_id)).first()
        except Exception:
            user = User.objects(id=user_id).first()

        if not user:
            return jsonify({'message': 'User not found'}), 404

        avatar_url = None
        if user.avatar_path:
            avatar_url = url_for('static', filename=user.avatar_path, _external=True)

        return jsonify({
            'id': str(user.id),
            'name': user.name,
            'email': user.email,
            'phone': user.phone,
            'role': user.role,
            'address': user.address,
            'latitude': user.latitude,
            'longitude': user.longitude,
            'avatar_url': avatar_url,
            'credits': user.credits or 0,
            'rating': user.rating or 0
        })
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'message': f'Error loading profile: {str(e)}'}), 500


@auth_bp.get('/profile')
@jwt_required(optional=True)
def profile_page():
    return render_template('profile.html')


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


@auth_bp.delete('/profile/delete')
@jwt_required()
def delete_account():
    ident = get_jwt_identity()
    user_id = str(ident) if isinstance(ident, str) else str(ident.get('id') or ident)
    user = User.objects(id=user_id).first()
    if not user:
        return jsonify({'message': 'User not found'}), 404
    try:
        # If provider, remove provider profile as well
        if user.provider_profile:
            try:
                user.provider_profile.delete()
            except Exception:
                pass
        user.delete()
        resp = make_response(jsonify({'message': 'Account deleted'}))
        unset_jwt_cookies(resp)
        return resp
    except Exception as e:
        return jsonify({'message': 'Failed to delete account'}), 500


# Preferences API
@auth_bp.get('/profile/preferences')
@jwt_required()
def get_preferences():
    ident = get_jwt_identity()
    user_id = str(ident) if isinstance(ident, str) else str(ident.get('id') or ident)
    user = User.objects(id=user_id).first()
    if not user:
        return jsonify({'message': 'User not found'}), 404
    return jsonify({
        'prefers_email_notifications': bool(user.prefers_email_notifications),
        'prefers_sms_notifications': bool(user.prefers_sms_notifications),
        'dark_mode': bool(user.dark_mode),
        'language': user.language or 'en'
    })


@auth_bp.post('/profile/preferences')
@jwt_required()
def update_preferences():
    ident = get_jwt_identity()
    user_id = str(ident) if isinstance(ident, str) else str(ident.get('id') or ident)
    user = User.objects(id=user_id).first()
    if not user:
        return jsonify({'message': 'User not found'}), 404
    data = request.get_json() or {}
    if 'prefers_email_notifications' in data:
        user.prefers_email_notifications = bool(data.get('prefers_email_notifications'))
    if 'prefers_sms_notifications' in data:
        user.prefers_sms_notifications = bool(data.get('prefers_sms_notifications'))
    if 'dark_mode' in data:
        user.dark_mode = bool(data.get('dark_mode'))
    if 'language' in data:
        user.language = str(data.get('language') or 'en')[:10]
    user.save()
    return jsonify({'message': 'Preferences updated'})


# Saved addresses API
@auth_bp.get('/profile/addresses')
@jwt_required()
def list_addresses():
    ident = get_jwt_identity()
    user_id = str(ident) if isinstance(ident, str) else str(ident.get('id') or ident)
    user = User.objects(id=user_id).first()
    if not user:
        return jsonify({'message': 'User not found'}), 404
    addresses = []
    for a in (user.saved_addresses or []):
        addresses.append({
            'uid': a.uid,
            'label': a.label,
            'address': a.address,
            'latitude': a.latitude,
            'longitude': a.longitude,
            'is_default': bool(a.is_default)
        })
    return jsonify(addresses)


@auth_bp.post('/profile/addresses')
@jwt_required()
def add_address():
    from models import SavedAddress
    ident = get_jwt_identity()
    user_id = str(ident) if isinstance(ident, str) else str(ident.get('id') or ident)
    user = User.objects(id=user_id).first()
    if not user:
        return jsonify({'message': 'User not found'}), 404
    data = request.get_json() or {}
    try:
        saved = SavedAddress(
            uid=str(uuid.uuid4())[:8],
            label=str(data.get('label') or 'Home')[:100],
            address=str(data.get('address') or '')[:255],
            latitude=float(data.get('latitude')),
            longitude=float(data.get('longitude')),
            is_default=bool(data.get('is_default', False))
        )
    except Exception:
        return jsonify({'message': 'Invalid address payload'}), 400
    if saved.is_default:
        for a in (user.saved_addresses or []):
            a.is_default = False
    user.saved_addresses = (user.saved_addresses or []) + [saved]
    user.save()
    return jsonify({'message': 'Address added', 'uid': saved.uid})


@auth_bp.post('/profile/addresses/<addr_uid>/default')
@jwt_required()
def set_default_address(addr_uid):
    ident = get_jwt_identity()
    user_id = str(ident) if isinstance(ident, str) else str(ident.get('id') or ident)
    user = User.objects(id=user_id).first()
    if not user:
        return jsonify({'message': 'User not found'}), 404
    found = False
    for a in (user.saved_addresses or []):
        if a.uid == addr_uid:
            a.is_default = True
            found = True
        else:
            a.is_default = False
    if not found:
        return jsonify({'message': 'Address not found'}), 404
    user.save()
    return jsonify({'message': 'Default address updated'})


@auth_bp.delete('/profile/addresses/<addr_uid>')
@jwt_required()
def delete_address(addr_uid):
    ident = get_jwt_identity()
    user_id = str(ident) if isinstance(ident, str) else str(ident.get('id') or ident)
    user = User.objects(id=user_id).first()
    if not user:
        return jsonify({'message': 'User not found'}), 404
    before = len(user.saved_addresses or [])
    user.saved_addresses = [a for a in (user.saved_addresses or []) if a.uid != addr_uid]
    if len(user.saved_addresses or []) == before:
        return jsonify({'message': 'Address not found'}), 404
    user.save()
    return jsonify({'message': 'Address deleted'})
