from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from extensions import socketio
from models import Booking, Service, Provider, Payment, User
from datetime import datetime
from bson import ObjectId
import math

booking_bp = Blueprint('booking', __name__)


@booking_bp.get('/bookings/user')
@jwt_required()
def get_user_bookings():
    ident = get_jwt_identity()
    user_id = str(ident) if isinstance(ident, str) else str(ident['id'])
    user = User.objects(id=ObjectId(user_id)).first()
    if not user:
        return jsonify({'message': 'User not found'}), 404
    
    bookings = Booking.objects(user=user).order_by('-created_at')
    return jsonify([serialize_booking(b) for b in bookings])


@booking_bp.get('/bookings/provider')
@jwt_required()
def get_provider_bookings():
    ident = get_jwt_identity()
    user_id = str(ident) if isinstance(ident, str) else str(ident['id'])
    user = User.objects(id=ObjectId(user_id)).first()
    if not user or not user.provider_profile:
        return jsonify({'message': 'Not a provider'}), 403
    
    # Get bookings assigned to this provider AND general bookings they can handle
    provider = user.provider_profile
    provider_bookings = Booking.objects(provider=provider).order_by('-created_at')
    
    # Also get unassigned bookings that match provider skills
    if provider.skills:
        # Get all unassigned bookings first
        unassigned_bookings = Booking.objects(provider__exists=False).order_by('-created_at')
        
        # Filter by matching services
        matching_bookings = []
        for booking in unassigned_bookings:
            # Check both service.name and service_name for matching
            service_name = booking.service_name or (booking.service.name if booking.service else None)
            if service_name and service_name in provider.skills:
                matching_bookings.append(booking)
        
        # Combine and deduplicate
        all_bookings = list(provider_bookings) + [b for b in matching_bookings if b not in provider_bookings]
    else:
        all_bookings = list(provider_bookings)
    
    return jsonify([serialize_booking(b) for b in all_bookings])


