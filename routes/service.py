from flask import Blueprint, request, jsonify, url_for
from flask_jwt_extended import jwt_required, get_jwt_identity
from werkzeug.utils import secure_filename
from models import Service, User, Booking
from bson import ObjectId
import os

service_bp = Blueprint('service', __name__)


@service_bp.get('/api/services')
def list_services():
    services = Service.objects()
    return jsonify([{
        'id': str(s.id),
        'name': s.name,
        'category': s.category,
        'base_price': s.base_price,
        'image_url': url_for('static', filename=s.image_path, _external=False) if s.image_path else None,
        'location_lat': s.location_lat,
        'location_lon': s.location_lon,
    } for s in services])


@service_bp.post('/services')
@jwt_required()
def create_service():
    ident = get_jwt_identity()
    user_id = str(ident['id']) if isinstance(ident, dict) else str(ident)
    try:
        user = User.objects(id=ObjectId(user_id)).first()
        if not user or user.role != 'admin':
            return jsonify({'message': 'Admin only'}), 403
    except Exception:
        return jsonify({'message': 'Invalid user ID'}), 400

    # multipart form support
    name = request.form.get('name')
    category = request.form.get('category')
    base_price = request.form.get('base_price', type=float) or 0
    location_lat = request.form.get('location_lat', type=float)
    location_lon = request.form.get('location_lon', type=float)

    s = Service(name=name, category=category, base_price=base_price, location_lat=location_lat, location_lon=location_lon)

    file = request.files.get('image')
    if file and file.filename:
        filename = secure_filename(file.filename)
        upload_dir = os.path.join('static', 'images', 'services')
        os.makedirs(upload_dir, exist_ok=True)
        save_path = os.path.join(upload_dir, filename)
        file.save(save_path)
        s.image_path = os.path.join('images', 'services', filename).replace('\\', '/')

    s.save()
    return jsonify({'id': str(s.id)})


@service_bp.get('/admin/stats')
@jwt_required()
def admin_stats():
    ident = get_jwt_identity()
    user_id = str(ident['id']) if isinstance(ident, dict) else str(ident)
    try:
        user = User.objects(id=ObjectId(user_id)).first()
        if not user or user.role != 'admin':
            return jsonify({'message': 'Admin only'}), 403
    except Exception:
        return jsonify({'message': 'Invalid user ID'}), 400
    
    total_users = User.objects.count()
    total_bookings = Booking.objects.count()
    revenue = sum([b.price or 0 for b in Booking.objects()])
    return jsonify({'users': total_users, 'bookings': total_bookings, 'revenue': revenue})
