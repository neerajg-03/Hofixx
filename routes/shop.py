from flask import Blueprint, request, jsonify, url_for, render_template
from flask_jwt_extended import jwt_required, get_jwt_identity
from werkzeug.utils import secure_filename
from models import Shop, Product, Cart, Order, User, DeliveryPartner, Payment
from bson import ObjectId
from datetime import datetime
import os
import math
from mongoengine.queryset.visitor import Q

shop_bp = Blueprint('shop', __name__)


def calculate_distance(lat1, lon1, lat2, lon2):
    """Calculate distance between two coordinates using Haversine formula"""
    R = 6371  # Earth radius in km
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat/2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon/2)**2
    c = 2 * math.asin(math.sqrt(a))
    return R * c


def group_shops_by_proximity(shops_data, user_lat, user_lon, max_radius_km=1.0):
    """
    Group shops by proximity. Shops within max_radius_km (default 1km) of each other are grouped together.
    Returns list of shop clusters, each containing shops within the radius.
    """
    if not shops_data or len(shops_data) == 0:
        return []
    
    clusters = []
    processed_shops = set()
    
    for shop_data in shops_data:
        shop_id = shop_data['shop_id']
        if shop_id in processed_shops:
            continue
        
        shop_lat = shop_data.get('shop_lat')
        shop_lon = shop_data.get('shop_lon')
        
        if shop_lat is None or shop_lon is None:
            # Shop without coordinates - create separate cluster
            clusters.append({
                'shops': [shop_data],
                'cluster_id': f"cluster_{shop_id}",
                'is_within_radius': False,
                'delivery_charge': 50.0  # Default delivery charge
            })
            processed_shops.add(shop_id)
            continue
        
        # Start new cluster with this shop
        cluster = {
            'shops': [shop_data],
            'shop_ids': [shop_id],
            'cluster_id': f"cluster_{shop_id}",
            'is_within_radius': True,
            'avg_lat': shop_lat,
            'avg_lon': shop_lon
        }
        processed_shops.add(shop_id)
        
        # Find other shops within radius
        for other_shop in shops_data:
            other_shop_id = other_shop['shop_id']
            if other_shop_id in processed_shops:
                continue
            
            other_shop_lat = other_shop.get('shop_lat')
            other_shop_lon = other_shop.get('shop_lon')
            
            if other_shop_lat is None or other_shop_lon is None:
                continue
            
            # Check if shop is within radius of any shop in this cluster
            within_radius = False
            for cluster_shop in cluster['shops']:
                cluster_lat = cluster_shop.get('shop_lat')
                cluster_lon = cluster_shop.get('shop_lon')
                if cluster_lat and cluster_lon:
                    distance = calculate_distance(
                        cluster_lat, cluster_lon,
                        other_shop_lat, other_shop_lon
                    )
                    if distance <= max_radius_km:
                        within_radius = True
                        break
            
            if within_radius:
                cluster['shops'].append(other_shop)
                cluster['shop_ids'].append(other_shop_id)
                # Update average coordinates
                cluster['avg_lat'] = sum(s.get('shop_lat', 0) for s in cluster['shops']) / len(cluster['shops'])
                cluster['avg_lon'] = sum(s.get('shop_lon', 0) for s in cluster['shops']) / len(cluster['shops'])
                processed_shops.add(other_shop_id)
        
        # Calculate delivery charge for this cluster
        if user_lat and user_lon and cluster['shops']:
            first_shop = cluster['shops'][0]
            shop_lat = first_shop.get('shop_lat')
            shop_lon = first_shop.get('shop_lon')
            if shop_lat and shop_lon:
                distance_to_user = calculate_distance(user_lat, user_lon, shop_lat, shop_lon)
                # Base delivery charge: ₹30 for first km, ₹10 per additional km
                if distance_to_user <= 1:
                    cluster['delivery_charge'] = 30.0
                else:
                    cluster['delivery_charge'] = 30.0 + ((distance_to_user - 1) * 10)
            else:
                cluster['delivery_charge'] = 50.0  # Default
        else:
            cluster['delivery_charge'] = 50.0  # Default
        
        clusters.append(cluster)
    
    return clusters


def calculate_delivery_charge(shop_lat, shop_lon, user_lat, user_lon):
    """Calculate delivery charge based on distance from shop to user"""
    if not all([shop_lat, shop_lon, user_lat, user_lon]):
        return 50.0  # Default delivery charge
    
    distance = calculate_distance(user_lat, user_lon, shop_lat, shop_lon)
    
    # Base delivery charge: ₹30 for first km, ₹10 per additional km
    if distance <= 1:
        return 30.0
    else:
        return 30.0 + ((distance - 1) * 10)


# Shop Registration and Management
@shop_bp.post('/api/shop/register')
@jwt_required()
def register_shop():
    """Register a new shop"""
    try:
        ident = get_jwt_identity()
        user_id = str(ident['id']) if isinstance(ident, dict) else str(ident)
        user = User.objects(id=ObjectId(user_id)).first()
        if not user:
            return jsonify({'message': 'User not found'}), 404
        
        # Handle form data for shop registration
        name = request.form.get('name')
        description = request.form.get('description', '')
        # Handle multiple categories - can be comma-separated string or list
        categories = request.form.getlist('categories[]') or request.form.getlist('category') or [request.form.get('category')]
        # Filter out empty values
        categories = [cat for cat in categories if cat and cat.strip()]
        address = request.form.get('address')
        location_lat = request.form.get('location_lat')
        location_lon = request.form.get('location_lon')
        contact_phone = request.form.get('contact_phone')
        contact_email = request.form.get('contact_email')
        
        if not all([name, categories, address, location_lat, location_lon, contact_phone]):
            return jsonify({'message': 'Missing required fields'}), 400
        
        # Validate and convert coordinates
        try:
            location_lat = float(location_lat)
            location_lon = float(location_lon)
        except (ValueError, TypeError):
            return jsonify({'message': 'Invalid coordinates format'}), 400
        
        # Validate coordinate ranges (India roughly: lat 6-37, lon 68-97)
        # But allow wider range for global compatibility
        if not (-90 <= location_lat <= 90) or not (-180 <= location_lon <= 180):
            return jsonify({'message': 'Coordinates out of valid range'}), 400
        
        # Check if user already has a shop
        existing_shop = Shop.objects(owner=user).first()
        if existing_shop:
            return jsonify({'message': 'You already have a registered shop'}), 400
        
        print(f"Registering shop '{name}' with coordinates: ({location_lat}, {location_lon})")
        
        shop = Shop(
            owner=user,
            name=name,
            description=description,
            category=categories,
            address=address,
            location_lat=location_lat,
            location_lon=location_lon,
            contact_phone=contact_phone,
            contact_email=contact_email
        )
        
        # Handle image upload
        if 'image' in request.files:
            file = request.files.get('image')
            if file and file.filename:
                filename = secure_filename(file.filename)
                upload_dir = os.path.join('static', 'images', 'shops')
                os.makedirs(upload_dir, exist_ok=True)
                save_path = os.path.join(upload_dir, filename)
                file.save(save_path)
                shop.image_path = os.path.join('images', 'shops', filename).replace('\\', '/')
        
        shop.save()
        return jsonify({
            'message': 'Shop registered successfully',
            'shop_id': str(shop.id)
        }), 201
    except Exception as e:
        print(f"Error registering shop: {e}")
        return jsonify({'message': 'Failed to register shop'}), 500


