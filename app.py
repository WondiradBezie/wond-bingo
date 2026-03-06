from flask import Flask, render_template, request, jsonify, redirect, url_for, flash
from flask_socketio import SocketIO, emit
from flask_login import LoginManager, login_required, current_user, login_user, logout_user
from flask_cors import CORS
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
import json
import re
import threading
import time
import os
import random
from datetime import datetime

# ============================================
# APP CONFIGURATION
# ============================================
app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'simple-dev-key')
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///bingo.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

from models import db, User, GamePlayer, Win
db.init_app(app)

CORS(app)
# NO EVENTLET! Using threading instead
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# Admin decorator
def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_admin:
            flash('Admin access required')
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    return decorated_function

# ============================================
# BINGO GAME CLASS
# ============================================
class BingoGame:
    def __init__(self, socketio):
        self.socketio = socketio
        self.current_game = None
        self.game_lock = threading.Lock()
        self.pending_winners = []
        self.winner_timeout = None
        self.drawn_numbers = []
        self.game_running = False
        self.round_number = 1
        self.stop_drawing = False
        self.draw_thread = None
        self.start_draw_thread()
        
    def start_draw_thread(self):
        """Start the background thread for drawing numbers"""
        self.stop_drawing = False
        self.draw_thread = threading.Thread(target=self.auto_draw_loop)
        self.draw_thread.daemon = True
        self.draw_thread.start()
    
    def auto_draw_loop(self):
        """Background loop to draw numbers every 2 seconds"""
        while not self.stop_drawing:
            time.sleep(2)
            if self.game_running:
                number = self.draw_number()
                if number:
                    self.socketio.emit('number_drawn', {'number': number})
    
    def generate_card(self):
        """Generate a random bingo card"""
        card = []
        ranges = [(1, 15), (16, 30), (31, 45), (46, 60), (61, 75)]
        for col_range in ranges:
            column_numbers = random.sample(range(col_range[0], col_range[1] + 1), 5)
            card.append(column_numbers)
        card = list(map(list, zip(*card)))
        card[2][2] = "FREE"
        return card
    
    def check_win(self, card, drawn_numbers):
        """Check if card has won"""
        called = set(str(n) for n in drawn_numbers)
        called.add("FREE")
        str_card = [[str(cell) for cell in row] for row in card]
        
        # Check rows
        for row in str_card:
            if all(cell in called for cell in row):
                return True
        
        # Check columns
        for col in range(5):
            if all(str_card[row][col] in called for row in range(5)):
                return True
        
        # Check diagonals
        if all(str_card[i][i] in called for i in range(5)):
            return True
        if all(str_card[i][4-i] in called for i in range(5)):
            return True
        
        # Check corners
        corners = [str_card[0][0], str_card[0][4], str_card[4][0], str_card[4][4]]
        if all(c in called for c in corners):
            return True
        
        return False
    
    def start_new_round(self):
        """Start a new game round"""
        with self.game_lock:
            self.round_number += 1
            self.drawn_numbers = []
            self.pending_winners = []
            self.game_running = True
            print(f"Started new round #{self.round_number}")
    
    def add_player(self, user_id, card_number=None):
        """Add a player to the game"""
        with self.game_lock:
            # Check if player already in this round
            existing = GamePlayer.query.filter_by(
                user_id=user_id,
                game_round=self.round_number
            ).first()
            
            if existing:
                return True, json.loads(existing.card)
            
            # Generate new card
            card = self.generate_card()
            game_player = GamePlayer(
                user_id=user_id,
                card=json.dumps(card),
                card_number=card_number,
                game_round=self.round_number
            )
            db.session.add(game_player)
            db.session.commit()
            return True, card
    
    def draw_number(self):
        """Draw a new number"""
        with self.game_lock:
            if not self.game_running:
                return None
            
            available = set(range(1, 76)) - set(self.drawn_numbers)
            if not available:
                self.game_running = False
                return None
            
            number = random.choice(list(available))
            self.drawn_numbers.append(number)
            return number
    
    def claim_win(self, user_id):
        """Player claims a win"""
        with self.game_lock:
            if not self.game_running:
                return 'NO_GAME'
            
            player = GamePlayer.query.filter_by(
                user_id=user_id,
                game_round=self.round_number
            ).first()
            
            if not player:
                return 'NOT_PLAYING'
            
            if player.disqualified:
                return 'DISQUALIFIED'
            
            if user_id in self.pending_winners:
                return 'ALREADY_WON'
            
            card = json.loads(player.card)
            if self.check_win(card, self.drawn_numbers):
                self.pending_winners.append(user_id)
                player.claim_time = datetime.utcnow()
                db.session.commit()
                return 'VALID'
            else:
                player.disqualified = True
                db.session.commit()
                return 'DISQUALIFIED'