@booking_bp.post('/bookings/create')
@jwt_required()
def create_booking():
    ident = get_jwt_identity()
    data = request.get_json() or {}
    
    print(f"Booking creation request data: {data}")  # Debug logging
    
    # Get user
    user_id = str(ident) if isinstance(ident, str) else str(ident['id'])
    user = User.objects(id=ObjectId(user_id)).first()
    if not user:
        return jsonify({'message': 'User not found'}), 404
    
    # Coerce and sanitize inputs
    try:
        service_id = str(data.get('service_id')) if data.get('service_id') not in (None, '',) else None
        print(f"Service ID from request: {service_id}")  # Debug logging
        if service_id:
            try:
                service = Service.objects(id=ObjectId(service_id)).first()
                print(f"Service found: {service.name if service else 'None'}")  # Debug logging
            except Exception as e:
                print(f"Error looking up service: {e}")  # Debug logging
                service = None
        else:
            service = None
    except Exception as e:
        print(f"Error processing service_id: {e}")  # Debug logging
        service = None
    
    try:
        provider_id = str(data.get('provider_id')) if data.get('provider_id') not in (None, '',) else None
        provider = Provider.objects(id=ObjectId(provider_id)).first() if provider_id else None
    except Exception:
        provider = None
    
    scheduled_time = data.get('scheduled_time')
    try:
        price = float(data.get('price')) if data.get('price') not in (None, '',) else 0.0
    except Exception:
        price = 0.0
    try:
        location_lat = float(data.get('location_lat')) if data.get('location_lat') not in (None, '',) else None
    except Exception:
        location_lat = None
    try:
        location_lon = float(data.get('location_lon')) if data.get('location_lon') not in (None, '',) else None
    except Exception:
        location_lon = None
    notes = data.get('notes')

    if scheduled_time:
        try:
            scheduled_time = datetime.fromisoformat(scheduled_time)
        except Exception:
            scheduled_time = None

    # Auto-select a service if not provided/invalid
    if not service:
        print("No service provided, attempting auto-selection...")
        if provider and getattr(provider, 'skills', None):
            print(f"Provider skills: {provider.skills}")
            service = Service.objects(category__in=provider.skills).first() or Service.objects(name__in=provider.skills).first()
            print(f"Service found by provider skills: {service.name if service else 'None'}")
        
        if not service:
            print("No service found by provider skills, trying first available service...")
            service = Service.objects.first()
            print(f"First available service: {service.name if service else 'None'}")
        
        if not service:
            print("No services available in database")
            return jsonify({'message': 'No services available'}), 400
    
    print(f"Final service selected: {service.name if service else 'None'}")
    
    # Validate that we have a service (this should never fail now)
    if not service:
        print(f"CRITICAL: No service found after auto-selection. Service ID provided: {data.get('service_id')}")
        return jsonify({'message': 'Service field is missing'}), 400

    booking = Booking(
        user=user,
        provider=provider,
        service=service,
        scheduled_time=scheduled_time,
        price=price or 0,
        location_lat=location_lat,
        location_lon=location_lon,
        notes=notes,
        service_name=service.name if service else None,
        provider_id=str(provider.id) if provider else None,
        provider_name=provider.user.name if provider and provider.user else None,
        has_payment=False,
        payment_status='Pending'
    )
    booking.save()

    # Send notifications
    print(f"Booking created: {booking.id}, Provider: {provider.id if provider else 'None'}")
    if provider:
        # Notify specific provider
        provider_room = f"provider_{provider.id}"
        user_room = f"provider_{provider.user.id}" if provider.user else None
        print(f"Sending notification to provider room: {provider_room}")
        if user_room:
            print(f"Also sending to user room: {user_room}")
        
        socketio.emit('booking_created', serialize_booking(booking), to=provider_room)
        if user_room and user_room != provider_room:
            socketio.emit('booking_created', serialize_booking(booking), to=user_room)
    else:
        # Notify all providers in the area or with matching skills
        if service:
            # Find providers with matching skills - improved matching
            matching_providers = []
            
            # Try exact service name match first
            exact_match = Provider.objects(skills__in=[service.name])
            matching_providers.extend(list(exact_match))
            
            # Try category match
            category_match = Provider.objects(skills__in=[service.category])
            matching_providers.extend([p for p in category_match if p not in matching_providers])
            
            # Try partial name match (for services like "Electrician" matching "Electrical")
            if service.name:
                # Get all providers and filter manually for partial matches
                all_providers = Provider.objects()
                for provider in all_providers:
                    if provider not in matching_providers and provider.skills:
                        for skill in provider.skills:
                            for search_term in [service.name.lower(), service.category.lower()]:
                                if search_term and (search_term in skill.lower() or skill.lower() in search_term):
                                    matching_providers.append(provider)
                                    break
                        if provider in matching_providers:
                            break
            
            # Send notifications to matching providers
            print(f"Found {len(matching_providers)} matching providers for service: {service.name}")
            for provider in matching_providers:
                print(f"Notifying provider: {provider.id} (user: {provider.user.id if provider.user else 'None'})")
                socketio.emit('new_booking_available', {
                    'booking': serialize_booking(booking),
                    'service_name': service.name,
                    'location': {
                        'lat': location_lat,
                        'lon': location_lon
                    }
                }, to=f"provider_{provider.id}")
                
                # Also notify the user object for the provider
                if provider.user:
                    socketio.emit('new_booking_available', {
                        'booking': serialize_booking(booking),
                        'service_name': service.name,
                        'location': {
                            'lat': location_lat,
                            'lon': location_lon
                        }
                    }, to=f"provider_{provider.user.id}")
        
        # Also broadcast to all connected providers
        socketio.emit('new_booking_available', {
            'booking': serialize_booking(booking),
            'service_name': service.name if service else 'General Service',
            'location': {
                'lat': location_lat,
                'lon': location_lon
            }
        }, to='all_providers')
    
    return jsonify(serialize_booking(booking)), 201


@booking_bp.post('/payments/mock')
@jwt_required()
def mock_payment():
    data = request.get_json() or {}
    booking_id = str(data.get('booking_id'))
    amount = data.get('amount')
    method = data.get('method', 'Cash')

    try:
        booking = Booking.objects(id=ObjectId(booking_id)).first()
        if not booking:
            return jsonify({'message': 'Booking not found'}), 404

        payment = Payment(booking=booking, amount=amount or (booking.price or 0), method=method, status='Success')
        payment.save()
        
        # Update booking with payment reference
        booking.payment = payment
        booking.save()
        
        return jsonify({'message': 'Payment recorded', 'payment_id': str(payment.id)})
    except Exception as e:
        return jsonify({'message': 'Invalid booking ID'}), 400