@shop_bp.get('/api/shop/my-shop')
@jwt_required()
def get_my_shop():
    """Get shopkeeper's own shop"""
    try:
        ident = get_jwt_identity()
        if not ident:
            return jsonify({'message': 'Authentication required'}), 401
        
        # Handle both dict and string formats
        if isinstance(ident, dict):
            user_id = str(ident.get('id', ident))
        else:
            user_id = str(ident)
        
        if not user_id or user_id == 'None':
            return jsonify({'message': 'Invalid user identity'}), 400
        
        try:
            user = User.objects(id=ObjectId(user_id)).first()
        except Exception as e:
            print(f"Error querying user: {e}")
            return jsonify({'message': 'Invalid user ID format'}), 400
        
        if not user:
            return jsonify({'message': 'User not found'}), 404
        
        shop = Shop.objects(owner=user).first()
        if not shop:
            return jsonify({'message': 'No shop found'}), 404
        
        return jsonify({
            'id': str(shop.id),
            'name': shop.name,
            'description': shop.description,
            'category': shop.category,
            'address': shop.address,
            'location_lat': shop.location_lat,
            'location_lon': shop.location_lon,
            'contact_phone': shop.contact_phone,
            'contact_email': shop.contact_email,
            'image_url': url_for('static', filename=shop.image_path, _external=True) if shop.image_path else None,
            'is_active': shop.is_active,
            'is_verified': shop.is_verified,
            'rating': shop.rating,
            'total_orders': shop.total_orders
        })
    except Exception as e:
        import traceback
        print(f"Error getting my shop: {e}")
        traceback.print_exc()
        # Return 404 if it's a not found error, 500 for other errors
        if 'not found' in str(e).lower() or 'does not exist' in str(e).lower():
            return jsonify({'message': 'No shop found'}), 404
        return jsonify({'message': 'Error fetching shop', 'error': str(e)}), 500


@shop_bp.put('/api/shop/update')
@jwt_required()
def update_shop():
    """Update shop details"""
    try:
        ident = get_jwt_identity()
        user_id = str(ident['id']) if isinstance(ident, dict) else str(ident)
        user = User.objects(id=ObjectId(user_id)).first()
        if not user:
            return jsonify({'message': 'User not found'}), 404
        
        shop = Shop.objects(owner=user).first()
        if not shop:
            return jsonify({'message': 'Shop not found'}), 404
        
        # Handle both JSON and form data
        if request.is_json:
            data = request.get_json() or {}
        else:
            data = request.form.to_dict()
            # Handle multiple categories from form
            if 'categories[]' in request.form:
                data['category'] = request.form.getlist('categories[]')
            elif 'category' in request.form:
                # Single category - convert to list
                cat = request.form.get('category')
                data['category'] = [cat] if cat else []
        
        # Validate and update coordinates if provided
        if 'location_lat' in data or 'location_lon' in data:
            location_lat = data.get('location_lat') or shop.location_lat
            location_lon = data.get('location_lon') or shop.location_lon
            
            # Validate coordinate format
            try:
                location_lat = float(location_lat)
                location_lon = float(location_lon)
            except (ValueError, TypeError):
                return jsonify({'message': 'Invalid coordinates format'}), 400
            
            # Validate coordinate ranges
            if not (-90 <= location_lat <= 90) or not (-180 <= location_lon <= 180):
                return jsonify({'message': 'Coordinates out of valid range'}), 400
            
            print(f"Updating shop '{shop.name}' coordinates: OLD ({shop.location_lat}, {shop.location_lon}) -> NEW ({location_lat}, {location_lon})")
            
            shop.location_lat = location_lat
            shop.location_lon = location_lon
            data['location_lat'] = location_lat
            data['location_lon'] = location_lon
        
        if 'name' in data:
            shop.name = data['name']
        if 'description' in data:
            shop.description = data['description']
        if 'category' in data:
            # Ensure category is a list
            categories = data['category']
            if isinstance(categories, str):
                categories = [c.strip() for c in categories.split(',') if c.strip()]
            elif not isinstance(categories, list):
                categories = [categories] if categories else []
            shop.category = categories
        if 'address' in data:
            shop.address = data['address']
        # Location coordinates are already validated above if provided
        # No need to set them again here since they're already set in the validation block
        if 'contact_phone' in data:
            shop.contact_phone = data['contact_phone']
        if 'contact_email' in data:
            shop.contact_email = data['contact_email']
        
        # Handle image upload if provided
        if 'image' in request.files:
            file = request.files.get('image')
            if file and file.filename:
                filename = secure_filename(file.filename)
                upload_dir = os.path.join('static', 'images', 'shops')
                os.makedirs(upload_dir, exist_ok=True)
                save_path = os.path.join(upload_dir, filename)
                file.save(save_path)
                shop.image_path = os.path.join('images', 'shops', filename).replace('\\', '/')
        
        shop.save()
        return jsonify({'message': 'Shop updated successfully'})
    except Exception as e:
        print(f"Error updating shop: {e}")
        return jsonify({'message': 'Failed to update shop'}), 500


