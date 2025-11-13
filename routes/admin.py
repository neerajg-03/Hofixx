from flask import Blueprint, render_template, request, jsonify, redirect, url_for, flash
from flask_jwt_extended import jwt_required, get_jwt_identity, decode_token
from werkzeug.utils import secure_filename
from models import Feedback, User, Booking, Provider, ShopAd, Payment, Shop, ReferralRequest
from services.wallet_service import record_transaction, WalletError, resolve_user
from datetime import datetime
from bson import ObjectId
import os

admin_bp = Blueprint('admin', __name__)

def get_user_from_token():
    """Helper function to get user from token in cookie, header, or query parameter"""
    try:
        # PRIORITY 1: Check query parameter first (most reliable for client-side navigation)
        token = request.args.get('token')
        if token:
            try:
                decoded = decode_token(token)
                user_id = decoded.get('sub')
                print(f"DEBUG get_user_from_token: Decoded token, user_id={user_id}, type={type(user_id)}")
                if user_id:
                    user_id_str = str(user_id)
                    print(f"DEBUG get_user_from_token: Looking up user with id={user_id_str}")
                    # Try with ObjectId first (most reliable for MongoDB)
                    try:
                        user = User.objects(id=ObjectId(user_id_str)).first()
                    except:
                        # Fallback to string if ObjectId conversion fails
                        user = User.objects(id=user_id_str).first()
                    print(f"DEBUG get_user_from_token: User found={user is not None}, role={user.role if user else None}")
                    if user and user.role == 'admin':
                        return user_id_str, user
                    else:
                        print(f"DEBUG get_user_from_token: User check failed - user exists: {user is not None}, is admin: {user.role == 'admin' if user else False}")
            except Exception as e:
                print(f"Error decoding token from query: {e}")
                import traceback
                traceback.print_exc()
        
        # PRIORITY 2: Try to get identity from JWT (checks cookies and headers)
        user_id = get_jwt_identity()
        if user_id:
            user_id_str = str(user_id)
            try:
                user = User.objects(id=ObjectId(user_id_str)).first()
            except:
                user = User.objects(id=user_id_str).first()
            if user and user.role == 'admin':
                return user_id_str, user
        
        # PRIORITY 3: Check Authorization header
        auth_header = request.headers.get('Authorization', '')
        if auth_header.startswith('Bearer '):
            token = auth_header.replace('Bearer ', '')
            try:
                decoded = decode_token(token)
                user_id = decoded.get('sub')
                if user_id:
                    user_id_str = str(user_id)
                    try:
                        user = User.objects(id=ObjectId(user_id_str)).first()
                    except:
                        user = User.objects(id=user_id_str).first()
                    if user and user.role == 'admin':
                        return user_id_str, user
            except Exception:
                pass
        
        return None, None
    except Exception as e:
        print(f"Error in get_user_from_token: {e}")
        import traceback
        traceback.print_exc()
        return None, None

@admin_bp.route('/admin')
@jwt_required(optional=True)
def admin_dashboard():
    """Admin dashboard for managing feedback and reviews"""
    try:
        # Check if token is in query params (for passing along)
        token_param = request.args.get('token', '')
        current_user_id, user = get_user_from_token()
        
        if not current_user_id or not user or user.role != 'admin':
            # If no token, redirect to login with return URL
            next_url = '/admin'
            if token_param:
                next_url += f'?token={token_param}'
            return redirect(url_for('auth.login') + f'?next={next_url}')
        
        # Get feedback statistics
        total_feedback = Feedback.objects.count()
        approved_feedback = Feedback.objects(is_approved=True).count()
        pending_feedback = Feedback.objects(is_approved=False).count()
        featured_feedback = Feedback.objects(is_featured=True).count()
        
        # Get recent feedback
        recent_feedback = Feedback.objects().order_by('-created_at').limit(10)
        
        # Get booking statistics
        total_bookings = Booking.objects.count()
        completed_bookings = Booking.objects(status='Completed').count()
        
        # Get provider statistics
        total_providers = Provider.objects.count()
        available_providers = Provider.objects(availability=True).count()
        
        stats = {
            'total_feedback': total_feedback,
            'approved_feedback': approved_feedback,
            'pending_feedback': pending_feedback,
            'featured_feedback': featured_feedback,
            'total_bookings': total_bookings,
            'completed_bookings': completed_bookings,
            'total_providers': total_providers,
            'available_providers': available_providers
        }
        
        # Shops summary
        total_shops = ShopAd.objects.count()
        active_shops = ShopAd.objects(is_active=True).count()
        shops_stats = {'total_shops': total_shops, 'active_shops': active_shops}
        
        return render_template('admin_dashboard.html', 
                             stats=stats, 
                             recent_feedback=recent_feedback,
                             shops_stats=shops_stats)
        
    except Exception as e:
        print(f"Error loading admin dashboard: {str(e)}")
        return redirect(url_for('auth.login'))

@admin_bp.route('/admin/feedback')
@jwt_required(optional=True)
def admin_feedback():
    """Admin feedback management page"""
    try:
        current_user_id, user = get_user_from_token()
        
        if not current_user_id or not user or user.role != 'admin':
            return redirect(url_for('auth.login') + f'?next=/admin/feedback')
        
        # Get all feedback with pagination
        page = request.args.get('page', 1, type=int)
        per_page = 20
        
        try:
            feedback_list = Feedback.objects().order_by('-created_at').paginate(
                page=page, per_page=per_page
            )
        except Exception as pagination_error:
            print(f"Pagination error (feedback): {pagination_error}")
            all_feedback = list(Feedback.objects().order_by('-created_at'))
            start = (page - 1) * per_page
            end = start + per_page
            class Pagination:
                def __init__(self, items, page, per_page, total):
                    self.items = items
                    self.page = page
                    self.pages = (total + per_page - 1) // per_page if per_page > 0 else 1
                    self.per_page = per_page
                    self.total = total
                    self.has_prev = page > 1
                    self.has_next = end < total
                    self.prev_num = page - 1 if page > 1 else None
                    self.next_num = page + 1 if end < total else None
                def iter_pages(self, left_edge=2, right_edge=2, left_current=2, right_current=2):
                    return range(1, self.pages + 1)
            feedback_list = Pagination(all_feedback[start:end], page, per_page, len(all_feedback))
        
        return render_template('admin_feedback.html', feedback_list=feedback_list)
        
    except Exception as e:
        print(f"Error loading admin feedback: {str(e)}")
        return redirect(url_for('auth.login'))

