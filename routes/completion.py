from flask import Blueprint, request, jsonify, current_app
from flask_jwt_extended import jwt_required, get_jwt_identity
from extensions import socketio
from models import Booking, ServiceCompletion, Payment, User, Provider
from bson import ObjectId
from datetime import datetime
import os
import uuid
import razorpay
from werkzeug.utils import secure_filename

completion_bp = Blueprint('completion', __name__)

# Configure Razorpay (Live Mode)
RAZORPAY_KEY_ID = os.getenv('RAZORPAY_KEY_ID', 'rzp_live_your_live_key_id_here')
RAZORPAY_KEY_SECRET = os.getenv('RAZORPAY_KEY_SECRET', 'your_live_key_secret_here')

razorpay_client = razorpay.Client(auth=(RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET))

# Allowed file extensions for image uploads
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


@completion_bp.post('/completion/upload')
@jwt_required()
def upload_service_completion():
    """Upload service completion details and images"""
    ident = get_jwt_identity()
    user_id = str(ident) if isinstance(ident, str) else str(ident['id'])
    
    print(f"Completion upload request - User ID: {user_id}")  # Debug logging
    print(f"Request content type: {request.content_type}")  # Debug logging
    print(f"Request form data: {request.form}")  # Debug logging
    print(f"Request files: {list(request.files.keys())}")  # Debug logging
    
    try:
        user = User.objects(id=ObjectId(user_id)).first()
        if not user or user.role != 'provider':
            return jsonify({'message': 'Provider not found'}), 404
        
        provider = user.provider_profile
        if not provider:
            return jsonify({'message': 'Provider profile not found'}), 404
        
        # Handle both JSON and form data
        if request.is_json:
            data = request.get_json() or {}
            booking_id = data.get('booking_id')
            completion_notes = data.get('completion_notes', '')
        else:
            # Handle form data
            booking_id = request.form.get('booking_id')
            completion_notes = request.form.get('completion_notes', '')
        
        print(f"Parsed booking_id: {booking_id}")  # Debug logging
        print(f"Parsed completion_notes: {completion_notes}")  # Debug logging
        
        if not booking_id:
            return jsonify({'message': 'Booking ID is required'}), 400
        
        try:
            booking = Booking.objects(id=ObjectId(booking_id)).first()
            print(f"Booking found: {booking.id if booking else 'None'}")  # Debug logging
        except Exception as e:
            print(f"Error looking up booking: {e}")  # Debug logging
            return jsonify({'message': 'Invalid booking ID format'}), 400
        
        if not booking:
            return jsonify({'message': 'Booking not found'}), 404
        
        # Verify provider owns this booking
        if not booking.provider or str(booking.provider.id) != str(provider.id):
            return jsonify({'message': 'Unauthorized'}), 403
        
        # Check if booking is in progress
        if booking.status != 'In Progress':
            return jsonify({'message': 'Booking must be in progress to upload completion'}), 400
        
        # Handle file uploads
        uploaded_images = []
        if 'images' in request.files:
            files = request.files.getlist('images')
            for file in files:
                if file and allowed_file(file.filename):
                    # Generate unique filename
                    filename = secure_filename(file.filename)
                    unique_filename = f"{uuid.uuid4()}_{filename}"
                    
                    # Create upload directory if it doesn't exist
                    upload_dir = os.path.join(current_app.static_folder, 'uploads', 'completions')
                    os.makedirs(upload_dir, exist_ok=True)
                    
                    # Save file
                    file_path = os.path.join(upload_dir, unique_filename)
                    file.save(file_path)
                    
                    # Store relative URL
                    relative_path = f"uploads/completions/{unique_filename}"
                    uploaded_images.append(relative_path)
        
        # Create service completion record
        completion = ServiceCompletion(
            booking=booking,
            provider=provider,
            completion_notes=completion_notes,
            images=uploaded_images
        )
        completion.save()
        
        # Update booking with completion details
        booking.completion_notes = completion_notes
        booking.completion_images = uploaded_images
        booking.completed_at = datetime.utcnow()
        booking.status = 'Completed'
        booking.save()
        
        # Notify user about service completion
        user_room = f"user_{booking.user.id}"
        socketio.emit('service_completed', {
            'booking_id': str(booking.id),
            'provider_name': user.name,
            'service_name': booking.service.name if booking.service else 'Service',
            'completion_notes': completion_notes,
            'images': uploaded_images,
            'completed_at': booking.completed_at.isoformat()
        }, to=user_room)
        
        # Notify provider
        provider_room = f"provider_{provider.id}"
        socketio.emit('completion_uploaded', {
            'booking_id': str(booking.id),
            'user_name': booking.user.name,
            'service_name': booking.service.name if booking.service else 'Service',
            'completion_notes': completion_notes,
            'images': uploaded_images
        }, to=provider_room)
        
        return jsonify({
            'message': 'Service completion uploaded successfully',
            'completion_id': str(completion.id),
            'booking_id': str(booking.id),
            'images': uploaded_images
        })
        
    except Exception as e:
        print(f"Error uploading service completion: {e}")
        import traceback
        traceback.print_exc()  # Print full traceback for debugging
        return jsonify({'message': f'Error uploading service completion: {str(e)}'}), 500


