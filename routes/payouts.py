from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from models import ProviderPayout, User, Provider, Payment, Booking
from bson import ObjectId
from datetime import datetime
import razorpay
import os

payouts_bp = Blueprint('payouts', __name__)

# Initialize Razorpay client for payouts
razorpay_key_id = os.getenv('RAZORPAY_KEY_ID', 'rzp_test_ROb7lXNQKK4t1c')
razorpay_key_secret = os.getenv('RAZORPAY_KEY_SECRET', 'cR1Q452dHCJ6dy2ET4shqjOG')

razorpay_client = razorpay.Client(
    auth=(razorpay_key_id, razorpay_key_secret)
)


@payouts_bp.get('/api/payouts')
@jwt_required()
def get_payouts():
    """Get all payouts (admin only)"""
    try:
        ident = get_jwt_identity()
        user_id = str(ident) if isinstance(ident, str) else str(ident.get('id') or ident)
        user = User.objects(id=ObjectId(user_id)).first()
        
        if not user or user.role != 'admin':
            return jsonify({'error': 'Unauthorized. Admin access required.'}), 403
        
        # Get filter parameters
        status_filter = request.args.get('status', 'all')
        page = int(request.args.get('page', 1))
        per_page = int(request.args.get('per_page', 20))
        
        # Build query
        if status_filter == 'all':
            payouts_query = ProviderPayout.objects()
        else:
            payouts_query = ProviderPayout.objects(status=status_filter)
        
        # Get total count
        total_count = payouts_query.count()
        
        # Paginate
        payouts = payouts_query.order_by('-created_at').skip((page - 1) * per_page).limit(per_page)
        
        payouts_data = []
        for payout in payouts:
            provider = payout.provider
            booking = payout.booking
            payment = payout.payment
            
            payouts_data.append({
                'id': str(payout.id),
                'provider_id': str(provider.id),
                'provider_name': provider.user.name if provider.user else 'Unknown',
                'provider_phone': provider.user.phone if provider.user else None,
                'booking_id': str(booking.id),
                'payment_id': str(payment.id) if payment else None,
                'original_amount': payout.original_amount,
                'commission_amount': payout.commission_amount,
                'payout_amount': payout.payout_amount,
                'status': payout.status,
                'bank_account_holder_name': payout.bank_account_holder_name,
                'bank_account_number': payout.bank_account_number,
                'bank_ifsc_code': payout.bank_ifsc_code,
                'bank_name': payout.bank_name,
                'transfer_reference': payout.transfer_reference,
                'transfer_date': payout.transfer_date.isoformat() if payout.transfer_date else None,
                'failure_reason': payout.failure_reason,
                'created_at': payout.created_at.isoformat() if payout.created_at else None,
                'updated_at': payout.updated_at.isoformat() if payout.updated_at else None
            })
        
        return jsonify({
            'payouts': payouts_data,
            'total': total_count,
            'page': page,
            'per_page': per_page,
            'total_pages': (total_count + per_page - 1) // per_page
        })
        
    except Exception as e:
        print(f"Error getting payouts: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': 'Failed to get payouts'}), 500


@payouts_bp.post('/api/payouts/process/<payout_id>')
@jwt_required()
def process_provider_payout(payout_id):
    """Process a provider payout using Razorpay Payouts API"""
    try:
        # Verify admin access
        ident = get_jwt_identity()
        user_id = str(ident) if isinstance(ident, str) else str(ident.get('id') or ident)
        user = User.objects(id=ObjectId(user_id)).first()
        
        if not user or user.role != 'admin':
            return jsonify({'error': 'Unauthorized. Admin access required.'}), 403
        
        # Get payout record
        payout = ProviderPayout.objects(id=ObjectId(payout_id)).first()
        if not payout:
            return jsonify({'error': 'Payout not found'}), 404
        
        # Check if payout is already processed
        if payout.status in ['completed', 'processing']:
            return jsonify({'error': f'Payout already {payout.status}'}), 400
        
        # Verify provider has bank details
        provider = payout.provider
        provider.reload()
        
        if not provider.bank_account_number or not provider.bank_ifsc_code:
            return jsonify({'error': 'Provider bank details are incomplete'}), 400
        
        # Update payout status to processing
        payout.status = 'processing'
        payout.updated_at = datetime.utcnow()
        payout.save()
        
        # Prepare payout data for Razorpay
        payout_amount_paise = int(payout.payout_amount * 100)  # Convert to paise
        
        # Razorpay Payouts requires:
        # 1. Create a Contact
        # 2. Create a Fund Account linked to the contact
        # 3. Create payout using fund_account_id
        
        try:
            # Step 1: Create or get Contact
            contact_data = {
                'name': provider.bank_account_holder_name or provider.user.name,
                'email': provider.user.email or f'provider_{provider.id}@hofix.com',
                'contact': provider.user.phone or '',
                'type': 'vendor',
                'reference_id': f'provider_{provider.id}'
            }
            
            # Try to find existing contact
            contact_id = None
            try:
                contacts = razorpay_client.contact.all({'count': 100})
                for contact in contacts.get('items', []):
                    if contact.get('reference_id') == f'provider_{provider.id}':
                        contact_id = contact['id']
                        break
            except:
                pass
            
            # Create contact if not found
            if not contact_id:
                contact_response = razorpay_client.contact.create(contact_data)
                contact_id = contact_response['id']
                print(f"Created Razorpay contact: {contact_id}")
            
            # Step 2: Create or get Fund Account
            fund_account_id = None
            try:
                fund_accounts = razorpay_client.fund_account.all({'contact_id': contact_id, 'count': 100})
                for fa in fund_accounts.get('items', []):
                    if (fa.get('account_type') == 'bank_account' and 
                        fa.get('bank_account', {}).get('account_number') == provider.bank_account_number):
                        fund_account_id = fa['id']
                        break
            except:
                pass
            
            # Create fund account if not found
            if not fund_account_id:
                fund_account_data = {
                    'contact_id': contact_id,
                    'account_type': 'bank_account',
                    'bank_account': {
                        'name': provider.bank_account_holder_name or provider.user.name,
                        'ifsc': provider.bank_ifsc_code,
                        'account_number': provider.bank_account_number
                    }
                }
                fund_account_response = razorpay_client.fund_account.create(fund_account_data)
                fund_account_id = fund_account_response['id']
                print(f"Created Razorpay fund account: {fund_account_id}")
            
            # Step 3: Create payout using fund_account_id
            payout_data = {
                'account_number': os.getenv('RAZORPAY_ACCOUNT_NUMBER', ''),  # Your Razorpay account number
                'fund_account_id': fund_account_id,
                'amount': payout_amount_paise,
                'currency': 'INR',
                'mode': 'IMPS',  # Instant transfer mode
                'purpose': 'payout',
                'narration': f'Service payment for booking {str(payout.booking.id)[:8]}',
                'queue_if_low_balance': True,
                'reference_id': f'payout_{payout_id}'
            }
            
            payout_response = razorpay_client.payout.create(payout_data)
            
            # Update payout record with transfer reference
            payout.transfer_reference = payout_response.get('id', '')
            payout.status = 'processing'
            payout.updated_at = datetime.utcnow()
            payout.save()
            
            # Update payment record
            payment = payout.payment
            if payment:
                payment.payout_status = 'processing'
                payment.save()
            
            return jsonify({
                'success': True,
                'message': 'Payout initiated successfully',
                'payout_id': str(payout.id),
                'transfer_id': payout.transfer_reference,
                'status': payout.status
            })
            
        except razorpay.errors.BadRequestError as e:
            payout.status = 'failed'
            payout.failure_reason = str(e)
            payout.updated_at = datetime.utcnow()
            payout.save()
            return jsonify({'error': f'Payout failed: {str(e)}'}), 400
        except Exception as e:
            payout.status = 'failed'
            payout.failure_reason = str(e)
            payout.updated_at = datetime.utcnow()
            payout.save()
            print(f"Error processing payout: {e}")
            import traceback
            traceback.print_exc()
            return jsonify({'error': f'Failed to process payout: {str(e)}'}), 500
            
    except Exception as e:
        print(f"Error in process_provider_payout: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': 'Failed to process payout'}), 500


@payouts_bp.post('/api/payouts/webhook')
def payout_webhook():
    """Handle Razorpay payout webhook events"""
    try:
        # Get webhook signature for verification
        webhook_signature = request.headers.get('X-Razorpay-Signature')
        webhook_secret = os.getenv('RAZORPAY_WEBHOOK_SECRET', '')
        
        # Get raw payload for signature verification
        payload = request.get_data(as_text=True)
        data = request.get_json()
        
        if not data:
            return jsonify({'error': 'No data received'}), 400
        
        # Verify webhook signature if secret is configured
        if webhook_secret:
            try:
                import hmac
                import hashlib
                expected_signature = hmac.new(
                    webhook_secret.encode(),
                    payload.encode(),
                    hashlib.sha256
                ).hexdigest()
                
                if not hmac.compare_digest(expected_signature, webhook_signature or ''):
                    print("Webhook signature verification failed")
                    return jsonify({'error': 'Invalid signature'}), 400
            except Exception as e:
                print(f"Error verifying webhook signature: {e}")
        
        event = data.get('event')
        payload_data = data.get('payload', {})
        payout_entity = payload_data.get('payout', {})
        
        if not event:
            return jsonify({'error': 'Invalid webhook data - no event'}), 400
        
        # Get transfer reference from Razorpay payout
        transfer_id = payout_entity.get('id')
        if not transfer_id:
            # Try alternative structure
            transfer_id = data.get('payload', {}).get('payout', {}).get('id')
        
        if not transfer_id:
            print(f"No transfer ID in webhook. Event: {event}, Data: {data}")
            return jsonify({'message': 'No transfer ID in webhook'}), 200  # Return 200 to acknowledge receipt
        
        # Find payout by transfer reference
        payout = ProviderPayout.objects(transfer_reference=transfer_id).first()
        if not payout:
            print(f"Payout not found for transfer ID: {transfer_id}")
            return jsonify({'message': 'Payout not found'}), 200  # Return 200 to acknowledge receipt
        
        # Update payout status based on webhook event
        if event in ['payout.processed', 'payout.paid', 'payout.completed']:
            payout.status = 'completed'
            payout.transfer_date = datetime.utcnow()
            payout.updated_at = datetime.utcnow()
            
            # Update payment record
            payment = payout.payment
            if payment:
                payment.payout_status = 'completed'
                payment.save()
            
            print(f"Payout {payout.id} marked as completed via webhook")
            
        elif event in ['payout.failed', 'payout.reversed', 'payout.cancelled']:
            payout.status = 'failed'
            payout.failure_reason = payout_entity.get('failure_reason', payout_entity.get('status_details', {}).get('description', 'Payout failed'))
            payout.updated_at = datetime.utcnow()
            
            # Update payment record
            payment = payout.payment
            if payment:
                payment.payout_status = 'failed'
                payment.save()
            
            print(f"Payout {payout.id} marked as failed via webhook: {payout.failure_reason}")
        
        elif event == 'payout.processing':
            payout.status = 'processing'
            payout.updated_at = datetime.utcnow()
            print(f"Payout {payout.id} is processing via webhook")
        
        payout.save()
        
        return jsonify({'message': 'Webhook processed successfully'})
        
    except Exception as e:
        print(f"Error processing payout webhook: {e}")
        import traceback
        traceback.print_exc()
        # Return 200 to acknowledge receipt even on error (to prevent retries)
        return jsonify({'error': 'Failed to process webhook'}), 200


@payouts_bp.get('/api/payouts/stats')
@jwt_required()
def get_payout_stats():
    """Get payout statistics (admin only)"""
    try:
        ident = get_jwt_identity()
        user_id = str(ident) if isinstance(ident, str) else str(ident.get('id') or ident)
        user = User.objects(id=ObjectId(user_id)).first()
        
        if not user or user.role != 'admin':
            return jsonify({'error': 'Unauthorized. Admin access required.'}), 403
        
        # Calculate statistics
        total_payouts = ProviderPayout.objects().count()
        pending_payouts = ProviderPayout.objects(status='pending').count()
        processing_payouts = ProviderPayout.objects(status='processing').count()
        completed_payouts = ProviderPayout.objects(status='completed').count()
        failed_payouts = ProviderPayout.objects(status='failed').count()
        
        # Calculate amounts
        total_payout_amount = sum(p.payout_amount for p in ProviderPayout.objects(status='completed'))
        total_commission = sum(p.commission_amount for p in ProviderPayout.objects())
        pending_amount = sum(p.payout_amount for p in ProviderPayout.objects(status='pending'))
        
        return jsonify({
            'total_payouts': total_payouts,
            'pending_payouts': pending_payouts,
            'processing_payouts': processing_payouts,
            'completed_payouts': completed_payouts,
            'failed_payouts': failed_payouts,
            'total_payout_amount': total_payout_amount,
            'total_commission': total_commission,
            'pending_amount': pending_amount
        })
        
    except Exception as e:
        print(f"Error getting payout stats: {e}")
        return jsonify({'error': 'Failed to get payout stats'}), 500