@admin_bp.route('/api/admin/feedback/<feedback_id>/approve', methods=['POST'])
@jwt_required()
def approve_feedback(feedback_id):
    """Approve feedback for display"""
    try:
        current_user_id = get_jwt_identity()
        user = User.objects(id=current_user_id).first()
        
        if not user or user.role != 'admin':
            return jsonify({'error': 'Unauthorized'}), 403
        
        feedback = Feedback.objects(id=feedback_id).first()
        if not feedback:
            return jsonify({'error': 'Feedback not found'}), 404
        
        feedback.is_approved = True
        feedback.save()
        
        return jsonify({'message': 'Feedback approved successfully'}), 200
        
    except Exception as e:
        print(f"Error approving feedback: {str(e)}")
        return jsonify({'error': 'Failed to approve feedback'}), 500

@admin_bp.route('/api/admin/feedback/<feedback_id>/feature', methods=['POST'])
@jwt_required()
def feature_feedback(feedback_id):
    """Feature feedback on homepage"""
    try:
        current_user_id = get_jwt_identity()
        user = User.objects(id=current_user_id).first()
        
        if not user or user.role != 'admin':
            return jsonify({'error': 'Unauthorized'}), 403
        
        feedback = Feedback.objects(id=feedback_id).first()
        if not feedback:
            return jsonify({'error': 'Feedback not found'}), 404
        
        feedback.is_featured = not feedback.is_featured
        feedback.save()
        
        status = 'featured' if feedback.is_featured else 'unfeatured'
        return jsonify({'message': f'Feedback {status} successfully'}), 200
        
    except Exception as e:
        print(f"Error featuring feedback: {str(e)}")
        return jsonify({'error': 'Failed to feature feedback'}), 500

@admin_bp.route('/api/admin/feedback/<feedback_id>/delete', methods=['DELETE'])
@jwt_required()
def delete_feedback(feedback_id):
    """Delete feedback"""
    try:
        current_user_id = get_jwt_identity()
        user = User.objects(id=current_user_id).first()
        
        if not user or user.role != 'admin':
            return jsonify({'error': 'Unauthorized'}), 403
        
        feedback = Feedback.objects(id=feedback_id).first()
        if not feedback:
            return jsonify({'error': 'Feedback not found'}), 404
        
        feedback.delete()
        
        return jsonify({'message': 'Feedback deleted successfully'}), 200
        
    except Exception as e:
        print(f"Error deleting feedback: {str(e)}")
        return jsonify({'error': 'Failed to delete feedback'}), 500


@admin_bp.route('/admin/shops')
@jwt_required(optional=True)
def admin_shops_page():
    token_param = request.args.get('token', '')
    current_user_id, user = get_user_from_token()
    
    if not current_user_id or not user or user.role != 'admin':
        next_url = '/admin/shops'
        if token_param:
            next_url += f'?token={token_param}'
        return redirect(url_for('auth.login') + f'?next={next_url}')
    shops = ShopAd.objects().order_by('-is_active', '-priority', '-created_at')
    return render_template('admin_shops.html', shops=shops)


@admin_bp.get('/api/admin/shops/coordinates')
@jwt_required()
def get_shops_coordinates():
    """Admin endpoint to check all shop coordinates"""
    try:
        current_user_id, user = get_user_from_token()
        if not current_user_id or not user or user.role != 'admin':
            return jsonify({'error': 'Admin access required'}), 403
        
        shops = Shop.objects().order_by('name')
        shops_data = []
        for shop in shops:
            shops_data.append({
                'id': str(shop.id),
                'name': shop.name,
                'address': shop.address,
                'location_lat': shop.location_lat,
                'location_lon': shop.location_lon,
                'is_verified': shop.is_verified or shop.verification_status == 'verified',
                'owner_name': shop.owner.name if shop.owner else 'N/A'
            })
        
        return jsonify({
            'shops': shops_data,
            'total': len(shops_data)
        })
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': f'Error fetching shop coordinates: {str(e)}'}), 500


@admin_bp.put('/api/admin/shops/<shop_id>/coordinates')
@jwt_required()
def update_shop_coordinates(shop_id):
    """Admin endpoint to update shop coordinates"""
    try:
        current_user_id, user = get_user_from_token()
        if not current_user_id or not user or user.role != 'admin':
            return jsonify({'error': 'Admin access required'}), 403
        
        data = request.get_json() or {}
        location_lat = data.get('location_lat')
        location_lon = data.get('location_lon')
        
        if location_lat is None or location_lon is None:
            return jsonify({'error': 'Both location_lat and location_lon are required'}), 400
        
        # Validate coordinates
        try:
            location_lat = float(location_lat)
            location_lon = float(location_lon)
        except (ValueError, TypeError):
            return jsonify({'error': 'Invalid coordinates format'}), 400
        
        if not (-90 <= location_lat <= 90) or not (-180 <= location_lon <= 180):
            return jsonify({'error': 'Coordinates out of valid range'}), 400
        
        shop = Shop.objects(id=ObjectId(shop_id)).first()
        if not shop:
            return jsonify({'error': 'Shop not found'}), 404
        
        old_lat = shop.location_lat
        old_lon = shop.location_lon
        
        shop.location_lat = location_lat
        shop.location_lon = location_lon
        shop.save()
        
        print(f"Admin updated shop '{shop.name}' coordinates: OLD ({old_lat}, {old_lon}) -> NEW ({location_lat}, {location_lon})")
        
        return jsonify({
            'message': 'Shop coordinates updated successfully',
            'shop': {
                'id': str(shop.id),
                'name': shop.name,
                'location_lat': shop.location_lat,
                'location_lon': shop.location_lon
            }
        })
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': f'Error updating shop coordinates: {str(e)}'}), 500


