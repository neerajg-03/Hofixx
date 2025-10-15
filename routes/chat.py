from flask import Blueprint, request, jsonify, url_for
from flask_jwt_extended import jwt_required, get_jwt_identity
from werkzeug.utils import secure_filename
from models import ChatMessage, Booking, User, Provider, ServiceRequest, ProviderQuote
from bson import ObjectId
import os
from datetime import datetime

chat_bp = Blueprint('chat', __name__)


@chat_bp.get('/api/chat/<booking_id>/messages')
@jwt_required()
def get_chat_messages(booking_id):
    """Get all messages for a specific booking"""
    try:
        # Verify user has access to this booking
        user_id = get_jwt_identity()
        if isinstance(user_id, dict):
            user_id = user_id.get('id')
        
        booking = Booking.objects(id=ObjectId(booking_id)).first()
        if not booking:
            return jsonify({'error': 'Booking not found'}), 404
        
        # Check if user is either the customer or the provider
        user = User.objects(id=ObjectId(user_id)).first()
        if not user:
            return jsonify({'error': 'User not found'}), 404
        
        has_access = False
        if str(booking.user.id) == str(user_id):
            has_access = True
        elif booking.provider and str(booking.provider.user.id) == str(user_id):
            has_access = True
        
        if not has_access:
            return jsonify({'error': 'Access denied'}), 403
        
        # Get messages
        messages = ChatMessage.objects(booking_id=booking_id).order_by('created_at')
        
        result = []
        for msg in messages:
            result.append({
                'id': str(msg.id),
                'booking_id': msg.booking_id,
                'sender_type': msg.sender_type,
                'sender_name': msg.customer_name if msg.sender_type == 'user' else msg.provider_name,
                'sender_avatar': get_user_avatar(msg.sender),
                'type': msg.message_type,
                'content': msg.content,
                'file_name': msg.file_name,
                'file_url': msg.file_url,
                'location': msg.location,
                'status': msg.status,
                'timestamp': msg.created_at.isoformat()
            })
        
        return jsonify(result)
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@chat_bp.get('/api/provider/conversations')
@jwt_required()
def get_provider_conversations():
    """Get all conversations for a provider"""
    try:
        user_id = get_jwt_identity()
        if isinstance(user_id, dict):
            user_id = user_id.get('id')
        
        user = User.objects(id=ObjectId(user_id)).first()
        if not user or user.role != 'provider':
            return jsonify({'error': 'Provider access required'}), 403
        
        # Get all bookings for this provider
        # First get the provider object, then query bookings
        provider = Provider.objects(user=user).first()
        if not provider:
            return jsonify({'error': 'Provider profile not found'}), 404
        
        bookings = Booking.objects(provider=provider).order_by('-created_at')
        
        conversations = []
        for booking in bookings:
            # Get last message
            last_message = ChatMessage.objects(booking_id=str(booking.id)).order_by('-created_at').first()
            
            # Count unread messages (messages from user that are not read)
            unread_count = ChatMessage.objects(
                booking_id=str(booking.id),
                sender_type='user',
                status__in=['sent', 'delivered']
            ).count()
            
            conversations.append({
                'booking_id': str(booking.id),
                'customer_name': booking.user.name,
                'customer_avatar': get_user_avatar(booking.user),
                'service_name': booking.service_name or 'Service',
                'last_message': {
                    'content': last_message.content if last_message else 'No messages yet',
                    'timestamp': last_message.created_at.isoformat() if last_message else booking.created_at.isoformat()
                } if last_message else None,
                'updated_at': last_message.created_at.isoformat() if last_message else booking.created_at.isoformat(),
                'unread_count': unread_count
            })
        
        return jsonify(conversations)
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@chat_bp.post('/api/chat/upload')
@jwt_required()
def upload_chat_file():
    """Upload a file for chat"""
    try:
        if 'file' not in request.files:
            return jsonify({'error': 'No file provided'}), 400
        
        file = request.files['file']
        if file.filename == '':
            return jsonify({'error': 'No file selected'}), 400
        
        # Get file info
        filename = secure_filename(file.filename)
        file_ext = os.path.splitext(filename)[1]
        
        # Create upload directory
        upload_dir = os.path.join('static', 'uploads', 'chat')
        os.makedirs(upload_dir, exist_ok=True)
        
        # Generate unique filename
        unique_filename = f"{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}_{filename}"
        file_path = os.path.join(upload_dir, unique_filename)
        
        # Save file
        file.save(file_path)
        
        # Return file URL
        file_url = url_for('static', filename=f'uploads/chat/{unique_filename}', _external=True)
        
        return jsonify({
            'success': True,
            'file_url': file_url,
            'file_name': filename
        })
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@chat_bp.post('/api/chat/send')
@jwt_required()
def send_chat_message():
    """Send a chat message"""
    try:
        data = request.get_json()
        
        user_id = get_jwt_identity()
        if isinstance(user_id, dict):
            user_id = user_id.get('id')
        
        user = User.objects(id=ObjectId(user_id)).first()
        if not user:
            return jsonify({'error': 'User not found'}), 404
        
        # Validate required fields
        required_fields = ['booking_id', 'sender_type', 'type']
        for field in required_fields:
            if field not in data:
                return jsonify({'error': f'Missing required field: {field}'}), 400
        
        # Verify booking exists and user has access
        booking = Booking.objects(id=ObjectId(data['booking_id'])).first()
        if not booking:
            return jsonify({'error': 'Booking not found'}), 404
        
        # Check access
        has_access = False
        if str(booking.user.id) == str(user_id):
            has_access = True
        elif booking.provider and str(booking.provider.user.id) == str(user_id):
            has_access = True
        
        if not has_access:
            return jsonify({'error': 'Access denied'}), 403
        
        # Create message
        message = ChatMessage(
            booking=booking,
            sender=user,
            sender_type=data['sender_type'],
            message_type=data['type'],
            booking_id=data['booking_id'],
            status='sent'
        )
        
        # Set content based on message type
        if data['type'] == 'text':
            message.content = data.get('content', '')
        elif data['type'] == 'file':
            message.file_name = data.get('file_name', '')
            message.file_url = data.get('file_url', '')
        elif data['type'] == 'location':
            message.location = data.get('location', {})
        
        # Set names for easier querying
        if data['sender_type'] == 'user':
            message.customer_name = user.name
            if booking.provider:
                message.provider_name = booking.provider.user.name
                message.provider_id = str(booking.provider.id)
        else:
            message.provider_name = user.name
            message.provider_id = str(booking.provider.id) if booking.provider else None
            message.customer_name = booking.user.name
        
        message.save()
        
        # Emit WebSocket event to notify the other party
        from app import socketio
        
        # Emit to provider if user sent the message
        if data['sender_type'] == 'user' and booking.provider:
            # Try both possible provider room formats
            provider_user_id = str(booking.provider.user.id)
            provider_profile_id = str(booking.provider.id)
            booking_provider_id = booking.provider_id
            
            print(f"=== WEBSOCKET EMISSION DEBUG ===")
            print(f"Provider user ID: {provider_user_id}")
            print(f"Provider profile ID: {provider_profile_id}")
            print(f"Booking provider_id field: {booking_provider_id}")
            
            # Try the provider user ID first (most likely correct)
            provider_room = f"provider_{provider_user_id}"
            message_data = {
                'booking_id': message.booking_id,
                'message': message.content,
                'sender_type': message.sender_type,
                'sender_name': message.customer_name,
                'timestamp': message.created_at.isoformat()
            }
            print(f"Emitting new_message to room: {provider_room}")
            print(f"Message data: {message_data}")
            socketio.emit('new_message', message_data, room=provider_room)
        
        # Emit to user if provider sent the message
        elif data['sender_type'] == 'provider':
            socketio.emit('new_message', {
                'booking_id': message.booking_id,
                'message': message.content,
                'sender_type': message.sender_type,
                'sender_name': message.provider_name,
                'timestamp': message.created_at.isoformat()
            }, room=f"user_{booking.user.id}")
        
        # Return message data
        result = {
            'id': str(message.id),
            'booking_id': message.booking_id,
            'sender_type': message.sender_type,
            'sender_name': message.customer_name if message.sender_type == 'user' else message.provider_name,
            'sender_avatar': get_user_avatar(message.sender),
            'type': message.message_type,
            'content': message.content,
            'file_name': message.file_name,
            'file_url': message.file_url,
            'location': message.location,
            'status': message.status,
            'timestamp': message.created_at.isoformat()
        }
        
        return jsonify(result)
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500


