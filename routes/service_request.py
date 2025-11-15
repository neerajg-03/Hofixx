from flask import Blueprint, request, jsonify, current_app
from flask_jwt_extended import jwt_required, get_jwt_identity
from werkzeug.utils import secure_filename
from datetime import datetime, timedelta, timezone
import os
import uuid
from bson import ObjectId

from models import User, Provider, ServiceRequest, ProviderQuote, ProviderNotification, Booking
from extensions import socketio

service_request_bp = Blueprint('service_request', __name__)

# Allowed file extensions for images
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}

# Allowed file extensions for audio
ALLOWED_AUDIO_EXTENSIONS = {'webm', 'mp3', 'wav', 'ogg', 'm4a'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def allowed_audio_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_AUDIO_EXTENSIONS

def save_uploaded_files(files, request_id):
    """Save uploaded files and return their URLs"""
    if not files:
        return []
    
    saved_files = []
    upload_folder = os.path.join(current_app.static_folder, 'uploads', 'service_requests', str(request_id))
    
    # Create directory if it doesn't exist
    os.makedirs(upload_folder, exist_ok=True)
    
    for file in files:
        if file and allowed_file(file.filename):
            # Generate unique filename
            filename = secure_filename(file.filename)
            unique_filename = f"{uuid.uuid4()}_{filename}"
            file_path = os.path.join(upload_folder, unique_filename)
            
            file.save(file_path)
            
            # Return relative URL for serving
            relative_url = f"/static/uploads/service_requests/{request_id}/{unique_filename}"
            saved_files.append(relative_url)
    
    return saved_files

def save_audio_file(file, request_id):
    """Save uploaded audio file and return its URL"""
    if not file or not file.filename:
        return None
    
    if not allowed_audio_file(file.filename):
        return None
    
    upload_folder = os.path.join(current_app.static_folder, 'uploads', 'service_requests', str(request_id))
    os.makedirs(upload_folder, exist_ok=True)
    
    # Generate unique filename
    filename = secure_filename(file.filename)
    unique_filename = f"{uuid.uuid4()}_{filename}"
    file_path = os.path.join(upload_folder, unique_filename)
    
    file.save(file_path)
    
    # Return relative URL for serving
    relative_url = f"/static/uploads/service_requests/{request_id}/{unique_filename}"
    return relative_url

def to_iso(dt):
    if not dt:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.isoformat()

@service_request_bp.post('/api/service-requests')
@jwt_required()
def create_service_request():
    """Create a new service request"""
    try:
        # Get current user
        ident = get_jwt_identity()
        user_id = str(ident) if isinstance(ident, str) else str(ident['id'])
        user = User.objects(id=ObjectId(user_id)).first()
        
        if not user:
            return jsonify({'error': 'User not found'}), 404
        
        # Get form data
        service_type = request.form.get('service_type', '').strip()
        urgency = request.form.get('urgency', 'normal')
        location = request.form.get('location', '').strip()
        work_description = request.form.get('work_description', '').strip()
        preferred_date = request.form.get('preferred_date')
        preferred_time = request.form.get('preferred_time')
        
        # Get coordinates
        try:
            lat = float(request.form.get('lat', 0))
            lon = float(request.form.get('lon', 0))
        except (ValueError, TypeError):
            lat, lon = 28.6139, 77.2090  # Default to Delhi
        
        # Validate required fields
        if not all([service_type, location, work_description]):
            return jsonify({'error': 'Missing required fields'}), 400
        
        # Parse preferred date if provided
        preferred_datetime = None
        if preferred_date and preferred_time:
            try:
                preferred_datetime = datetime.strptime(f"{preferred_date} {preferred_time}", "%Y-%m-%d %H:%M")
            except ValueError:
                # If time is not in HH:MM format, use default times
                time_mapping = {
                    'morning': '09:00',
                    'afternoon': '14:00', 
                    'evening': '18:00'
                }
                default_time = time_mapping.get(preferred_time, '14:00')
                preferred_datetime = datetime.strptime(f"{preferred_date} {default_time}", "%Y-%m-%d %H:%M")
        
        # Block new request if previous booking unpaid
        unpaid = Booking.objects(user=user, status='Completed', has_payment=False).first()
        if unpaid:
            return jsonify({'error': 'You have an unpaid previous service. Please complete payment to book the next service.', 'unpaid_booking_id': str(unpaid.id)}), 400
        
        # Generate request ID for file organization
        request_id = str(uuid.uuid4())
        
        # Save uploaded images
        images = save_uploaded_files(request.files.getlist('images'), request_id)
        
        # Save voice description if provided
        voice_description_url = None
        if 'voice_description' in request.files:
            voice_file = request.files.get('voice_description')
            if voice_file and voice_file.filename:
                voice_description_url = save_audio_file(voice_file, request_id)
        
        # Create service request
        service_request = ServiceRequest(
            user=user,
            service_category=service_type,
            title=f"{service_type.title()} Service Request",
            description=work_description,
            images=images,
            voice_description_url=voice_description_url,
            location_lat=lat,
            location_lon=lon,
            location_address=location,
            urgency=urgency,
            preferred_date=preferred_datetime,
            preferred_time_slot=preferred_time,
            status='open',
            quote_deadline=datetime.utcnow() + timedelta(minutes=10),  # 10 minutes for quotes
            expires_at=datetime.utcnow() + timedelta(days=7)  # 7 days to expire
        )
        
        service_request.save()
        
        # Notify nearby providers
        notify_nearby_providers(service_request)
        
        return jsonify({
            'success': True,
            'request_id': str(service_request.id),
            'message': 'Service request created successfully'
        })
        
    except Exception as e:
        print(f"Error creating service request: {e}")
        return jsonify({'error': 'Failed to create service request'}), 500

def notify_nearby_providers(service_request):
    """Notify nearby providers about the new service request"""
    try:
        # Find providers within 15km radius
        providers = Provider.objects(availability=True)
        nearby_providers = []
        
        print(f"Found {providers.count()} available providers")
        
        for provider in providers:
            if provider.user.latitude and provider.user.longitude:
                # Calculate distance using Haversine formula
                distance = calculate_distance_haversine(
                    service_request.location_lat, service_request.location_lon,
                    provider.user.latitude, provider.user.longitude
                )
                
                print(f"Provider {provider.user.name} is {distance:.2f}km away")
                
                if distance <= 15:  # 15km radius
                    nearby_providers.append(provider)
            else:
                print(f"Provider {provider.user.name} has no location set")
        
        # If no nearby providers found, notify all available providers
        if not nearby_providers:
            print("No nearby providers found, notifying all available providers")
            nearby_providers = list(providers)
        
        # Create notifications for nearby providers
        for provider in nearby_providers:
            try:
                notification = ProviderNotification(
                    provider=provider,
                    service_request=service_request,
                    notification_type='new_request',
                    title=f"New {service_request.service_category.title()} Request",
                    message=f"New service request near you: {service_request.description[:100]}...",
                    is_sent=True
                )
                notification.save()
                
                # Emit real-time notification via WebSocket
                # Use provider.user.id for room to match client-side room joining
                provider_user_id = str(provider.user.id)
                provider_room = f'provider_{provider_user_id}'
                
                socketio.emit('new_service_request', {
                    'request_id': str(service_request.id),
                    'service_category': service_request.service_category,
                    'title': service_request.title,
                    'description': service_request.description,
                    'urgency': service_request.urgency,
                    'location': service_request.location_address,
                    'distance': calculate_distance_haversine(
                        service_request.location_lat, service_request.location_lon,
                        provider.user.latitude or 0, provider.user.longitude or 0
                    ) if provider.user.latitude and provider.user.longitude else 0
                }, room=provider_room)
                
                print(f"Emitting to room: {provider_room} for provider user: {provider.user.name}")
                
                print(f"Notified provider {provider.user.name}")
            except Exception as e:
                print(f"Error notifying provider {provider.user.name}: {e}")
        
        print(f"Notified {len(nearby_providers)} providers about new service request")
        
    except Exception as e:
        print(f"Error notifying providers: {e}")

def calculate_distance_haversine(lat1, lon1, lat2, lon2):
    """Calculate distance between two points using Haversine formula"""
    import math
    
    # Convert latitude and longitude from degrees to radians
    lat1, lon1, lat2, lon2 = map(math.radians, [lat1, lon1, lat2, lon2])
    
    # Haversine formula
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = math.sin(dlat/2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon/2)**2
    c = 2 * math.asin(math.sqrt(a))
    
    # Radius of earth in kilometers
    r = 6371
    
    return c * r

@service_request_bp.get('/api/service-requests/<request_id>')
@jwt_required()
def get_service_request(request_id):
    """Get service request details"""
    try:
        # Get current user
        ident = get_jwt_identity()
        user_id = str(ident) if isinstance(ident, str) else str(ident['id'])
        
        # Get service request
        service_request = ServiceRequest.objects(id=ObjectId(request_id)).first()
        if not service_request:
            return jsonify({'error': 'Service request not found'}), 404
        
        # Check if user owns this request or is a provider
        user = User.objects(id=ObjectId(user_id)).first()
        if not user:
            return jsonify({'error': 'User not found'}), 404
        
        # Check permissions
        if str(service_request.user.id) != user_id and user.role != 'provider':
            return jsonify({'error': 'Unauthorized'}), 403
        
        # Get quotes if user owns the request
        quotes = []
        if str(service_request.user.id) == user_id:
            quotes = ProviderQuote.objects(service_request=service_request).order_by('submitted_at')
        
        return jsonify({
            'service_request': {
                'id': str(service_request.id),
                'title': service_request.title,
                'description': service_request.description,
                'service_category': service_request.service_category,
                'urgency': service_request.urgency,
                'location': service_request.location_address,
                'location_lat': service_request.location_lat,
                'location_lon': service_request.location_lon,
                'images': service_request.images,
                'voice_description_url': service_request.voice_description_url or None,
                'preferred_date': to_iso(service_request.preferred_date),
                'preferred_time_slot': service_request.preferred_time_slot,
                'status': service_request.status,
                'created_at': to_iso(service_request.created_at),
                'quote_deadline': to_iso(service_request.quote_deadline),
                'expires_at': to_iso(service_request.expires_at)
            },
            'quotes': [{
                'id': str(quote.id),
                'provider_name': quote.provider_name,
                'provider_rating': quote.provider_rating,
                'price': quote.price,
                'estimated_duration': quote.estimated_duration,
                'quote_notes': quote.quote_notes,
                'quote_images': quote.quote_images,
                'status': quote.status,
                'submitted_at': to_iso(quote.submitted_at)
            } for quote in quotes]
        })
        
    except Exception as e:
        print(f"Error getting service request: {e}")
        return jsonify({'error': 'Failed to get service request'}), 500

@service_request_bp.get('/api/service-requests')
@jwt_required()
def get_user_service_requests():
    """Get all service requests for the current user"""
    try:
        # Get current user
        ident = get_jwt_identity()
        user_id = str(ident) if isinstance(ident, str) else str(ident['id'])
        user = User.objects(id=ObjectId(user_id)).first()
        
        if not user:
            return jsonify({'error': 'User not found'}), 404
        
        # Get service requests
        service_requests = ServiceRequest.objects(user=user).order_by('-created_at')
        
        return jsonify({
            'service_requests': [{
                'id': str(req.id),
                'title': req.title,
                'service_category': req.service_category,
                'urgency': req.urgency,
                'status': req.status,
                'created_at': to_iso(req.created_at),
                'quote_deadline': to_iso(req.quote_deadline),
                'expires_at': to_iso(req.expires_at)
            } for req in service_requests]
        })
        
    except Exception as e:
        print(f"Error getting service requests: {e}")
        return jsonify({'error': 'Failed to get service requests'}), 500

@service_request_bp.post('/api/service-requests/<request_id>/select-quote')
@jwt_required()
def select_quote(request_id):
    """Select a quote and create a booking"""
    try:
        ident = get_jwt_identity()
        user_id = str(ident) if isinstance(ident, str) else str(ident['id'])
        user = User.objects(id=ObjectId(user_id)).first()
        if not user:
            return jsonify({'error': 'User not found'}), 404
        
        data = request.get_json() or {}
        quote_id = data.get('quote_id')
        if not quote_id:
            return jsonify({'error': 'Quote ID is required'}), 400
        
        service_request = ServiceRequest.objects(id=ObjectId(request_id)).first()
        if not service_request:
            return jsonify({'error': 'Service request not found'}), 404
        
        if str(service_request.user.id) != user_id:
            return jsonify({'error': 'Unauthorized'}), 403
        
        quote = ProviderQuote.objects(id=ObjectId(quote_id), service_request=service_request).first()
        if not quote:
            return jsonify({'error': 'Quote not found'}), 404
        if quote.status != 'submitted':
            return jsonify({'error': 'Quote is no longer available'}), 400
        
        provider = quote.provider
        if not provider:
            return jsonify({'error': 'Provider not found'}), 404
        if provider.verification_status != 'verified':
            return jsonify({
                'error': 'Provider not verified',
                'details': 'This provider is not verified yet. Please select a verified provider.'
            }), 403
        
        active_booking = Booking.objects(provider=provider, status__in=['Accepted', 'In Progress']).first()
        if active_booking:
            return jsonify({
                'error': 'Provider is busy',
                'details': 'This provider is currently working on another job. Please select a different provider or wait for them to complete their current job.'
            }), 400
        
        from models import Service
        service = Service.objects(category=service_request.service_category).first()
        if not service:
            service = Service(
                name=f"{service_request.service_category.title()} Service",
                category=service_request.service_category,
                base_price=quote.price
            )
            service.save()
        
        booking = Booking(
            user=user,
            provider=provider,
            service=service,
            status='Accepted',
            scheduled_time=service_request.preferred_date,
            price=quote.price,
            location_lat=service_request.location_lat,
            location_lon=service_request.location_lon,
            notes=service_request.description,
            service_name=service.name,
            provider_id=str(provider.user.id),
            provider_name=quote.provider_name or provider.user.name,
            has_payment=False,
            payment_status='Pending'
        )
        booking.save()
        
        service_request.status = 'quote_selected'
        service_request.selected_quote = quote
        service_request.final_booking = booking
        service_request.save()
        
        quote.status = 'selected'
        quote.save()
        
        other_quotes = ProviderQuote.objects(service_request=service_request, id__ne=quote.id)
        other_provider_ids = []
        for other_quote in other_quotes:
            other_quote.status = 'rejected'
            other_quote.save()
            if other_quote.provider:
                other_provider_ids.append(other_quote.provider.id)

        ProviderNotification.objects(service_request=service_request, provider__ne=provider).delete()

        notification = ProviderNotification(
            provider=provider,
            service_request=service_request,
            notification_type='quote_selected',
            title='🎉 Your Quote Was Selected!',
            message=f'Congratulations! Your quote for "{service_request.title}" has been selected by the customer.',
            is_sent=True,
            is_read=False
        )
        notification.save()
        
        socketio.emit('quote_selected', {
            'request_id': str(service_request.id),
            'booking_id': str(booking.id),
            'provider_id': str(provider.id),
            'message': 'Your quote has been selected!',
            'title': service_request.title
        }, room=f'provider_{provider.id}')

        for other_provider_id in other_provider_ids:
            socketio.emit('request_assigned_to_other', {
                'request_id': str(service_request.id),
                'message': 'This service request has been assigned to another provider'
            }, room=f'provider_{other_provider_id}')

        socketio.emit('request_cancelled', {
            'request_id': str(service_request.id),
            'title': service_request.title,
            'reason': 'Assigned to selected provider'
        }, room='all_providers')

        socketio.emit('quote_selected', {
            'request_id': str(service_request.id),
            'booking_id': str(booking.id),
            'provider_id': str(provider.id),
            'message': 'Quote selected',
            'title': service_request.title
        }, room=f'user_{user.id}')
        
        return jsonify({
            'success': True,
            'booking_id': str(booking.id),
            'message': 'Quote selected successfully'
        })
        
    except Exception as e:
        print(f"Error selecting quote: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': 'Failed to select quote', 'details': str(e)}), 500

@service_request_bp.get('/api/provider/notifications')
@jwt_required()
def get_provider_notifications():
    """Get notifications for the current provider"""
    try:
        # Get current user
        ident = get_jwt_identity()
        user_id = str(ident) if isinstance(ident, str) else str(ident.get('id', ident))
        
        print(f"Getting notifications for user ID: {user_id}")
        
        user = User.objects(id=ObjectId(user_id)).first()
        
        if not user:
            print(f"User not found: {user_id}")
            return jsonify({
                'error': 'User not found',
                'notifications': []
            }), 404
        
        print(f"User found: {user.name}, role: {user.role}")
        
        if user.role != 'provider':
            print(f"User is not a provider: {user.role}")
            return jsonify({
                'error': 'Access denied',
                'notifications': []
            }), 403
        
        provider = Provider.objects(user=user).first()
        if not provider:
            print(f"Provider profile not found for user: {user_id}")
            return jsonify({
                'error': 'Provider profile not found',
                'notifications': []
            }), 404
        
        print(f"Provider found: {provider.id}")
        
        # Get notifications - show new requests and quote selected notifications
        notifications = ProviderNotification.objects(
            provider=provider,
            notification_type__in=['new_request', 'quote_selected']
        ).order_by('-created_at').limit(50)
        
        print(f"Found {notifications.count()} notifications")
        
        notification_list = []
        for notif in notifications:
            try:
                notification_list.append({
                'id': str(notif.id),
                'type': notif.notification_type,
                'title': notif.title,
                'message': notif.message,
                'is_read': notif.is_read,
                    'created_at': to_iso(notif.created_at),
                    'service_request_id': str(notif.service_request.id) if notif.service_request else None
                })
            except Exception as e:
                print(f"Error processing notification {notif.id}: {e}")
                continue
        
        return jsonify({
            'success': True,
            'notifications': notification_list,
            'total': len(notification_list)
        })
        
    except Exception as e:
        print(f"Error getting provider notifications: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({
            'error': 'Failed to get notifications',
            'details': str(e),
            'notifications': []
        }), 500

@service_request_bp.get('/api/provider/service-requests')
@jwt_required()
def get_provider_service_requests():
    """Get service requests available for the current provider to quote on"""
    try:
        # Get current user
        ident = get_jwt_identity()
        user_id = str(ident) if isinstance(ident, str) else str(ident.get('id', ident))
        
        print(f"Provider service requests - User ID: {user_id}")
        
        user = User.objects(id=ObjectId(user_id)).first()
        
        print(f"User found: {user.name if user else 'None'}")
        print(f"User role: {user.role if user else 'None'}")
        
        if not user:
            return jsonify({'error': 'User not found', 'details': 'Could not find user with provided ID'}), 404
            
        if user.role != 'provider':
            return jsonify({'error': 'Access denied', 'details': 'Only providers can access this endpoint'}), 403
        
        provider = Provider.objects(user=user).first()
        print(f"Provider profile found: {provider is not None}")
        
        if not provider:
            return jsonify({'error': 'Provider profile not found', 'details': 'No provider profile associated with this user'}), 404
        
        # Check minimum deposit balance (₹500 required)
        from services.provider_deposit_service import check_minimum_balance
        is_eligible, error_message = check_minimum_balance(provider, minimum_balance=500.0)
        if not is_eligible:
            return jsonify({
                'error': 'Insufficient deposit balance',
                'details': error_message,
                'deposit_balance': float(provider.deposit_balance or 0.0),
                'minimum_required': 500.0,
                'requires_recharge': True
            }), 403
        
        print(f"Provider skills: {provider.skills}")
        print(f"Provider location: {provider.user.latitude}, {provider.user.longitude}")
        
        # Get open service requests (exclude quote_selected, in_progress, completed, cancelled)
        service_requests = ServiceRequest.objects(status__in=['open', 'quotes_received'])
        print(f"Total open service requests: {service_requests.count()}")
        
        nearby_requests = []
        
        for req in service_requests:
            print(f"Checking request: {req.title} at {req.location_address}")
            
            distance = 0
            if provider.user.latitude and provider.user.longitude and req.location_lat and req.location_lon:
                distance = calculate_distance_haversine(
                    req.location_lat, req.location_lon,
                    provider.user.latitude, provider.user.longitude
                )
                
                print(f"Distance: {distance:.2f}km")
                
                # Only show requests within 50km (increased range)
                if distance > 50:
                    print(f"Request too far: {distance:.2f}km")
                    continue
            else:
                print(f"Provider or request has no location set, showing all requests")
            
            # Check if provider already quoted
            existing_quote = ProviderQuote.objects(service_request=req, provider=provider).first()
            
            nearby_requests.append({
                'id': str(req.id),
                'title': req.title,
                'description': req.description,
                'service_category': req.service_category,
                'urgency': req.urgency,
                'location': req.location_address,
                'distance': round(distance, 2),
                'images': req.images or [],
                'voice_description_url': req.voice_description_url or None,
                'preferred_date': to_iso(req.preferred_date),
                'preferred_time_slot': req.preferred_time_slot or '',
                'created_at': to_iso(req.created_at),
                'quote_deadline': to_iso(req.quote_deadline),
                'has_quoted': existing_quote is not None,
                'quote_status': existing_quote.status if existing_quote else None
            })
            print(f"Added request to nearby list: {req.title}")
        
        # Sort by distance
        nearby_requests.sort(key=lambda x: x['distance'])
        
        print(f"Returning {len(nearby_requests)} nearby requests")
        return jsonify({
            'success': True,
            'service_requests': nearby_requests,
            'total': len(nearby_requests)
        })
        
    except Exception as e:
        print(f"Error getting provider service requests: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({
            'error': 'Failed to get service requests',
            'details': str(e)
        }), 500