@admin_bp.route('/admin/provider-verifications')
@jwt_required(optional=True)
def admin_provider_verifications_page():
    """Admin page for provider verifications"""
    try:
        token_param = request.args.get('token', '')
        current_user_id, user = get_user_from_token()
        
        if not current_user_id or not user or user.role != 'admin':
            next_url = '/admin/provider-verifications'
            if token_param:
                next_url += f'?token={token_param}'
            return redirect(url_for('auth.login') + f'?next={next_url}')
        
        return render_template('admin_provider_verifications.html')
    except Exception as e:
        print(f"Error loading provider verifications: {e}")
        return redirect(url_for('admin.admin_dashboard'))

@admin_bp.route('/admin/shopkeeper-verifications')
@jwt_required(optional=True)
def admin_shopkeeper_verifications_page():
    """Admin page for shopkeeper verifications"""
    try:
        token_param = request.args.get('token', '')
        current_user_id, user = get_user_from_token()
        
        if not current_user_id or not user or user.role != 'admin':
            next_url = '/admin/shopkeeper-verifications'
            if token_param:
                next_url += f'?token={token_param}'
            return redirect(url_for('auth.login') + f'?next={next_url}')
        
        return render_template('admin_shopkeeper_verifications.html')
    except Exception as e:
        print(f"Error loading shopkeeper verifications: {e}")
        return redirect(url_for('admin.admin_dashboard'))

@admin_bp.route('/admin/shop-verifications')
@jwt_required(optional=True)
def admin_shop_verifications_page():
    """Admin page for managing shopkeeper shop verifications"""
    try:
        token_param = request.args.get('token', '')
        current_user_id, user = get_user_from_token()
        
        if not current_user_id or not user or user.role != 'admin':
            next_url = '/admin/shop-verifications'
            if token_param:
                next_url += f'?token={token_param}'
            return redirect(url_for('auth.login') + f'?next={next_url}')
        
        # Get pending shops for verification
        pending_shops = Shop.objects(is_verified=False).order_by('-created_at')
        verified_shops = Shop.objects(is_verified=True).order_by('-created_at').limit(50)
        
        return render_template('admin_shop_verifications.html', 
                             pending_shops=pending_shops,
                             verified_shops=verified_shops)
    except Exception as e:
        print(f"Error loading shop verifications: {e}")
        return redirect(url_for('admin.admin_dashboard'))


@admin_bp.get('/api/admin/shop-verifications')
@jwt_required()
def get_shop_verifications():
    """API endpoint to get shops pending verification"""
    try:
        current_user_id, user = get_user_from_token()
        if not current_user_id or not user or user.role != 'admin':
            return jsonify({'error': 'Unauthorized'}), 403
        
        status = request.args.get('status', 'pending')  # pending or verified
        
        if status == 'pending':
            shops = Shop.objects(is_verified=False).order_by('-created_at')
        else:
            shops = Shop.objects(is_verified=True).order_by('-created_at').limit(100)
        
        shops_list = []
        for shop in shops:
            shops_list.append({
                'id': str(shop.id),
                'name': shop.name,
                'description': shop.description,
                'category': shop.category,
                'address': shop.address,
                'contact_phone': shop.contact_phone,
                'contact_email': shop.contact_email,
                'owner_name': shop.owner.name if shop.owner else 'Unknown',
                'owner_email': shop.owner.email if shop.owner else '',
                'rating': shop.rating,
                'total_orders': shop.total_orders,
                'is_verified': shop.is_verified,
                'is_active': shop.is_active,
                'created_at': shop.created_at.isoformat() if shop.created_at else None,
                'image_url': url_for('static', filename=shop.image_path, _external=True) if shop.image_path else None
            })
        
        return jsonify({'shops': shops_list})
    except Exception as e:
        print(f"Error getting shop verifications: {e}")
        return jsonify({'error': 'Failed to get shops'}), 500


