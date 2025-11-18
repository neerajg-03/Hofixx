from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from models import Booking, Payment, User, Order
from bson import ObjectId
from datetime import datetime
import razorpay
import os
import time
import hmac
import hashlib
from services.wallet_service import record_transaction, WalletError
from services.provider_deposit_service import deduct_commission, ProviderDepositError

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
            'receipt': order['receipt'],
            'key_id': os.getenv('RAZORPAY_KEY_ID', 'rzp_test_ROb7lXNQKK4t1c')
        })
        
    except Exception as e:
        print(f"Error creating test order: {e}")
        return jsonify({'message': f'Error: {str(e)}'}), 500

# Initialize Razorpay client
# Validate keys before initializing
razorpay_key_id = os.getenv('RAZORPAY_KEY_ID', 'rzp_test_ROb7lXNQKK4t1c')
razorpay_key_secret = os.getenv('RAZORPAY_KEY_SECRET', 'cR1Q452dHCJ6dy2ET4shqjOG')

# Check if placeholder keys are being used
if 'your_live_key_id_here' in razorpay_key_id or 'placeholder' in razorpay_key_id.lower():
    print("WARNING: Razorpay API key appears to be a placeholder. Please set RAZORPAY_KEY_ID in your environment variables.")
if 'your_live_key_secret_here' in razorpay_key_secret or 'placeholder' in razorpay_key_secret.lower():
    print("WARNING: Razorpay API secret appears to be a placeholder. Please set RAZORPAY_KEY_SECRET in your environment variables.")

razorpay_client = razorpay.Client(
    auth=(razorpay_key_id, razorpay_key_secret)
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
            'receipt': order['receipt'],
            'key_id': os.getenv('RAZORPAY_KEY_ID', 'rzp_test_ROb7lXNQKK4t1c')
        })
        
    except Exception as e:
        print(f"Error creating Razorpay order: {e}")
        return jsonify({'message': 'Failed to create payment order'}), 500

@payment_bp.get('/payments/razorpay/get-key')
def get_razorpay_key():
    """Get Razorpay key ID for frontend"""
    return jsonify({
        'key_id': os.getenv('RAZORPAY_KEY_ID', 'rzp_test_ROb7lXNQKK4t1c')
    })

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


@payment_bp.post('/payments/wallet/pay')
@jwt_required()
def pay_booking_with_wallet():
    """Allow a user to pay for a booking using wallet credits."""
    try:
        data = request.get_json() or {}
        booking_id = data.get('booking_id')
        amount_param = data.get('amount')

        if not booking_id:
            return jsonify({'error': 'booking_id is required'}), 400

        # Get current user
        ident = get_jwt_identity()
        user_id = str(ident) if isinstance(ident, str) else str(ident['id'])
        user = User.objects(id=ObjectId(user_id)).first()
        if not user:
            return jsonify({'error': 'User not found'}), 404

        # Locate booking
        try:
            booking = Booking.objects(id=ObjectId(booking_id)).first()
        except Exception:
            booking = Booking.objects(id=booking_id).first()

        if not booking:
            return jsonify({'error': 'Booking not found'}), 404

        if not booking.user or str(booking.user.id) != user_id:
            return jsonify({'error': 'You are not authorized to pay for this booking'}), 403

        if booking.has_payment:
            return jsonify({'error': 'This booking already has a completed payment'}), 400

        booking_amount = float(booking.price or 0.0)
        if booking_amount <= 0:
            return jsonify({'error': 'Booking amount is invalid'}), 400

        if amount_param is None:
            payable_amount = booking_amount
        else:
            try:
                payable_amount = float(amount_param)
            except (ValueError, TypeError):
                return jsonify({'error': 'Invalid amount format'}), 400

        if payable_amount <= 0:
            return jsonify({'error': 'Amount must be greater than zero'}), 400

        # If amount provided differs notably from booking amount, enforce booking amount
        if abs(payable_amount - booking_amount) > 0.5:
            return jsonify({'error': 'Amount does not match booking total'}), 400

        payable_amount = booking_amount  # Ensure exact booking price is charged

        try:
            new_balance = record_transaction(
                user,
                payable_amount,
                transaction_type='debit',
                source='service_payment',
                description=f'Wallet payment for booking {booking.service_name or str(booking.id)}'
            )
        except WalletError as exc:
            return jsonify({'error': str(exc)}), 400
        except Exception as exc:
            print(f"Wallet transaction error: {exc}")
            return jsonify({'error': 'Failed to process wallet payment'}), 500

        payment = Payment(
            amount=payable_amount,
            currency='INR',
            status='Success',
            method='Wallet',
            user=user,
            booking=booking,
            created_at=datetime.utcnow()
        )
        payment.save()

        booking.payment = payment
        booking.has_payment = True
        booking.payment_status = 'Success'
        booking.save()

        return jsonify({
            'success': True,
            'payment_id': str(payment.id),
            'new_balance': new_balance,
            'message': 'Payment completed using wallet funds'
        })

    except Exception as e:
        print(f"Error processing wallet payment: {e}")
        return jsonify({'error': 'Failed to complete wallet payment'}), 500

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