@service_request_bp.post('/api/service-requests/<request_id>/quote')
@jwt_required()
def submit_quote(request_id):
    """Submit a quote for a service request"""
    try:
        # Get current user
        ident = get_jwt_identity()
        user_id = str(ident) if isinstance(ident, str) else str(ident.get('id', ident))
        
        print(f"Submit quote - User ID: {user_id}, Request ID: {request_id}")
        
        user = User.objects(id=ObjectId(user_id)).first()
        
        if not user:
            return jsonify({'error': 'User not found', 'details': 'Could not find user'}), 404
        
        if user.role != 'provider':
            return jsonify({'error': 'Access denied', 'details': 'Only providers can submit quotes'}), 403
        
        provider = Provider.objects(user=user).first()
        if not provider:
            return jsonify({'error': 'Provider profile not found', 'details': 'No provider profile found'}), 404
        
        # Check if provider is verified
        if provider.verification_status != 'verified':
            return jsonify({
                'error': 'Verification required',
                'details': 'Please complete your verification to submit quotes. Go to Provider Dashboard to start verification.'
            }), 403
        
        # Get request data
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No data provided', 'details': 'Request body is empty'}), 400
            
        price = data.get('price')
        estimated_duration = data.get('estimated_duration', '')
        quote_notes = data.get('quote_notes', '')
        
        print(f"Quote data - Price: {price}, Duration: {estimated_duration}")
        
        if not price:
            return jsonify({'error': 'Price is required', 'details': 'Please enter a valid price'}), 400
            
        try:
            price = float(price)
            if price <= 0:
                return jsonify({'error': 'Invalid price', 'details': 'Price must be greater than 0'}), 400
        except (ValueError, TypeError):
            return jsonify({'error': 'Invalid price format', 'details': 'Price must be a number'}), 400
        
        if not estimated_duration:
            return jsonify({'error': 'Estimated duration is required', 'details': 'Please select an estimated duration'}), 400
        
        # Get service request
        try:
            service_request = ServiceRequest.objects(id=ObjectId(request_id)).first()
        except Exception as e:
            return jsonify({'error': 'Invalid request ID', 'details': str(e)}), 400
            
        if not service_request:
            return jsonify({'error': 'Service request not found', 'details': 'The service request does not exist'}), 404
        
        # Check if request is still open
        if service_request.status not in ['open', 'quotes_received']:
            return jsonify({'error': 'Service request is closed', 'details': f'This request is no longer accepting quotes (Status: {service_request.status})'}), 400
        
        # Check if provider already quoted
        existing_quote = ProviderQuote.objects(service_request=service_request, provider=provider).first()
        if existing_quote:
            return jsonify({'error': 'Quote already submitted', 'details': 'You have already submitted a quote for this request'}), 400
        
        # Check if provider has an active job in progress
        active_booking = Booking.objects(provider=provider, status='In Progress').first()
        if active_booking:
            return jsonify({
                'error': 'Cannot accept new job',
                'details': f'You have an active job in progress. Please complete your current job (Booking ID: {str(active_booking.id)[:8]}...) before accepting new requests.'
            }), 400
        
        # Check if quote deadline has passed
        if service_request.quote_deadline and datetime.utcnow() > service_request.quote_deadline:
            return jsonify({'error': 'Deadline passed', 'details': 'The quote deadline has passed'}), 400
        
        # Create quote
        quote = ProviderQuote(
            service_request=service_request,
            provider=provider,
            price=price,
            estimated_duration=estimated_duration,
            quote_notes=quote_notes,
            status='submitted',
            expires_at=service_request.expires_at,
            provider_name=provider.user.name,
            provider_rating=provider.user.rating or 5.0,
            provider_phone=provider.user.phone
        )
        quote.save()
        
        print(f"Quote created successfully: {quote.id}")
        
        # Mark the original notification as read since provider has now quoted
        ProviderNotification.objects(
            provider=provider,
            service_request=service_request,
            notification_type='new_request'
        ).update(is_read=True)
        
        # Update service request status
        if service_request.status == 'open':
            service_request.status = 'quotes_received'
            service_request.save()
        
        # Notify user about new quote
        try:
            user_notification = {
                'type': 'new_quote',
                'title': 'New Quote Received',
                'message': f'You received a new quote for "{service_request.title}"',
                'request_id': str(service_request.id),
                'quote_id': str(quote.id)
            }
            
            # Emit real-time notification to user
            socketio.emit('new_quote_received', user_notification, room=f'user_{service_request.user.id}')
        except Exception as e:
            print(f"Error sending notification: {e}")
        
        return jsonify({
            'success': True,
            'quote_id': str(quote.id),
            'message': 'Quote submitted successfully'
        })
        
    except Exception as e:
        print(f"Error submitting quote: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({
            'error': 'Failed to submit quote',
            'details': str(e)
        }), 500

