from flask import Blueprint, request, jsonify, url_for, render_template
from flask_jwt_extended import jwt_required, get_jwt_identity
from werkzeug.utils import secure_filename
from models import Service, User, Booking
from bson import ObjectId
import os

service_bp = Blueprint('service', __name__)


@service_bp.get('/api/services')
def list_services():
    try:
        services = Service.objects()
        print(f"Found {services.count()} services in database")
        
        # Clean up unwanted services first
        unwanted_services = ['Gardener', 'Locksmith', 'HVAC Technician']
        for unwanted in unwanted_services:
            Service.objects(name=unwanted).delete()
            print(f"Removed unwanted service: {unwanted}")
        
        # If no services exist, create some sample services
        if services.count() == 0:
            print("No services found, creating sample services...")
            sample_services = [
                {'name': 'Electrician', 'category': 'Electrical', 'base_price': 500},
                {'name': 'Plumber', 'category': 'Plumbing', 'base_price': 400},
                {'name': 'Carpenter', 'category': 'Woodwork', 'base_price': 600},
                {'name': 'Cleaner', 'category': 'Cleaning', 'base_price': 300},
                {'name': 'Painter', 'category': 'Painting', 'base_price': 450},
                {'name': 'AC Repair', 'category': 'HVAC', 'base_price': 700}
            ]
            
            for service_data in sample_services:
                service = Service(**service_data)
                service.save()
                print(f"Created service: {service_data['name']}")
            
            # Reload services after creating
            services = Service.objects()
            print(f"Created {services.count()} sample services")
        
        services_list = [{
            'id': str(s.id),
            'name': s.name,
            'category': s.category,
            'base_price': s.base_price,
            'image_url': url_for('static', filename=s.image_path, _external=False) if s.image_path else None,
            'location_lat': s.location_lat,
            'location_lon': s.location_lon,
        } for s in services]
        
        print(f"Returning {len(services_list)} services")
        return jsonify(services_list)
    except Exception as e:
        print(f"Error in list_services: {str(e)}")
        return jsonify([])


@service_bp.get('/public/stats')
def public_stats():
    """Public endpoint with live counters for homepage.
    Use raw collection access to avoid triggering index builds (which
    can fail on legacy data, e.g., duplicate nulls in unique indexes).
    """
    try:
        users_coll = User._get_collection()
        services_coll = Service._get_collection()
        try:
            from models import Provider  # local import to avoid circulars
            providers_coll = Provider._get_collection()
        except Exception:
            providers_coll = None

        customers = users_coll.estimated_document_count() if users_coll is not None else 0
        providers = (providers_coll.estimated_document_count() if providers_coll is not None else 0)
        categories = (
            len(list(filter(lambda v: v is not None, services_coll.distinct('category'))))
            if services_coll is not None else 0
        )

        return jsonify({
            'customers': int(customers),
            'providers': int(providers),
            'categories': int(categories)
        })
    except Exception as e:
        print(f"Error in public_stats: {str(e)}")
        return jsonify({'customers': 0, 'providers': 0, 'categories': 0})


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


@service_bp.get('/services/<service_id>')
def service_detail(service_id):
    """Get detailed information about a specific service"""
    try:
        service = Service.objects(id=ObjectId(service_id)).first()
        if not service:
            return jsonify({'error': 'Service not found'}), 404
        
        service_data = {
            'id': str(service.id),
            'name': service.name,
            'category': service.category,
            'base_price': service.base_price,
            'image_url': url_for('static', filename=service.image_path, _external=False) if service.image_path else None,
            'location_lat': service.location_lat,
            'location_lon': service.location_lon,
        }
        
        return jsonify(service_data)
    except Exception as e:
        print(f"Error in service_detail: {str(e)}")
        return jsonify({'error': 'Service not found'}), 404


@service_bp.get('/services/<service_id>/view')
def service_view(service_id):
    """Render the service detail page"""
    try:
        service = Service.objects(id=ObjectId(service_id)).first()
        if not service:
            return render_template('404.html'), 404
        
        # Service icons mapping
        service_icons = {
            'Electrician': 'fas fa-bolt',
            'Plumber': 'fas fa-wrench',
            'Carpenter': 'fas fa-hammer',
            'Cleaner': 'fas fa-broom',
            'Painter': 'fas fa-paint-brush',
            'AC Repair': 'fas fa-snowflake'
        }
        
        service_icon = service_icons.get(service.name, 'fas fa-tools')
        
        return render_template('service_detail.html', service=service, service_icon=service_icon)
    except Exception as e:
        print(f"Error in service_view: {str(e)}")
        return render_template('404.html'), 404


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