# ============================================
# CREATE GAME ENGINE
# ============================================
game_engine = BingoGame(socketio)

# ============================================
# ROUTES
# ============================================
@app.route('/')
def index():
    return render_template('game.html')

@app.route('/admin')
@login_required
@admin_required
def admin_panel():
    return render_template('admin.html')

# ============================================
# FIXED LOGIN ROUTE - NOW REDIRECTS TO HOME
# ============================================
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        user = User.query.filter_by(username=username).first()
        if user and check_password_hash(user.password_hash, password):
            login_user(user)
            # IMPORTANT: Redirect to home page after successful login
            return redirect(url_for('index'))
        
        flash('Invalid username or password')
    return render_template('login.html')

# ============================================
# FIXED REGISTER ROUTE - NOW REDIRECTS TO HOME
# ============================================
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        if User.query.filter_by(username=username).first():
            flash('Username exists')
            return redirect(url_for('register'))
        
        user = User(
            username=username,
            password_hash=generate_password_hash(password),
            is_admin=(username == 'admin')
        )
        db.session.add(user)
        db.session.commit()
        login_user(user)
        # IMPORTANT: Redirect to home page after successful registration
        return redirect(url_for('index'))
    
    return render_template('register.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

@app.route('/profile')
@login_required
def profile():
    return render_template('profile.html', user=current_user)

@app.route('/api/balance')
@login_required
def get_balance():
    return jsonify({'balance': 100})  # Default balance for demo

@app.route('/api/join_game', methods=['POST'])
@login_required
def join_game():
    data = request.get_json()
    card_number = data.get('cardNumber')
    
    if not card_number:
        return jsonify({'success': False, 'message': 'Card number required'})
    
    success, result = game_engine.add_player(current_user.id, card_number)
    
    if success:
        return jsonify({'success': True, 'card': result})
    
    return jsonify({'success': False, 'message': 'Error joining game'})

# ============================================
# SOCKET.IO EVENTS
# ============================================
@socketio.on('connect')
def handle_connect():
    if current_user.is_authenticated:
        emit('connected', {'user_id': current_user.id})

@socketio.on('identify')
def handle_identify(data):
    # Just acknowledge
    pass

@socketio.on('select_card')
def handle_select_card(data):
    # Broadcast to all other users
    emit('card_selected', data, broadcast=True, include_self=False)

@socketio.on('release_card')
def handle_release_card(data):
    # Broadcast to all other users
    emit('card_released', data, broadcast=True, include_self=False)

@socketio.on('join_game')
@login_required
def handle_join():
    success, result = game_engine.add_player(current_user.id)
    if success:
        emit('game_joined', {'card': result})

@socketio.on('claim_bingo')
@login_required
def handle_claim():
    result = game_engine.claim_win(current_user.id)
    emit('claim_result', {'result': result})

@socketio.on('get_state')
@login_required
def handle_get_state():
    player = GamePlayer.query.filter_by(
        user_id=current_user.id,
        game_round=game_engine.round_number
    ).first()
    
    emit('game_state', {
        'round': game_engine.round_number,
        'drawn': game_engine.drawn_numbers,
        'card': json.loads(player.card) if player else None,
        'in_game': player is not None,
        'disqualified': player.disqualified if player else False,
        'winners': game_engine.pending_winners
    })

# ============================================
# DATABASE INIT
# ============================================
with app.app_context():
    db.create_all()
    
    # Create admin user if not exists
    if not User.query.filter_by(username='admin').first():
        admin = User(
            username='admin',
            password_hash=generate_password_hash('admin123'),
            is_admin=True
        )
        db.session.add(admin)
        db.session.commit()
        print("=" * 50)
        print("✅ ADMIN CREATED!")
        print("   Username: admin")
        print("   Password: admin123")
        print("=" * 50)

# ============================================
# START THE GAME ROUND
# ============================================
with app.app_context():
    # Start the first round
    game_engine.start_new_round()

# ============================================
# START APP
# ============================================
if __name__ == '__main__':
    print("=" * 50)
    print("🚀 WOND BINGO STARTING...")
    print("📍 http://localhost:10000")
    print("=" * 50)
    socketio.run(app, host='0.0.0.0', port=10000, debug=True)