@service_request_bp.post('/api/service-requests/<request_id>/cancel')
@jwt_required()
def cancel_service_request(request_id):
    """Cancel a service request"""
    try:
        # Get current user
        ident = get_jwt_identity()
        user_id = str(ident) if isinstance(ident, str) else str(ident['id'])
        user = User.objects(id=ObjectId(user_id)).first()
        
        if not user:
            return jsonify({'error': 'User not found'}), 404
        
        # Get service request
        service_request = ServiceRequest.objects(id=ObjectId(request_id)).first()
        if not service_request:
            return jsonify({'error': 'Service request not found'}), 404
        
        # Check if user owns this request
        if str(service_request.user.id) != user_id:
            return jsonify({'error': 'Unauthorized'}), 403
        
        # Check if request can be cancelled
        if service_request.status in ['completed', 'cancelled', 'quote_selected']:
            return jsonify({'error': 'Cannot cancel request in current status'}), 400
        
        # Update request status
        service_request.status = 'cancelled'
        service_request.save()
        
        # Get all providers who were notified about this request (not just those who quoted)
        # First, get all providers who have notifications for this request
        existing_notifications = ProviderNotification.objects(service_request=service_request)
        
        # Clean up all existing notifications for this request
        existing_notifications.delete()
        
        # Get all quotes for this request to notify providers
        quotes = ProviderQuote.objects(service_request=service_request)
        quote_provider_ids = set()
        
        # Mark existing quotes as cancelled and notify providers
        for quote in quotes:
            quote.status = 'cancelled'
            quote.save()
            quote_provider_ids.add(quote.provider.id)
            notification = ProviderNotification(
                provider=quote.provider,
                service_request=service_request,
                notification_type='request_cancelled',
                title='Service Request Cancelled',
                message=f'The service request "{service_request.title}" has been cancelled by the customer.',
                is_sent=True
            )
            notification.save()
            socketio.emit('request_cancelled', {
                'request_id': str(service_request.id),
                'title': service_request.title,
                'reason': 'Cancelled by customer'
            }, room=f'provider_{quote.provider.id}')
        
        # Notify all providers who were originally alerted (including those without quotes)
        socketio.emit('request_cancelled', {
            'request_id': str(service_request.id),
            'title': service_request.title,
            'reason': 'Cancelled by customer'
        }, room='all_providers')
        
        # Emit to user room as well
        socketio.emit('request_cancelled', {
            'request_id': str(service_request.id),
            'title': service_request.title,
            'reason': 'Cancelled by you'
        }, room=f'user_{user.id}')
        
        return jsonify({
            'success': True,
            'message': 'Service request cancelled successfully'
        })
        
    except Exception as e:
        print(f"Error cancelling service request: {e}")
        return jsonify({'error': 'Failed to cancel service request'}), 500

