import os
import sys
from datetime import timedelta
from flask import Flask, render_template, redirect, url_for, jsonify, request
from flask_cors import CORS
from flask_socketio import join_room
from extensions import jwt, bcrypt, socketio, init_mongodb
from models import User, Service


def create_app():
    app = Flask(__name__, static_folder='static', static_url_path='/static')

    app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'dev-secret')
    app.config['JWT_SECRET_KEY'] = os.getenv('JWT_SECRET_KEY', 'dev-jwt-secret')
    app.config['JWT_ACCESS_TOKEN_EXPIRES'] = timedelta(days=7)
    app.config['JWT_TOKEN_LOCATION'] = ['cookies', 'headers']
    
    # Production security settings
    is_production = os.getenv('FLASK_ENV') == 'production'
    app.config['JWT_COOKIE_SECURE'] = is_production  # HTTPS only in production
    app.config['JWT_COOKIE_CSRF_PROTECT'] = is_production  # CSRF protection in production
    app.config['JWT_COOKIE_SAMESITE'] = 'Lax'

    # Init extensions
    CORS(app)
    init_mongodb()  # Initialize MongoDB connection
    jwt.init_app(app)
    bcrypt.init_app(app)
    # SocketIO configuration for production
    redis_url = os.getenv('REDIS_URL')
    if redis_url and is_production:
        socketio.init_app(app, async_mode='gevent', cors_allowed_origins="*", 
                         message_queue=redis_url)
    else:
        socketio.init_app(app, async_mode='threading', cors_allowed_origins="*")

    # WebSocket event handlers
    @socketio.on('join_provider_room')
    def on_join_provider_room(data):
        from flask_jwt_extended import decode_token
        try:
            token = data.get('token')
            if token:
                decoded_token = decode_token(token)
                user_id = decoded_token.get('sub', {}).get('id') or decoded_token.get('sub')
                join_room(f'provider_{user_id}')
                print(f'Provider {user_id} joined their room')
        except Exception as e:
            print(f'Error joining provider room: {e}')

    @socketio.on('join_user_room')
    def on_join_user_room(data):
        from flask_jwt_extended import decode_token
        try:
            token = data.get('token')
            if token:
                decoded_token = decode_token(token)
                user_id = decoded_token.get('sub', {}).get('id') or decoded_token.get('sub')
                join_room(f'user_{user_id}')
                print(f'User {user_id} joined their room')
        except Exception as e:
            print(f'Error joining user room: {e}')

    # Register blueprints
    from routes.auth import auth_bp
    from routes.booking import booking_bp
    from routes.provider import provider_bp
    from routes.service import service_bp
    from routes.feedback import feedback_bp
    from routes.completion import completion_bp
    from routes.dashboard import dashboard_bp
    from routes.payment import payment_bp
    from routes.firebase_auth import firebase_auth_bp
    from routes.admin import admin_bp
    from routes.service_request import service_request_bp
    from routes.shop import shop_bp
    from routes.wallet import wallet_bp
    from routes.verification import verification_bp

    app.register_blueprint(auth_bp, url_prefix='/')
    app.register_blueprint(booking_bp, url_prefix='/')
    app.register_blueprint(provider_bp, url_prefix='/')
    app.register_blueprint(service_bp, url_prefix='/')
    app.register_blueprint(feedback_bp, url_prefix='/')
    app.register_blueprint(completion_bp, url_prefix='/')
    app.register_blueprint(dashboard_bp, url_prefix='/')
    app.register_blueprint(payment_bp, url_prefix='/')
    app.register_blueprint(service_request_bp, url_prefix='/')
    app.register_blueprint(firebase_auth_bp, url_prefix='/')
    app.register_blueprint(admin_bp, url_prefix='/')
    app.register_blueprint(shop_bp, url_prefix='/')
    app.register_blueprint(wallet_bp, url_prefix='/')
    app.register_blueprint(verification_bp, url_prefix='/')

    @app.route('/')
    def home():
        return render_template('home.html')
    
    @app.route('/about')
    def about():
        return render_template('about.html')
    
    @app.route('/support')
    def support():
        return render_template('support.html')
    
    @app.route('/policy')
    def policy():
        return render_template('policy.html')
    
    @app.route('/orders')
    def orders():
        return render_template('orders.html')
    
    @app.route('/order/summary')
    def order_summary():
        return render_template('order_summary.html')

    # Public shops listing for homepage ads
    @app.route('/public/shops')
    def public_shops():
        try:
            from models import ShopAd
            limit = int(request.args.get('limit', 8))
            shops = ShopAd.objects(is_active=True).order_by('-priority', '-created_at').limit(limit)
            result = []
            for s in shops:
                image_url = None
                if s.image_path:
                    image_url = request.url_root.rstrip('/') + '/' + os.path.join('static', s.image_path).replace('\\','/')
                result.append({
                    'id': str(s.id),
                    'name': s.name,
                    'category': s.category,
                    'address': s.address,
                    'contact_phone': s.contact_phone,
                    'contact_email': s.contact_email,
                    'website': s.website,
                    'image_url': image_url
                })
            return jsonify(result)
        except Exception as e:
            return jsonify([])

    @app.route('/shop')
    def shop_page():
        return render_template('shop.html')
    
    @app.route('/shop/category/<category>')
    def shop_category_page(category):
        return render_template('shop_category.html', category=category)
    
    @app.route('/shop/dashboard')
    def shop_dashboard_page():
        return render_template('shop_dashboard.html')
    
    @app.route('/verification/provider')
    def provider_verification_page():
        return render_template('provider_verification.html')
    
    @app.route('/verification/shopkeeper')
    def shopkeeper_verification_page():
        return render_template('shopkeeper_verification.html')

    @app.route('/booking-map')
    def booking_map_page():
        return render_template('booking_map.html')

    @app.route('/track-provider')
    def track_provider_page():
        return render_template('track_provider.html')
    
    @app.route('/test-tracking')
    def test_tracking_page():
        return render_template('test_tracking.html')
    
    @app.route('/provider/navigation')
    def provider_navigation_page():
        return render_template('provider_navigation.html')
    
    @app.route('/simulate-movement', methods=['POST'])
    def simulate_movement():
        try:
            import subprocess
            import threading
            
            def run_simulation():
                subprocess.run([sys.executable, 'simulate_provider_movement.py'], 
                             cwd=os.path.dirname(os.path.abspath(__file__)))
            
            # Run simulation in background
            thread = threading.Thread(target=run_simulation)
            thread.daemon = True
            thread.start()
            
            return jsonify({'success': True, 'message': 'Simulation started'})
        except Exception as e:
            return jsonify({'success': False, 'message': str(e)})

    @app.route('/dashboard')
    def dashboard_redirect():
        return redirect(url_for('auth.login_page'))

    # Socket events
    @socketio.on('connect')
    def on_connect():
        print('Client connected')
    
    @socketio.on('disconnect')
    def on_disconnect():
        print('Client disconnected')
    
    @socketio.on('join')
    def on_join(data):
        try:
            room = data.get('room')
            if room:
                join_room(room)
                print(f'Client joined room: {room}')
        except Exception as e:
            print(f'Error in join event: {e}')
    
    @socketio.on('join_provider_room')
    def on_join_provider_room(data):
        try:
            provider_id = data.get('provider_id')
            print(f'=== PROVIDER JOINING ROOM ===')
            print(f'Provider ID received: {provider_id}')
            print(f'Data received: {data}')
            if provider_id:
                room_name = f"provider_{provider_id}"
                join_room(room_name)
                join_room('all_providers')
                print(f'Provider {provider_id} joined rooms: {room_name}, all_providers')
            else:
                print('No provider_id provided')
        except Exception as e:
            print(f'Error in join_provider_room event: {e}')
    
    @socketio.on('join_booking_room')
    def on_join_booking_room(data):
        try:
            booking_id = data.get('booking_id')
            if booking_id:
                join_room(f"booking_{booking_id}")
                print(f'Client joined booking room: {booking_id}')
        except Exception as e:
            print(f'Error in join_booking_room event: {e}')
    
    # Chat events
    @socketio.on('chat_message')
    def handle_chat_message(data):
        try:
            from models import ChatMessage, Booking, User
            from bson import ObjectId
            
            booking_id = data.get('booking_id')
            sender_id = data.get('sender_id')
            sender_type = data.get('sender_type')
            message_type = data.get('type')
            content = data.get('content', '')
            
            # Get booking and user
            booking = Booking.objects(id=ObjectId(booking_id)).first()
            user = User.objects(id=ObjectId(sender_id)).first()
            
            if not booking or not user:
                return
            
            # Create message
            message = ChatMessage(
                booking=booking,
                sender=user,
                sender_type=sender_type,
                message_type=message_type,
                content=content,
                booking_id=booking_id,
                status='sent'
            )
            
            # Set names
            if sender_type == 'user':
                message.customer_name = user.name
                if booking.provider:
                    message.provider_name = booking.provider.user.name
                    message.provider_id = str(booking.provider.id)
            else:
                message.provider_name = user.name
                message.provider_id = str(booking.provider.id) if booking.provider else None
                message.customer_name = booking.user.name
            
            message.save()
            
            # Emit to booking room
            socketio.emit('new_message', {
                'id': str(message.id),
                'booking_id': booking_id,
                'sender_type': sender_type,
                'sender_name': message.customer_name if sender_type == 'user' else message.provider_name,
                'type': message_type,
                'content': content,
                'timestamp': message.created_at.isoformat()
            }, room=f"booking_{booking_id}")
            
            # Emit to provider room if message is from user
            if sender_type == 'user' and booking.provider:
                socketio.emit('new_message', {
                    'id': str(message.id),
                    'booking_id': booking_id,
                    'sender_type': sender_type,
                    'sender_name': message.customer_name,
                    'type': message_type,
                    'content': content,
                    'timestamp': message.created_at.isoformat()
                }, room=f"provider_{booking.provider.id}")
            
        except Exception as e:
            print(f'Error in chat_message event: {e}')
    
    @socketio.on('typing_start')
    def handle_typing_start(data):
        try:
            booking_id = data.get('booking_id')
            sender_type = data.get('sender_type')
            sender_name = data.get('sender_name')
            
            socketio.emit('user_typing', {
                'booking_id': booking_id,
                'sender_type': sender_type,
                'sender_name': sender_name
            }, room=f"booking_{booking_id}")
        except Exception as e:
            print(f'Error in typing_start event: {e}')
    
    @socketio.on('typing_stop')
    def handle_typing_stop(data):
        try:
            booking_id = data.get('booking_id')
            sender_type = data.get('sender_type')
            
            socketio.emit('user_stopped_typing', {
                'booking_id': booking_id,
                'sender_type': sender_type
            }, room=f"booking_{booking_id}")
        except Exception as e:
            print(f'Error in typing_stop event: {e}')

    # Seed minimal services and demo shops if empty
    with app.app_context():
        try:
            if Service.objects.count() == 0:
                services = [
                    Service(name='Electrician', category='Electrical', base_price=20.0),
                    Service(name='Plumber', category='Plumbing', base_price=18.0),
                    Service(name='Carpenter', category='Woodwork', base_price=22.0),
                    Service(name='Cleaner', category='Cleaning', base_price=15.0),
                ]
                for service in services:
                    service.save()
            # Seed demo shops for homepage if none exist
            from models import ShopAd
            if ShopAd.objects.count() == 0:
                demo_shops = [
                    ShopAd(name='Sharma Hardware', category='hardware', address='MG Road, Gurgaon', contact_phone='+91 98765 43210', priority=5, is_active=True),
                    ShopAd(name='Bright Electricals', category='electricals', address='Sector 14, Gurgaon', contact_phone='+91 99887 66554', priority=4, is_active=True)
                ]
                for s in demo_shops:
                    s.save()
        except Exception as e:
            print(f"Error seeding services: {e}")

    return app


app = create_app()


if __name__ == '__main__':
    port = int(os.getenv('PORT', 5000))
    socketio.run(app, host='0.0.0.0', port=port)