@payment_bp.post('/payments/mark-cash')
@jwt_required()
def mark_cash_payment():
    """Mark a booking as paid with cash and deduct commission from provider deposit"""
    try:
        ident = get_jwt_identity()
        user_id = str(ident) if isinstance(ident, str) else str(ident['id'])
        user = User.objects(id=ObjectId(user_id)).first()
        
        if not user or user.role != 'provider':
            return jsonify({'error': 'Only providers can mark cash payments'}), 403
        
        provider = user.provider_profile
        if not provider:
            return jsonify({'error': 'Provider profile not found'}), 404
        
        data = request.get_json() or {}
        booking_id = data.get('booking_id')
        
        if not booking_id:
            return jsonify({'error': 'Booking ID is required'}), 400
        
        booking = Booking.objects(id=ObjectId(booking_id)).first()
        if not booking:
            return jsonify({'error': 'Booking not found'}), 404
        
        # Verify provider owns this booking
        if not booking.provider or str(booking.provider.id) != str(provider.id):
            return jsonify({'error': 'Unauthorized'}), 403
        
        # Check if payment already exists
        if booking.payment and booking.has_payment:
            return jsonify({'error': 'Payment already recorded for this booking'}), 400
        
        # Create cash payment record
        payment = Payment(
            amount=booking.price or 0,
            currency='INR',
            status='Success',
            method='Cash',
            user=booking.user,
            booking=booking,
            created_at=datetime.utcnow()
        )
        payment.save()
        
        # Update booking with payment
        booking.payment = payment
        booking.has_payment = True
        booking.payment_status = 'Success'
        booking.save()
        
        # Deduct commission from provider's deposit
        try:
            commission_result = deduct_commission(
                provider=provider,
                booking=booking,
                commission_rate=10.0  # 10% commission
            )
            
            return jsonify({
                'success': True,
                'message': 'Cash payment recorded and commission deducted',
                'payment_id': str(payment.id),
                'commission_deducted': commission_result['commission_amount'],
                'commission_rate': commission_result['commission_rate'],
                'provider_deposit_balance': commission_result['new_balance']
            })
        except ProviderDepositError as e:
            # If commission deduction fails, still mark payment but return warning
            return jsonify({
                'success': True,
                'warning': f'Payment recorded but commission deduction failed: {str(e)}',
                'payment_id': str(payment.id),
                'requires_action': True
            }), 207  # 207 Multi-Status
        except Exception as e:
            print(f"Error deducting commission: {e}")
            import traceback
            traceback.print_exc()
            return jsonify({
                'success': True,
                'warning': f'Payment recorded but commission deduction failed: {str(e)}',
                'payment_id': str(payment.id),
                'requires_action': True
            }), 207
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': f'Failed to mark cash payment: {str(e)}'}), 500




# Razorpay payment endpoints for shop orders
@payment_bp.post('/payments/razorpay/create-order-shop')
@jwt_required()
def create_razorpay_order_shop():
    """Create a Razorpay order for shop order payment"""
    try:
        data = request.get_json()
        amount = data.get('amount')  # Amount in paise
        currency = data.get('currency', 'INR')
        order_id = data.get('order_id')  # Shop order ID
        
        if not amount or not order_id:
            return jsonify({'message': 'Missing required fields'}), 400
        
        # Get user
        ident = get_jwt_identity()
        user_id = str(ident) if isinstance(ident, str) else str(ident['id'])
        user = User.objects(id=ObjectId(user_id)).first()
        if not user:
            return jsonify({'message': 'User not found'}), 404
        
        # Get shop order
        shop_order = Order.objects(id=ObjectId(order_id)).first()
        if not shop_order:
            return jsonify({'message': 'Order not found'}), 404
        
        # Verify user owns this order
        if str(shop_order.user.id) != user_id:
            return jsonify({'message': 'Unauthorized'}), 403
        
        # Create Razorpay order
        # Receipt should be max 40 characters and unique
        receipt = f'ord_{str(shop_order.id)[:20]}' if len(str(shop_order.id)) > 20 else f'order_{str(shop_order.id)}'
        
        order_data = {
            'amount': amount,
            'currency': currency,
            'receipt': receipt[:40],  # Razorpay requires max 40 characters
            'notes': {
                'order_id': str(shop_order.id),
                'user_id': str(user.id),
                'shop_name': shop_order.shop.name if shop_order.shop else 'Shop'
            }
        }
        
        # Validate Razorpay key before proceeding
        razorpay_key_id = os.getenv('RAZORPAY_KEY_ID', 'rzp_test_ROb7lXNQKK4t1c')
        if 'your_live_key_id_here' in razorpay_key_id or 'placeholder' in razorpay_key_id.lower():
            return jsonify({
                'message': 'Razorpay API key not configured. Please set RAZORPAY_KEY_ID in your environment variables with a valid Razorpay key.',
                'error': 'invalid_key_config'
            }), 500
        
        try:
            razorpay_order = razorpay_client.order.create(data=order_data)
        except Exception as razorpay_error:
            print(f"Razorpay order creation error: {razorpay_error}")
            # Check if it's an authentication error
            error_str = str(razorpay_error).lower()
            if 'unauthorized' in error_str or '401' in error_str or 'invalid' in error_str:
                return jsonify({
                    'message': 'Invalid Razorpay API credentials. Please check your RAZORPAY_KEY_ID and RAZORPAY_KEY_SECRET in environment variables.',
                    'error': 'invalid_credentials'
                }), 401
            raise
        
        return jsonify({
            'id': razorpay_order['id'],
            'amount': razorpay_order['amount'],
            'currency': razorpay_order['currency'],
            'receipt': razorpay_order['receipt'],
            'key_id': razorpay_key_id
        })
        
    except Exception as e:
        print(f"Error creating Razorpay order for shop: {e}")
        import traceback
        traceback.print_exc()
        error_message = str(e)
        if 'amount' in error_message.lower():
            return jsonify({'message': 'Invalid payment amount. Amount must be at least ₹1 (100 paise).'}), 400
        return jsonify({'message': f'Failed to create payment order: {error_message}'}), 500