@service_request_bp.post('/api/service-requests/<request_id>/cancel-quote')
@jwt_required()
def cancel_provider_quote(request_id):
    """Cancel a provider's quote for a service request"""
    try:
        # Get current user
        ident = get_jwt_identity()
        user_id = str(ident) if isinstance(ident, str) else str(ident['id'])
        user = User.objects(id=ObjectId(user_id)).first()
        
        if not user or user.role != 'provider':
            return jsonify({'error': 'Provider not found'}), 404
        
        provider = Provider.objects(user=user).first()
        if not provider:
            return jsonify({'error': 'Provider profile not found'}), 404
        
        # Get service request
        service_request = ServiceRequest.objects(id=ObjectId(request_id)).first()
        if not service_request:
            return jsonify({'error': 'Service request not found'}), 404
        
        # Get the provider's quote
        quote = ProviderQuote.objects(service_request=service_request, provider=provider).first()
        if not quote:
            return jsonify({'error': 'Quote not found'}), 404
        
        # Check if quote can be cancelled
        if quote.status in ['selected', 'rejected', 'expired']:
            return jsonify({'error': 'Cannot cancel quote in current status'}), 400
        
        # Update quote status
        quote.status = 'cancelled'
        quote.save()
        
        # Clean up any existing notifications for this provider and request
        ProviderNotification.objects(
            provider=provider,
            service_request=service_request
        ).delete()
        
        # Notify the customer
        notification = ProviderNotification(
            provider=provider,
            service_request=service_request,
            notification_type='quote_cancelled',
            title='Quote Withdrawn',
            message=f'Provider {provider.user.name} has withdrawn their quote for "{service_request.title}".',
            is_sent=True
        )
        notification.save()
        
        # Emit real-time notification to customer
        socketio.emit('quote_cancelled', {
            'request_id': str(service_request.id),
            'quote_id': str(quote.id),
            'provider_name': provider.user.name,
            'message': 'Quote has been withdrawn'
        }, room=f'user_{service_request.user.id}')
        
        return jsonify({
            'success': True,
            'message': 'Quote cancelled successfully'
        })
        
    except Exception as e:
        print(f"Error cancelling quote: {e}")
        return jsonify({'error': 'Failed to cancel quote'}), 500