# Product Management
@shop_bp.post('/api/shop/products')
@jwt_required()
def add_product():
    """Add a product to shop"""
    try:
        ident = get_jwt_identity()
        user_id = str(ident['id']) if isinstance(ident, dict) else str(ident)
        user = User.objects(id=ObjectId(user_id)).first()
        if not user:
            return jsonify({'message': 'User not found'}), 404
        
        shop = Shop.objects(owner=user).first()
        if not shop:
            return jsonify({'message': 'Shop not found'}), 404
        
        # Handle both JSON and form data
        if request.is_json:
            data = request.get_json()
            name = data.get('name')
            description = data.get('description', '')
            category = data.get('category')
            price = data.get('price')
            stock_quantity = data.get('stock_quantity', 0)
        else:
            name = request.form.get('name')
            description = request.form.get('description', '')
            category = request.form.get('category')
            price = request.form.get('price')
            stock_quantity = request.form.get('stock_quantity', 0)
        
        if not all([name, category, price]):
            return jsonify({'message': 'Missing required fields'}), 400
        
        product = Product(
            shop=shop,
            name=name,
            description=description,
            category=category,
            price=float(price),
            stock_quantity=int(stock_quantity)
        )
        
        # Handle image upload
        if 'image' in request.files:
            file = request.files.get('image')
            if file and file.filename:
                filename = secure_filename(file.filename)
                upload_dir = os.path.join('static', 'images', 'products')
                os.makedirs(upload_dir, exist_ok=True)
                save_path = os.path.join(upload_dir, filename)
                file.save(save_path)
                product.image_path = os.path.join('images', 'products', filename).replace('\\', '/')
        
        product.save()
        return jsonify({
            'message': 'Product added successfully',
            'product_id': str(product.id)
        }), 201
    except Exception as e:
        print(f"Error adding product: {e}")
        return jsonify({'message': 'Failed to add product'}), 500


@shop_bp.get('/api/shop/products')
@jwt_required()
def get_shop_products():
    """Get all products for shopkeeper's shop"""
    try:
        ident = get_jwt_identity()
        user_id = str(ident['id']) if isinstance(ident, dict) else str(ident)
        user = User.objects(id=ObjectId(user_id)).first()
        if not user:
            return jsonify({'message': 'User not found'}), 404
        
        shop = Shop.objects(owner=user).first()
        if not shop:
            return jsonify({'message': 'Shop not found'}), 404
        
        products = Product.objects(shop=shop)
        products_list = [{
            'id': str(p.id),
            'name': p.name,
            'description': p.description,
            'category': p.category,
            'price': p.price,
            'stock_quantity': p.stock_quantity,
            'image_url': url_for('static', filename=p.image_path, _external=True) if p.image_path else None,
            'is_available': p.is_available
        } for p in products]
        
        return jsonify(products_list)
    except Exception as e:
        print(f"Error getting products: {e}")
        return jsonify({'message': 'Failed to get products'}), 500


@shop_bp.put('/api/shop/products/<product_id>')
@jwt_required()
def update_product(product_id):
    """Update a product"""
    try:
        ident = get_jwt_identity()
        user_id = str(ident['id']) if isinstance(ident, dict) else str(ident)
        user = User.objects(id=ObjectId(user_id)).first()
        if not user:
            return jsonify({'message': 'User not found'}), 404
        
        shop = Shop.objects(owner=user).first()
        if not shop:
            return jsonify({'message': 'Shop not found'}), 404
        
        product = Product.objects(id=ObjectId(product_id), shop=shop).first()
        if not product:
            return jsonify({'message': 'Product not found'}), 404
        
        data = request.get_json() or {}
        if 'name' in data:
            product.name = data['name']
        if 'description' in data:
            product.description = data['description']
        if 'category' in data:
            product.category = data['category']
        if 'price' in data:
            product.price = float(data['price'])
        if 'stock_quantity' in data:
            product.stock_quantity = int(data['stock_quantity'])
        if 'is_available' in data:
            product.is_available = data['is_available']
        
        product.updated_at = datetime.utcnow()
        product.save()
        return jsonify({'message': 'Product updated successfully'})
    except Exception as e:
        print(f"Error updating product: {e}")
        return jsonify({'message': 'Failed to update product'}), 500


@shop_bp.delete('/api/shop/products/<product_id>')
@jwt_required()
def delete_product(product_id):
    """Delete a product"""
    try:
        ident = get_jwt_identity()
        user_id = str(ident['id']) if isinstance(ident, dict) else str(ident)
        user = User.objects(id=ObjectId(user_id)).first()
        if not user:
            return jsonify({'message': 'User not found'}), 404
        
        shop = Shop.objects(owner=user).first()
        if not shop:
            return jsonify({'message': 'Shop not found'}), 404
        
        product = Product.objects(id=ObjectId(product_id), shop=shop).first()
        if not product:
            return jsonify({'message': 'Product not found'}), 404
        
        product.delete()
        return jsonify({'message': 'Product deleted successfully'})
    except Exception as e:
        print(f"Error deleting product: {e}")
        return jsonify({'message': 'Failed to delete product'}), 500


# Shopping - Browse Shops by Category
@shop_bp.get('/api/shop/browse')
def browse_shops_by_category():
    """Browse shops by category (shop category, not product category)"""
    try:
        shop_category = request.args.get('shop_category', '')  # hardware, electricals, plumbing, etc.
        user_lat = request.args.get('lat', type=float)
        user_lon = request.args.get('lon', type=float)
        
        # Find shops by category - include shops verified via new or legacy flag
        shops_query = Shop.objects(is_active=True).filter(
            Q(verification_status='verified') | Q(is_verified=True)
        )
        if shop_category:
            # For MongoEngine ListField, to check if a value exists in the list, use category=value
            # This will match any shop where shop_category is in the category list
            shops_query = shops_query.filter(category=shop_category)
        
        shops = shops_query.limit(50)  # Limit to 50 shops
        
        shops_list = []
        for shop in shops:
            # Get products count for this shop
            products_count = Product.objects(shop=shop, is_available=True).count()
            
            # Validate shop coordinates
            shop_lat = shop.location_lat
            shop_lon = shop.location_lon
            
            # Check if coordinates are valid
            if shop_lat is None or shop_lon is None:
                print(f"WARNING: Shop '{shop.name}' (ID: {shop.id}) has missing coordinates (lat: {shop_lat}, lon: {shop_lon})")
                continue  # Skip shops without valid coordinates
            
            # Validate coordinate ranges (India roughly: lat 6-37, lon 68-97)
            if not (-90 <= shop_lat <= 90) or not (-180 <= shop_lon <= 180):
                print(f"WARNING: Shop '{shop.name}' (ID: {shop.id}) has invalid coordinates (lat: {shop_lat}, lon: {shop_lon})")
                continue  # Skip shops with invalid coordinates
            
            shop_data = {
                'id': str(shop.id),
                'name': shop.name,
                'description': shop.description,
                'category': shop.category,
                'address': shop.address,
                'location_lat': shop_lat,
                'location_lon': shop_lon,
                'image_url': url_for('static', filename=shop.image_path, _external=True) if shop.image_path else None,
                'rating': shop.rating,
                'is_verified': shop.is_verified,
                'total_orders': shop.total_orders,
                'products_count': products_count
            }
            
            # Calculate distance if user location provided and shop coordinates are valid
            if user_lat and user_lon and shop_lat is not None and shop_lon is not None:
                try:
                    distance = calculate_distance(
                        float(user_lat), float(user_lon),
                        float(shop_lat), float(shop_lon)
                    )
                    shop_data['distance'] = round(distance, 2)
                    print(f"Shop '{shop.name}': coords ({shop_lat}, {shop_lon}), distance: {shop_data['distance']} km from user ({user_lat}, {user_lon})")
                except (ValueError, TypeError) as e:
                    print(f"Error calculating distance for shop '{shop.name}': {e}")
                    shop_data['distance'] = None
            else:
                shop_data['distance'] = None
            
            shops_list.append(shop_data)
        
        # Sort by distance if location provided
        if user_lat and user_lon:
            shops_list.sort(key=lambda x: x.get('distance', float('inf')))
        else:
            shops_list.sort(key=lambda x: x.get('rating', 0), reverse=True)
        
        return jsonify({
            'shops': shops_list,
            'total_shops': len(shops_list),
            'category': shop_category
        })
    except Exception as e:
        print(f"Error browsing shops: {e}")
        return jsonify({'message': 'Failed to browse shops'}), 500