@admin_bp.post('/api/admin/shop-verifications/<shop_id>/verify')
@jwt_required()
def verify_shop(shop_id):
    """API endpoint to verify a shop"""
    try:
        current_user_id, user = get_user_from_token()
        if not current_user_id or not user or user.role != 'admin':
            print(f"Unauthorized: current_user_id={current_user_id}, user={user}, role={user.role if user else None}")
            return jsonify({'error': 'Unauthorized'}), 403
        
        print(f"Verifying shop with ID: {shop_id}")
        
        # Try to convert to ObjectId, handle both string and ObjectId
        try:
            shop = Shop.objects(id=ObjectId(shop_id)).first()
        except:
            # If ObjectId conversion fails, try as string
            shop = Shop.objects(id=shop_id).first()
        
        if not shop:
            print(f"Shop not found: {shop_id}")
            return jsonify({'error': 'Shop not found'}), 404
        
        print(f"Shop found: {shop.name}, current verified status: {shop.is_verified}")
        
        shop.is_verified = True
        shop.save()
        
        print(f"Shop verified successfully: {shop.name}")
        return jsonify({'message': 'Shop verified successfully', 'shop_id': str(shop.id)})
    except Exception as e:
        print(f"Error verifying shop: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': f'Failed to verify shop: {str(e)}'}), 500


@admin_bp.post('/api/admin/shop-verifications/<shop_id>/reject')
@jwt_required()
def reject_shop(shop_id):
    """API endpoint to reject a shop (deactivate)"""
    try:
        current_user_id, user = get_user_from_token()
        if not current_user_id or not user or user.role != 'admin':
            return jsonify({'error': 'Unauthorized'}), 403
        
        # Try to convert to ObjectId, handle both string and ObjectId
        try:
            shop = Shop.objects(id=ObjectId(shop_id)).first()
        except:
            # If ObjectId conversion fails, try as string
            shop = Shop.objects(id=shop_id).first()
        
        if not shop:
            return jsonify({'error': 'Shop not found'}), 404
        
        shop.is_active = False
        shop.save()
        
        return jsonify({'message': 'Shop rejected and deactivated', 'shop_id': str(shop.id)})
    except Exception as e:
        print(f"Error rejecting shop: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': f'Failed to reject shop: {str(e)}'}), 500


@admin_bp.route('/admin/services')
@jwt_required(optional=True)
def admin_services_page():
    """Admin services management page"""
    try:
        token_param = request.args.get('token', '')
        current_user_id, user = get_user_from_token()
        
        if not current_user_id or not user or user.role != 'admin':
            next_url = '/admin/services'
            if token_param:
                next_url += f'?token={token_param}'
            return redirect(url_for('auth.login') + f'?next={next_url}')
        
        return render_template('admin_services.html')
        
    except Exception as e:
        print(f"Error loading admin services: {str(e)}")
        return redirect(url_for('auth.login'))


@admin_bp.post('/api/admin/shops')
@jwt_required()
def create_shop():
    current_user_id = get_jwt_identity()
    user = User.objects(id=current_user_id).first()
    if not user or user.role != 'admin':
        return jsonify({'error': 'Unauthorized'}), 403

    name = request.form.get('name')
    category = request.form.get('category')
    address = request.form.get('address')
    contact_phone = request.form.get('contact_phone')
    contact_email = request.form.get('contact_email')
    website = request.form.get('website')
    priority = int(request.form.get('priority') or 0)

    image_path = None
    file = request.files.get('image')
    if file and file.filename:
        filename = secure_filename(file.filename)
        upload_dir = os.path.join('static', 'images', 'shops')
        os.makedirs(upload_dir, exist_ok=True)
        path = os.path.join(upload_dir, filename)
        file.save(path)
        image_path = os.path.join('images', 'shops', filename).replace('\\','/')

    shop = ShopAd(
        name=name, category=category, address=address, contact_phone=contact_phone,
        contact_email=contact_email, website=website, image_path=image_path, priority=priority
    )
    shop.save()
    return jsonify({'message': 'Shop created', 'id': str(shop.id)})


@admin_bp.post('/api/admin/shops/<shop_id>')
@jwt_required()
def update_shop(shop_id):
    current_user_id = get_jwt_identity()
    user = User.objects(id=current_user_id).first()
    if not user or user.role != 'admin':
        return jsonify({'error': 'Unauthorized'}), 403

    shop = ShopAd.objects(id=shop_id).first()
    if not shop:
        return jsonify({'error': 'Not found'}), 404

    shop.name = request.form.get('name', shop.name)
    shop.category = request.form.get('category', shop.category)
    shop.address = request.form.get('address', shop.address)
    shop.contact_phone = request.form.get('contact_phone', shop.contact_phone)
    shop.contact_email = request.form.get('contact_email', shop.contact_email)
    shop.website = request.form.get('website', shop.website)
    shop.priority = int(request.form.get('priority') or shop.priority)
    shop.is_active = (request.form.get('is_active') == 'true') if request.form.get('is_active') is not None else shop.is_active

    file = request.files.get('image')
    if file and file.filename:
        filename = secure_filename(file.filename)
        upload_dir = os.path.join('static', 'images', 'shops')
        os.makedirs(upload_dir, exist_ok=True)
        path = os.path.join(upload_dir, filename)
        file.save(path)
        shop.image_path = os.path.join('images', 'shops', filename).replace('\\','/')

    shop.save()
    return jsonify({'message': 'Shop updated'})


@admin_bp.delete('/api/admin/shops/<shop_id>')
@jwt_required()
def delete_shop(shop_id):
    current_user_id = get_jwt_identity()
    user = User.objects(id=current_user_id).first()
    if not user or user.role != 'admin':
        return jsonify({'error': 'Unauthorized'}), 403
    shop = ShopAd.objects(id=shop_id).first()
    if not shop:
        return jsonify({'error': 'Not found'}), 404
    shop.delete()
    return jsonify({'message': 'Shop deleted'})


# Bookings Management
@admin_bp.route('/admin/bookings')
@jwt_required(optional=True)
def admin_bookings_page():
    """Admin bookings management page"""
    try:
        token_param = request.args.get('token', '')
        current_user_id, user = get_user_from_token()
        
        if not current_user_id or not user or user.role != 'admin':
            next_url = '/admin/bookings'
            if token_param:
                next_url += f'?token={token_param}'
            return redirect(url_for('auth.login') + f'?next={next_url}')
        
        # Get filter parameters
        status_filter = request.args.get('status', 'all')
        page = request.args.get('page', 1, type=int)
        per_page = 20
        
        # Build query
        bookings_query = Booking.objects()
        if status_filter and status_filter != 'all':
            bookings_query = bookings_query.filter(status=status_filter)
        
        # Get bookings with pagination
        try:
            bookings = bookings_query.order_by('-created_at').paginate(page=page, per_page=per_page)
        except Exception as pagination_error:
            print(f"Pagination error: {pagination_error}")
            # Fallback: get all and manually paginate
            all_bookings = list(bookings_query.order_by('-created_at'))
            start = (page - 1) * per_page
            end = start + per_page
            class Pagination:
                def __init__(self, items, page, per_page, total):
                    self.items = items
                    self.page = page
                    self.pages = (total + per_page - 1) // per_page if per_page > 0 else 1
                    self.per_page = per_page
                    self.total = total
                    self.has_prev = page > 1
                    self.has_next = end < total
                    self.prev_num = page - 1 if page > 1 else None
                    self.next_num = page + 1 if end < total else None
                def iter_pages(self, left_edge=2, right_edge=2, left_current=2, right_current=2):
                    return range(1, self.pages + 1)
            bookings = Pagination(all_bookings[start:end], page, per_page, len(all_bookings))
        
        # Get statistics
        total_bookings = Booking.objects.count()
        pending_bookings = Booking.objects(status='Pending').count()
        in_progress_bookings = Booking.objects(status='In Progress').count()
        completed_bookings = Booking.objects(status='Completed').count()
        cancelled_bookings = Booking.objects(status='Cancelled').count()
        
        stats = {
            'total': total_bookings,
            'pending': pending_bookings,
            'in_progress': in_progress_bookings,
            'completed': completed_bookings,
            'cancelled': cancelled_bookings
        }
        
        return render_template('admin_bookings.html', 
                             bookings=bookings, 
                             status_filter=status_filter,
                             stats=stats)
    except Exception as e:
        print(f"ERROR in admin_bookings_page: {str(e)}")
        import traceback
        traceback.print_exc()
        # Return error instead of redirecting so we can see it
        return f"<h1>Error Loading Bookings</h1><p>{str(e)}</p><pre>{traceback.format_exc()}</pre>", 500


@admin_bp.post('/api/admin/bookings/<booking_id>/status')
@jwt_required()
def update_booking_status(booking_id):
    """Update booking status"""
    try:
        current_user_id = get_jwt_identity()
        user = User.objects(id=current_user_id).first()
        
        if not user or user.role != 'admin':
            return jsonify({'error': 'Unauthorized'}), 403
        
        data = request.get_json() or {}
        new_status = data.get('status')
        
        if not new_status:
            return jsonify({'error': 'Status is required'}), 400
        
        booking = Booking.objects(id=booking_id).first()
        if not booking:
            return jsonify({'error': 'Booking not found'}), 404
        
        booking.status = new_status
        booking.save()
        
        return jsonify({'message': 'Booking status updated successfully'}), 200
        
    except Exception as e:
        print(f"Error updating booking status: {str(e)}")
        return jsonify({'error': 'Failed to update booking status'}), 500


@admin_bp.get('/api/admin/bookings/<booking_id>')
@jwt_required()
def get_booking_details(booking_id):
    """Get booking details"""
    try:
        current_user_id = get_jwt_identity()
        user = User.objects(id=current_user_id).first()
        
        if not user or user.role != 'admin':
            return jsonify({'error': 'Unauthorized'}), 403
        
        booking = Booking.objects(id=booking_id).first()
        if not booking:
            return jsonify({'error': 'Booking not found'}), 404
        
        booking_data = {
            'id': str(booking.id),
            'user_name': booking.user.name if booking.user else 'N/A',
            'user_email': booking.user.email if booking.user else 'N/A',
            'user_phone': booking.user.phone if booking.user else 'N/A',
            'provider_name': booking.provider_name or (booking.provider.user.name if booking.provider and booking.provider.user else 'N/A'),
            'service_name': booking.service_name or (booking.service.name if booking.service else 'N/A'),
            'status': booking.status,
            'price': booking.price,
            'scheduled_time': booking.scheduled_time.isoformat() if booking.scheduled_time else None,
            'notes': booking.notes,
            'rating': booking.rating,
            'review': booking.review,
            'created_at': booking.created_at.isoformat() if booking.created_at else None,
            'completed_at': booking.completed_at.isoformat() if booking.completed_at else None,
            'completion_notes': booking.completion_notes,
            'completion_images': booking.completion_images or [],
            'payment_status': booking.payment_status or 'Pending'
        }
        
        return jsonify(booking_data), 200
        
    except Exception as e:
        print(f"Error getting booking details: {str(e)}")
        return jsonify({'error': 'Failed to get booking details'}), 500


# Providers Management
@admin_bp.route('/admin/providers')
@jwt_required(optional=True)
def admin_providers_page():
    """Admin providers management page"""
    try:
        token_param = request.args.get('token', '')
        current_user_id, user = get_user_from_token()
        
        if not current_user_id or not user or user.role != 'admin':
            next_url = '/admin/providers'
            if token_param:
                next_url += f'?token={token_param}'
            return redirect(url_for('auth.login') + f'?next={next_url}')
        
        # Get filter parameters
        availability_filter = request.args.get('availability', 'all')
        page = request.args.get('page', 1, type=int)
        per_page = 20
        
        # Build query
        providers_query = Provider.objects()
        if availability_filter == 'available':
            providers_query = providers_query.filter(availability=True)
        elif availability_filter == 'unavailable':
            providers_query = providers_query.filter(availability=False)
        
        # Get providers with pagination
        try:
            providers = providers_query.order_by('-id').paginate(page=page, per_page=per_page)
        except Exception as pagination_error:
            print(f"Pagination error: {pagination_error}")
            # Fallback: get all and manually paginate
            all_providers = list(providers_query.order_by('-id'))
            start = (page - 1) * per_page
            end = start + per_page
            from mongoengine.queryset import QuerySet
            class Pagination:
                def __init__(self, items, page, per_page, total):
                    self.items = items
                    self.page = page
                    self.pages = (total + per_page - 1) // per_page
                    self.per_page = per_page
                    self.total = total
                    self.has_prev = page > 1
                    self.has_next = end < total
                    self.prev_num = page - 1 if page > 1 else None
                    self.next_num = page + 1 if end < total else None
                def iter_pages(self, left_edge=2, right_edge=2, left_current=2, right_current=2):
                    return range(1, self.pages + 1)
            providers = Pagination(all_providers[start:end], page, per_page, len(all_providers))
        
        # Get statistics
        total_providers = Provider.objects.count()
        available_providers = Provider.objects(availability=True).count()
        unavailable_providers = Provider.objects(availability=False).count()
        
        stats = {
            'total': total_providers,
            'available': available_providers,
            'unavailable': unavailable_providers
        }
        
        return render_template('admin_providers.html', 
                             providers=providers,
                             availability_filter=availability_filter,
                             stats=stats)
    except Exception as e:
        print(f"ERROR in admin_providers_page: {str(e)}")
        import traceback
        traceback.print_exc()
        # Return error instead of redirecting so we can see it
        return f"<h1>Error Loading Providers</h1><p>{str(e)}</p><pre>{traceback.format_exc()}</pre>", 500


@admin_bp.post('/api/admin/providers/<provider_id>/availability')
@jwt_required()
def update_provider_availability(provider_id):
    """Update provider availability"""
    try:
        current_user_id = get_jwt_identity()
        user = User.objects(id=current_user_id).first()
        
        if not user or user.role != 'admin':
            return jsonify({'error': 'Unauthorized'}), 403
        
        data = request.get_json() or {}
        availability = data.get('availability')
        
        if availability is None:
            return jsonify({'error': 'Availability is required'}), 400
        
        provider = Provider.objects(id=provider_id).first()
        if not provider:
            return jsonify({'error': 'Provider not found'}), 404
        
        provider.availability = bool(availability)
        provider.save()
        
        return jsonify({'message': 'Provider availability updated successfully'}), 200
        
    except Exception as e:
        print(f"Error updating provider availability: {str(e)}")
        return jsonify({'error': 'Failed to update provider availability'}), 500


# Users Management
@admin_bp.route('/admin/users')
@jwt_required(optional=True)
def admin_users_page():
    """Admin users management page"""
    try:
        token_param = request.args.get('token', '')
        current_user_id, user = get_user_from_token()
        
        if not current_user_id or not user or user.role != 'admin':
            next_url = '/admin/users'
            if token_param:
                next_url += f'?token={token_param}'
            return redirect(url_for('auth.login') + f'?next={next_url}')
        
        # Get filter parameters
        role_filter = request.args.get('role', 'all')
        page = request.args.get('page', 1, type=int)
        per_page = 20
        
        # Build query
        users_query = User.objects()
        if role_filter and role_filter != 'all':
            users_query = users_query.filter(role=role_filter)
        
        # Get users with pagination
        try:
            users = users_query.order_by('-created_at').paginate(page=page, per_page=per_page)
        except Exception as pagination_error:
            print(f"Pagination error: {pagination_error}")
            # Fallback: get all and manually paginate
            all_users = list(users_query.order_by('-created_at'))
            start = (page - 1) * per_page
            end = start + per_page
            class Pagination:
                def __init__(self, items, page, per_page, total):
                    self.items = items
                    self.page = page
                    self.pages = (total + per_page - 1) // per_page if per_page > 0 else 1
                    self.per_page = per_page
                    self.total = total
                    self.has_prev = page > 1
                    self.has_next = end < total
                    self.prev_num = page - 1 if page > 1 else None
                    self.next_num = page + 1 if end < total else None
                def iter_pages(self, left_edge=2, right_edge=2, left_current=2, right_current=2):
                    return range(1, self.pages + 1)
            users = Pagination(all_users[start:end], page, per_page, len(all_users))
        
        # Get statistics
        total_users = User.objects.count()
        regular_users = User.objects(role='user').count()
        provider_users = User.objects(role='provider').count()
        admin_users = User.objects(role='admin').count()
        
        stats = {
            'total': total_users,
            'users': regular_users,
            'providers': provider_users,
            'admins': admin_users
        }
        
        return render_template('admin_users.html', 
                             users=users,
                             role_filter=role_filter,
                             stats=stats,
                             current_user_id=current_user_id)
    except Exception as e:
        print(f"ERROR in admin_users_page: {str(e)}")
        import traceback
        traceback.print_exc()
        # Return error instead of redirecting so we can see it
        return f"<h1>Error Loading Users</h1><p>{str(e)}</p><pre>{traceback.format_exc()}</pre>", 500


@admin_bp.post('/api/admin/users/<user_id>/role')
@jwt_required()
def update_user_role(user_id):
    """Update user role"""
    try:
        current_user_id = get_jwt_identity()
        current_user = User.objects(id=current_user_id).first()
        
        if not current_user or current_user.role != 'admin':
            return jsonify({'error': 'Unauthorized'}), 403
        
        # Prevent changing own role
        if str(current_user_id) == str(user_id):
            return jsonify({'error': 'Cannot change your own role'}), 400
        
        data = request.get_json() or {}
        new_role = data.get('role')
        
        if not new_role or new_role not in ['user', 'provider', 'admin']:
            return jsonify({'error': 'Invalid role'}), 400
        
        user = User.objects(id=user_id).first()
        if not user:
            return jsonify({'error': 'User not found'}), 404
        
        user.role = new_role
        user.save()
        
        # If changing to provider, create provider profile if doesn't exist
        if new_role == 'provider' and not user.provider_profile:
            provider = Provider(user=user, skills=['General'], availability=True)
            provider.save()
            user.provider_profile = provider
            user.save()
        # If changing from provider, remove provider profile
        elif new_role != 'provider' and user.provider_profile:
            try:
                user.provider_profile.delete()
            except:
                pass
            user.provider_profile = None
            user.save()
        
        return jsonify({'message': 'User role updated successfully'}), 200
        
    except Exception as e:
        print(f"Error updating user role: {str(e)}")
        return jsonify({'error': 'Failed to update user role'}), 500


@admin_bp.delete('/api/admin/users/<user_id>')
@jwt_required()
def delete_user(user_id):
    """Delete user"""
    try:
        current_user_id = get_jwt_identity()
        current_user = User.objects(id=current_user_id).first()
        
        if not current_user or current_user.role != 'admin':
            return jsonify({'error': 'Unauthorized'}), 403
        
        # Prevent deleting self
        if str(current_user_id) == str(user_id):
            return jsonify({'error': 'Cannot delete your own account'}), 400
        
        user = User.objects(id=user_id).first()
        if not user:
            return jsonify({'error': 'User not found'}), 404
        
        # Delete provider profile if exists
        if user.provider_profile:
            try:
                user.provider_profile.delete()
            except:
                pass
        
        user.delete()
        
        return jsonify({'message': 'User deleted successfully'}), 200
        
    except Exception as e:
        print(f"Error deleting user: {str(e)}")
        return jsonify({'error': 'Failed to delete user'}), 500


# Payments Management
@admin_bp.route('/admin/payments')
@jwt_required(optional=True)
def admin_payments_page():
    """Admin payments management page"""
    try:
        token_param = request.args.get('token', '')
        current_user_id, user = get_user_from_token()
        
        if not current_user_id or not user or user.role != 'admin':
            next_url = '/admin/payments'
            if token_param:
                next_url += f'?token={token_param}'
            return redirect(url_for('auth.login') + f'?next={next_url}')
        
        # Get filter parameters
        status_filter = request.args.get('status', 'all')
        method_filter = request.args.get('method', 'all')
        user_filter = request.args.get('user', '')
        provider_filter = request.args.get('provider', '')
        page = request.args.get('page', 1, type=int)
        per_page = 20
        
        # Build query
        payments_query = Payment.objects()
        
        if status_filter and status_filter != 'all':
            payments_query = payments_query.filter(status=status_filter)
        
        if method_filter and method_filter != 'all':
            payments_query = payments_query.filter(method=method_filter)
        
        # Filter by customer (user)
        if user_filter:
            try:
                user_obj = User.objects(id=ObjectId(user_filter)).first()
                if user_obj:
                    payments_query = payments_query.filter(user=user_obj)
            except:
                pass
        
        # Get payments with pagination
        try:
            payments = payments_query.order_by('-created_at').paginate(page=page, per_page=per_page)
        except Exception as pagination_error:
            print(f"Pagination error: {pagination_error}")
            # Fallback: get all and manually paginate
            all_payments = list(payments_query.order_by('-created_at'))
            start = (page - 1) * per_page
            end = start + per_page
            class Pagination:
                def __init__(self, items, page, per_page, total):
                    self.items = items
                    self.page = page
                    self.pages = (total + per_page - 1) // per_page if per_page > 0 else 1
                    self.per_page = per_page
                    self.total = total
                    self.has_prev = page > 1
                    self.has_next = end < total
                    self.prev_num = page - 1 if page > 1 else None
                    self.next_num = page + 1 if end < total else None
                def iter_pages(self, left_edge=2, right_edge=2, left_current=2, right_current=2):
                    return range(1, self.pages + 1)
            payments = Pagination(all_payments[start:end], page, per_page, len(all_payments))
        
        # Get statistics
        total_payments = Payment.objects.count()
        success_payments = Payment.objects(status='Success').count()
        pending_payments = Payment.objects(status='Pending').count()
        failed_payments = Payment.objects(status='Failed').count()
        refunded_payments = Payment.objects(status='Refunded').count()
        
        # Calculate total revenue (only successful payments)
        total_revenue = sum([p.amount for p in Payment.objects(status='Success')])
        
        # Get method breakdown
        method_counts = {
            'Cash': Payment.objects(method='Cash', status='Success').count(),
            'Card': Payment.objects(method='Card', status='Success').count(),
            'UPI': Payment.objects(method='UPI', status='Success').count(),
            'Bank Transfer': Payment.objects(method='Bank Transfer', status='Success').count(),
            'Razorpay': Payment.objects(method='Razorpay', status='Success').count()
        }
        
        stats = {
            'total': total_payments,
            'success': success_payments,
            'pending': pending_payments,
            'failed': failed_payments,
            'refunded': refunded_payments,
            'total_revenue': total_revenue,
            'method_counts': method_counts
        }
        
        # Get all users and providers for filter dropdowns
        all_users = User.objects(role='user').order_by('name')
        
        return render_template('admin_payments.html', 
                             payments=payments,
                             status_filter=status_filter,
                             method_filter=method_filter,
                             user_filter=user_filter,
                             provider_filter=provider_filter,
                             stats=stats,
                             all_users=all_users)
    except Exception as e:
        print(f"ERROR in admin_payments_page: {str(e)}")
        import traceback
        traceback.print_exc()
        # Return error instead of redirecting so we can see it
        return f"<h1>Error Loading Payments</h1><p>{str(e)}</p><pre>{traceback.format_exc()}</pre>", 500


@admin_bp.get('/api/admin/payments/<payment_id>')
@jwt_required(optional=True)
def get_payment_details(payment_id):
    """Get detailed payment information"""
    try:
        current_user_id, user = get_user_from_token()
        
        if not current_user_id or not user or user.role != 'admin':
            return jsonify({'error': 'Unauthorized'}), 403
        
        payment = Payment.objects(id=ObjectId(payment_id)).first()
        if not payment:
            return jsonify({'error': 'Payment not found'}), 404
        
        # Get related booking and provider info
        booking = payment.booking
        customer = payment.user
        provider_info = None
        
        if booking and booking.provider:
            provider_info = {
                'id': str(booking.provider.id),
                'name': booking.provider_name or 'N/A',
                'user_email': booking.provider.user.email if booking.provider.user else 'N/A',
                'user_phone': booking.provider.user.phone if booking.provider.user else 'N/A'
            }
        
        payment_data = {
            'id': str(payment.id),
            'amount': payment.amount,
            'currency': payment.currency,
            'method': payment.method,
            'status': payment.status,
            'created_at': payment.created_at.isoformat() if payment.created_at else None,
            'razorpay_payment_id': payment.razorpay_payment_id,
            'razorpay_order_id': payment.razorpay_order_id,
            'customer': {
                'id': str(customer.id),
                'name': customer.name,
                'email': customer.email,
                'phone': customer.phone
            },
            'booking': {
                'id': str(booking.id),
                'service_name': booking.service_name or 'N/A',
                'status': booking.status,
                'scheduled_time': booking.scheduled_time.isoformat() if booking.scheduled_time else None
            },
            'provider': provider_info
        }
        
        return jsonify(payment_data), 200
        
    except Exception as e:
        print(f"Error getting payment details: {str(e)}")
        return jsonify({'error': 'Failed to get payment details'}), 500


@admin_bp.get('/api/admin/referrals')
@jwt_required()
def list_referral_requests():
    admin_id, admin_user = get_user_from_token()
    if not admin_id or not admin_user:
        return jsonify({'error': 'Unauthorized'}), 403

    status = request.args.get('status', 'pending')
    query = ReferralRequest.objects()
    if status != 'all':
        query = query.filter(status=status)

    requests_data = []
    for req in query.order_by('-created_at'):
        requests_data.append({
            'id': str(req.id),
            'user': {
                'id': str(req.user.id),
                'name': req.user.name,
                'email': req.user.email
            },
            'referrer': {
                'id': str(req.referrer.id),
                'name': req.referrer.name,
                'email': req.referrer.email
            },
            'referral_code': req.referral_code,
            'bonus_new_user': req.bonus_new_user,
            'bonus_referrer': req.bonus_referrer,
            'status': req.status,
            'admin_notes': req.admin_notes,
            'created_at': req.created_at.isoformat() if req.created_at else None,
            'processed_at': req.processed_at.isoformat() if req.processed_at else None
        })

    return jsonify(requests_data)


@admin_bp.post('/api/admin/referrals/<request_id>/action')
@jwt_required()
def process_referral_request(request_id):
    admin_id, admin_user = get_user_from_token()
    if not admin_id or not admin_user:
        return jsonify({'error': 'Unauthorized'}), 403

    data = request.get_json() or {}
    action = data.get('action', '').lower()
    notes = data.get('notes', '')

    referral_request = ReferralRequest.objects(id=ObjectId(request_id)).first()
    if not referral_request:
        return jsonify({'error': 'Referral request not found'}), 404

    if referral_request.status != 'pending':
        return jsonify({'error': 'Referral request already processed'}), 400

    if action not in ['approve', 'reject']:
        return jsonify({'error': 'Invalid action'}), 400

    if action == 'reject':
        referral_request.status = 'rejected'
        referral_request.admin_notes = notes
        referral_request.processed_at = datetime.utcnow()
        referral_request.save()
        return jsonify({'success': True, 'status': referral_request.status})

    try:
        new_balance_user = record_transaction(
            referral_request.user,
            referral_request.bonus_new_user,
            transaction_type='credit',
            source='referral_bonus',
            description='Referral bonus approved by admin'
        )
        record_transaction(
            referral_request.referrer,
            referral_request.bonus_referrer,
            transaction_type='credit',
            source='referral_bonus',
            description=f"Referral bonus for inviting {referral_request.user.name or 'user'}"
        )
    except WalletError as exc:
        return jsonify({'error': str(exc)}), 400

    referral_request.status = 'approved'
    referral_request.admin_notes = notes
    referral_request.processed_at = datetime.utcnow()
    referral_request.user.referral_bonus_claimed = True
    referral_request.user.referred_by = str(referral_request.referrer.id)
    referral_request.user.save()
    referral_request.save()

    return jsonify({'success': True, 'status': referral_request.status})


@admin_bp.post('/api/admin/wallet/bonus')
@jwt_required()
def admin_wallet_bonus():
    """Credit a user's wallet with a bonus amount."""
    try:
        admin_id, admin_user = get_user_from_token()
        if not admin_id or not admin_user:
            return jsonify({'error': 'Unauthorized. Admin access required.'}), 403

        data = request.get_json() or {}
        user_id = data.get('user_id')
        amount_str = data.get('amount')
        reason = data.get('reason', '').strip()

        if not user_id:
            return jsonify({'error': 'User ID is required'}), 400

        if amount_str is None:
            return jsonify({'error': 'Amount is required'}), 400

        try:
            amount = float(amount_str)
        except (ValueError, TypeError):
            return jsonify({'error': 'Invalid amount format'}), 400

        if amount <= 0:
            return jsonify({'error': 'Amount must be greater than zero'}), 400

        # Find user
        try:
            user = User.objects(id=ObjectId(user_id)).first()
        except Exception:
            try:
                user = User.objects(id=str(user_id)).first()
            except Exception:
                user = None

        if not user:
            return jsonify({'error': 'User not found'}), 404

        # Record the transaction
        try:
            new_balance = record_transaction(
                user,
                amount,
                transaction_type='credit',
                source='admin_bonus',
                description=reason or f'Admin wallet bonus (by {admin_user.name})'
            )
        except WalletError as exc:
            return jsonify({'error': str(exc)}), 400
        except Exception as exc:
            import traceback
            traceback.print_exc()
            return jsonify({'error': f'Failed to add bonus: {str(exc)}'}), 500

        return jsonify({
            'success': True,
            'user_id': str(user.id),
            'user_name': user.name,
            'amount_added': amount,
            'new_balance': new_balance,
            'message': f'Successfully added ₹{amount:.2f} bonus to {user.name}\'s wallet'
        })

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': f'Unexpected error: {str(e)}'}), 500

