# bot.py
import os
from flask import Flask, request
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo
import threading
import time

# Your existing Flask app import
from app import app, socketio

# Telegram Bot Token - Get from @BotFather
BOT_TOKEN = "8364528174:AAHYYdkt5F1kqlKjbe6QhxvBgNcSfsc7aFY"  # Replace after getting from BotFather

bot = telebot.TeleBot(BOT_TOKEN, threaded=False)

# Web app URL - Change after deployment
WEB_APP_URL = "https://your-app-name.koyeb.app"  # Replace later

@bot.message_handler(commands=['start'])
def send_welcome(message):
    """Send welcome message with Web App button"""
    user_name = message.from_user.first_name
    
    # Create inline keyboard with Web App button
    markup = InlineKeyboardMarkup()
    
    # Web App button - opens your game in Telegram
    web_app_button = InlineKeyboardButton(
        text="🎮 Play Wond Bingo", 
        web_app=WebAppInfo(url=WEB_APP_URL)
    )
    
    # Admin panel button (only for admins)
    admin_button = InlineKeyboardButton(
        text="⚙️ Admin Panel",
        web_app=WebAppInfo(url=f"{WEB_APP_URL}/admin")
    )
    
    markup.add(web_app_button)
    
    # Check if user is admin (you'll add user IDs later)
    ADMIN_IDS = [8576569079]  # Replace with your Telegram user ID
    if message.from_user.id in ADMIN_IDS:
        markup.add(admin_button)
    
    welcome_text = f"""
    🎰 **Welcome to Wond Bingo, {user_name}!** 🎰
    
    Click the button below to launch the game inside Telegram.
    
    **Features:**
    • 🎲 75-ball Bingo
    • 🎴 400 cards to choose from
    • 👥 Play with hundreds of players
    • 🏆 Win and see leaderboards
    
    Made with ❤️ for Telegram
    """
    
    bot.send_message(
        message.chat.id, 
        welcome_text, 
        parse_mode="Markdown",
        reply_markup=markup
    )

@bot.message_handler(commands=['help'])
def send_help(message):
    """Send help message"""
    help_text = """
    **Wond Bingo Commands:**
    
    /start - Launch the game
    /help - Show this help
    /rules - Game rules
    /stats - Your statistics (coming soon)
    
    **How to Play:**
    1. Click "Play Wond Bingo"
    2. Login or Register
    3. Select a card number (1-400)
    4. Click "Join Game"
    5. Wait for numbers to be called
    6. Click "BINGO!" when you win!
    """
    bot.send_message(message.chat.id, help_text, parse_mode="Markdown")

@bot.message_handler(commands=['rules'])
def send_rules(message):
    """Send game rules"""
    rules_text = """
    **📖 Bingo Rules:**
    
    • 5x5 card with numbers 1-75
    • FREE space in the center
    • Numbers are called every 2 seconds
    • Win by completing:
      - Any row
      - Any column
      - Either diagonal
      - Four corners
    
    First player to complete a pattern wins!
    Multiple winners split the prize pool.
    """
    bot.send_message(message.chat.id, rules_text, parse_mode="Markdown")

# Webhook endpoint for Telegram
@app.route(f'/webhook/{BOT_TOKEN}', methods=['POST'])
def webhook():
    """Handle incoming Telegram updates via webhook"""
    update = request.get_json()
    if update:
        bot.process_new_updates([telebot.types.Update.de_json(update)])
    return 'OK', 200

def set_webhook():
    """Set webhook for Telegram bot"""
    time.sleep(2)  # Wait for server to start
    webhook_url = f"{WEB_APP_URL}/webhook/{BOT_TOKEN}"
    bot.remove_webhook()
    bot.set_webhook(url=webhook_url)
    print(f"✅ Webhook set to: {webhook_url}")

# Start webhook setup in background thread
threading.Thread(target=set_webhook, daemon=True).start()

# Keep your existing Flask app code here
# (your app.py continues below this)
