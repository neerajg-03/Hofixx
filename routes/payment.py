from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from models import Booking, Payment, User
from bson import ObjectId
from datetime import datetime
import razorpay
import os
import time
import hmac
import hashlib

payment_bp = Blueprint('payment', __name__)

# Test route
@payment_bp.get('/payments/test')
def test_payment_route():
    return jsonify({'message': 'Payment blueprint is working!'})

# Test payment route without booking requirement
@payment_bp.post('/payments/test-create-order')
@jwt_required()
def test_create_order():
    """Test Razorpay order creation without booking requirement"""
    try:
        data = request.get_json()
        amount = data.get('amount', 10000)  # Default ₹100
        currency = data.get('currency', 'INR')
        
        # Create Razorpay order
        order_data = {
            'amount': amount,
            'currency': currency,
            'receipt': f'test_order_{int(time.time())}',
            'notes': {
                'test': True
            }
        }
        
        order = razorpay_client.order.create(data=order_data)
        
        return jsonify({
            'id': order['id'],
            'amount': order['amount'],
            'currency': order['currency'],
            'receipt': order['receipt']
        })
        
    except Exception as e:
        print(f"Error creating test order: {e}")
        return jsonify({'message': f'Error: {str(e)}'}), 500

# Initialize Razorpay client
razorpay_client = razorpay.Client(
    auth=(os.getenv('RAZORPAY_KEY_ID', 'rzp_test_ROb7lXNQKK4t1c'), 
          os.getenv('RAZORPAY_KEY_SECRET', 'cR1Q452dHCJ6dy2ET4shqjOG'))
)

@payment_bp.post('/payments/razorpay/create-order')
@jwt_required()
def create_razorpay_order():
    """Create a Razorpay order for payment"""
    try:
        data = request.get_json()
        amount = data.get('amount')  # Amount in paise
        currency = data.get('currency', 'INR')
        booking_id = data.get('booking_id')
        
        if not amount or not booking_id:
            return jsonify({'message': 'Missing required fields'}), 400
        
        # Get user
        ident = get_jwt_identity()
        user_id = str(ident) if isinstance(ident, str) else str(ident['id'])
        user = User.objects(id=ObjectId(user_id)).first()
        if not user:
            return jsonify({'message': 'User not found'}), 404
        
        # Get booking
        booking = Booking.objects(id=ObjectId(booking_id)).first()
        if not booking:
            return jsonify({'message': 'Booking not found'}), 404
        
        # Create Razorpay order
        order_data = {
            'amount': amount,
            'currency': currency,
            'receipt': f'booking_{booking_id}',
            'notes': {
                'booking_id': str(booking.id),
                'user_id': str(user.id),
                'service_name': booking.service_name or 'Service'
            }
        }
        
        order = razorpay_client.order.create(data=order_data)
        
        return jsonify({
            'id': order['id'],
            'amount': order['amount'],
            'currency': order['currency'],
            'receipt': order['receipt']
        })
        
    except Exception as e:
        print(f"Error creating Razorpay order: {e}")
        return jsonify({'message': 'Failed to create payment order'}), 500

@payment_bp.post('/payments/razorpay/verify')
@jwt_required()
def verify_razorpay_payment():
    """Verify Razorpay payment signature"""
    try:
        data = request.get_json()
        razorpay_payment_id = data.get('razorpay_payment_id')
        razorpay_order_id = data.get('razorpay_order_id')
        razorpay_signature = data.get('razorpay_signature')
        booking_id = data.get('booking_id')
        
        if not all([razorpay_payment_id, razorpay_order_id, razorpay_signature, booking_id]):
            return jsonify({'message': 'Missing required fields'}), 400
        
        # Get user
        ident = get_jwt_identity()
        user_id = str(ident) if isinstance(ident, str) else str(ident['id'])
        user = User.objects(id=ObjectId(user_id)).first()
        if not user:
            return jsonify({'message': 'User not found'}), 404
        
        # Get booking
        booking = Booking.objects(id=ObjectId(booking_id)).first()
        if not booking:
            return jsonify({'message': 'Booking not found'}), 404
        
        # Verify payment signature
        razorpay_secret = os.getenv('RAZORPAY_KEY_SECRET', 'test_secret')
        message = f"{razorpay_order_id}|{razorpay_payment_id}"
        generated_signature = hmac.new(
            razorpay_secret.encode(),
            message.encode(),
            hashlib.sha256
        ).hexdigest()
        
        if not hmac.compare_digest(generated_signature, razorpay_signature):
            return jsonify({'message': 'Invalid payment signature'}), 400
        
        # Get payment details from Razorpay
        payment_details = razorpay_client.payment.fetch(razorpay_payment_id)
        
        # Create payment record
        payment = Payment(
            razorpay_payment_id=razorpay_payment_id,
            razorpay_order_id=razorpay_order_id,
            amount=payment_details['amount'] / 100,  # Convert from paise to rupees
            currency=payment_details['currency'],
            status=payment_details['status'],
            method=payment_details['method'],
            user=user,
            booking=booking,
            created_at=datetime.utcnow()
        )
        payment.save()
        
        # Update booking with payment reference and status
        booking.payment = payment
        booking.has_payment = True
        booking.payment_status = payment.status
        booking.save()
        
        return jsonify({
            'message': 'Payment verified successfully',
            'payment_id': str(payment.id),
            'status': payment.status
        })
        
    except Exception as e:
        print(f"Error verifying payment: {e}")
        return jsonify({'message': 'Payment verification failed'}), 500

@payment_bp.get('/payments/booking/<booking_id>')
@jwt_required()
def get_booking_payment(booking_id):
    """Get payment details for a booking"""
    try:
        # Get user
        ident = get_jwt_identity()
        user_id = str(ident) if isinstance(ident, str) else str(ident['id'])
        
        # Get booking
        booking = Booking.objects(id=ObjectId(booking_id)).first()
        if not booking:
            return jsonify({'message': 'Booking not found'}), 404
        
        # Check if user owns this booking
        if str(booking.user.id) != user_id:
            return jsonify({'message': 'Unauthorized'}), 403
        
        if not booking.payment:
            return jsonify({'message': 'No payment found for this booking'}), 404
        
        payment = booking.payment
        return jsonify({
            'id': str(payment.id),
            'razorpay_payment_id': payment.razorpay_payment_id,
            'amount': payment.amount,
            'currency': payment.currency,
            'status': payment.status,
            'method': payment.method,
            'created_at': payment.created_at.isoformat() if payment.created_at else None
        })
        
    except Exception as e:
        print(f"Error getting payment details: {e}")
        return jsonify({'message': 'Failed to get payment details'}), 500