@service_request_bp.get('/api/user/service-requests')
@jwt_required()
def get_user_service_requests_dashboard():
    """Get service requests for user dashboard"""
    try:
        # Get current user
        ident = get_jwt_identity()
        user_id = str(ident) if isinstance(ident, str) else str(ident['id'])
        user = User.objects(id=ObjectId(user_id)).first()
        
        if not user:
            return jsonify({'error': 'User not found'}), 404
        
        # Get service requests
        service_requests = ServiceRequest.objects(user=user).order_by('-created_at').limit(10)
        
        return jsonify({
            'service_requests': [{
                'id': str(req.id),
                'title': req.title,
                'service_category': req.service_category,
                'urgency': req.urgency,
                'status': req.status,
                'location': req.location_address,
                'created_at': to_iso(req.created_at),
                'quote_deadline': to_iso(req.quote_deadline),
                'expires_at': to_iso(req.expires_at),
                'has_quotes': ProviderQuote.objects(service_request=req).count() > 0,
                'quote_count': ProviderQuote.objects(service_request=req).count()
            } for req in service_requests]
        })
        
    except Exception as e:
        print(f"Error getting user service requests: {e}")
        return jsonify({'error': 'Failed to get service requests'}), 500

@service_request_bp.get('/api/debug/check-provider-auth')
@jwt_required()
def check_provider_auth():
    """Debug endpoint to check provider authentication"""
    try:
        ident = get_jwt_identity()
        user_id = str(ident) if isinstance(ident, str) else str(ident.get('id', ident))
        
        user = User.objects(id=ObjectId(user_id)).first()
        
        if not user:
            return jsonify({
                'authenticated': False,
                'error': 'User not found',
                'user_id': user_id
            })
        
        provider = Provider.objects(user=user).first()
        
        return jsonify({
            'authenticated': True,
            'user': {
                'id': str(user.id),
                'name': user.name,
                'email': user.email,
                'role': user.role,
                'has_provider_profile': provider is not None
            },
            'provider': {
                'id': str(provider.id) if provider else None,
                'skills': provider.skills if provider else [],
                'availability': provider.availability if provider else False,
                'location': {
                    'latitude': user.latitude,
                    'longitude': user.longitude,
                    'address': user.address
                }
            } if provider else None,
            'message': 'Provider authentication successful'
        })
        
    except Exception as e:
        return jsonify({
            'authenticated': False,
            'error': str(e)
        }), 500

