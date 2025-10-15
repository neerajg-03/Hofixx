from flask import Blueprint, request, jsonify, render_template
from flask_jwt_extended import jwt_required, get_jwt_identity
from extensions import socketio
from models import User, Provider, Booking
from bson import ObjectId
from datetime import datetime, timedelta
import math
import random
import json

provider_bp = Blueprint('provider', __name__)

def calculate_distance_haversine(lat1, lon1, lat2, lon2):
    """Calculate distance between two coordinates using Haversine formula"""
    R = 6371  # Earth's radius in kilometers
    dLat = math.radians(lat2 - lat1)
    dLon = math.radians(lon2 - lon1)
    a = (math.sin(dLat/2) * math.sin(dLat/2) +
         math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) *
         math.sin(dLon/2) * math.sin(dLon/2))
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
    return R * c


@provider_bp.get('/providers/nearby')
@jwt_required(optional=True)
def providers_nearby():
    try:
        lat = float(request.args.get('lat'))
        lon = float(request.args.get('lon'))
    except Exception:
        print("No valid lat/lon provided, using default")
        lat, lon = 28.6139, 77.2090  # Default to Delhi

    # Get radius filter (default 15km)
    try:
        radius_km = float(request.args.get('radius', 15))
    except Exception:
        radius_km = 15.0

    # Get optional service filter
    service_type = request.args.get('service_type', '').lower()
    print(f"Searching for providers near {lat}, {lon} within {radius_km}km with service: {service_type}")
    
    # Get all provider users
    users = User.objects(role='provider')
    print(f"Found {users.count()} provider users")
    results = []
    
    for u in users:
        print(f"Checking provider user: {u.name} (ID: {u.id})")
        
        # Check if provider has location set
        if u.latitude is None or u.longitude is None:
            print(f"  Provider {u.name} has no location set, skipping")
            continue
            
        provider_lat = u.latitude
        provider_lon = u.longitude
        
        # Calculate accurate distance using Haversine formula
        dist = calculate_distance_haversine(lat, lon, provider_lat, provider_lon)
        print(f"  Distance: {dist:.2f}km")
        
        # Filter by radius
        if dist > radius_km:
            print(f"  Provider {u.name} is {dist:.2f}km away, outside {radius_km}km range")
            continue
            
        provider = u.provider_profile
        print(f"  Provider profile: {provider}")
        if not provider:
            print(f"  No provider profile found for {u.name}")
            continue
            
        skills = provider.skills if provider.skills else []
        print(f"  Skills: {skills}")
        
        # Filter by service type if provided
        if service_type:
            print(f"  Filtering by service type: {service_type}")
            # Check if provider has the requested service - improved matching
            service_match = False
            
            # Exact match
            if service_type in [skill.lower() for skill in skills]:
                service_match = True
            
            # Partial match (e.g., "electrician" matches "Electrical")
            if not service_match:
                for skill in skills:
                    if (service_type in skill.lower() or 
                        skill.lower() in service_type or
                        service_type.replace(' ', '') in skill.lower().replace(' ', '') or
                        skill.lower().replace(' ', '') in service_type.replace(' ', '')):
                        service_match = True
                        break
            
            # Category-based matching
            if not service_match and service_type:
                service_categories = {
                    'electrician': ['electrical', 'electric', 'wiring', 'power'],
                    'plumber': ['plumbing', 'water', 'pipe', 'drain'],
                    'carpenter': ['carpentry', 'wood', 'furniture', 'cabinet'],
                    'cleaner': ['cleaning', 'housekeeping', 'maid'],
                    'painter': ['painting', 'paint', 'wall', 'decor'],
                    'ac': ['air conditioning', 'cooling', 'refrigerator', 'hvac']
                }
                
                for category, keywords in service_categories.items():
                    if category in service_type:
                        for keyword in keywords:
                            if any(keyword in skill.lower() for skill in skills):
                                service_match = True
                                break
                        if service_match:
                            break
            
            if not service_match:
                print(f"  Service mismatch for {u.name}")
                continue
            else:
                print(f"  Service match found for {u.name}")
        
        # Calculate hourly rate based on skills and experience
        base_rate = 300  # Base rate in INR
        skill_multiplier = len(skills) * 50
        hourly_rate = base_rate + skill_multiplier
        
        # Get jobs count from bookings
        from models import Booking
        jobs_count = Booking.objects(provider=provider).count()
        
        results.append({
            'id': str(provider.id),
            'name': u.name,
            'skills': skills,
            'rating': u.rating or 5.0,
            'hourly_rate': hourly_rate,
            'price': hourly_rate,  # For backward compatibility
            'lat': provider_lat,
            'lon': provider_lon,
            'jobs_count': jobs_count,
            'distance_km': round(dist, 2),
            'avatar': u.avatar_path,
            'availability': provider.availability
        })
    
    # Sort by distance first, then by rating
    results.sort(key=lambda x: (x['distance_km'], -x['rating']))
    print(f"Returning {len(results)} providers")
    return jsonify(results[:50])