@payment_bp.post('/payments/razorpay/verify-shop')
@jwt_required()
def verify_razorpay_payment_shop():
    """Verify Razorpay payment signature for shop orders"""
    try:
        data = request.get_json()
        razorpay_payment_id = data.get('razorpay_payment_id')
        razorpay_order_id = data.get('razorpay_order_id')
        razorpay_signature = data.get('razorpay_signature')
        order_id = data.get('order_id')  # Shop order ID
        
        if not all([razorpay_payment_id, razorpay_order_id, razorpay_signature, order_id]):
            return jsonify({'message': 'Missing required fields'}), 400
        
        # Get user
        ident = get_jwt_identity()
        user_id = str(ident) if isinstance(ident, str) else str(ident['id'])
        user = User.objects(id=ObjectId(user_id)).first()
        if not user:
            return jsonify({'message': 'User not found'}), 404
        
        # Get shop order
        shop_order = Order.objects(id=ObjectId(order_id)).first()
        if not shop_order:
            return jsonify({'message': 'Order not found'}), 404
        
        # Verify user owns this order
        if str(shop_order.user.id) != user_id:
            return jsonify({'message': 'Unauthorized'}), 403
        
        # Verify payment signature
        razorpay_secret = os.getenv('RAZORPAY_KEY_SECRET', 'cR1Q452dHCJ6dy2ET4shqjOG')
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
            method=payment_details.get('method', 'Razorpay'),
            user=user,
            order=shop_order,
            created_at=datetime.utcnow()
        )
        payment.save()
        
        # Update order with payment reference and status
        shop_order.payment = payment
        shop_order.payment_status = 'paid' if payment.status == 'Success' else 'failed'
        shop_order.payment_method = 'Razorpay'
        
        # Auto-confirm order and assign delivery partner if payment successful
        if payment.status == 'Success':
            shop_order.status = 'confirmed'
            shop_order.confirmed_at = datetime.utcnow()
            shop_order.save()
            
            # Auto-assign delivery partner
            try:
                from models import DeliveryPartner
                import random
                
                # Get all available delivery partners
                delivery_partners = list(DeliveryPartner.objects(is_available=True))
                if delivery_partners:
                    # Randomly select a delivery partner
                    partner = random.choice(delivery_partners)
                    shop_order.delivery_partner = partner
                    shop_order.status = 'assigned'
                    partner.is_available = False
                    partner.save()
                    shop_order.save()
                    print(f"Auto-assigned delivery partner {partner.user.name if partner.user else 'N/A'} to order {shop_order.id}")
            except Exception as e:
                print(f"Error auto-assigning delivery partner: {e}")
                import traceback
                traceback.print_exc()
                # Continue even if assignment fails
        else:
            shop_order.save()
        
        return jsonify({
            'success': True,
            'message': 'Payment verified successfully',
            'payment_id': str(payment.id),
            'status': payment.status,
            'order_id': str(shop_order.id)
        })
        
    except Exception as e:
        print(f"Error verifying shop payment: {e}")
        import traceback
        traceback.print_exc()
        error_message = str(e)
        return jsonify({'message': f'Payment verification failed: {error_message}'}), 500
