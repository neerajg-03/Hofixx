from app import create_app
from flask_bcrypt import Bcrypt
from datetime import datetime
import time

app = create_app()
bcrypt = Bcrypt()

with app.app_context():
    try:
        # Use raw MongoDB connection to avoid index issues
        from mongoengine import get_db
        db = get_db()
        users_coll = db.users
        
        # Check if admin already exists
        existing_admin = users_coll.find_one({'email': 'admin@hofix.com'})
        
        if existing_admin:
            print("✅ Admin user already exists!")
            print(f"📧 Email: {existing_admin['email']}")
            print("🔑 You can login with this account")
            print("\n📋 Login Instructions:")
            print("1. Go to http://localhost:5000/login (or your deployed URL)")
            print("2. Enter email: admin@hofix.com")
            print("3. Enter password: admin123")
            print("4. After login, you can access /admin for admin dashboard")
        else:
            # Generate unique phone number using timestamp
            unique_phone = f"9{int(time.time()) % 1000000000:09d}"
            
            # Create admin user
            password_hash = bcrypt.generate_password_hash('admin123').decode('utf-8')
            admin_doc = {
                'name': 'Admin User',
                'email': 'admin@hofix.com',
                'phone': unique_phone,
                'role': 'admin',
                'password_hash': password_hash,
                'created_at': datetime.utcnow(),
                'credits': 0.0,
                'rating': 5.0
            }
            
            users_coll.insert_one(admin_doc)
            print("✅ Admin user created successfully!")
            print("📧 Email: admin@hofix.com")
            print("🔑 Password: admin123")
            print("\n📋 Login Instructions:")
            print("1. Go to http://localhost:5000/login (or your deployed URL)")
            print("2. Enter email: admin@hofix.com")
            print("3. Enter password: admin123")
            print("4. After login, you can access /admin for admin dashboard")
            
    except Exception as e:
        print(f"❌ Error creating admin user: {e}")
        print("\n💡 Alternative Method:")
        print("You can also create an admin user through the signup API:")
        print("1. Make a POST request to /signup with:")
        print("   - name: 'Admin User'")
        print("   - email: 'admin@hofix.com'")
        print("   - phone: 'any-unique-phone-number'")
        print("   - password: 'admin123'")
        print("   - role: 'admin'")