def get_user_avatar(user):
    """Get user avatar URL"""
    if user.avatar_path:
        return url_for('static', filename=user.avatar_path, _external=True)
    else:
        # Generate avatar using user's name
        initials = ''.join([name[0] for name in user.name.split()[:2]]).upper()
        return f"https://api.dicebear.com/7.x/initials/svg?seed={initials}&size=40"


# Provider-Service Request Chat Endpoints

@chat_bp.get('/api/provider/conversations/<request_id>')
@jwt_required()
def get_provider_conversation(request_id):
    """Get chat messages for a service request (provider side)"""
    try:
        user_id = get_jwt_identity()
        if isinstance(user_id, dict):
            user_id = user_id.get('id')
        
        # Get provider
        provider = Provider.objects(user=ObjectId(user_id)).first()
        if not provider:
            return jsonify({'error': 'Provider not found'}), 404
        
        # Get service request
        service_request = ServiceRequest.objects(id=ObjectId(request_id)).first()
        if not service_request:
            return jsonify({'error': 'Service request not found'}), 404
        
        # Check if provider has quoted on this request
        quote = ProviderQuote.objects(service_request=service_request, provider=provider).first()
        if not quote:
            return jsonify({'error': 'Access denied. You must submit a quote to chat.'}), 403
        
        # Get messages for this service request
        messages = ChatMessage.objects(
            service_request_id=request_id
        ).order_by('created_at')
        
        result = []
        for msg in messages:
            result.append({
                'id': str(msg.id),
                'request_id': request_id,
                'sender_type': msg.sender_type,
                'sender_name': msg.customer_name if msg.sender_type == 'user' else msg.provider_name,
                'message': msg.message,
                'timestamp': msg.created_at.isoformat(),
                'avatar': get_user_avatar(msg.sender) if msg.sender else None
            })
        
        return jsonify({'messages': result})
        
    except Exception as e:
        print(f"Error getting provider conversation: {e}")
        return jsonify({'error': 'Failed to get conversation'}), 500