@booking_bp.post('/bookings/accept')
@jwt_required()
def accept_booking():
    data = request.get_json() or {}
    booking_id = str(data.get('booking_id'))
    try:
        booking = Booking.objects(id=ObjectId(booking_id)).first()
        if not booking:
            return jsonify({'message': 'Booking not found'}), 404
        booking.status = 'Accepted'
        booking.save()
        _broadcast_status(booking)
        return jsonify({'message': 'Accepted'})
    except Exception as e:
        return jsonify({'message': 'Invalid booking ID'}), 400


@booking_bp.post('/bookings/reject')
@jwt_required()
def reject_booking():
    data = request.get_json() or {}
    booking_id = str(data.get('booking_id'))
    try:
        booking = Booking.objects(id=ObjectId(booking_id)).first()
        if not booking:
            return jsonify({'message': 'Booking not found'}), 404
        booking.status = 'Rejected'
        booking.save()
        _broadcast_status(booking)
        return jsonify({'message': 'Rejected'})
    except Exception as e:
        return jsonify({'message': 'Invalid booking ID'}), 400


@booking_bp.post('/bookings/update_status')
@jwt_required()
def update_status():
    data = request.get_json() or {}
    booking_id = str(data.get('booking_id'))
    status = data.get('status')
    if not status:
        return jsonify({'message': 'Missing status'}), 400
    
    try:
        booking = Booking.objects(id=ObjectId(booking_id)).first()
        if not booking:
            return jsonify({'message': 'Booking not found'}), 404
        booking.status = status
        booking.save()
        _broadcast_status(booking)
        return jsonify({'message': 'Updated'})
    except Exception as e:
        return jsonify({'message': 'Invalid booking ID'}), 400


@booking_bp.post('/bookings/rate')
@jwt_required()
def rate_booking_old():
    data = request.get_json() or {}
    booking_id = str(data.get('booking_id'))
    try:
        rating = float(data.get('rating'))
    except Exception:
        return jsonify({'message': 'rating must be a number'}), 400

    if rating < 1 or rating > 5:
        return jsonify({'message': 'rating must be between 1 and 5'}), 400

    try:
        booking = Booking.objects(id=ObjectId(booking_id)).first()
        if not booking:
            return jsonify({'message': 'Booking not found'}), 404
        booking.rating = rating
        booking.save()
        return jsonify({'message': 'Rated', 'booking': serialize_booking(booking)})
    except Exception:
        return jsonify({'message': 'Invalid booking ID'}), 400


def _broadcast_status(booking: Booking):
    payload = serialize_booking(booking)
    socketio.emit('booking_status', payload, to=f"booking_{booking.id}")


def serialize_booking(b: Booking):
    return {
        'id': str(b.id),
        'user_id': str(b.user.id) if b.user else None,
        'provider_id': str(b.provider.id) if b.provider else b.provider_id,
        'provider_name': b.provider_name or (b.provider.user.name if b.provider and b.provider.user else None),
        'service_id': str(b.service.id) if b.service else None,
        'service_name': b.service_name or (b.service.name if b.service else 'Unknown Service'),
        'status': b.status,
        'scheduled_time': b.scheduled_time.isoformat() if b.scheduled_time else None,
        'price': b.price,
        'location_lat': b.location_lat,
        'location_lon': b.location_lon,
        'notes': b.notes,
        'rating': b.rating,
        'review': b.review,
        'completion_notes': b.completion_notes,
        'completion_images': b.completion_images or [],
        'completed_at': b.completed_at.isoformat() if b.completed_at else None,
        'created_at': b.created_at.isoformat() if b.created_at else None,
        'has_payment': b.has_payment or (b.payment is not None),
        'payment_status': b.payment_status or (b.payment.status if b.payment else 'Pending')
    }