@provider_bp.get('/nearby')
@jwt_required(optional=True)
def nearby_page():
    booking_id = request.args.get('booking_id')
    lat = request.args.get('lat')
    lon = request.args.get('lon')
    return render_template('nearby.html', booking_id=booking_id, lat=lat, lon=lon)


@provider_bp.post('/providers/location')
@jwt_required()
def update_provider_location():
    ident = get_jwt_identity()
    user_id = str(ident) if isinstance(ident, str) else str(ident['id'])
    try:
        user = User.objects(id=ObjectId(user_id)).first()
        if not user:
            return jsonify({'message': 'User not found'}), 404
        
        data = request.get_json() or {}
        user.latitude = data.get('lat')
        user.longitude = data.get('lon')
        # Optional human-readable address
        if 'address' in data:
            user.address = data.get('address')
        user.save()
        # Broadcast provider location update to clients
        try:
            room = f"provider_{user.id}"
            socketio.emit('provider_location', {
                'user_id': str(user.id),
                'name': user.name,
                'lat': user.latitude,
                'lon': user.longitude,
                'address': user.address,
                'rating': user.rating
            })
        except Exception:
            pass
        return jsonify({'message': 'Location updated', 'address': user.address})
    except Exception as e:
        return jsonify({'message': 'Invalid user ID'}), 400


@provider_bp.post('/providers/add-service')
@jwt_required()
def add_provider_service():
    ident = get_jwt_identity()
    user_id = str(ident) if isinstance(ident, str) else str(ident['id'])
    
    try:
        user = User.objects(id=ObjectId(user_id)).first()
        if not user or user.role != 'provider':
            return jsonify({'message': 'Provider not found'}), 404
        
        provider = user.provider_profile
        if not provider:
            return jsonify({'message': 'Provider profile not found'}), 404
        
        data = request.get_json() or {}
        service_name = data.get('service_name')
        
        if not service_name:
            return jsonify({'message': 'Service name is required'}), 400
        
        # Add service to provider's skills if not already present
        if service_name not in provider.skills:
            provider.skills.append(service_name)
            provider.save()
            
            # Broadcast provider update
            try:
                socketio.emit('provider_services_updated', {
                    'provider_id': str(provider.id),
                    'services': provider.skills
                }, to='all_providers')
            except Exception:
                pass
            
            return jsonify({'message': 'Service added successfully', 'services': provider.skills})
        else:
            return jsonify({'message': 'Service already exists'}), 400
            
    except Exception as e:
        return jsonify({'message': 'Invalid request'}), 400