# Shopping - Search and Browse
@shop_bp.get('/api/shop/search')
def search_products():
    """Search for products and get nearby shops"""
    try:
        query = request.args.get('q', '').strip().lower()
        user_lat = request.args.get('lat', type=float)
        user_lon = request.args.get('lon', type=float)
        category = request.args.get('category', '')
        
        if not query:
            return jsonify({'message': 'Search query required'}), 400
        
        # Build a flexible search over name and description (multi-word AND matching)
        words = [w for w in query.split() if len(w) > 1]

        base_q = Q(is_available=True)
        text_q = Q(name__icontains=query) | Q(description__icontains=query)
        if words:
            # Require all words to appear in either name or description
            for w in words:
                text_q = text_q | (Q(name__icontains=w) | Q(description__icontains=w))

        products = Product.objects(base_q & text_q)
        
        if category:
            products = products.filter(category=category)
        
        # Group products by shop - only verified shops
        shops_dict = {}
        products_count = 0
        skipped_products = 0
        for product in products:
            products_count += 1
            try:
                shop = product.shop
                if not shop:
                    skipped_products += 1
                    print(f"Product '{product.name}' (ID: {product.id}) has no shop reference - skipped")
                    continue
            except Exception as e:
                skipped_products += 1
                print(f"Error accessing shop for product '{product.name}': {e}")
                continue
            
            # Only include products from shops that are active and verified (new flag or legacy boolean)
            is_shop_verified = (shop.verification_status == 'verified') or bool(shop.is_verified)
            if not shop.is_active or not is_shop_verified:
                skipped_products += 1
                print(f"Product '{product.name}' from shop '{shop.name}' skipped - verification_status: {shop.verification_status}, active: {shop.is_active}")
                continue
                
            # Log shop coordinates for debugging
            print(f"DEBUG: Shop '{shop.name}' (ID: {shop.id}) - Address: '{shop.address}', Coordinates: ({shop.location_lat}, {shop.location_lon})")
            
            shop_id = str(shop.id)
            if shop_id not in shops_dict:
                shops_dict[shop_id] = {
                    'shop': {
                        'id': str(shop.id),
                        'name': shop.name,
                        'category': shop.category,  # include shop category for client-side filtering
                        'address': shop.address,
                        'location_lat': shop.location_lat,
                        'location_lon': shop.location_lon,
                        'image_url': url_for('static', filename=shop.image_path, _external=True) if shop.image_path else None,
                        'rating': shop.rating,
                        'is_verified': shop.is_verified
                    },
                    'products': []
                }
            
            shops_dict[shop_id]['products'].append({
                'id': str(product.id),
                'name': product.name,
                'description': product.description,
                'category': product.category,
                'price': product.price,
                'stock_quantity': product.stock_quantity,
                'image_url': url_for('static', filename=product.image_path, _external=True) if product.image_path else None
            })
        
        print(f"Search query '{query}': Found {products_count} products, {skipped_products} skipped, {len(shops_dict)} shops")
        
        # Calculate distances if user location provided
        shops_list = list(shops_dict.values())
        if user_lat and user_lon:
            print(f"Calculating distances from user location: ({user_lat}, {user_lon})")
            valid_shops = []
            for shop_data in shops_list:
                shop = shop_data['shop']
                shop_lat = shop.get('location_lat')
                shop_lon = shop.get('location_lon')
                
                # Validate shop coordinates
                if shop_lat is None or shop_lon is None:
                    print(f"WARNING: Shop '{shop.get('name', 'Unknown')}' has missing coordinates (lat: {shop_lat}, lon: {shop_lon}) - skipping")
                    shop_data['distance'] = None
                    valid_shops.append(shop_data)
                    continue
                
                # Validate coordinate ranges (India roughly: lat 6-37, lon 68-97)
                try:
                    shop_lat = float(shop_lat)
                    shop_lon = float(shop_lon)
                    
                    if not (-90 <= shop_lat <= 90) or not (-180 <= shop_lon <= 180):
                        print(f"WARNING: Shop '{shop.get('name', 'Unknown')}' has invalid coordinates (lat: {shop_lat}, lon: {shop_lon}) - skipping distance calculation")
                        shop_data['distance'] = None
                        valid_shops.append(shop_data)
                        continue
                    
                    # Calculate distance
                    distance = calculate_distance(
                        float(user_lat), float(user_lon),
                        shop_lat, shop_lon
                    )
                    shop_data['distance'] = round(distance, 2)
                    print(f"Shop '{shop.get('name', 'Unknown')}': coordinates ({shop_lat}, {shop_lon}), distance: {shop_data['distance']} km from user ({user_lat}, {user_lon})")
                    
                    # Update shop dict with validated coordinates
                    shop['location_lat'] = shop_lat
                    shop['location_lon'] = shop_lon
                    
                except (ValueError, TypeError) as e:
                    print(f"Error processing coordinates for shop '{shop.get('name', 'Unknown')}': {e}")
                    shop_data['distance'] = None
                
                valid_shops.append(shop_data)
            
            shops_list = valid_shops
            
            # Sort by distance (shops with None distance go to the end)
            shops_list.sort(key=lambda x: (x.get('distance') is None, x.get('distance', float('inf'))))
        else:
            for shop_data in shops_list:
                shop_data['distance'] = None
        
        return jsonify({
            'shops': shops_list,
            'total_shops': len(shops_list)
        })
    except Exception as e:
        print(f"Error searching products: {e}")
        return jsonify({'message': 'Failed to search products'}), 500