@booking_bp.post('/bookings/<booking_id>/rate')
@jwt_required()
def rate_booking(booking_id):
    """Rate a completed booking"""
    ident = get_jwt_identity()
    user_id = str(ident) if isinstance(ident, str) else str(ident['id'])
    
    try:
        booking = Booking.objects(id=ObjectId(booking_id)).first()
        if not booking:
            return jsonify({'message': 'Booking not found'}), 404
        
        # Verify user owns this booking
        if str(booking.user.id) != user_id:
            return jsonify({'message': 'Unauthorized'}), 403
        
        # Verify booking is completed
        if booking.status != 'Completed':
            return jsonify({'message': 'Can only rate completed bookings'}), 400
        
        # Check if already rated
        if booking.rating:
            return jsonify({'message': 'Booking already rated'}), 400
        
        data = request.get_json()
        rating = data.get('rating')
        review = data.get('review', '')
        
        if not rating or not isinstance(rating, (int, float)) or rating < 1 or rating > 5:
            return jsonify({'message': 'Invalid rating. Must be between 1 and 5'}), 400
        
        # Update booking with rating and review
        booking.rating = float(rating)
        booking.review = review
        booking.save()
        
        # Update provider's average rating
        if booking.provider:
            provider = booking.provider
            provider_user = provider.user
            
            # Calculate new average rating
            provider_bookings = Booking.objects(provider=provider, rating__exists=True)
            if provider_bookings:
                total_rating = sum(b.rating for b in provider_bookings)
                provider_user.rating = round(total_rating / len(provider_bookings), 1)
                provider_user.save()
        
        # Emit rating event to provider
        if booking.provider:
            provider_room = f"provider_{booking.provider.id}"
            user_room = f"provider_{booking.provider.user.id}" if booking.provider.user else None
            
            socketio.emit('booking_rated', {
                'booking_id': str(booking.id),
                'rating': rating,
                'review': review,
                'user_name': booking.user.name
            }, to=provider_room)
            
            if user_room and user_room != provider_room:
                socketio.emit('booking_rated', {
                    'booking_id': str(booking.id),
                    'rating': rating,
                    'review': review,
                    'user_name': booking.user.name
                }, to=user_room)
        
        # Emit to user room
        user_room = f"user_{user_id}"
        socketio.emit('rating_submitted', {
            'booking_id': str(booking.id),
            'rating': rating,
            'review': review
        }, to=user_room)
        
        return jsonify({'message': 'Rating submitted successfully'})
        
    except Exception as e:
        print(f"Error rating booking: {e}")
        return jsonify({'message': 'Error rating booking'}), 500


@booking_bp.put('/bookings/<booking_id>/status')
@jwt_required()
def update_booking_status(booking_id):
    """Update booking status (for providers)"""
    ident = get_jwt_identity()
    user_id = str(ident) if isinstance(ident, str) else str(ident['id'])
    
    try:
        booking = Booking.objects(id=ObjectId(booking_id)).first()
        if not booking:
            return jsonify({'message': 'Booking not found'}), 404
        
        # Verify user is the provider for this booking
        if not booking.provider or str(booking.provider.user.id) != user_id:
            return jsonify({'message': 'Unauthorized'}), 403
        
        data = request.get_json()
        new_status = data.get('status')
        
        if not new_status or new_status not in ['Accepted', 'Rejected', 'In Progress', 'Completed', 'Cancelled']:
            return jsonify({'message': 'Invalid status'}), 400
        
        old_status = booking.status
        booking.status = new_status
        booking.save()
        
        # Emit status change to user
        user_room = f"user_{booking.user.id}"
        socketio.emit('booking_status_change', {
            'booking_id': str(booking.id),
            'status': new_status,
            'old_status': old_status,
            'provider_name': booking.provider.user.name,
            'service_name': booking.service.name if booking.service else 'Service'
        }, to=user_room)
        
        # Emit to provider room
        provider_room = f"provider_{booking.provider.id}"
        socketio.emit('booking_status_updated', {
            'booking_id': str(booking.id),
            'status': new_status,
            'old_status': old_status,
            'user_name': booking.user.name,
            'service_name': booking.service.name if booking.service else 'Service'
        }, to=provider_room)
        
        return jsonify({'message': 'Status updated successfully'})
        
    except Exception as e:
        print(f"Error updating booking status: {e}")
        return jsonify({'message': 'Error updating booking status'}), 500

