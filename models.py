from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from datetime import datetime
import json

db = SQLAlchemy()

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    is_admin = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class GamePlayer(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    card = db.Column(db.Text, nullable=False)
    card_number = db.Column(db.Integer)
    game_round = db.Column(db.Integer, default=1)
    disqualified = db.Column(db.Boolean, default=False)
    claim_time = db.Column(db.DateTime)
    
    user = db.relationship('User', backref='game_links')

class Win(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    game_round = db.Column(db.Integer)
    claimed_at = db.Column(db.DateTime, default=datetime.utcnow)
