import random
import json
import threading
import time
from datetime import datetime
from flask_socketio import emit
from flask_login import current_user
from models import db, Game, GamePlayer, User, Win, Transaction
from config import Config
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class BingoGame:
    def __init__(self, socketio):
        self.socketio = socketio
        self.current_game = None
        self.game_lock = threading.Lock()
        self.pending_winners = []
        self.winner_timeout = None
        self.running = True
        
        self.start_new_round()

    def generate_card(self):
        card = []
        ranges = [(1, 15), (16, 30), (31, 45), (46, 60), (61, 75)]
        
        for col_range in ranges:
            column_numbers = random.sample(range(col_range[0], col_range[1] + 1), 5)
            card.append(column_numbers)
        
        card = list(map(list, zip(*card)))
        card[2][2] = "FREE"
        
        return card

    def check_win(self, card, drawn_numbers):
        called = set(str(n) for n in drawn_numbers)
        called.add("FREE")
        
        str_card = [[str(cell) for cell in row] for row in card]
        
        for row in str_card:
            if all(cell in called for cell in row):
                return True
        
        for col in range(5):
            if all(str_card[row][col] in called for row in range(5)):
                return True
        
        if all(str_card[i][i] in called for i in range(5)):
            return True
        if all(str_card[i][4-i] in called for i in range(5)):
            return True
        
        corners = [str_card[0][0], str_card[0][4], str_card[4][0], str_card[4][4]]
        if all(c in called for c in corners):
            return True
        
        return False

    def start_new_round(self):
        with self.game_lock:
            last_game = Game.query.order_by(Game.round_number.desc()).first()
            round_num = (last_game.round_number + 1) if last_game else 1
            
            self.current_game = Game(
                round_number=round_num,
                status='running',
                drawn_numbers='[]',
                prize_pool=0.0
            )
            db.session.add(self.current_game)
            db.session.commit()
            
            self.pending_winners = []
            logger.info(f"Started new round #{round_num}")

    def add_player(self, user_id, card_number=None):
        with self.game_lock:
            if not self.current_game or self.current_game.status != 'running':
                return False, "Game not available"
            
            existing = GamePlayer.query.filter_by(
                game_id=self.current_game.id,
                user_id=user_id
            ).first()
            
            if existing:
                return True, json.loads(existing.card)
            
            user = User.query.get(user_id)
            if user.balance < Config.ENTRY_FEE:
                return False, "Insufficient balance"
            
            card = self.generate_card()
            game_player = GamePlayer(
                game_id=self.current_game.id,
                user_id=user_id,
                card=json.dumps(card),
                card_number=card_number
            )
            
            user.balance -= Config.ENTRY_FEE
            self.current_game.prize_pool += Config.ENTRY_FEE * Config.PRIZE_PERCENT
            
            transaction = Transaction(
                user_id=user_id,
                amount=-Config.ENTRY_FEE,
                type='game_entry',
                reference_id=self.current_game.id
            )
            
            db.session.add(game_player)
            db.session.add(transaction)
            db.session.commit()
            
            logger.info(f"Player {user_id} joined round #{self.current_game.round_number}")
            return True, card

    def draw_number(self):
        with self.game_lock:
            if not self.current_game or self.current_game.status != 'running':
                return None
            
            drawn = self.current_game.get_drawn_numbers()
            available = set(range(1, 76)) - set(drawn)
            
            if not available:
                self.end_game()
                return None
            
            number = random.choice(list(available))
            self.current_game.add_drawn_number(number)
            db.session.commit()
            
            self.check_winners(number)
            
            return number

    def check_winners(self, number):
        players = GamePlayer.query.filter_by(
            game_id=self.current_game.id,
            disqualified=False
        ).all()
        
        drawn = self.current_game.get_drawn_numbers()
        new_winners = []
        
        for player in players:
            if player.user_id not in self.pending_winners:
                card = json.loads(player.card)
                if self.check_win(card, drawn):
                    new_winners.append(player.user_id)
        
        if new_winners:
            self.pending_winners.extend(new_winners)
            
            self.socketio.emit('winners', {
                'winners': new_winners,
                'number': number
            })
            
            if not self.winner_timeout:
                self.start_winner_countdown()

    def start_winner_countdown(self):
        def countdown():
            time.sleep(Config.WINNER_WAIT_SECONDS)
            with self.game_lock:
                if self.pending_winners:
                    self.end_game()
        
        self.winner_timeout = threading.Thread(target=countdown)
        self.winner_timeout.daemon = True
        self.winner_timeout.start()

    def claim_win(self, user_id, card_number=None):
        with self.game_lock:
            if not self.current_game or self.current_game.status != 'running':
                return 'NO_GAME'
            
            player = GamePlayer.query.filter_by(
                game_id=self.current_game.id,
                user_id=user_id
            ).first()
            
            if not player:
                return 'NOT_PLAYING'
            
            if player.disqualified:
                return 'DISQUALIFIED'
            
            if user_id in self.pending_winners:
                return 'ALREADY_WON'
            
            drawn = self.current_game.get_drawn_numbers()
            card = json.loads(player.card)
            
            if self.check_win(card, drawn):
                self.pending_winners.append(user_id)
                player.claim_time = datetime.utcnow()
                db.session.commit()
                
                if len(self.pending_winners) == 1:
                    self.start_winner_countdown()
                
                return 'VALID'
            else:
                player.disqualified = True
                db.session.commit()
                return 'DISQUALIFIED'

    def end_game(self):
        with self.game_lock:
            if not self.current_game or self.current_game.status != 'running':
                return
            
            self.current_game.status = 'completed'
            self.current_game.completed_at = datetime.utcnow()
            
            if self.pending_winners:
                prize_per_winner = self.current_game.prize_pool / len(self.pending_winners)
                
                for user_id in self.pending_winners:
                    user = User.query.get(user_id)
                    user.balance += prize_per_winner
                    
                    win = Win(
                        game_id=self.current_game.id,
                        user_id=user_id,
                        amount=prize_per_winner
                    )
                    
                    transaction = Transaction(
                        user_id=user_id,
                        amount=prize_per_winner,
                        type='prize',
                        reference_id=self.current_game.id
                    )
                    
                    db.session.add(win)
                    db.session.add(transaction)
            
            db.session.commit()
            
            self.socketio.emit('game_ended', {
                'winners': self.pending_winners,
                'prize_per_winner': prize_per_winner if self.pending_winners else 0
            })
            
            logger.info(f"Round #{self.current_game.round_number} ended. Winners: {self.pending_winners}")
            
            self.pending_winners = []
            self.winner_timeout = None
            
            threading.Timer(5.0, self.start_new_round).start()

    def get_game_state(self, user_id):
        if not self.current_game:
            return None
        
        player = GamePlayer.query.filter_by(
            game_id=self.current_game.id,
            user_id=user_id
        ).first()
        
        return {
            'round': self.current_game.round_number,
            'status': self.current_game.status,
            'drawn': self.current_game.get_drawn_numbers(),
            'card': json.loads(player.card) if player else None,
            'in_game': player is not None,
            'disqualified': player.disqualified if player else False,
            'winners': self.pending_winners
        }