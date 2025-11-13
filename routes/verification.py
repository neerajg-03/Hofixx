from flask import Blueprint, request, jsonify, url_for
from flask_jwt_extended import jwt_required, get_jwt_identity
from werkzeug.utils import secure_filename
from models import User, Provider, Shop
from bson import ObjectId
from datetime import datetime
import os
import uuid

verification_bp = Blueprint('verification', __name__)

# Allowed file extensions
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'pdf'}
UPLOAD_FOLDER = 'static/uploads/verification'

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def save_verification_file(file, prefix):
    """Save uploaded file and return URL"""
    if file and allowed_file(file.filename):
        # Generate unique filename
        ext = file.filename.rsplit('.', 1)[1].lower()
        filename = f"{prefix}_{uuid.uuid4().hex[:8]}.{ext}"
        
        # Ensure upload directory exists
        os.makedirs(UPLOAD_FOLDER, exist_ok=True)
        
        filepath = os.path.join(UPLOAD_FOLDER, filename)
        file.save(filepath)
        
        return url_for('static', filename=f'uploads/verification/{filename}', _external=True)
    return None


def _get_user_from_identity(expected_role=None):
    ident = get_jwt_identity()
    user_id = str(ident.get('id', ident)) if isinstance(ident, dict) else str(ident)
    user = None

    try:
        user = User.objects(id=ObjectId(user_id)).first()
    except Exception:
        user = User.objects(id=user_id).first()

    if not user:
        return None, user_id, jsonify({'message': 'User not found'}), 404

    if expected_role and user.role != expected_role:
        return user, user_id, jsonify({'message': f'Not a {expected_role}'}), 403

    return user, user_id, None, None


def _ensure_provider_profile(user):
    provider = Provider.objects(user=user).first()
    if not provider:
        provider = Provider(user=user)
        provider.verification_status = 'not_started'
        provider.save()
        user.provider_profile = provider
        user.save()
    elif provider.verification_status == 'pending' and not provider.verification_submitted_at:
        provider.verification_status = 'not_started'
        provider.save()
    return provider


def _compute_missing_provider_fields(provider):
    missing = []
    if not provider.aadhaar_front_url:
        missing.append('Aadhaar front document')
    if not provider.aadhaar_back_url:
        missing.append('Aadhaar back document')
    if not provider.pan_url:
        missing.append('PAN card')
    if not provider.selfie_url:
        missing.append('Selfie verification')
    if not (provider.verification_gps_lat is not None and provider.verification_gps_lon is not None):
        missing.append('GPS coordinates')
    if not provider.verification_address:
        missing.append('Verification address')
    return missing


# Provider Verification Routes
@verification_bp.get('/api/verification/provider/status')
@jwt_required()
def get_provider_verification_status():
    """Get provider verification status"""
    try:
        user, user_id, error_response, status_code = _get_user_from_identity(expected_role='provider')
        if error_response:
            return error_response, status_code

        provider = _ensure_provider_profile(user)
        verification_status = provider.verification_status or 'not_started'
        missing_fields = _compute_missing_provider_fields(provider)
        
        return jsonify({
            'verification_status': verification_status,
            'aadhaar_front_url': provider.aadhaar_front_url,
            'aadhaar_back_url': provider.aadhaar_back_url,
            'pan_url': provider.pan_url,
            'selfie_url': provider.selfie_url,
            'skill_cert_url': provider.skill_cert_url,
            'police_verification_url': provider.police_verification_url,
            'verification_gps_lat': provider.verification_gps_lat,
            'verification_gps_lon': provider.verification_gps_lon,
            'verification_address': provider.verification_address,
            'admin_remarks': provider.admin_remarks,
            'submitted_at': provider.verification_submitted_at.isoformat() if provider.verification_submitted_at else None,
            'missing_fields': missing_fields
        })
    except Exception as e:
        print(f"Error getting provider verification status: {e}")
        return jsonify({'message': 'Error fetching verification status'}), 500