@booking_bp.post('/bookings/<booking_id>/cancel')
@jwt_required()
def cancel_booking(booking_id):
    ident = get_jwt_identity()
    user_id = str(ident) if isinstance(ident, str) else str(ident['id'])
    
    booking = Booking.objects(id=ObjectId(booking_id)).first()
    if not booking:
        return jsonify({'error': 'Booking not found'}), 404
    
    # Check if user owns this booking
    if str(booking.user.id) != user_id:
        return jsonify({'error': 'Unauthorized'}), 403
    
    # Check if booking can be cancelled
    if booking.status in ['completed', 'cancelled']:
        return jsonify({'error': 'Booking cannot be cancelled'}), 400
    
    # Update booking status
    booking.status = 'cancelled'
    booking.cancelled_at = datetime.utcnow()
    booking.save()
    
    # Emit cancellation event via WebSocket
    socketio.emit('booking_cancelled', {
        'booking_id': str(booking.id),
        'user_id': user_id,
        'timestamp': datetime.utcnow().isoformat()
    }, room=f'booking_{booking_id}')
    
    return jsonify({'success': True, 'message': 'Booking cancelled successfully'})


@booking_bp.get('/bookings/<booking_id>/navigation')
@jwt_required()
def get_booking_navigation(booking_id):
    """Get booking data for provider navigation"""
    try:
        ident = get_jwt_identity()
        user_id = str(ident) if isinstance(ident, str) else str(ident['id'])
        user = User.objects(id=ObjectId(user_id)).first()
        
        if not user or not user.provider_profile:
            return jsonify({'error': 'Not authorized'}), 403
        
        booking = Booking.objects(id=ObjectId(booking_id)).first()
        if not booking:
            return jsonify({'error': 'Booking not found'}), 404
        
        # Verify this provider is assigned to this booking
        if not booking.provider or booking.provider.id != user.provider_profile.id:
            return jsonify({'error': 'Not authorized for this booking'}), 403
        
        # Get user details
        booking_user = booking.user
        if not booking_user:
            return jsonify({'error': 'User not found'}), 404
        
        navigation_data = {
            'user_name': booking_user.name,
            'user_phone': booking_user.phone,
            'service_name': booking.service_name or (booking.service.name if booking.service else 'Service'),
            'price': booking.price,
            'status': booking.status,
            'scheduled_time': booking.scheduled_time.isoformat() if booking.scheduled_time else None,
            'destination': {
                'lat': booking.location_lat,
                'lon': booking.location_lon
            }
        }
        
        return jsonify(navigation_data)
        
    except Exception as e:
        print(f"Error getting booking navigation: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': 'Failed to get navigation data'}), 500


# Chat API Endpoint
@booking_bp.post('/api/chat/send')
@jwt_required()
def send_chat_message():
    """Send a chat message"""
    try:
        ident = get_jwt_identity()
        user_id = str(ident) if isinstance(ident, str) else str(ident['id'])
        user = User.objects(id=ObjectId(user_id)).first()
        
        if not user:
            return jsonify({'error': 'User not found'}), 404
        
        data = request.get_json()
        booking_id = data.get('booking_id')
        sender_type = data.get('sender_type')
        message_type = data.get('type', 'text')
        content = data.get('content')
        
        if not booking_id or not sender_type or not content:
            return jsonify({'error': 'Missing required fields'}), 400
        
        booking = Booking.objects(id=ObjectId(booking_id)).first()
        if not booking:
            return jsonify({'error': 'Booking not found'}), 404
        
        # Create a simple message response (we'll use Socket.IO to handle the actual persistence)
        message_data = {
            'booking_id': booking_id,
            'sender_id': user_id,
            'sender_type': sender_type,
            'type': message_type,
            'content': content,
            'timestamp': datetime.utcnow().isoformat(),
            'status': 'sent'
        }
        
        # Emit via Socket.IO
        socketio.emit('new_message', {
            'id': f'msg_{int(datetime.utcnow().timestamp() * 1000)}',
            'booking_id': booking_id,
            'sender_type': sender_type,
            'sender_name': user.name,
            'type': message_type,
            'content': content,
            'timestamp': datetime.utcnow().isoformat()
        }, room=f'booking_{booking_id}')
        
        return jsonify(message_data)
        
    except Exception as e:
        print(f"Error sending chat message: {e}")
        return jsonify({'error': 'Failed to send message'}), 500

