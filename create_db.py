from app import app, db
from app import User  
with app.app_context():
    db.create_all()
    print("Database tables created.")