@verification_bp.post('/api/verification/provider/submit')
@jwt_required()
def submit_provider_verification():
    """Submit provider verification (multi-step)"""
    try:
        user, user_id, error_response, status_code = _get_user_from_identity(expected_role='provider')
        if error_response:
            return error_response, status_code
        
        provider = _ensure_provider_profile(user)
        uploaded_field = None
        uploaded_url = None
        
        # Step 1: Basic details (already in user profile)
        # Step 2: Document uploads
        if 'aadhaar_front' in request.files:
            aadhaar_front_url = save_verification_file(request.files['aadhaar_front'], 'aadhaar_front')
            if aadhaar_front_url:
                provider.aadhaar_front_url = aadhaar_front_url
                uploaded_field = 'aadhaar_front'
                uploaded_url = aadhaar_front_url
        
        if 'aadhaar_back' in request.files:
            aadhaar_back_url = save_verification_file(request.files['aadhaar_back'], 'aadhaar_back')
            if aadhaar_back_url:
                provider.aadhaar_back_url = aadhaar_back_url
                uploaded_field = 'aadhaar_back'
                uploaded_url = aadhaar_back_url
        
        if 'pan' in request.files:
            pan_url = save_verification_file(request.files['pan'], 'pan')
            if pan_url:
                provider.pan_url = pan_url
                uploaded_field = 'pan'
                uploaded_url = pan_url
        
        if 'skill_cert' in request.files:
            skill_cert_url = save_verification_file(request.files['skill_cert'], 'skill_cert')
            if skill_cert_url:
                provider.skill_cert_url = skill_cert_url
                uploaded_field = 'skill_cert'
                uploaded_url = skill_cert_url
        
        if 'police_verification' in request.files:
            police_verification_url = save_verification_file(request.files['police_verification'], 'police_verification')
            if police_verification_url:
                provider.police_verification_url = police_verification_url
                uploaded_field = 'police_verification'
                uploaded_url = police_verification_url
        
        # Step 3: Selfie (can be uploaded as file or base64)
        if 'selfie' in request.files:
            selfie_url = save_verification_file(request.files['selfie'], 'selfie')
            if selfie_url:
                provider.selfie_url = selfie_url
                uploaded_field = 'selfie'
                uploaded_url = selfie_url
        
        # Step 4: GPS location
        if request.form.get('gps_lat') and request.form.get('gps_lon'):
            provider.verification_gps_lat = float(request.form.get('gps_lat'))
            provider.verification_gps_lon = float(request.form.get('gps_lon'))
            provider.verification_address = request.form.get('verification_address', '')
            uploaded_field = 'location'
            uploaded_url = None
        
        # Step 5: Submit verification
        if request.form.get('action') == 'submit':
            # Validate all required fields
            missing = _compute_missing_provider_fields(provider)
            if missing:
                return jsonify({
                    'message': 'Please complete all verification steps before submitting.',
                    'missing_fields': missing,
                    'verification_status': provider.verification_status or 'not_started'
                }), 400
            
            provider.verification_status = 'pending'
            provider.verification_submitted_at = datetime.utcnow()
            provider.verification_updated_at = datetime.utcnow()
        
        provider.save()
        missing_after_update = _compute_missing_provider_fields(provider)
        
        return jsonify({
            'message': 'Verification details saved successfully',
            'verification_status': provider.verification_status or 'not_started',
            'uploaded_field': uploaded_field,
            'uploaded_url': uploaded_url,
            'missing_fields': missing_after_update
        })
        
    except Exception as e:
        print(f"Error submitting provider verification: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'message': 'Error submitting verification'}), 500


# Shopkeeper Verification Routes
@verification_bp.get('/api/verification/shopkeeper/status')
@jwt_required()
def get_shopkeeper_verification_status():
    """Get shopkeeper verification status"""
    try:
        ident = get_jwt_identity()
        user_id = str(ident['id']) if isinstance(ident, dict) else str(ident)
        user = User.objects(id=ObjectId(user_id)).first()
        
        if not user or user.role != 'shopkeeper':
            return jsonify({'message': 'Not a shopkeeper'}), 403
        
        shop = Shop.objects(owner=user).first()
        if not shop:
            return jsonify({
                'verification_status': 'not_started',
                'message': 'Shop not found'
            }), 404
        
        # If verification_status is None or empty, it means verification hasn't started
        verification_status = shop.verification_status
        if not verification_status:
            verification_status = 'not_started'
        
        return jsonify({
            'verification_status': verification_status,
            'aadhaar_front_url': shop.shopkeeper_aadhaar_front_url,
            'aadhaar_back_url': shop.shopkeeper_aadhaar_back_url,
            'pan_url': shop.shopkeeper_pan_url,
            'selfie_url': shop.shopkeeper_selfie_url,
            'shop_license_url': shop.shop_license_url,
            'police_verification_url': shop.police_verification_url,
            'verification_gps_lat': shop.verification_gps_lat,
            'verification_gps_lon': shop.verification_gps_lon,
            'verification_address': shop.verification_address,
            'admin_remarks': shop.admin_remarks,
            'submitted_at': shop.verification_submitted_at.isoformat() if shop.verification_submitted_at else None
        })
    except Exception as e:
        print(f"Error getting shopkeeper verification status: {e}")
        return jsonify({'message': 'Error fetching verification status'}), 500


@verification_bp.post('/api/verification/shopkeeper/submit')
@jwt_required()
def submit_shopkeeper_verification():
    """Submit shopkeeper verification (multi-step)"""
    try:
        ident = get_jwt_identity()
        user_id = str(ident['id']) if isinstance(ident, dict) else str(ident)
        user = User.objects(id=ObjectId(user_id)).first()
        
        if not user or user.role != 'shopkeeper':
            return jsonify({'message': 'Not a shopkeeper'}), 403
        
        shop = Shop.objects(owner=user).first()
        if not shop:
            return jsonify({'message': 'Shop not found'}), 404
        
        # Document uploads
        if 'aadhaar_front' in request.files:
            aadhaar_front_url = save_verification_file(request.files['aadhaar_front'], 'shopkeeper_aadhaar_front')
            if aadhaar_front_url:
                shop.shopkeeper_aadhaar_front_url = aadhaar_front_url
        
        if 'aadhaar_back' in request.files:
            aadhaar_back_url = save_verification_file(request.files['aadhaar_back'], 'shopkeeper_aadhaar_back')
            if aadhaar_back_url:
                shop.shopkeeper_aadhaar_back_url = aadhaar_back_url
        
        if 'pan' in request.files:
            pan_url = save_verification_file(request.files['pan'], 'shopkeeper_pan')
            if pan_url:
                shop.shopkeeper_pan_url = pan_url
        
        if 'shop_license' in request.files:
            shop_license_url = save_verification_file(request.files['shop_license'], 'shop_license')
            if shop_license_url:
                shop.shop_license_url = shop_license_url
        
        if 'police_verification' in request.files:
            police_verification_url = save_verification_file(request.files['police_verification'], 'shopkeeper_police_verification')
            if police_verification_url:
                shop.police_verification_url = police_verification_url
        
        # Selfie
        if 'selfie' in request.files:
            selfie_url = save_verification_file(request.files['selfie'], 'shopkeeper_selfie')
            if selfie_url:
                shop.shopkeeper_selfie_url = selfie_url
        
        # GPS location
        if request.form.get('gps_lat') and request.form.get('gps_lon'):
            shop.verification_gps_lat = float(request.form.get('gps_lat'))
            shop.verification_gps_lon = float(request.form.get('gps_lon'))
            shop.verification_address = request.form.get('verification_address', '')
        
        # Submit verification
        if request.form.get('action') == 'submit':
            # Validate all required fields
            if not all([shop.shopkeeper_aadhaar_front_url, shop.shopkeeper_aadhaar_back_url,
                       shop.shopkeeper_pan_url, shop.shopkeeper_selfie_url,
                       shop.verification_gps_lat, shop.verification_gps_lon]):
                return jsonify({
                    'message': 'Please complete all verification steps',
                    'missing_fields': {
                        'aadhaar_front': not shop.shopkeeper_aadhaar_front_url,
                        'aadhaar_back': not shop.shopkeeper_aadhaar_back_url,
                        'pan': not shop.shopkeeper_pan_url,
                        'selfie': not shop.shopkeeper_selfie_url,
                        'shop_license': not shop.shop_license_url,
                        'gps_location': not (shop.verification_gps_lat and shop.verification_gps_lon)
                    }
                }), 400
            
            shop.verification_status = 'pending'
            shop.verification_submitted_at = datetime.utcnow()
            shop.verification_updated_at = datetime.utcnow()
        
        shop.save()
        
        return jsonify({
            'message': 'Verification details saved successfully',
            'verification_status': shop.verification_status
        })
        
    except Exception as e:
        print(f"Error submitting shopkeeper verification: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'message': 'Error submitting verification'}), 500


# Admin Verification Routes
@verification_bp.get('/api/admin/verifications/providers')
@jwt_required()
def get_provider_verifications():
    """Get all provider verification requests for admin"""
    try:
        ident = get_jwt_identity()
        user_id = str(ident['id']) if isinstance(ident, dict) else str(ident)
        user = User.objects(id=ObjectId(user_id)).first()
        
        if not user or user.role != 'admin':
            return jsonify({'message': 'Unauthorized'}), 403
        
        providers = Provider.objects().order_by('-verification_submitted_at')
        verifications = []
        
        for provider in providers:
            if provider.user:
                missing_fields = _compute_missing_provider_fields(provider)
                verifications.append({
                    'provider_id': str(provider.id),
                    'user_id': str(provider.user.id),
                    'name': provider.user.name,
                    'email': provider.user.email,
                    'phone': provider.user.phone,
                    'verification_status': provider.verification_status or 'pending',
                    'aadhaar_front_url': provider.aadhaar_front_url,
                    'aadhaar_back_url': provider.aadhaar_back_url,
                    'pan_url': provider.pan_url,
                    'selfie_url': provider.selfie_url,
                    'skill_cert_url': provider.skill_cert_url,
                    'police_verification_url': provider.police_verification_url,
                    'verification_gps_lat': provider.verification_gps_lat,
                    'verification_gps_lon': provider.verification_gps_lon,
                    'verification_address': provider.verification_address,
                    'admin_remarks': provider.admin_remarks,
                    'submitted_at': provider.verification_submitted_at.isoformat() if provider.verification_submitted_at else None,
                    'verified_at': provider.verified_at.isoformat() if provider.verified_at else None,
                    'rejected_at': provider.rejected_at.isoformat() if provider.rejected_at else None,
                    'missing_fields': missing_fields
                })
        
        return jsonify({'verifications': verifications})
    except Exception as e:
        print(f"Error getting provider verifications: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'message': 'Error fetching verifications'}), 500


@verification_bp.post('/api/admin/verifications/providers/<provider_id>/approve')
@jwt_required()
def approve_provider_verification(provider_id):
    """Approve provider verification"""
    try:
        ident = get_jwt_identity()
        user_id = str(ident['id']) if isinstance(ident, dict) else str(ident)
        admin_user = User.objects(id=ObjectId(user_id)).first()
        
        if not admin_user or admin_user.role != 'admin':
            return jsonify({'message': 'Unauthorized'}), 403
        
        provider = Provider.objects(id=ObjectId(provider_id)).first()
        if not provider:
            return jsonify({'message': 'Provider not found'}), 404
        
        provider.verification_status = 'verified'
        provider.verified_by = admin_user
        provider.verified_at = datetime.utcnow()
        provider.verification_updated_at = datetime.utcnow()
        provider.save()
        
        return jsonify({'message': 'Provider verification approved successfully'})
    except Exception as e:
        print(f"Error approving provider verification: {e}")
        return jsonify({'message': 'Error approving verification'}), 500


@verification_bp.post('/api/admin/verifications/providers/<provider_id>/reject')
@jwt_required()
def reject_provider_verification(provider_id):
    """Reject provider verification"""
    try:
        ident = get_jwt_identity()
        user_id = str(ident['id']) if isinstance(ident, dict) else str(ident)
        admin_user = User.objects(id=ObjectId(user_id)).first()
        
        if not admin_user or admin_user.role != 'admin':
            return jsonify({'message': 'Unauthorized'}), 403
        
        provider = Provider.objects(id=ObjectId(provider_id)).first()
        if not provider:
            return jsonify({'message': 'Provider not found'}), 404
        
        data = request.get_json() or {}
        remarks = data.get('remarks', '')
        
        provider.verification_status = 'rejected'
        provider.admin_remarks = remarks
        provider.rejected_at = datetime.utcnow()
        provider.verification_updated_at = datetime.utcnow()
        provider.save()
        
        return jsonify({'message': 'Provider verification rejected'})
    except Exception as e:
        print(f"Error rejecting provider verification: {e}")
        return jsonify({'message': 'Error rejecting verification'}), 500


@verification_bp.get('/api/admin/verifications/shopkeepers')
@jwt_required()
def get_shopkeeper_verifications():
    """Get all shopkeeper verification requests for admin"""
    try:
        ident = get_jwt_identity()
        user_id = str(ident['id']) if isinstance(ident, dict) else str(ident)
        user = User.objects(id=ObjectId(user_id)).first()
        
        if not user or user.role != 'admin':
            return jsonify({'message': 'Unauthorized'}), 403
        
        shops = Shop.objects().order_by('-verification_submitted_at')
        verifications = []
        
        for shop in shops:
            if shop.owner:
                verifications.append({
                    'shop_id': str(shop.id),
                    'user_id': str(shop.owner.id),
                    'shop_name': shop.name,
                    'owner_name': shop.owner.name,
                    'owner_email': shop.owner.email,
                    'owner_phone': shop.owner.phone,
                    'verification_status': shop.verification_status or 'pending',
                    'aadhaar_front_url': shop.shopkeeper_aadhaar_front_url,
                    'aadhaar_back_url': shop.shopkeeper_aadhaar_back_url,
                    'pan_url': shop.shopkeeper_pan_url,
                    'selfie_url': shop.shopkeeper_selfie_url,
                    'shop_license_url': shop.shop_license_url,
                    'police_verification_url': shop.police_verification_url,
                    'verification_gps_lat': shop.verification_gps_lat,
                    'verification_gps_lon': shop.verification_gps_lon,
                    'verification_address': shop.verification_address,
                    'admin_remarks': shop.admin_remarks,
                    'submitted_at': shop.verification_submitted_at.isoformat() if shop.verification_submitted_at else None,
                    'verified_at': shop.verified_at.isoformat() if shop.verified_at else None,
                    'rejected_at': shop.rejected_at.isoformat() if shop.rejected_at else None
                })
        
        return jsonify({'verifications': verifications})
    except Exception as e:
        print(f"Error getting shopkeeper verifications: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'message': 'Error fetching verifications'}), 500


@verification_bp.post('/api/admin/verifications/shopkeepers/<shop_id>/approve')
@jwt_required()
def approve_shopkeeper_verification(shop_id):
    """Approve shopkeeper verification"""
    try:
        ident = get_jwt_identity()
        user_id = str(ident['id']) if isinstance(ident, dict) else str(ident)
        admin_user = User.objects(id=ObjectId(user_id)).first()
        
        if not admin_user or admin_user.role != 'admin':
            return jsonify({'message': 'Unauthorized'}), 403
        
        shop = Shop.objects(id=ObjectId(shop_id)).first()
        if not shop:
            return jsonify({'message': 'Shop not found'}), 404
        
        shop.verification_status = 'verified'
        shop.is_verified = True  # Keep legacy field updated
        shop.verified_by = admin_user
        shop.verified_at = datetime.utcnow()
        shop.verification_updated_at = datetime.utcnow()
        shop.save()
        
        return jsonify({'message': 'Shopkeeper verification approved successfully'})
    except Exception as e:
        print(f"Error approving shopkeeper verification: {e}")
        return jsonify({'message': 'Error approving verification'}), 500


@verification_bp.post('/api/admin/verifications/shopkeepers/<shop_id>/reject')
@jwt_required()
def reject_shopkeeper_verification(shop_id):
    """Reject shopkeeper verification"""
    try:
        ident = get_jwt_identity()
        user_id = str(ident['id']) if isinstance(ident, dict) else str(ident)
        admin_user = User.objects(id=ObjectId(user_id)).first()
        
        if not admin_user or admin_user.role != 'admin':
            return jsonify({'message': 'Unauthorized'}), 403
        
        shop = Shop.objects(id=ObjectId(shop_id)).first()
        if not shop:
            return jsonify({'message': 'Shop not found'}), 404
        
        data = request.get_json() or {}
        remarks = data.get('remarks', '')
        
        shop.verification_status = 'rejected'
        shop.is_verified = False
        shop.admin_remarks = remarks
        shop.rejected_at = datetime.utcnow()
        shop.verification_updated_at = datetime.utcnow()
        shop.save()
        
        return jsonify({'message': 'Shopkeeper verification rejected'})
    except Exception as e:
        print(f"Error rejecting shopkeeper verification: {e}")
        return jsonify({'message': 'Error rejecting verification'}), 500