@provider_bp.post('/providers/remove-service')
@jwt_required()
def remove_provider_service():
    ident = get_jwt_identity()
    user_id = str(ident) if isinstance(ident, str) else str(ident['id'])
    
    try:
        user = User.objects(id=ObjectId(user_id)).first()
        if not user or user.role != 'provider':
            return jsonify({'message': 'Provider not found'}), 404
        
        provider = user.provider_profile
        if not provider:
            return jsonify({'message': 'Provider profile not found'}), 404
        
        data = request.get_json() or {}
        service_name = data.get('service_name')
        
        if not service_name:
            return jsonify({'message': 'Service name is required'}), 400
        
        # Remove service from provider's skills
        if service_name in provider.skills:
            provider.skills.remove(service_name)
            provider.save()
            
            # Broadcast provider update
            try:
                socketio.emit('provider_services_updated', {
                    'provider_id': str(provider.id),
                    'services': provider.skills
                }, to='all_providers')
            except Exception:
                pass
            
            return jsonify({'message': 'Service removed successfully', 'services': provider.skills})
        else:
            return jsonify({'message': 'Service not found'}), 400
            
    except Exception as e:
        return jsonify({'message': 'Invalid request'}), 400


@provider_bp.get('/providers/<provider_id>/location-data')
def get_provider_location_data(provider_id):
    """Test tracking endpoint without authentication"""
    print(f"\n=== LOCATION DATA REQUEST ===")
    print(f"Provider ID received: {provider_id}")
    print(f"Provider ID length: {len(provider_id)}")
    print(f"Provider ID type: {type(provider_id)}")
    
    try:
        # Get provider user - try as User ID first, then as Provider profile ID
        try:
            obj_id = ObjectId(provider_id)
            print(f"ObjectId created successfully: {obj_id}")
            
            # Try to find as User ID first
            provider_user = User.objects(id=obj_id).first()
            print(f"User query result: {provider_user}")
            
            # If not found as User, try as Provider profile ID (for backward compatibility)
            if not provider_user:
                print(f"Not found as User ID, trying as Provider profile ID...")
                provider_profile = Provider.objects(id=obj_id).first()
                if provider_profile:
                    provider_user = provider_profile.user
                    print(f"Found provider through profile: {provider_user.name if provider_user else 'None'}")
                    
        except Exception as e:
            print(f"ERROR converting provider_id to ObjectId: {e}")
            import traceback
            traceback.print_exc()
            return jsonify({'message': 'Invalid provider ID format', 'error': str(e)}), 400
        
        if not provider_user:
            print(f"Provider user not found: {provider_id}")
            return jsonify({'message': 'Provider not found', 'details': 'No user or provider profile found with this ID'}), 404
            
        if provider_user.role != 'provider':
            print(f"User is not a provider: {provider_user.role}")
            return jsonify({'message': 'User is not a provider', 'role': provider_user.role}), 404
        
        provider = provider_user.provider_profile
        if not provider:
            print(f"Provider profile not found for user: {provider_id}")
            return jsonify({'message': 'Provider profile not found', 'details': 'User exists but has no provider profile'}), 404
        
        # Get user location from request or default
        user_lat = float(request.args.get('user_lat', 28.6139))
        user_lon = float(request.args.get('user_lon', 77.2090))
        
        # Get provider's current location
        provider_lat = provider_user.latitude if provider_user.latitude else 28.6139
        provider_lon = provider_user.longitude if provider_user.longitude else 77.2090
        
        # Calculate distance and ETA
        distance_km = calculate_distance_haversine(user_lat, user_lon, provider_lat, provider_lon)
        eta_minutes = max(5, int((distance_km / 30) * 60))  # 30 km/h average
        
        # Determine status
        if distance_km < 0.5:
            status = "Arrived"
        elif distance_km < 2:
            status = "Nearby"
        else:
            status = "On the way"
        
        tracking_data = {
            'provider': {
                'id': str(provider.id),
                'name': provider_user.name,
                'phone': provider_user.phone,
                'rating': provider_user.rating
            },
            'location': {
                'lat': provider_lat,
                'lon': provider_lon,
                'address': provider_user.address or 'Current location'
            },
            'distance': {
                'km': round(distance_km, 2),
                'eta_minutes': eta_minutes
            },
            'status': status,
            'last_updated': datetime.utcnow().isoformat()
        }
        
        return jsonify(tracking_data)
        
    except Exception as e:
        print(f"Error in test tracking: {e}")
        return jsonify({'message': 'Failed to track provider', 'error': str(e)}), 500