# Cart Management
@shop_bp.post('/api/cart/add')
@jwt_required()
def add_to_cart():
    """Add product to cart with proximity validation for multi-shop orders"""
    try:
        ident = get_jwt_identity()
        user_id = str(ident['id']) if isinstance(ident, dict) else str(ident)
        user = User.objects(id=ObjectId(user_id)).first()
        if not user:
            return jsonify({'message': 'User not found'}), 404
        
        data = request.get_json()
        product_id = data.get('product_id')
        quantity = int(data.get('quantity', 1))
        user_lat = data.get('user_lat', type=float) or user.latitude
        user_lon = data.get('user_lon', type=float) or user.longitude
        
        if not product_id:
            return jsonify({'message': 'Product ID required'}), 400
        
        product = Product.objects(id=ObjectId(product_id)).first()
        if not product or not product.is_available:
            return jsonify({'message': 'Product not available'}), 404
        
        if product.stock_quantity < quantity:
            return jsonify({'message': 'Insufficient stock'}), 400
        
        new_shop = product.shop
        if not new_shop:
            return jsonify({'message': 'Shop not found'}), 404
        
        # Get or create cart
        cart = Cart.objects(user=user).first()
        if not cart:
            cart = Cart(user=user, items=[], total_amount=0.0)
        
        # Check if product already in cart
        item_index = None
        for i, item in enumerate(cart.items):
            if item.get('product_id') == product_id and item.get('shop_id') == str(new_shop.id):
                item_index = i
                break
        
        if item_index is not None:
            # Update quantity
            cart.items[item_index]['quantity'] += quantity
            cart.items[item_index]['total_price'] = cart.items[item_index]['quantity'] * product.price
        else:
            # Validate proximity if cart has items from other shops
            existing_shops = set()
            for item in cart.items:
                shop_id = item.get('shop_id')
                if shop_id and shop_id != str(new_shop.id):
                    existing_shops.add(shop_id)
            
            proximity_warning = None
            if existing_shops and new_shop.location_lat and new_shop.location_lon:
                # Check if new shop is within 1km of any existing shop in cart
                within_radius = False
                for existing_shop_id in existing_shops:
                    existing_shop = Shop.objects(id=ObjectId(existing_shop_id)).first()
                    if existing_shop and existing_shop.location_lat and existing_shop.location_lon:
                        distance = calculate_distance(
                            existing_shop.location_lat, existing_shop.location_lon,
                            new_shop.location_lat, new_shop.location_lon
                        )
                        if distance <= 1.0:
                            within_radius = True
                            break
                
                if not within_radius:
                    proximity_warning = {
                        'message': f'{new_shop.name} is more than 1km away from other shops in your cart. Separate delivery charges will apply.',
                        'within_radius': False
                    }
            
            # Add new item
            cart.items.append({
                'product_id': product_id,
                'product_name': product.name,
                'shop_id': str(new_shop.id),
                'shop_name': new_shop.name,
                'quantity': quantity,
                'price': product.price,
                'total_price': product.price * quantity
            })
        
        # Recalculate total
        cart.total_amount = sum(item['total_price'] for item in cart.items)
        cart.updated_at = datetime.utcnow()
        cart.save()
        
        response_data = {
            'message': 'Product added to cart',
            'cart': {
                'items_count': len(cart.items),
                'total_amount': cart.total_amount
            }
        }
        
        # Include proximity warning if applicable
        if 'proximity_warning' in locals() and proximity_warning:
            response_data['proximity_warning'] = proximity_warning
        
        return jsonify(response_data)
    except Exception as e:
        print(f"Error adding to cart: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'message': 'Failed to add to cart'}), 500


@shop_bp.get('/api/cart')
@jwt_required()
def get_cart():
    """Get user's cart with shop clusters and delivery charges"""
    try:
        ident = get_jwt_identity()
        user_id = str(ident['id']) if isinstance(ident, dict) else str(ident)
        user = User.objects(id=ObjectId(user_id)).first()
        if not user:
            return jsonify({'message': 'User not found'}), 404
        
        # Get user location from request (optional)
        user_lat = request.args.get('user_lat', type=float) or user.latitude
        user_lon = request.args.get('user_lon', type=float) or user.longitude
        
        cart = Cart.objects(user=user).first()
        if not cart:
            return jsonify({
                'items': [],
                'total_amount': 0.0,
                'items_count': 0,
                'shop_clusters': [],
                'total_delivery_charge': 0.0
            })
        
        # Enrich items with product and shop details
        shops_dict = {}  # shop_id -> shop data
        enriched_items = []
        
        for item in cart.items:
            product_id = item.get('product_id')
            shop_id = item.get('shop_id')
            
            if product_id:
                product = Product.objects(id=ObjectId(product_id)).first()
                if product:
                    item['product_image'] = url_for('static', filename=product.image_path, _external=True) if product.image_path else None
                    item['product_description'] = product.description
            
            # Get shop details if not already fetched
            if shop_id and shop_id not in shops_dict:
                shop = Shop.objects(id=ObjectId(shop_id)).first()
                if shop:
                    shops_dict[shop_id] = {
                        'shop_id': shop_id,
                        'shop_name': shop.name,
                        'shop_lat': shop.location_lat,
                        'shop_lon': shop.location_lon,
                        'shop_address': shop.address
                    }
            
            enriched_items.append(item)
        
        # Group shops by proximity
        shops_data = []
        for shop_id, shop_data in shops_dict.items():
            # Calculate items total for this shop
            shop_items = [item for item in enriched_items if item.get('shop_id') == shop_id]
            items_total = sum(item.get('total_price', 0) for item in shop_items)
            
            shops_data.append({
                'shop_id': shop_id,
                'shop_name': shop_data['shop_name'],
                'shop_lat': shop_data['shop_lat'],
                'shop_lon': shop_data['shop_lon'],
                'shop_address': shop_data['shop_address'],
                'items_total': items_total,
                'items_count': len(shop_items)
            })
        
        # Group shops by proximity (within 1km)
        shop_clusters = group_shops_by_proximity(shops_data, user_lat, user_lon, max_radius_km=1.0)
        
        # Calculate total delivery charge
        total_delivery_charge = sum(cluster.get('delivery_charge', 0) for cluster in shop_clusters)
        
        return jsonify({
            'items': enriched_items,
            'total_amount': cart.total_amount,
            'items_count': len(cart.items),
            'shop_clusters': shop_clusters,
            'total_delivery_charge': round(total_delivery_charge, 2),
            'grand_total': round(cart.total_amount + total_delivery_charge, 2)
        })
    except Exception as e:
        print(f"Error getting cart: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'message': 'Failed to get cart'}), 500


@shop_bp.delete('/api/cart/item/<product_id>')
@jwt_required()
def remove_from_cart(product_id):
    """Remove item from cart"""
    try:
        ident = get_jwt_identity()
        user_id = str(ident['id']) if isinstance(ident, dict) else str(ident)
        user = User.objects(id=ObjectId(user_id)).first()
        if not user:
            return jsonify({'message': 'User not found'}), 404
        
        cart = Cart.objects(user=user).first()
        if not cart:
            return jsonify({'message': 'Cart is empty'}), 404
        
        # Remove item
        cart.items = [item for item in cart.items if item.get('product_id') != product_id]
        
        # Recalculate total
        cart.total_amount = sum(item['total_price'] for item in cart.items)
        cart.updated_at = datetime.utcnow()
        cart.save()
        
        return jsonify({'message': 'Item removed from cart'})
    except Exception as e:
        print(f"Error removing from cart: {e}")
        return jsonify({'message': 'Failed to remove from cart'}), 500


@shop_bp.put('/api/cart/item/<product_id>')
@jwt_required()
def update_cart_item(product_id):
    """Update cart item quantity"""
    try:
        ident = get_jwt_identity()
        user_id = str(ident['id']) if isinstance(ident, dict) else str(ident)
        user = User.objects(id=ObjectId(user_id)).first()
        if not user:
            return jsonify({'message': 'User not found'}), 404
        
        data = request.get_json()
        quantity = int(data.get('quantity', 1))
        
        if quantity <= 0:
            return jsonify({'message': 'Quantity must be positive'}), 400
        
        cart = Cart.objects(user=user).first()
        if not cart:
            return jsonify({'message': 'Cart is empty'}), 404
        
        # Find and update item
        for item in cart.items:
            if item.get('product_id') == product_id:
                product = Product.objects(id=ObjectId(product_id)).first()
                if not product or product.stock_quantity < quantity:
                    return jsonify({'message': 'Insufficient stock'}), 400
                
                item['quantity'] = quantity
                item['total_price'] = quantity * item['price']
                break
        
        # Recalculate total
        cart.total_amount = sum(item['total_price'] for item in cart.items)
        cart.updated_at = datetime.utcnow()
        cart.save()
        
        return jsonify({'message': 'Cart updated'})
    except Exception as e:
        print(f"Error updating cart: {e}")
        return jsonify({'message': 'Failed to update cart'}), 500


# Order Management
@shop_bp.post('/api/orders/create')
@jwt_required()
def create_order():
    """Create order(s) from cart - supports multi-shop orders with distance-based delivery charges"""
    try:
        ident = get_jwt_identity()
        user_id = str(ident['id']) if isinstance(ident, dict) else str(ident)
        user = User.objects(id=ObjectId(user_id)).first()
        if not user:
            return jsonify({'message': 'User not found'}), 404
        
        data = request.get_json()
        shop_ids = data.get('shop_ids')  # Can be single shop_id or list of shop_ids
        delivery_address = data.get('delivery_address')
        delivery_lat = data.get('delivery_lat')
        delivery_lon = data.get('delivery_lon')
        contact_phone = data.get('contact_phone')
        payment_method = data.get('payment_method', 'Razorpay')
        
        # Support both single shop_id (backward compatibility) and list of shop_ids
        if shop_ids and isinstance(shop_ids, str):
            shop_ids = [shop_ids]
        elif not shop_ids:
            # Try old format for backward compatibility
            shop_id = data.get('shop_id')
            if shop_id:
                shop_ids = [shop_id]
        
        if not all([shop_ids, delivery_address, delivery_lat, delivery_lon, contact_phone]):
            return jsonify({'message': 'Missing required fields'}), 400
        
        # Get cart
        cart = Cart.objects(user=user).first()
        if not cart or not cart.items:
            return jsonify({'message': 'Cart is empty'}), 400
        
        # Filter cart items for requested shops
        shop_items_dict = {}  # shop_id -> items list
        for shop_id in shop_ids:
            shop_items = [item for item in cart.items if item.get('shop_id') == shop_id]
            if shop_items:
                shop_items_dict[shop_id] = shop_items
        
        if not shop_items_dict:
            return jsonify({'message': 'No items from requested shops in cart'}), 400
        
        # Get shop details and validate
        shops_data = []
        for shop_id, items in shop_items_dict.items():
            shop = Shop.objects(id=ObjectId(shop_id)).first()
            if not shop:
                return jsonify({'message': f'Shop {shop_id} not found'}), 404
            
            # Check if shop is verified
            is_shop_verified = (shop.verification_status == 'verified') or bool(shop.is_verified)
            if not is_shop_verified:
                return jsonify({
                    'message': f'Shop {shop.name} is not verified',
                    'details': 'This shop is not verified yet and cannot receive orders.'
                }), 403
            
            # Verify stock availability
            for item in items:
                product = Product.objects(id=ObjectId(item['product_id'])).first()
                if not product or product.stock_quantity < item['quantity']:
                    return jsonify({
                        'message': f'Insufficient stock for {item.get("product_name", "product")} in {shop.name}'
                    }), 400
            
            shops_data.append({
                'shop_id': shop_id,
                'shop': shop,
                'items': items,
                'shop_lat': shop.location_lat,
                'shop_lon': shop.location_lon
            })
        
        # Group shops by proximity (within 1km)
        shops_grouped = []
        for shop_data in shops_data:
            shops_grouped.append({
                'shop_id': shop_data['shop_id'],
                'shop_name': shop_data['shop'].name,
                'shop_lat': shop_data['shop_lat'],
                'shop_lon': shop_data['shop_lon'],
                'items_total': sum(item['total_price'] for item in shop_data['items'])
            })
        
        shop_clusters = group_shops_by_proximity(
            shops_grouped, 
            float(delivery_lat), 
            float(delivery_lon), 
            max_radius_km=1.0
        )
        
        # Create orders for each shop cluster
        created_orders = []
        shop_cluster_map = {}  # shop_id -> cluster info
        
        for cluster in shop_clusters:
            cluster_id = cluster.get('cluster_id', f"cluster_{datetime.utcnow().timestamp()}")
            cluster_delivery_charge = cluster.get('delivery_charge', 50.0)
            is_shared = len(cluster.get('shops', [])) > 1
            
            # If shared delivery, split delivery charge equally among shops
            if is_shared:
                shops_in_cluster = cluster.get('shops', [])
                delivery_per_shop = cluster_delivery_charge / len(shops_in_cluster)
            else:
                delivery_per_shop = cluster_delivery_charge
            
            for shop_in_cluster in cluster.get('shops', []):
                shop_id = shop_in_cluster['shop_id']
                shop_cluster_map[shop_id] = {
                    'cluster_id': cluster_id,
                    'delivery_charge': delivery_per_shop,
                    'is_shared': is_shared
                }
        
        # Create orders for each shop
        for shop_data in shops_data:
            shop_id = shop_data['shop_id']
            shop = shop_data['shop']
            items = shop_data['items']
            
            cluster_info = shop_cluster_map.get(shop_id, {
                'cluster_id': f"cluster_{shop_id}",
                'delivery_charge': calculate_delivery_charge(
                    shop_data['shop_lat'], shop_data['shop_lon'],
                    float(delivery_lat), float(delivery_lon)
                ),
                'is_shared': False
            })
            
            # Calculate total (items + delivery)
            items_total = sum(item['total_price'] for item in items)
            delivery_charge = cluster_info['delivery_charge']
            total_amount = items_total + delivery_charge
            
            # Create order
            order = Order(
                user=user,
                shop=shop,
                items=items,
                total_amount=total_amount,
                delivery_charge=delivery_charge,
                delivery_address=delivery_address,
                delivery_lat=float(delivery_lat),
                delivery_lon=float(delivery_lon),
                contact_phone=contact_phone,
                payment_method=payment_method,
                shop_cluster_id=cluster_info['cluster_id'],
                is_shared_delivery=cluster_info['is_shared'],
                status='pending',
                payment_status='pending'
            )
            order.save()
            
            # Update stock
            for item in items:
                product = Product.objects(id=ObjectId(item['product_id'])).first()
                if product:
                    product.stock_quantity -= item['quantity']
                    if product.stock_quantity <= 0:
                        product.is_available = False
                    product.save()
            
            created_orders.append({
                'order_id': str(order.id),
                'shop_id': shop_id,
                'shop_name': shop.name,
                'items_total': items_total,
                'delivery_charge': delivery_charge,
                'total_amount': total_amount
            })
        
        # Remove ordered items from cart
        ordered_shop_ids = set(shop_ids)
        cart.items = [item for item in cart.items if item.get('shop_id') not in ordered_shop_ids]
        cart.total_amount = sum(item['total_price'] for item in cart.items)
        cart.save()
        
        return jsonify({
            'message': 'Orders created successfully',
            'orders': created_orders,
            'total_orders': len(created_orders),
            'grand_total': sum(o['total_amount'] for o in created_orders)
        }), 201
    except Exception as e:
        print(f"Error creating order: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'message': 'Failed to create order'}), 500


@shop_bp.get('/api/orders/<order_id>/summary')
@jwt_required()
def get_order_summary(order_id):
    """Get detailed order summary for order confirmation page"""
    try:
        ident = get_jwt_identity()
        user_id = str(ident['id']) if isinstance(ident, dict) else str(ident)
        user = User.objects(id=ObjectId(user_id)).first()
        if not user:
            return jsonify({'message': 'User not found'}), 404
        
        order = Order.objects(id=ObjectId(order_id)).first()
        if not order:
            return jsonify({'message': 'Order not found'}), 404
        
        # Verify user owns this order
        if str(order.user.id) != user_id:
            return jsonify({'message': 'Unauthorized'}), 403
        
        # Get shop details
        shop_data = None
        if order.shop:
            shop = order.shop
            shop_data = {
                'id': str(shop.id),
                'name': shop.name,
                'address': shop.address,
                'location_lat': shop.location_lat,
                'location_lon': shop.location_lon,
                'contact_phone': shop.contact_phone
            }
        
        # Get delivery partner details
        delivery_partner_data = None
        if order.delivery_partner:
            partner = order.delivery_partner
            delivery_partner_data = {
                'id': str(partner.id),
                'name': partner.user.name if partner.user else 'N/A',
                'phone': partner.user.phone if partner.user else 'N/A',
                'vehicle_number': partner.vehicle_number or 'N/A'
            }
        
        # Calculate totals
        items_total = sum(item.get('total_price', item.get('price', 0)) for item in order.items)
        delivery_charge = float(order.delivery_charge or 0)
        total_amount = float(order.total_amount or 0)
        
        return jsonify({
            'order_id': str(order.id),
            'status': order.status,
            'items': order.items,
            'items_total': items_total,
            'delivery_charge': delivery_charge,
            'total_amount': total_amount,
            'delivery_address': order.delivery_address,
            'delivery_lat': order.delivery_lat,
            'delivery_lon': order.delivery_lon,
            'contact_phone': order.contact_phone,
            'payment_status': order.payment_status,
            'payment_method': order.payment_method,
            'shop': shop_data,
            'delivery_partner': delivery_partner_data,
            'created_at': order.created_at.isoformat() if order.created_at else None,
            'confirmed_at': order.confirmed_at.isoformat() if order.confirmed_at else None,
            'delivered_at': order.delivered_at.isoformat() if order.delivered_at else None,
            'pending_at': order.created_at.isoformat() if order.created_at else None,
            'preparing_at': None,  # Can be added later
            'ready_at': None,  # Can be added later
            'assigned_at': order.confirmed_at.isoformat() if order.delivery_partner and order.confirmed_at else None,
            'out_for_delivery_at': None  # Can be added later
        })
    except Exception as e:
        print(f"Error getting order summary: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'message': 'Failed to get order summary'}), 500


@shop_bp.get('/api/orders')
@jwt_required()
def get_orders():
    """Get user's orders"""
    try:
        ident = get_jwt_identity()
        user_id = str(ident['id']) if isinstance(ident, dict) else str(ident)
        user = User.objects(id=ObjectId(user_id)).first()
        if not user:
            return jsonify({'message': 'User not found'}), 404
        
        orders = Order.objects(user=user).order_by('-created_at')
        orders_list = []
        for o in orders:
            order_data = {
                'id': str(o.id),
                'shop_name': o.shop.name if o.shop else 'Shop',
                'items': o.items,
                'total_amount': o.total_amount,
                'status': o.status,
                'payment_status': o.payment_status,
                'payment_method': o.payment_method,
                'delivery_address': o.delivery_address,
                'contact_phone': o.contact_phone,
                'created_at': o.created_at.isoformat() if o.created_at else None,
                'confirmed_at': o.confirmed_at.isoformat() if o.confirmed_at else None,
                'delivered_at': o.delivered_at.isoformat() if o.delivered_at else None
            }
            
            # Add delivery partner info if assigned
            if o.delivery_partner:
                order_data['delivery_partner'] = {
                    'name': o.delivery_partner.user.name if o.delivery_partner.user else 'N/A',
                    'phone': o.delivery_partner.user.phone if o.delivery_partner.user else 'N/A',
                    'vehicle_type': o.delivery_partner.vehicle_type,
                    'vehicle_number': o.delivery_partner.vehicle_number,
                    'rating': o.delivery_partner.rating
                }
            
            orders_list.append(order_data)
        
        return jsonify(orders_list)
    except Exception as e:
        print(f"Error getting orders: {e}")
        return jsonify({'message': 'Failed to get orders'}), 500


@shop_bp.get('/api/orders/<order_id>')
@jwt_required()
def get_order_detail(order_id):
    """Get details of a specific order"""
    try:
        ident = get_jwt_identity()
        user_id = str(ident['id']) if isinstance(ident, dict) else str(ident)
        user = User.objects(id=ObjectId(user_id)).first()
        if not user:
            return jsonify({'message': 'User not found'}), 404
        
        order = Order.objects(id=ObjectId(order_id), user=user).first()
        if not order:
            return jsonify({'message': 'Order not found'}), 404
        
        order_data = {
            'id': str(order.id),
            'shop_name': order.shop.name if order.shop else 'Shop',
            'items': order.items,
            'total_amount': order.total_amount,
            'status': order.status,
            'payment_status': order.payment_status,
            'payment_method': order.payment_method,
            'delivery_address': order.delivery_address,
            'contact_phone': order.contact_phone,
            'created_at': order.created_at.isoformat() if order.created_at else None,
            'confirmed_at': order.confirmed_at.isoformat() if order.confirmed_at else None,
            'delivered_at': order.delivered_at.isoformat() if order.delivered_at else None
        }
        
        # Add delivery partner info if assigned
        if order.delivery_partner:
            order_data['delivery_partner'] = {
                'name': order.delivery_partner.user.name if order.delivery_partner.user else 'N/A',
                'phone': order.delivery_partner.user.phone if order.delivery_partner.user else 'N/A',
                'vehicle_type': order.delivery_partner.vehicle_type,
                'vehicle_number': order.delivery_partner.vehicle_number,
                'rating': order.delivery_partner.rating
            }
        
        return jsonify(order_data)
    except Exception as e:
        print(f"Error getting order detail: {e}")
        return jsonify({'message': 'Failed to get order details'}), 500


@shop_bp.get('/api/shop/orders')
@jwt_required()
def get_shop_orders():
    """Get orders for shopkeeper's shop"""
    try:
        ident = get_jwt_identity()
        user_id = str(ident['id']) if isinstance(ident, dict) else str(ident)
        user = User.objects(id=ObjectId(user_id)).first()
        if not user:
            return jsonify({'message': 'User not found'}), 404
        
        shop = Shop.objects(owner=user).first()
        if not shop:
            return jsonify({'message': 'Shop not found'}), 404
        
        orders = Order.objects(shop=shop).order_by('-created_at')
        orders_list = [{
            'id': str(o.id),
            'user_name': o.user.name,
            'items': o.items,
            'total_amount': o.total_amount,
            'status': o.status,
            'payment_status': o.payment_status,
            'delivery_address': o.delivery_address,
            'contact_phone': o.contact_phone,
            'created_at': o.created_at.isoformat() if o.created_at else None
        } for o in orders]
        
        return jsonify(orders_list)
    except Exception as e:
        print(f"Error getting shop orders: {e}")
        return jsonify({'message': 'Failed to get orders'}), 500


@shop_bp.put('/api/shop/orders/<order_id>/status')
@jwt_required()
def update_order_status(order_id):
    """Update order status (shopkeeper)"""
    try:
        ident = get_jwt_identity()
        user_id = str(ident['id']) if isinstance(ident, dict) else str(ident)
        user = User.objects(id=ObjectId(user_id)).first()
        if not user:
            return jsonify({'message': 'User not found'}), 404
        
        shop = Shop.objects(owner=user).first()
        if not shop:
            return jsonify({'message': 'Shop not found'}), 404
        
        order = Order.objects(id=ObjectId(order_id), shop=shop).first()
        if not order:
            return jsonify({'message': 'Order not found'}), 404
        
        data = request.get_json()
        new_status = data.get('status')
        
        if new_status not in ['pending', 'confirmed', 'preparing', 'ready', 'assigned', 'out_for_delivery', 'delivered', 'cancelled']:
            return jsonify({'message': 'Invalid status'}), 400
        
        order.status = new_status
        if new_status == 'confirmed':
            order.confirmed_at = datetime.utcnow()
        elif new_status == 'delivered':
            order.delivered_at = datetime.utcnow()
            shop.total_orders += 1
            shop.save()
        
        order.save()
        return jsonify({'message': 'Order status updated'})
    except Exception as e:
        print(f"Error updating order status: {e}")
        return jsonify({'message': 'Failed to update order status'}), 500


# Delivery Partner Assignment
@shop_bp.post('/api/orders/<order_id>/assign-delivery')
@jwt_required()
def assign_delivery_partner(order_id):
    """Assign delivery partner to order"""
    try:
        ident = get_jwt_identity()
        user_id = str(ident['id']) if isinstance(ident, dict) else str(ident)
        user = User.objects(id=ObjectId(user_id)).first()
        if not user or user.role != 'admin':
            return jsonify({'message': 'Admin only'}), 403
        
        order = Order.objects(id=ObjectId(order_id)).first()
        if not order:
            return jsonify({'message': 'Order not found'}), 404
        
        if order.status != 'ready':
            return jsonify({'message': 'Order must be ready before assigning delivery'}), 400
        
        # Find nearest available delivery partner
        delivery_partners = DeliveryPartner.objects(is_available=True)
        if not delivery_partners:
            return jsonify({'message': 'No delivery partners available'}), 404
        
        # Find nearest partner
        nearest_partner = None
        min_distance = float('inf')
        
        for partner in delivery_partners:
            if partner.current_location_lat and partner.current_location_lon:
                distance = calculate_distance(
                    partner.current_location_lat, partner.current_location_lon,
                    order.delivery_lat, order.delivery_lon
                )
                if distance < min_distance:
                    min_distance = distance
                    nearest_partner = partner
        
        if not nearest_partner:
            return jsonify({'message': 'No delivery partner found'}), 404
        
        # Assign partner
        order.delivery_partner = nearest_partner
        order.status = 'assigned'
        order.save()
        
        nearest_partner.is_available = False
        nearest_partner.save()
        
        return jsonify({
            'message': 'Delivery partner assigned',
            'partner_id': str(nearest_partner.id),
            'partner_name': nearest_partner.user.name
        })
    except Exception as e:
        print(f"Error assigning delivery partner: {e}")
        return jsonify({'message': 'Failed to assign delivery partner'}), 500