@service_request_bp.post('/api/create-test-service-requests')
@jwt_required()
def create_test_service_requests():
    """Create test service requests for development"""
    try:
        # Get current user
        ident = get_jwt_identity()
        user_id = str(ident) if isinstance(ident, str) else str(ident['id'])
        user = User.objects(id=ObjectId(user_id)).first()
        
        if not user:
            return jsonify({'error': 'User not found'}), 404
        
        # Create test service requests
        test_requests = [
            {
                'service_category': 'electrician',
                'title': 'Electrical Repair Needed',
                'description': 'Need to fix faulty wiring in the kitchen. Power outlets are not working properly.',
                'location_address': 'Sector 18, Noida, Uttar Pradesh',
                'location_lat': 28.5937,
                'location_lon': 77.3803,
                'urgency': 'urgent',
                'preferred_date': datetime.utcnow() + timedelta(days=1),
                'preferred_time_slot': 'morning'
            },
            {
                'service_category': 'plumber',
                'title': 'Bathroom Leak Repair',
                'description': 'Water leaking from bathroom tap. Need urgent repair.',
                'location_address': 'Connaught Place, New Delhi',
                'location_lat': 28.6315,
                'location_lon': 77.2167,
                'urgency': 'emergency',
                'preferred_date': datetime.utcnow() + timedelta(hours=6),
                'preferred_time_slot': 'afternoon'
            },
            {
                'service_category': 'carpenter',
                'title': 'Furniture Assembly',
                'description': 'Need help assembling new bedroom furniture including bed frame and wardrobe.',
                'location_address': 'Karol Bagh, New Delhi',
                'location_lat': 28.6519,
                'location_lon': 77.1909,
                'urgency': 'normal',
                'preferred_date': datetime.utcnow() + timedelta(days=3),
                'preferred_time_slot': 'morning'
            },
            {
                'service_category': 'cleaner',
                'title': 'Deep House Cleaning',
                'description': 'Complete deep cleaning of 3BHK apartment including kitchen and bathrooms.',
                'location_address': 'Lajpat Nagar, New Delhi',
                'location_lat': 28.5644,
                'location_lon': 77.2432,
                'urgency': 'flexible',
                'preferred_date': datetime.utcnow() + timedelta(days=2),
                'preferred_time_slot': 'morning'
            },
            {
                'service_category': 'painter',
                'title': 'Wall Painting Service',
                'description': 'Need to paint living room and bedroom walls. Area is about 800 sq ft.',
                'location_address': 'Rajouri Garden, New Delhi',
                'location_lat': 28.6448,
                'location_lon': 77.1226,
                'urgency': 'normal',
                'preferred_date': datetime.utcnow() + timedelta(days=5),
                'preferred_time_slot': 'morning'
            }
        ]
        
        created_count = 0
        for req_data in test_requests:
            # Check if similar request already exists
            existing = ServiceRequest.objects(
                title=req_data['title'],
                service_category=req_data['service_category']
            ).first()
            
            if not existing:
                service_request = ServiceRequest(
                    user=user,
                    service_category=req_data['service_category'],
                    title=req_data['title'],
                    description=req_data['description'],
                    location_lat=req_data['location_lat'],
                    location_lon=req_data['location_lon'],
                    location_address=req_data['location_address'],
                    urgency=req_data['urgency'],
                    preferred_date=req_data['preferred_date'],
                    preferred_time_slot=req_data['preferred_time_slot'],
                    status='open',
                    quote_deadline=datetime.utcnow() + timedelta(minutes=10),
                    expires_at=datetime.utcnow() + timedelta(days=7)
                )
                service_request.save()
                created_count += 1
                
                # Notify nearby providers
                notify_nearby_providers(service_request)
        
        return jsonify({
            'success': True,
            'message': f'Created {created_count} test service requests',
            'created_count': created_count
        })
        
    except Exception as e:
        print(f"Error creating test service requests: {e}")
        return jsonify({'error': 'Failed to create test service requests'}), 500