@chat_bp.post('/api/provider/send-message')
@jwt_required()
def send_provider_message():
    """Send a message from provider to customer for a service request"""
    try:
        user_id = get_jwt_identity()
        if isinstance(user_id, dict):
            user_id = user_id.get('id')
        
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No data provided'}), 400
        
        request_id = data.get('request_id')
        message = data.get('message', '').strip()
        
        if not request_id or not message:
            return jsonify({'error': 'Request ID and message are required'}), 400
        
        # Get provider
        provider = Provider.objects(user=ObjectId(user_id)).first()
        if not provider:
            return jsonify({'error': 'Provider not found'}), 404
        
        # Get service request
        service_request = ServiceRequest.objects(id=ObjectId(request_id)).first()
        if not service_request:
            return jsonify({'error': 'Service request not found'}), 404
        
        # Check if provider has quoted on this request
        quote = ProviderQuote.objects(service_request=service_request, provider=provider).first()
        if not quote:
            return jsonify({'error': 'Access denied. You must submit a quote to chat.'}), 403
        
        # Create message
        chat_message = ChatMessage(
            service_request=service_request,
            service_request_id=request_id,
            sender=ObjectId(user_id),
            sender_type='provider',
            message_type='text',
            message=message,
            content=message,
            provider_name=provider.user.name,
            customer_name=service_request.user.name
        )
        chat_message.save()
        
        # Emit to customer via WebSocket
        from app import socketio
        socketio.emit('new_message', {
            'request_id': request_id,
            'message': message,
            'sender_type': 'provider',
            'sender_name': provider.user.name,
            'timestamp': chat_message.created_at.isoformat()
        }, room=f"user_{service_request.user.id}")
        
        return jsonify({'success': True, 'message_id': str(chat_message.id)})
        
    except Exception as e:
        print(f"Error sending provider message: {e}")
        return jsonify({'error': 'Failed to send message'}), 500


