from app import app
from models import db, User
from werkzeug.security import generate_password_hash

with app.app_context():
    admin = User.query.filter_by(username='admin').first()
    if not admin:
        admin = User(
            username='admin',
            email='wondiradbeziemitikuhulu2@gmail.com',
            password_hash=generate_password_hash('BirtplasWond204695$'),
            balance=0,
            is_admin=True
        )
        db.session.add(admin)
        db.session.commit()
        print("✅ Admin created successfully!")
        print("Username: admin")
        print("Password: BirtplasWond204695$")
    else:
        print("✅ Admin already exists")
