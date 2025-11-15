from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
import os
import razorpay
from datetime import datetime
from bson import ObjectId
from models import ReferralRequest, User
from services.wallet_service import record_transaction, get_wallet_summary, WalletError, resolve_user


wallet_bp = Blueprint('wallet', __name__)

razorpay_key_id = os.getenv('RAZORPAY_KEY_ID', 'rzp_test_ROb7lXNQKK4t1c')
razorpay_key_secret = os.getenv('RAZORPAY_KEY_SECRET', 'cR1Q452dHCJ6dy2ET4shqjOG')
wallet_razorpay_client = razorpay.Client(auth=(razorpay_key_id, razorpay_key_secret))


@wallet_bp.get('/api/wallet')
@jwt_required()
def get_wallet():
    """Return wallet balance and recent transactions for the authenticated user."""
    ident = get_jwt_identity()
    user = resolve_user(ident)
    if not user:
        return jsonify({'error': 'User not found'}), 404

    summary = get_wallet_summary(user)
    return jsonify(summary)


@wallet_bp.post('/api/wallet/topup')
@jwt_required()
def topup_wallet():
    """Add funds to the current user's wallet (simulated bank transfer)."""
    ident = get_jwt_identity()
    user = resolve_user(ident)
    if not user:
        return jsonify({'error': 'User not found'}), 404

    data = request.get_json() or {}
    amount = float(data.get('amount') or 0)
    description = data.get('description', 'Wallet top-up via bank transfer')

    try:
        new_balance = record_transaction(user, amount, transaction_type='credit',
                                         source='topup', description=description)
        return jsonify({
            'success': True,
            'new_balance': new_balance
        })
    except WalletError as exc:
        return jsonify({'error': str(exc)}), 400


@wallet_bp.get('/api/wallet/transactions')
@jwt_required()
def wallet_transactions():
    """Return paginated wallet transactions."""
    ident = get_jwt_identity()
    user = resolve_user(ident)
    if not user:
        return jsonify({'error': 'User not found'}), 404

    limit = int(request.args.get('limit', 20))
    summary = get_wallet_summary(user, limit=limit)
    return jsonify(summary['transactions'])


@wallet_bp.post('/api/wallet/razorpay/create-order')
@jwt_required()
def create_wallet_razorpay_order():
    try:
        ident = get_jwt_identity()
        user = resolve_user(ident)
        if not user:
            return jsonify({'error': 'User not found'}), 404

        data = request.get_json() or {}
        amount = data.get('amount')
        
        if amount is None:
            return jsonify({'error': 'Amount is required'}), 400
            
        try:
            amount = float(amount)
        except (ValueError, TypeError):
            return jsonify({'error': 'Invalid amount format'}), 400
            
        if amount <= 0:
            return jsonify({'error': 'Amount must be greater than zero'}), 400
            
        # Razorpay minimum amount is 1 rupee (100 paise)
        if amount < 1:
            return jsonify({'error': 'Minimum amount is ₹1'}), 400

        amount_paise = int(round(amount * 100))
        
        # Validate Razorpay credentials
        if not razorpay_key_id or not razorpay_key_secret:
            return jsonify({
                'error': 'Razorpay API credentials not configured. Please contact support.'
            }), 500
            
        if 'your_live_key_id_here' in razorpay_key_id or 'placeholder' in razorpay_key_id.lower():
            return jsonify({
                'error': 'Razorpay API key not configured. Please set RAZORPAY_KEY_ID in environment variables.'
            }), 500

        # Create receipt ID (max 40 characters for Razorpay)
        receipt_id = f"wallet_{str(user.id)[:20]}_{int(datetime.utcnow().timestamp())}"
        if len(receipt_id) > 40:
            receipt_id = receipt_id[:40]

        try:
            order_data = {
                'amount': amount_paise,
                'currency': 'INR',
                'receipt': receipt_id,
                'notes': {
                    'user_id': str(user.id),
                    'type': 'wallet_topup'
                }
            }
            print(f"Creating Razorpay order with data: {order_data}")
            order = wallet_razorpay_client.order.create(order_data)
            print(f"Razorpay order created successfully: {order.get('id', 'N/A')}")
        except Exception as exc:
            error_msg = str(exc)
            error_type = type(exc).__name__
            import traceback
            traceback_str = traceback.format_exc()
            print(f"Razorpay wallet order error ({error_type}): {error_msg}")
            print(f"Traceback: {traceback_str}")
            
            # Check for common error patterns
            error_str = error_msg.lower()
            
            # Check for authentication/credential errors
            if any(keyword in error_str for keyword in ['authentication', 'unauthorized', '401', 'invalid key', 'bad request']):
                return jsonify({
                    'error': 'Invalid Razorpay API credentials. Please check your RAZORPAY_KEY_ID and RAZORPAY_KEY_SECRET environment variables.',
                    'details': 'The API credentials may be incorrect or expired. Please verify your Razorpay account settings.'
                }), 500
            # Check for network errors
            elif any(keyword in error_str for keyword in ['network', 'connection', 'timeout', 'connection error']):
                return jsonify({
                    'error': 'Network error connecting to Razorpay. Please check your internet connection and try again.',
                    'details': error_msg
                }), 500
            # Check for server errors
            elif any(keyword in error_str for keyword in ['server error', '500', '503', '502']):
                return jsonify({
                    'error': 'Razorpay server error. Please try again later.',
                    'details': error_msg
                }), 500
            # Check for validation errors
            elif any(keyword in error_str for keyword in ['invalid', 'validation', 'bad request', '400']):
                return jsonify({
                    'error': f'Invalid request to Razorpay: {error_msg}',
                    'details': 'Please check the amount and other parameters.'
                }), 400
            # Generic error
            else:
                return jsonify({
                    'error': 'Failed to create payment order',
                    'details': error_msg,
                    'error_type': error_type
                }), 500

        if not order or 'id' not in order:
            return jsonify({
                'error': 'Invalid response from Razorpay'
            }), 500

        return jsonify({
            'order_id': order['id'],
            'amount': order['amount'],
            'currency': order['currency'],
            'key_id': razorpay_key_id
        })
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({
            'error': f'Unexpected error: {str(e)}'
        }), 500