@completion_bp.get('/completion/<booking_id>')
@jwt_required()
def get_service_completion(booking_id):
    """Get service completion details for a booking"""
    ident = get_jwt_identity()
    user_id = str(ident) if isinstance(ident, str) else str(ident['id'])
    
    try:
        booking = Booking.objects(id=ObjectId(booking_id)).first()
        if not booking:
            return jsonify({'message': 'Booking not found'}), 404
        
        # Check if user has access to this booking
        user = User.objects(id=ObjectId(user_id)).first()
        if not user:
            return jsonify({'message': 'User not found'}), 404
        
        # Allow access if user is the booking owner or the provider
        has_access = False
        if str(booking.user.id) == user_id:
            has_access = True
        elif (booking.provider and booking.provider.user and 
              str(booking.provider.user.id) == user_id):
            has_access = True
        
        if not has_access:
            return jsonify({'message': 'Unauthorized'}), 403
        
        # Get completion details
        completion = ServiceCompletion.objects(booking=booking).first()
        
        return jsonify({
            'booking_id': str(booking.id),
            'status': booking.status,
            'completion_notes': booking.completion_notes,
            'completion_images': booking.completion_images or [],
            'completed_at': booking.completed_at.isoformat() if booking.completed_at else None,
            'completion_details': {
                'id': str(completion.id) if completion else None,
                'notes': completion.completion_notes if completion else None,
                'images': completion.images if completion else [],
                'completed_at': completion.completed_at.isoformat() if completion else None
            } if completion else None
        })
        
    except Exception as e:
        print(f"Error getting service completion: {e}")
        return jsonify({'message': 'Error getting service completion'}), 500


# Payment route moved to payment.py to avoid conflicts


# Payment verification route moved to payment.py to avoid conflicts


@completion_bp.get('/payments/<booking_id>/status')
@jwt_required()
def get_payment_status(booking_id):
    """Get payment status for a booking"""
    ident = get_jwt_identity()
    user_id = str(ident) if isinstance(ident, str) else str(ident['id'])
    
    try:
        booking = Booking.objects(id=ObjectId(booking_id)).first()
        if not booking:
            return jsonify({'message': 'Booking not found'}), 404
        
        # Verify user owns this booking
        if str(booking.user.id) != user_id:
            return jsonify({'message': 'Unauthorized'}), 403
        
        if not booking.payment:
            return jsonify({
                'has_payment': False,
                'status': 'No payment required',
                'amount': booking.price
            })
        
        payment = booking.payment
        return jsonify({
            'has_payment': True,
            'payment_id': str(payment.id),
            'amount': payment.amount,
            'method': payment.method,
            'status': payment.status,
            'created_at': payment.created_at.isoformat(),
            'razorpay_order_id': payment.razorpay_order_id,
            'razorpay_payment_id': payment.razorpay_payment_id
        })
        
    except Exception as e:
        print(f"Error getting payment status: {e}")
        return jsonify({'message': 'Error getting payment status'}), 500
