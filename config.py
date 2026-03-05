import os

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production')
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL', 'sqlite:///bingo.db')
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    ENTRY_FEE = 10.00
    PRIZE_PERCENT = 0.80
    DRAW_INTERVAL = 2
    WINNER_WAIT_SECONDS = 3
    
    RATE_LIMIT = 10
    SESSION_TYPE = 'filesystem'
    
    REDIS_URL = os.environ.get('REDIS_URL', 'redis://localhost:6379/0')