@wallet_bp.post('/api/wallet/razorpay/verify')
@jwt_required()
def verify_wallet_razorpay_payment():
    ident = get_jwt_identity()
    user = resolve_user(ident)
    if not user:
        return jsonify({'error': 'User not found'}), 404

    data = request.get_json() or {}
    payment_id = data.get('razorpay_payment_id')
    order_id = data.get('razorpay_order_id')
    signature = data.get('razorpay_signature')

    if not all([payment_id, order_id, signature]):
        return jsonify({'error': 'Missing payment verification data'}), 400

    try:
        wallet_razorpay_client.utility.verify_payment_signature({
            'razorpay_signature': signature,
            'razorpay_payment_id': payment_id,
            'razorpay_order_id': order_id
        })
    except Exception as exc:
        print(f"Razorpay wallet verification error: {exc}")
        return jsonify({'error': 'Payment verification failed'}), 400

    try:
        payment = wallet_razorpay_client.payment.fetch(payment_id)
    except Exception as exc:
        print(f"Razorpay fetch payment error: {exc}")
        return jsonify({'error': 'Unable to fetch payment details'}), 400

    amount_rupees = float(payment.get('amount', 0)) / 100.0

    try:
        new_balance = record_transaction(
            user,
            amount_rupees,
            transaction_type='credit',
            source='wallet_payment',
            description='Wallet top-up via Razorpay',
            external_reference=payment_id
        )
    except WalletError as exc:
        return jsonify({'error': str(exc)}), 400

    return jsonify({
        'success': True,
        'new_balance': new_balance
    })


@wallet_bp.post('/api/wallet/apply-referral')
@jwt_required()
def apply_referral_code():
    """Redeem a referral code and credit bonuses to both users."""
    ident = get_jwt_identity()
    user = resolve_user(ident)
    if not user:
        return jsonify({'error': 'User not found'}), 404

    data = request.get_json() or {}
    referral_code = (data.get('referral_code') or '').strip()

    if not referral_code:
        return jsonify({'error': 'Referral code is required'}), 400

    if user.referral_bonus_claimed:
        return jsonify({'error': 'Referral bonus already claimed'}), 400

    if user.referral_code and referral_code.lower() == user.referral_code.lower():
        return jsonify({'error': 'You cannot use your own referral code'}), 400

    referrer = User.objects(referral_code__iexact=referral_code).first()
    if not referrer:
        return jsonify({'error': 'Invalid referral code'}), 404

    if str(referrer.id) == str(user.id):
        return jsonify({'error': 'You cannot use your own referral code'}), 400

    bonus_new_user = float(os.getenv('REFERRAL_BONUS_NEW_USER', 100))
    bonus_referrer = float(os.getenv('REFERRAL_BONUS_REFERRER', 50))

    if ReferralRequest.objects(user=user, status='pending').first():
        return jsonify({'error': 'Referral request already pending approval'}), 400

    referral_request = ReferralRequest(
        user=user,
        referrer=referrer,
        referral_code=referral_code,
        bonus_new_user=bonus_new_user,
        bonus_referrer=bonus_referrer,
        status='pending'
    )
    referral_request.save()

    return jsonify({
        'success': True,
        'message': 'Referral bonus request submitted. Admin will review and credit your wallet soon.'
    })