@provider_bp.get('/debug/providers')
def debug_providers():
    """Debug endpoint to check provider data and services"""
    try:
        users = User.objects(role='provider')
        providers_data = []
        
        for user in users:
            provider = user.provider_profile
            if provider:
                providers_data.append({
                    'user_id': str(user.id),
                    'user_name': user.name,
                    'provider_id': str(provider.id),
                    'skills': provider.skills,
                    'availability': provider.availability,
                    'location': {
                        'lat': user.latitude,
                        'lon': user.longitude,
                        'address': user.address
                    }
                })
            else:
                providers_data.append({
                    'user_id': str(user.id),
                    'user_name': user.name,
                    'provider_id': None,
                    'skills': [],
                    'availability': False,
                    'location': {
                        'lat': user.latitude,
                        'lon': user.longitude,
                        'address': user.address
                    },
                    'error': 'No provider profile found'
                })
        
        return jsonify({
            'total_providers': len(providers_data),
            'total_users': users.count(),
            'providers': providers_data
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@provider_bp.get('/debug/bookings')
def debug_bookings():
    """Debug endpoint to check recent bookings"""
    try:
        from models import Booking
        recent_bookings = Booking.objects.order_by('-created_at').limit(10)
        
        bookings_data = []
        for booking in recent_bookings:
            bookings_data.append({
                'id': str(booking.id),
                'user_name': booking.user.name if booking.user else 'Unknown',
                'provider_name': booking.provider.user.name if booking.provider and booking.provider.user else 'Unassigned',
                'service_name': booking.service.name if booking.service else 'Unknown',
                'service_category': booking.service.category if booking.service else 'Unknown',
                'status': booking.status,
                'price': booking.price,
                'created_at': booking.created_at.isoformat() if booking.created_at else None,
                'location': {
                    'lat': booking.location_lat,
                    'lon': booking.location_lon
                }
            })
        
        return jsonify({
            'total_bookings': len(bookings_data),
            'recent_bookings': bookings_data
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@provider_bp.post('/debug/create-test-providers')
def create_test_providers():
    """Create test providers for debugging"""
    try:
        from models import User, Provider
        from flask_bcrypt import Bcrypt
        bcrypt = Bcrypt()
        
        # Create test providers
        test_providers = [
            {
                'name': 'Sahil Electric',
                'email': 'sahil@test.com',
                'phone': '9876543210',
                'skills': ['Electrician', 'Electrical'],
                'lat': 28.6139,
                'lon': 77.2090,
                'address': 'Delhi, India'
            },
            {
                'name': 'Rajesh Plumber',
                'email': 'rajesh@test.com', 
                'phone': '9876543211',
                'skills': ['Plumber', 'Plumbing'],
                'lat': 28.6140,
                'lon': 77.2091,
                'address': 'Delhi, India'
            },
            {
                'name': 'Amit Carpenter',
                'email': 'amit@test.com',
                'phone': '9876543212', 
                'skills': ['Carpenter', 'Woodwork'],
                'lat': 28.6141,
                'lon': 77.2092,
                'address': 'Delhi, India'
            }
        ]
        
        created_count = 0
        for provider_data in test_providers:
            # Check if user already exists
            existing_user = User.objects(email=provider_data['email']).first()
            if existing_user:
                print(f"User {provider_data['name']} already exists")
                continue
                
            # Create user
            user = User(
                name=provider_data['name'],
                email=provider_data['email'],
                phone=provider_data['phone'],
                role='provider',
                password_hash=bcrypt.generate_password_hash('password123').decode('utf-8'),
                latitude=provider_data['lat'],
                longitude=provider_data['lon'],
                address=provider_data['address']
            )
            user.save()
            
            # Create provider profile
            provider = Provider(
                user=user,
                skills=provider_data['skills'],
                availability=True
            )
            provider.save()
            
            # Update user with provider reference
            user.provider_profile = provider
            user.save()
            
            created_count += 1
            print(f"Created provider: {provider_data['name']}")
        
        return jsonify({
            'message': f'Created {created_count} test providers',
            'total_providers': User.objects(role='provider').count()
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@provider_bp.post('/providers/update-tracking-location')
@jwt_required()
def update_provider_tracking_location():
    """Update provider's current location for tracking"""
    ident = get_jwt_identity()
    user_id = str(ident) if isinstance(ident, str) else str(ident.get('id') or ident)
    
    try:
        user = User.objects(id=ObjectId(user_id)).first()
        if not user or user.role != 'provider':
            return jsonify({'message': 'Provider not found'}), 404
        
        data = request.get_json() or {}
        latitude = data.get('lat')
        longitude = data.get('lon')
        
        if latitude is None or longitude is None:
            return jsonify({'message': 'Latitude and longitude are required'}), 400
        
        # Update user location
        user.latitude = float(latitude)
        user.longitude = float(longitude)
        user.save()
        
        # Broadcast location update to clients tracking this provider
        try:
            from datetime import datetime
            socketio.emit('provider_location_update', {
                'provider_id': str(user.id),
                'name': user.name,
                'lat': latitude,
                'lon': longitude,
                'timestamp': datetime.utcnow().isoformat()
            })
        except Exception:
            pass
        
        return jsonify({
            'message': 'Location updated successfully',
            'lat': latitude,
            'lon': longitude
        })
        
    except Exception as e:
        return jsonify({'message': 'Invalid request'}), 400


@provider_bp.get('/providers/<provider_id>/location')
@jwt_required()
def get_provider_location(provider_id):
    """Get current location and ETA for a specific provider"""
    try:
        provider_user = User.objects(id=ObjectId(provider_id)).first()
        if not provider_user or provider_user.role != 'provider':
            return jsonify({'message': 'Provider not found'}), 404
        
        # Get current user location (for ETA calculation)
        ident = get_jwt_identity()
        user_id = str(ident) if isinstance(ident, str) else str(ident.get('id') or ident)
        current_user = User.objects(id=ObjectId(user_id)).first()
        
        if not current_user:
            return jsonify({'message': 'User not found'}), 404
        
        # Calculate ETA (simple distance-based calculation)
        if (provider_user.latitude and provider_user.longitude and 
            current_user.latitude and current_user.longitude):
            
            # Calculate distance in km
            lat_diff = provider_user.latitude - current_user.latitude
            lon_diff = provider_user.longitude - current_user.longitude
            distance_km = math.sqrt(lat_diff**2 + lon_diff**2) * 111
            
            # Estimate ETA (assuming average speed of 25 km/h in city traffic)
            eta_minutes = max(5, int((distance_km / 25) * 60))
            
            return jsonify({
                'provider_id': str(provider_user.id),
                'provider_name': provider_user.name,
                'location': {
                    'lat': provider_user.latitude,
                    'lon': provider_user.longitude,
                    'address': provider_user.address
                },
                'distance_km': round(distance_km, 2),
                'eta_minutes': eta_minutes,
                'status': 'On the way',
                'last_updated': datetime.utcnow().isoformat()
            })
        else:
            return jsonify({'message': 'Location data not available'}), 400
            
    except Exception as e:
        return jsonify({'message': 'Invalid provider ID'}), 400


@provider_bp.get('/providers/<provider_id>/track')
def get_provider_tracking(provider_id):
    """Get real-time tracking information for a provider"""
    try:
        # No authentication required for tracking
        
        # Get provider user first, then their provider profile
        provider_user = User.objects(id=ObjectId(provider_id)).first()
        if not provider_user or provider_user.role != 'provider':
            return jsonify({'message': 'Provider not found'}), 404
        
        provider = provider_user.provider_profile
        if not provider:
            return jsonify({'message': 'Provider profile not found'}), 404
        
        # Get user's current location (from request or default)
        user_lat = float(request.args.get('user_lat', 28.6139))
        user_lon = float(request.args.get('user_lon', 77.2090))
        
        # Get provider's current location
        provider_lat = provider_user.latitude if provider_user.latitude else 28.6139
        provider_lon = provider_user.longitude if provider_user.longitude else 77.2090
        
        # Add some realistic movement simulation
        if not hasattr(provider, 'last_update') or not provider.last_update:
            provider.last_update = datetime.utcnow()
            provider.current_lat = provider_lat
            provider.current_lon = provider_lon
            provider.save()
        else:
            # Simulate movement towards user
            time_diff = (datetime.utcnow() - provider.last_update).total_seconds()
            if time_diff > 30:  # Update every 30 seconds
                # Move provider slightly towards user
                lat_diff = user_lat - provider.current_lat
                lon_diff = user_lon - provider.current_lon
                
                # Move 10% of the distance towards user
                provider.current_lat += lat_diff * 0.1
                provider.current_lon += lon_diff * 0.1
                provider.last_update = datetime.utcnow()
                provider.save()
        
        # Calculate distance and ETA
        distance_km = calculate_distance(
            user_lat, user_lon, 
            provider.current_lat, provider.current_lon
        )
        
        # Estimate ETA based on distance (assuming 30 km/h average speed)
        eta_minutes = max(5, int((distance_km / 30) * 60))
        
        # Get current booking if provided
        booking_id = request.args.get('booking_id')
        booking = None
        if booking_id:
            booking = Booking.objects(id=ObjectId(booking_id)).first()
        
        # Determine provider status
        if distance_km < 0.5:
            status = "Arrived"
        elif distance_km < 2:
            status = "Nearby"
        else:
            status = "On the way"
        
        # Get provider's current address (reverse geocoding simulation)
        current_address = get_address_from_coords(provider.current_lat, provider.current_lon)
        
        tracking_data = {
            'provider': {
                'id': str(provider.id),
                'name': provider_user.name,
                'phone': provider_user.phone,
                'rating': provider_user.rating
            },
            'location': {
                'lat': provider.current_lat,
                'lon': provider.current_lon,
                'address': current_address
            },
            'distance': {
                'km': round(distance_km, 2),
                'eta_minutes': eta_minutes
            },
            'status': status,
            'last_updated': provider.last_update.isoformat(),
            'booking': {
                'id': str(booking.id) if booking else None,
                'service_name': booking.service_name if booking else None,
                'scheduled_time': booking.scheduled_time.isoformat() if booking and booking.scheduled_time else None,
                'price': booking.price if booking else None
            } if booking else None
        }
        
        return jsonify(tracking_data)
        
    except Exception as e:
        print(f"Error tracking provider: {e}")
        return jsonify({'message': 'Failed to track provider'}), 500


@provider_bp.get('/providers/<provider_id>/route')
def get_provider_route(provider_id):
    """Get route information from provider to user"""
    try:
        # Get user location
        user_lat = float(request.args.get('user_lat', 28.6139))
        user_lon = float(request.args.get('user_lon', 77.2090))
        
        # Get provider user first, then their provider profile
        provider_user = User.objects(id=ObjectId(provider_id)).first()
        if not provider_user or provider_user.role != 'provider':
            return jsonify({'message': 'Provider not found'}), 404
        
        provider = provider_user.provider_profile
        if not provider:
            return jsonify({'message': 'Provider profile not found'}), 404
        
        # Get provider location
        provider_lat = provider.current_lat if hasattr(provider, 'current_lat') else provider_user.latitude
        provider_lon = provider.current_lon if hasattr(provider, 'current_lon') else provider_user.longitude
        
        if not provider_lat or not provider_lon:
            return jsonify({'message': 'Provider location not available'}), 404
        
        # Generate route waypoints (simplified)
        route_points = generate_route_waypoints(
            provider_lat, provider_lon,
            user_lat, user_lon
        )
        
        # Calculate route statistics
        total_distance = calculate_route_distance(route_points)
        estimated_duration = max(5, int((total_distance / 30) * 60))  # 30 km/h average
        
        route_data = {
            'provider_id': str(provider.id),
            'waypoints': route_points,
            'total_distance_km': round(total_distance, 2),
            'estimated_duration_minutes': estimated_duration,
            'traffic_conditions': get_traffic_conditions(),
            'route_summary': {
                'start_address': get_address_from_coords(provider_lat, provider_lon),
                'end_address': get_address_from_coords(user_lat, user_lon),
                'distance': f"{round(total_distance, 1)} km",
                'duration': f"{estimated_duration} minutes"
            }
        }
        
        return jsonify(route_data)
        
    except Exception as e:
        print(f"Error getting provider route: {e}")
        return jsonify({'message': 'Failed to get route'}), 500


def calculate_distance(lat1, lon1, lat2, lon2):
    """Calculate distance between two points in kilometers"""
    R = 6371  # Earth's radius in kilometers
    
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    
    a = (math.sin(dlat/2) * math.sin(dlat/2) + 
         math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * 
         math.sin(dlon/2) * math.sin(dlon/2))
    
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
    distance = R * c
    
    return distance


def get_address_from_coords(lat, lon):
    """Get address from coordinates (simplified)"""
    # In a real app, you'd use a geocoding service like Google Maps API
    addresses = [
        "Sector 18, Noida",
        "Connaught Place, New Delhi",
        "Karol Bagh, New Delhi",
        "Lajpat Nagar, New Delhi",
        "Rajouri Garden, New Delhi"
    ]
    
    # Return a random address for simulation
    return random.choice(addresses)


def generate_route_waypoints(start_lat, start_lon, end_lat, end_lon):
    """Generate route waypoints between two points"""
    # Simplified route generation - in real app, use routing service
    waypoints = []
    
    # Add start point
    waypoints.append({
        'lat': start_lat,
        'lon': start_lon,
        'timestamp': datetime.utcnow().isoformat(),
        'status': 'start'
    })
    
    # Generate intermediate waypoints
    num_points = 5
    for i in range(1, num_points):
        progress = i / num_points
        lat = start_lat + (end_lat - start_lat) * progress
        lon = start_lon + (end_lon - start_lon) * progress
        
        # Add some realistic variation
        lat += random.uniform(-0.001, 0.001)
        lon += random.uniform(-0.001, 0.001)
        
        waypoints.append({
            'lat': lat,
            'lon': lon,
            'timestamp': (datetime.utcnow() + timedelta(minutes=i*2)).isoformat(),
            'status': 'in_transit'
        })
    
    # Add end point
    waypoints.append({
        'lat': end_lat,
        'lon': end_lon,
        'timestamp': (datetime.utcnow() + timedelta(minutes=10)).isoformat(),
        'status': 'destination'
    })
    
    return waypoints


def calculate_route_distance(waypoints):
    """Calculate total distance of route"""
    total_distance = 0
    for i in range(len(waypoints) - 1):
        distance = calculate_distance(
            waypoints[i]['lat'], waypoints[i]['lon'],
            waypoints[i+1]['lat'], waypoints[i+1]['lon']
        )
        total_distance += distance
    return total_distance


def get_traffic_conditions():
    """Get current traffic conditions (simplified)"""
    conditions = ['Light', 'Moderate', 'Heavy', 'Severe']
    return {
        'level': random.choice(conditions),
        'delay_minutes': random.randint(0, 15),
        'description': f"Traffic is {random.choice(['light', 'moderate', 'heavy']).lower()}"
    }