@chat_bp.get('/api/user/conversations/<request_id>')
@jwt_required()
def get_user_conversation(request_id):
    """Get chat messages for a service request (user side)"""
    try:
        user_id = get_jwt_identity()
        if isinstance(user_id, dict):
            user_id = user_id.get('id')
        
        # Get service request
        service_request = ServiceRequest.objects(id=ObjectId(request_id)).first()
        if not service_request:
            return jsonify({'error': 'Service request not found'}), 404
        
        # Check if user owns this request
        if str(service_request.user.id) != str(user_id):
            return jsonify({'error': 'Access denied'}), 403
        
        # Get messages for this service request
        messages = ChatMessage.objects(
            service_request_id=request_id
        ).order_by('created_at')
        
        result = []
        for msg in messages:
            result.append({
                'id': str(msg.id),
                'request_id': request_id,
                'sender_type': msg.sender_type,
                'sender_name': msg.customer_name if msg.sender_type == 'user' else msg.provider_name,
                'message': msg.message,
                'timestamp': msg.created_at.isoformat(),
                'avatar': get_user_avatar(msg.sender) if msg.sender else None
            })
        
        return jsonify({'messages': result})
        
    except Exception as e:
        print(f"Error getting user conversation: {e}")
        return jsonify({'error': 'Failed to get conversation'}), 500


@chat_bp.post('/api/user/send-message')
@jwt_required()
def send_user_message():
    """Send a message from user to provider for a service request"""
    try:
        user_id = get_jwt_identity()
        if isinstance(user_id, dict):
            user_id = user_id.get('id')
        
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No data provided'}), 400
        
        request_id = data.get('request_id')
        message = data.get('message', '').strip()
        
        if not request_id or not message:
            return jsonify({'error': 'Request ID and message are required'}), 400
        
        # Get service request
        service_request = ServiceRequest.objects(id=ObjectId(request_id)).first()
        if not service_request:
            return jsonify({'error': 'Service request not found'}), 404
        
        # Check if user owns this request
        if str(service_request.user.id) != str(user_id):
            return jsonify({'error': 'Access denied'}), 403
        
        # Create message
        chat_message = ChatMessage(
            service_request=service_request,
            service_request_id=request_id,
            sender=ObjectId(user_id),
            sender_type='user',
            message_type='text',
            message=message,
            content=message,
            customer_name=service_request.user.name,
            provider_name=service_request.user.name  # Will be updated if provider responds
        )
        chat_message.save()
        
        # Emit to providers who have quoted on this request
        from app import socketio
        quotes = ProviderQuote.objects(service_request=service_request)
        for quote in quotes:
            socketio.emit('new_message', {
                'request_id': request_id,
                'message': message,
                'sender_type': 'user',
                'sender_name': service_request.user.name,
                'timestamp': chat_message.created_at.isoformat()
            }, room=f"provider_{quote.provider.user.id}")
        
        return jsonify({'success': True, 'message_id': str(chat_message.id)})
        
    except Exception as e:
        print(f"Error sending user message: {e}")
        return jsonify({'error': 'Failed to send message'}), 500
