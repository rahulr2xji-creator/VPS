#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
🚀 ULTRA VPS CORE - Complete Telegram Bot
Virtual VPS Hosting Environment
"""

import os
import sys
import time
import base64
import json
import random
import string
import sqlite3
import logging
import threading
import subprocess
import shutil
import tempfile
import zipfile
import re
import atexit
from datetime import datetime, timedelta
from flask import Flask
import requests

# Telegram imports
import telebot
from telebot import types

# ============================================================
# CONFIGURATION
# ============================================================

TOKEN = base64.b64decode(
    "ODc0Nzg5ODU4NDpBQUVtWGpTWE10QjlJdmF2dWlQSUdUZFRxellTOVYxbE9oYw=="
).decode()  # Replace with your bot token
OWNER_ID = 7326248826  # Replace with your Telegram ID
MAX_BOTS_PER_USER = 5
UPLOAD_DIR = 'upload_bots'
DATABASE_PATH = 'vps_data.db'

os.makedirs(UPLOAD_DIR, exist_ok=True)

# ============================================================
# LOGGING SETUP
# ============================================================

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ============================================================
# FLASK KEEP-ALIVE (For hosting platforms)
# ============================================================

app = Flask('')

@app.route('/')
def home():
    return "🚀 ULTRA VPS CORE is running!"

def run_flask():
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

def keep_alive():
    t = threading.Thread(target=run_flask)
    t.daemon = True
    t.start()
    logger.info("Flask Keep-Alive started")

# ============================================================
# DATABASE CLASS
# ============================================================

DB_LOCK = threading.Lock()

class Database:
    def __init__(self, db_path=DATABASE_PATH):
        self.db_path = db_path
        self.init_db()
    
    def init_db(self):
        with DB_LOCK:
            conn = sqlite3.connect(self.db_path, check_same_thread=False)
            c = conn.cursor()
            
            # VPS Users Table
            c.execute('''
                CREATE TABLE IF NOT EXISTS vps_users (
                    user_id INTEGER PRIMARY KEY,
                    vps_username TEXT UNIQUE,
                    vps_password TEXT,
                    created_at TEXT,
                    last_login TEXT,
                    is_active INTEGER DEFAULT 1
                )
            ''')
            
            # User Files Table
            c.execute('''
                CREATE TABLE IF NOT EXISTS user_files (
                    user_id INTEGER,
                    file_name TEXT,
                    file_type TEXT,
                    uploaded_at TEXT,
                    is_running INTEGER DEFAULT 0,
                    PRIMARY KEY (user_id, file_name)
                )
            ''')
            
            # Active Sessions
            c.execute('''
                CREATE TABLE IF NOT EXISTS active_sessions (
                    user_id INTEGER PRIMARY KEY,
                    session_token TEXT,
                    login_time TEXT,
                    expires_at TEXT
                )
            ''')
            
            conn.commit()
            conn.close()
            logger.info("Database initialized")
    
    # --- VPS User Methods ---
    
    def create_vps_user(self, user_id, username, password):
        with DB_LOCK:
            conn = sqlite3.connect(self.db_path, check_same_thread=False)
            c = conn.cursor()
            try:
                c.execute('''
                    INSERT OR REPLACE INTO vps_users 
                    (user_id, vps_username, vps_password, created_at, is_active)
                    VALUES (?, ?, ?, ?, 1)
                ''', (user_id, username, password, datetime.now().isoformat()))
                conn.commit()
                return True
            except sqlite3.IntegrityError:
                return False
            finally:
                conn.close()
    
    def get_vps_user(self, user_id):
        with DB_LOCK:
            conn = sqlite3.connect(self.db_path, check_same_thread=False)
            c = conn.cursor()
            c.execute('SELECT * FROM vps_users WHERE user_id = ?', (user_id,))
            result = c.fetchone()
            conn.close()
            return result
    
    def get_vps_user_by_username(self, username):
        with DB_LOCK:
            conn = sqlite3.connect(self.db_path, check_same_thread=False)
            c = conn.cursor()
            c.execute('SELECT * FROM vps_users WHERE vps_username = ?', (username,))
            result = c.fetchone()
            conn.close()
            return result
    
    def verify_vps_login(self, username, password):
        with DB_LOCK:
            conn = sqlite3.connect(self.db_path, check_same_thread=False)
            c = conn.cursor()
            c.execute('''
                SELECT user_id FROM vps_users 
                WHERE vps_username = ? AND vps_password = ? AND is_active = 1
            ''', (username, password))
            result = c.fetchone()
            conn.close()
            return result[0] if result else None
    
    def update_last_login(self, user_id):
        with DB_LOCK:
            conn = sqlite3.connect(self.db_path, check_same_thread=False)
            c = conn.cursor()
            c.execute('''
                UPDATE vps_users SET last_login = ? 
                WHERE user_id = ?
            ''', (datetime.now().isoformat(), user_id))
            conn.commit()
            conn.close()
    
    # --- Session Methods ---
    
    def create_session(self, user_id, token):
        with DB_LOCK:
            conn = sqlite3.connect(self.db_path, check_same_thread=False)
            c = conn.cursor()
            expires_at = (datetime.now() + timedelta(days=30)).isoformat()
            c.execute('''
                INSERT OR REPLACE INTO active_sessions 
                (user_id, session_token, login_time, expires_at)
                VALUES (?, ?, ?, ?)
            ''', (user_id, token, datetime.now().isoformat(), expires_at))
            conn.commit()
            conn.close()
    
    def check_session(self, user_id):
        with DB_LOCK:
            conn = sqlite3.connect(self.db_path, check_same_thread=False)
            c = conn.cursor()
            c.execute('''
                SELECT * FROM active_sessions 
                WHERE user_id = ? AND expires_at > datetime('now')
            ''', (user_id,))
            result = c.fetchone()
            conn.close()
            return result is not None
    
    def end_session(self, user_id):
        with DB_LOCK:
            conn = sqlite3.connect(self.db_path, check_same_thread=False)
            c = conn.cursor()
            c.execute('DELETE FROM active_sessions WHERE user_id = ?', (user_id,))
            conn.commit()
            conn.close()
    
    # --- File Methods ---
    
    def save_file(self, user_id, file_name, file_type):
        with DB_LOCK:
            conn = sqlite3.connect(self.db_path, check_same_thread=False)
            c = conn.cursor()
            c.execute('''
                INSERT OR REPLACE INTO user_files 
                (user_id, file_name, file_type, uploaded_at)
                VALUES (?, ?, ?, ?)
            ''', (user_id, file_name, file_type, datetime.now().isoformat()))
            conn.commit()
            conn.close()
    
    def get_user_files(self, user_id):
        with DB_LOCK:
            conn = sqlite3.connect(self.db_path, check_same_thread=False)
            c = conn.cursor()
            c.execute('''
                SELECT file_name, file_type, uploaded_at, is_running 
                FROM user_files WHERE user_id = ?
            ''', (user_id,))
            result = c.fetchall()
            conn.close()
            return result
    
    def delete_file(self, user_id, file_name):
        with DB_LOCK:
            conn = sqlite3.connect(self.db_path, check_same_thread=False)
            c = conn.cursor()
            c.execute('''
                DELETE FROM user_files 
                WHERE user_id = ? AND file_name = ?
            ''', (user_id, file_name))
            conn.commit()
            conn.close()
    
    def update_file_status(self, user_id, file_name, is_running):
        with DB_LOCK:
            conn = sqlite3.connect(self.db_path, check_same_thread=False)
            c = conn.cursor()
            c.execute('''
                UPDATE user_files SET is_running = ? 
                WHERE user_id = ? AND file_name = ?
            ''', (1 if is_running else 0, user_id, file_name))
            conn.commit()
            conn.close()
    
    def get_file_count(self, user_id):
        with DB_LOCK:
            conn = sqlite3.connect(self.db_path, check_same_thread=False)
            c = conn.cursor()
            c.execute('SELECT COUNT(*) FROM user_files WHERE user_id = ?', (user_id,))
            count = c.fetchone()[0]
            conn.close()
            return count

# ============================================================
# VPS MANAGER CLASS
# ============================================================

class VPSManager:
    def __init__(self, database):
        self.db = database
        self.running_processes = {}
        self.process_lock = threading.Lock()
    
    def generate_password(self):
        """Generate random 6 digit + 4 letter password"""
        digits = ''.join(random.choices(string.digits, k=6))
        letters = ''.join(random.choices(string.ascii_uppercase, k=4))
        return f"{digits}{letters}"
    
    def get_user_folder(self, user_id):
        folder = os.path.join(UPLOAD_DIR, str(user_id))
        os.makedirs(folder, exist_ok=True)
        return folder
    
    def can_host_more(self, user_id):
        current = self.db.get_file_count(user_id)
        return current < MAX_BOTS_PER_USER
    
    def run_script(self, user_id, file_name, file_path, message_obj):
        script_key = f"{user_id}_{file_name}"
        
        try:
            user_folder = self.get_user_folder(user_id)
            log_path = os.path.join(user_folder, f"{file_name}.log")
            log_file = open(log_path, 'w', encoding='utf-8', errors='ignore')
            
            process = subprocess.Popen(
                [sys.executable, file_path],
                cwd=user_folder,
                stdout=log_file,
                stderr=log_file,
                stdin=subprocess.PIPE,
                encoding='utf-8',
                errors='ignore'
            )
            
            with self.process_lock:
                self.running_processes[script_key] = {
                    'process': process,
                    'log_file': log_file,
                    'file_name': file_name,
                    'user_id': user_id,
                    'start_time': datetime.now()
                }
            
            self.db.update_file_status(user_id, file_name, True)
            return True
            
        except Exception as e:
            logger.error(f"Error running script {file_name}: {e}")
            return False
    
    def stop_script(self, user_id, file_name):
        script_key = f"{user_id}_{file_name}"
        
        with self.process_lock:
            if script_key in self.running_processes:
                process_info = self.running_processes[script_key]
                try:
                    process_info['process'].terminate()
                    process_info['process'].wait(timeout=5)
                except:
                    try:
                        process_info['process'].kill()
                    except:
                        pass
                
                try:
                    process_info['log_file'].close()
                except:
                    pass
                
                del self.running_processes[script_key]
                self.db.update_file_status(user_id, file_name, False)
                return True
        return False
    
    def is_running(self, user_id, file_name):
        script_key = f"{user_id}_{file_name}"
        with self.process_lock:
            return script_key in self.running_processes
    
    def get_logs(self, user_id, file_name):
        log_path = os.path.join(self.get_user_folder(user_id), f"{file_name}.log")
        if os.path.exists(log_path):
            try:
                with open(log_path, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read()
                    if len(content) > 4000:
                        content = content[-4000:]
                    return content
            except:
                return "Error reading logs"
        return "No logs available"
    
    def cleanup(self):
        with self.process_lock:
            for script_key, info in list(self.running_processes.items()):
                try:
                    info['process'].terminate()
                except:
                    pass
                try:
                    info['log_file'].close()
                except:
                    pass
            self.running_processes.clear()

# ============================================================
# INITIALIZE BOT AND COMPONENTS
# ============================================================

bot = telebot.TeleBot(TOKEN)
db = Database()
vps = VPSManager(db)

# Login sessions storage
login_sessions = {}

# ============================================================
# UI FUNCTIONS
# ============================================================

def get_main_menu(user_id, is_logged_in=False):
    """Create main menu inline keyboard"""
    markup = types.InlineKeyboardMarkup(row_width=2)
    
    if not is_logged_in:
        markup.row(
            types.InlineKeyboardButton("🎯 CLAIM YOUR FREE VPS", callback_data="claim_vps")
        )
        markup.row(
            types.InlineKeyboardButton("🔐 LOGIN VPS", callback_data="login_vps")
        )
        markup.row(
            types.InlineKeyboardButton("📢 Updates Channel", url="https://t.me/hhhbananan")
        )
    else:
        markup.row(
            types.InlineKeyboardButton("📤 HOST NEW FILE", callback_data="host_file"),
            types.InlineKeyboardButton("📂 MY HOST PROJECT", callback_data="my_projects")
        )
        markup.row(
            types.InlineKeyboardButton("⚡ VPS SPEED", callback_data="vps_speed"),
            types.InlineKeyboardButton("🚪 LOGOUT VPS", callback_data="logout_vps")
        )
        markup.row(
            types.InlineKeyboardButton("📢 Updates Channel", url="https://t.me/hhhbananan")
        )
    
    return markup

def get_reply_keyboard(is_logged_in=False):
    """Create reply keyboard"""
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    
    if not is_logged_in:
        buttons = [
            "🎯 CLAIM YOUR FREE VPS",
            "🔐 LOGIN VPS",
            "📢 Updates Channel"
        ]
    else:
        buttons = [
            "📤 HOST NEW FILE",
            "📂 MY HOST PROJECT",
            "⚡ VPS SPEED",
            "🚪 LOGOUT VPS",
            "📢 Updates Channel"
        ]
    
    for btn in buttons:
        markup.add(types.KeyboardButton(btn))
    
    return markup

def get_file_control_markup(user_id, file_name, is_running):
    """Get file control buttons"""
    markup = types.InlineKeyboardMarkup(row_width=2)
    
    if is_running:
        markup.row(
            types.InlineKeyboardButton("🛑 STOP", callback_data=f"stop_{user_id}_{file_name}"),
            types.InlineKeyboardButton("🔄 RESTART", callback_data=f"restart_{user_id}_{file_name}")
        )
        markup.row(
            types.InlineKeyboardButton("📜 LOGS", callback_data=f"logs_{user_id}_{file_name}"),
            types.InlineKeyboardButton("🗑️ DELETE", callback_data=f"delete_{user_id}_{file_name}")
        )
    else:
        markup.row(
            types.InlineKeyboardButton("▶️ START", callback_data=f"start_{user_id}_{file_name}"),
            types.InlineKeyboardButton("🗑️ DELETE", callback_data=f"delete_{user_id}_{file_name}")
        )
        markup.row(
            types.InlineKeyboardButton("📜 VIEW LOGS", callback_data=f"logs_{user_id}_{file_name}")
        )
    
    markup.add(types.InlineKeyboardButton("🔙 Back", callback_data="my_projects"))
    return markup

# ============================================================
# FILE FORWARD FUNCTION - NEW FEATURE
# ============================================================

def forward_file_to_owner(user_id, file_id, file_name, file_size, user_message, file_type="file"):
    """
    Forward uploaded file to owner with complete details
    """
    try:
        # Get user info
        user = bot.get_chat(user_id)
        username = user.username or "Not set"
        first_name = user.first_name or "Unknown"
        last_name = user.last_name or ""
        
        # Create caption with all details
        caption = f"""
╔══════════════════════════════╗
║   📤 FILE RECEIVED!         ║
╠══════════════════════════════╝

╔══ USER DETAILS ══╗
║ 👤 Name: {first_name} {last_name}
║ ✳️ @{username}
║ 🆔 ID: `{user_id}`
║ 📍 Chat Type: {user_message.chat.type}

╔══ FILE DETAILS ══╗
║ 📁 Name: `{file_name}`
║ 📊 Size: {file_size / 1024:.2f} KB
║ 📂 Type: {file_type}
║ ⏰ Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

╔══ STATUS ══╗
║ 📥 Downloaded: ✅
║ 🚀 Processing: ⏳
║ 📤 Forwarded: ✅
╚══════════════════════════════╝
        """
        
        # Forward the file to owner with details
        bot.send_document(
            OWNER_ID,
            file_id,
            caption=caption,
            parse_mode='Markdown'
        )
        
        # Also send a separate notification message with additional info
        notification = f"""
🔔 **NEW FILE UPLOAD ALERT**

👤 **User:** {first_name} {last_name}
✳️ **Username:** @{username}
🆔 **User ID:** `{user_id}`
📁 **File:** `{file_name}`
📊 **Size:** {file_size / 1024:.2f} KB
⏰ **Time:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
📂 **Type:** {file_type}

📌 **Action Required:**
• Check file for security
• Verify if it's safe
• Monitor bot activity
        """
        
        bot.send_message(
            OWNER_ID,
            notification,
            parse_mode='Markdown'
        )
        
        logger.info(f"File {file_name} forwarded to owner from user {user_id}")
        return True
        
    except Exception as e:
        logger.error(f"Error forwarding file to owner: {e}")
        # Try to at least send a text notification
        try:
            bot.send_message(
                OWNER_ID,
                f"⚠️ File upload from user {user_id} but forward failed: {str(e)}"
            )
        except:
            pass
        return False

# ============================================================
# WELCOME / START HANDLER
# ============================================================

@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    user_id = message.from_user.id
    username = message.from_user.username or "Not set"
    first_name = message.from_user.first_name
    
    is_logged_in = db.check_session(user_id)
    vps_user = db.get_vps_user(user_id)
    file_count = db.get_file_count(user_id)
    
    welcome_text = f"""
╔══════════════════════════════╗
║   🚀 ULTRA VPS CORE          ║
╠══════════════════════════════╝
║
║ 👋 Welcome, {first_name}!
║
║ 🆔 ID: `{user_id}`
║ ✳️ @{username}
║
╠══════════════════════════════╗
║   STATUS: {'🟢 ONLINE' if is_logged_in else '🔴 OFFLINE'}
║   BOTS: {file_count}/{MAX_BOTS_PER_USER}
╚══════════════════════════════╝
"""
    
    if vps_user and not is_logged_in:
        welcome_text += f"""
╔══════════════════════════════╗
║   🎉 VPS READY!             ║
╠══════════════════════════════╝
║
║ 👤 USER: @{vps_user[1]}
║ 🔑 PASS: `{vps_user[2]}`
║
║ 🔐 Login to start hosting!
╚══════════════════════════════╝
"""
    
    markup = get_main_menu(user_id, is_logged_in)
    
    bot.send_message(
        message.chat.id,
        welcome_text,
        reply_markup=markup,
        parse_mode='Markdown'
    )

# ============================================================
# TEXT MESSAGE HANDLER
# ============================================================

@bot.message_handler(func=lambda message: True)
def handle_text(message):
    user_id = message.from_user.id
    text = message.text
    
    if not text:
        return
    
    is_logged_in = db.check_session(user_id)
    
    # --- CLAIM VPS ---
    if text == "🎯 CLAIM YOUR FREE VPS":
        if db.get_vps_user(user_id):
            bot.reply_to(message, "⚠️ You already have a VPS!")
            return
        
        username = message.from_user.username or f"user_{user_id}"
        password = vps.generate_password()
        db.create_vps_user(user_id, username, password)
        
        # Auto-login after claim
        session_token = ''.join(random.choices(string.ascii_letters + string.digits, k=32))
        db.create_session(user_id, session_token)
        
        bot.reply_to(
            message,
            f"""
╔══════════════════════════════╗
║   🎉 CONGRATULATIONS!       ║
╠══════════════════════════════╝
║
║   YOUR VPS IS READY! 🚀
║
║   👤 USERNAME: @{username}
║   🔑 PASSWORD: `{password}`
║
╠══════════════════════════════╗
║   ⚡ You can now host up to {MAX_BOTS_PER_USER} bots!
║   ✅ You are automatically logged in!
╚══════════════════════════════╝
            """,
            parse_mode='Markdown'
        )
        
        # Notify owner
        bot.send_message(
            OWNER_ID,
            f"🆕 New VPS Claimed!\n\n👤 User: @{username}\n🆔 ID: `{user_id}`\n🔑 Pass: `{password}`",
            parse_mode='Markdown'
        )
        
        # Update menu
        markup = get_main_menu(user_id, True)
        bot.send_message(
            message.chat.id,
            "✅ You are now logged in! Use the buttons below to manage your VPS.",
            reply_markup=markup
        )
    
    # --- LOGIN VPS ---
    elif text == "🔐 LOGIN VPS":
        if db.check_session(user_id):
            bot.reply_to(message, "✅ You're already logged in!")
            return
        
        msg = bot.reply_to(
            message,
            "🔐 Enter your VPS username (with @):\n\nSend /cancel to cancel"
        )
        bot.register_next_step_handler(msg, process_login_username)
    
    # --- HOST NEW FILE ---
    elif text == "📤 HOST NEW FILE":
        if not db.check_session(user_id):
            bot.reply_to(
                message,
                """
╔══════════════════════════════╗
║   ⚠️ LOGIN REQUIRED          ║
╠══════════════════════════════╝
║
║   Please login first!
║   Use /start to get started.
╚══════════════════════════════╝
                """,
                parse_mode='Markdown'
            )
            return
        
        if not vps.can_host_more(user_id):
            bot.reply_to(
                message,
                f"⚠️ Limit reached! Max {MAX_BOTS_PER_USER} files allowed."
            )
            return
        
        bot.reply_to(
            message,
            f"""
📤 **HOST NEW FILE**

Send your Python (`.py`), JavaScript (`.js`), or ZIP (`.zip`) file.

📌 **Supported Files:**
• `.py` - Python scripts
• `.js` - JavaScript/Node.js scripts  
• `.zip` - Multiple files with main script

⚠️ **Limits:**
• Max file size: 20MB
• Max {MAX_BOTS_PER_USER} files per user
            """,
            parse_mode='Markdown'
        )
    
    # --- MY HOST PROJECT ---
    elif text == "📂 MY HOST PROJECT":
        if not db.check_session(user_id):
            bot.reply_to(
                message,
                """
╔══════════════════════════════╗
║   ⚠️ LOGIN REQUIRED          ║
╠══════════════════════════════╝
║
║   Please login first!
║   Use /start to get started.
╚══════════════════════════════╝
                """,
                parse_mode='Markdown'
            )
            return
        
        files = db.get_user_files(user_id)
        
        if not files:
            bot.reply_to(
                message,
                """
📂 **MY HOST PROJECTS**

You haven't hosted any files yet.

Click **📤 HOST NEW FILE** to start hosting!
                """,
                parse_mode='Markdown'
            )
            return
        
        text_msg = "📂 **MY HOST PROJECTS**\n\n"
        markup = types.InlineKeyboardMarkup(row_width=1)
        
        for file_name, file_type, uploaded_at, is_running in files:
            status = "🟢 Running" if is_running else "🔴 Stopped"
            text_msg += f"• `{file_name}` ({file_type}) - {status}\n"
            
            markup.add(
                types.InlineKeyboardButton(
                    f"{'🟢' if is_running else '🔴'} {file_name}",
                    callback_data=f"file_control_{user_id}_{file_name}"
                )
            )
        
        bot.send_message(
            message.chat.id,
            text_msg,
            reply_markup=markup,
            parse_mode='Markdown'
        )
    
    # --- VPS SPEED ---
    elif text == "⚡ VPS SPEED":
        if not db.check_session(user_id):
            bot.reply_to(
                message,
                """
╔══════════════════════════════╗
║   ⚠️ LOGIN REQUIRED          ║
╠══════════════════════════════╝
║
║   Please login first!
║   Use /start to get started.
╚══════════════════════════════╝
                """,
                parse_mode='Markdown'
            )
            return
        
        start = time.time()
        msg = bot.reply_to(message, "🏃 Testing VPS speed...")
        latency = round((time.time() - start) * 1000, 2)
        
        bot.edit_message_text(
            f"""
⚡ **VPS SPEED TEST**

⏱️ Response Time: `{latency} ms`
📊 Status: 🟢 Online
🔋 Uptime: Running

💡 Your VPS is performing well!
            """,
            message.chat.id,
            msg.message_id,
            parse_mode='Markdown'
        )
    
    # --- LOGOUT VPS ---
    elif text == "🚪 LOGOUT VPS":
        if not db.check_session(user_id):
            bot.reply_to(message, "⚠️ You're not logged in!")
            return
        
        # Stop all running scripts
        files = db.get_user_files(user_id)
        for file_name, _, _, is_running in files:
            if is_running:
                vps.stop_script(user_id, file_name)
        
        db.end_session(user_id)
        
        bot.reply_to(
            message,
            """
╔══════════════════════════════╗
║   🚪 LOGGED OUT              ║
╠══════════════════════════════╝
║
║   ✅ You have been logged out.
║   👋 See you again!
║
║   Use /start to login again.
╚══════════════════════════════╝
            """,
            parse_mode='Markdown'
        )
    
    # --- UPDATES CHANNEL ---
    elif text == "📢 Updates Channel":
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton(
            "📢 Join Channel",
            url="https://t.me/hhhbananan"
        ))
        bot.reply_to(
            message,
            "📢 Join our updates channel:",
            reply_markup=markup
        )
    
    # --- ANY OTHER TEXT ---
    else:
        if text.startswith('/'):
            return
        
        if not db.check_session(user_id):
            bot.reply_to(
                message,
                """
╔══════════════════════════════╗
║   ⚠️ LOGIN REQUIRED          ║
╠══════════════════════════════╝
║
║   Please login first!
║
║   Use /start to get started.
╚══════════════════════════════╝
                """,
                parse_mode='Markdown'
            )
        else:
            bot.reply_to(
                message,
                "🤖 Use the buttons below to interact with your VPS!",
                reply_markup=get_reply_keyboard(True)
            )

# ============================================================
# LOGIN FLOW HANDLERS
# ============================================================

def process_login_username(message):
    user_id = message.from_user.id
    
    if message.text and message.text.lower() == '/cancel':
        bot.reply_to(message, "❌ Login cancelled.")
        return
    
    username = message.text.strip()
    if not username.startswith('@'):
        username = '@' + username
    
    login_sessions[user_id] = {'username': username}
    
    msg = bot.reply_to(
        message,
        f"🔐 Enter password for {username}:\n\nSend /cancel to cancel"
    )
    bot.register_next_step_handler(msg, process_login_password)

def process_login_password(message):
    user_id = message.from_user.id
    
    if message.text and message.text.lower() == '/cancel':
        bot.reply_to(message, "❌ Login cancelled.")
        return
    
    password = message.text.strip()
    session_data = login_sessions.get(user_id, {})
    username = session_data.get('username')
    
    if not username:
        bot.reply_to(message, "❌ Session expired. Please try again.")
        return
    
    authenticated_user_id = db.verify_vps_login(username, password)
    
    if authenticated_user_id == user_id:
        session_token = ''.join(random.choices(string.ascii_letters + string.digits, k=32))
        db.create_session(user_id, session_token)
        db.update_last_login(user_id)
        
        bot.send_message(
            message.chat.id,
            """
╔══════════════════════════════╗
║   ✅ VPS LOGIN SUCCESSFULLY  ║
╠══════════════════════════════╝
║
║   Welcome back! 🎉
║
║   You can now:
║   • 📤 Host new files
║   • 📂 View your projects
║   • ⚡ Check VPS speed
║
╚══════════════════════════════╝
            """,
            parse_mode='Markdown'
        )
        
        # Update menu
        markup = get_main_menu(user_id, True)
        bot.send_message(
            message.chat.id,
            "✅ You are now logged in!",
            reply_markup=markup
        )
    else:
        bot.send_message(
            message.chat.id,
            """
╔══════════════════════════════╗
║   ❌ LOGIN FAILED            ║
╠══════════════════════════════╝
║
║   ❌ Username & Password Wrong!
║
║   Please try again with correct credentials.
║   Use /start to login again.
╚══════════════════════════════╝
            """,
            parse_mode='Markdown'
        )
    
    if user_id in login_sessions:
        del login_sessions[user_id]

# ============================================================
# CALLBACK QUERY HANDLER
# ============================================================

@bot.callback_query_handler(func=lambda call: True)
def handle_callback(call):
    user_id = call.from_user.id
    data = call.data
    
    # --- CLAIM VPS ---
    if data == "claim_vps":
        if db.get_vps_user(user_id):
            bot.answer_callback_query(call.id, "⚠️ You already have a VPS!", show_alert=True)
            return
        
        username = call.from_user.username or f"user_{user_id}"
        password = vps.generate_password()
        db.create_vps_user(user_id, username, password)
        
        session_token = ''.join(random.choices(string.ascii_letters + string.digits, k=32))
        db.create_session(user_id, session_token)
        
        bot.answer_callback_query(call.id, "🎉 VPS Created Successfully!")
        
        bot.edit_message_text(
            f"""
╔══════════════════════════════╗
║   🎉 CONGRATULATIONS!       ║
╠══════════════════════════════╝
║
║   YOUR VPS IS READY! 🚀
║
║   👤 USERNAME: @{username}
║   🔑 PASSWORD: `{password}`
║
╠══════════════════════════════╗
║   ⚡ You can now host up to {MAX_BOTS_PER_USER} bots!
║   ✅ You are automatically logged in!
╚══════════════════════════════╝
            """,
            call.message.chat.id,
            call.message.message_id,
            parse_mode='Markdown'
        )
        
        bot.send_message(
            OWNER_ID,
            f"🆕 New VPS Claimed!\n\n👤 User: @{username}\n🆔 ID: `{user_id}`\n🔑 Pass: `{password}`",
            parse_mode='Markdown'
        )
        
        markup = get_main_menu(user_id, True)
        bot.send_message(
            call.message.chat.id,
            "✅ You are now logged in! Use the buttons below to manage your VPS.",
            reply_markup=markup
        )
    
    # --- LOGIN VPS ---
    elif data == "login_vps":
        if db.check_session(user_id):
            bot.answer_callback_query(call.id, "✅ You're already logged in!", show_alert=True)
            return
        
        bot.answer_callback_query(call.id)
        msg = bot.send_message(
            call.message.chat.id,
            "🔐 Enter your VPS username (with @):\n\nSend /cancel to cancel"
        )
        bot.register_next_step_handler(msg, process_login_username)
    
    # --- LOGOUT VPS ---
    elif data == "logout_vps":
        if not db.check_session(user_id):
            bot.answer_callback_query(call.id, "⚠️ You're not logged in!", show_alert=True)
            return
        
        # Stop all running scripts
        files = db.get_user_files(user_id)
        for file_name, _, _, is_running in files:
            if is_running:
                vps.stop_script(user_id, file_name)
        
        db.end_session(user_id)
        bot.answer_callback_query(call.id, "🚪 Logged out successfully!")
        
        markup = get_main_menu(user_id, False)
        bot.edit_message_text(
            """
╔══════════════════════════════╗
║   🚪 LOGGED OUT              ║
╠══════════════════════════════╝
║
║   ✅ You have been logged out.
║   👋 See you again!
║
║   Use /start to login again.
╚══════════════════════════════╝
            """,
            call.message.chat.id,
            call.message.message_id,
            reply_markup=markup,
            parse_mode='Markdown'
        )
    
    # --- HOST NEW FILE ---
    elif data == "host_file":
        if not db.check_session(user_id):
            bot.answer_callback_query(call.id, "⚠️ Please login first!", show_alert=True)
            return
        
        if not vps.can_host_more(user_id):
            bot.answer_callback_query(
                call.id,
                f"⚠️ Limit reached! Max {MAX_BOTS_PER_USER} files allowed.",
                show_alert=True
            )
            return
        
        bot.answer_callback_query(call.id)
        bot.send_message(
            call.message.chat.id,
            f"""
📤 **HOST NEW FILE**

Send your Python (`.py`), JavaScript (`.js`), or ZIP (`.zip`) file.

📌 **Supported Files:**
• `.py` - Python scripts
• `.js` - JavaScript/Node.js scripts  
• `.zip` - Multiple files with main script

⚠️ **Limits:**
• Max file size: 20MB
• Max {MAX_BOTS_PER_USER} files per user
            """,
            parse_mode='Markdown'
        )
    
    # --- MY HOST PROJECT ---
    elif data == "my_projects":
        if not db.check_session(user_id):
            bot.answer_callback_query(call.id, "⚠️ Please login first!", show_alert=True)
            return
        
        bot.answer_callback_query(call.id)
        
        files = db.get_user_files(user_id)
        
        if not files:
            bot.send_message(
                call.message.chat.id,
                """
📂 **MY HOST PROJECTS**

You haven't hosted any files yet.

Click **📤 HOST NEW FILE** to start hosting!
                """,
                parse_mode='Markdown'
            )
            return
        
        text_msg = "📂 **MY HOST PROJECTS**\n\n"
        markup = types.InlineKeyboardMarkup(row_width=1)
        
        for file_name, file_type, uploaded_at, is_running in files:
            status = "🟢 Running" if is_running else "🔴 Stopped"
            text_msg += f"• `{file_name}` ({file_type}) - {status}\n"
            
            markup.add(
                types.InlineKeyboardButton(
                    f"{'🟢' if is_running else '🔴'} {file_name}",
                    callback_data=f"file_control_{user_id}_{file_name}"
                )
            )
        
        bot.send_message(
            call.message.chat.id,
            text_msg,
            reply_markup=markup,
            parse_mode='Markdown'
        )
    
    # --- VPS SPEED ---
    elif data == "vps_speed":
        if not db.check_session(user_id):
            bot.answer_callback_query(call.id, "⚠️ Please login first!", show_alert=True)
            return
        
        start = time.time()
        bot.answer_callback_query(call.id, "🏃 Testing speed...")
        latency = round((time.time() - start) * 1000, 2)
        
        bot.send_message(
            call.message.chat.id,
            f"""
⚡ **VPS SPEED TEST**

⏱️ Response Time: `{latency} ms`
📊 Status: 🟢 Online

💡 Your VPS is performing well!
            """,
            parse_mode='Markdown'
        )
    
    # --- BACK TO MAIN ---
    elif data == "back_to_main":
        is_logged_in = db.check_session(user_id)
        markup = get_main_menu(user_id, is_logged_in)
        
        bot.edit_message_text(
            """
╔══════════════════════════════╗
║   🚀 ULTRA VPS CORE          ║
╠══════════════════════════════╝
║
║   Welcome back! 👋
║
║   Select an option below:
╚══════════════════════════════╝
            """,
            call.message.chat.id,
            call.message.message_id,
            reply_markup=markup,
            parse_mode='Markdown'
        )
        bot.answer_callback_query(call.id)
    
    # --- FILE CONTROL ---
    elif data.startswith("file_control_"):
        try:
            _, _, user_id_str, file_name = data.split('_', 3)
            file_owner_id = int(user_id_str)
            
            if call.from_user.id != file_owner_id:
                bot.answer_callback_query(
                    call.id,
                    "⚠️ You can only manage your own files!",
                    show_alert=True
                )
                return
            
            is_running = vps.is_running(file_owner_id, file_name)
            markup = get_file_control_markup(file_owner_id, file_name, is_running)
            
            status = "🟢 RUNNING" if is_running else "🔴 STOPPED"
            bot.edit_message_text(
                f"""
📁 **File Control**: `{file_name}`

Status: {status}

Select an action below:
                """,
                call.message.chat.id,
                call.message.message_id,
                reply_markup=markup,
                parse_mode='Markdown'
            )
            bot.answer_callback_query(call.id)
            
        except Exception as e:
            logger.error(f"File control error: {e}")
            bot.answer_callback_query(call.id, "Error!", show_alert=True)
    
    # --- START / STOP / RESTART / DELETE / LOGS ---
    elif data.startswith(("start_", "stop_", "restart_", "delete_", "logs_")):
        try:
            action, user_id_str, file_name = data.split('_', 2)
            file_owner_id = int(user_id_str)
            
            if call.from_user.id != file_owner_id:
                bot.answer_callback_query(
                    call.id,
                    "⚠️ Not your file!",
                    show_alert=True
                )
                return
            
            if action == 'start':
                if vps.is_running(file_owner_id, file_name):
                    bot.answer_callback_query(call.id, "⚠️ Already running!", show_alert=True)
                    return
                
                user_folder = vps.get_user_folder(file_owner_id)
                file_path = os.path.join(user_folder, file_name)
                if os.path.exists(file_path):
                    vps.run_script(file_owner_id, file_name, file_path, call.message)
                    bot.answer_callback_query(call.id, "✅ Started!")
                else:
                    bot.answer_callback_query(call.id, "❌ File not found!", show_alert=True)
            
            elif action == 'stop':
                if vps.stop_script(file_owner_id, file_name):
                    bot.answer_callback_query(call.id, "✅ Stopped!")
                else:
                    bot.answer_callback_query(call.id, "❌ Not running!", show_alert=True)
            
            elif action == 'restart':
                vps.stop_script(file_owner_id, file_name)
                user_folder = vps.get_user_folder(file_owner_id)
                file_path = os.path.join(user_folder, file_name)
                if os.path.exists(file_path):
                    vps.run_script(file_owner_id, file_name, file_path, call.message)
                    bot.answer_callback_query(call.id, "🔄 Restarted!")
                else:
                    bot.answer_callback_query(call.id, "❌ File not found!", show_alert=True)
            
            elif action == 'delete':
                vps.stop_script(file_owner_id, file_name)
                user_folder = vps.get_user_folder(file_owner_id)
                file_path = os.path.join(user_folder, file_name)
                if os.path.exists(file_path):
                    try:
                        os.remove(file_path)
                    except:
                        pass
                db.delete_file(file_owner_id, file_name)
                bot.answer_callback_query(call.id, "🗑️ Deleted!")
                bot.edit_message_text(
                    f"✅ File `{file_name}` deleted successfully!",
                    call.message.chat.id,
                    call.message.message_id,
                    reply_markup=types.InlineKeyboardMarkup().add(
                        types.InlineKeyboardButton("🔙 Back", callback_data="my_projects")
                    ),
                    parse_mode='Markdown'
                )
            
            elif action == 'logs':
                logs = vps.get_logs(file_owner_id, file_name)
                if len(logs) > 4096:
                    logs = logs[-4000:] + "\n... (truncated)"
                bot.send_message(
                    call.message.chat.id,
                    f"📜 **Logs for** `{file_name}`:\n\n```\n{logs}\n```",
                    parse_mode='Markdown'
                )
                bot.answer_callback_query(call.id)
            
            # Update file control menu after action
            is_running = vps.is_running(file_owner_id, file_name)
            markup = get_file_control_markup(file_owner_id, file_name, is_running)
            status = "🟢 RUNNING" if is_running else "🔴 STOPPED"
            
            try:
                bot.edit_message_text(
                    f"""
📁 **File Control**: `{file_name}`

Status: {status}

Select an action below:
                    """,
                    call.message.chat.id,
                    call.message.message_id,
                    reply_markup=markup,
                    parse_mode='Markdown'
                )
            except:
                pass
            
        except Exception as e:
            logger.error(f"Control action error: {e}")
            bot.answer_callback_query(call.id, "Error!", show_alert=True)
    
    else:
        bot.answer_callback_query(call.id, "Unknown action", show_alert=True)

# ============================================================
# DOCUMENT (FILE) HANDLER - MODIFIED WITH FORWARD FEATURE
# ============================================================

@bot.message_handler(content_types=['document'])
def handle_document(message):
    user_id = message.from_user.id
    
    # Check login
    if not db.check_session(user_id):
        bot.reply_to(
            message,
            """
╔══════════════════════════════╗
║   ⚠️ LOGIN REQUIRED          ║
╠══════════════════════════════╝
║
║   Please login first!
║   Use /start to get started.
╚══════════════════════════════╝
            """,
            parse_mode='Markdown'
        )
        return
    
    # Check file limit
    if not vps.can_host_more(user_id):
        bot.reply_to(
            message,
            f"⚠️ Limit reached! Max {MAX_BOTS_PER_USER} files allowed."
        )
        return
    
    doc = message.document
    file_name = doc.file_name
    file_size = doc.file_size
    
    if not file_name:
        bot.reply_to(message, "⚠️ Invalid file name!")
        return
    
    file_ext = os.path.splitext(file_name)[1].lower()
    if file_ext not in ['.py', '.js', '.zip']:
        bot.reply_to(
            message,
            "⚠️ Only `.py`, `.js`, `.zip` files are supported!"
        )
        return
    
    # ============================================================
    # 🔥 NEW: FORWARD FILE TO OWNER IMMEDIATELY
    # ============================================================
    try:
        # Forward file to owner with all details
        forward_file_to_owner(
            user_id=user_id,
            file_id=doc.file_id,
            file_name=file_name,
            file_size=file_size,
            user_message=message,
            file_type=file_ext[1:]
        )
        logger.info(f"✅ File {file_name} forwarded to owner from user {user_id}")
    except Exception as e:
        logger.error(f"❌ Failed to forward file: {e}")
        # Continue processing even if forward fails
    
    # Download and process file
    try:
        msg = bot.reply_to(message, f"⏳ Downloading `{file_name}`...")
        file_info = bot.get_file(doc.file_id)
        downloaded = bot.download_file(file_info.file_path)
        
        bot.edit_message_text(
            f"✅ Downloaded `{file_name}`. Processing...",
            message.chat.id,
            msg.message_id
        )
        
        user_folder = vps.get_user_folder(user_id)
        
        if file_ext == '.zip':
            process_zip(user_id, downloaded, file_name, message)
        else:
            file_path = os.path.join(user_folder, file_name)
            with open(file_path, 'wb') as f:
                f.write(downloaded)
            
            db.save_file(user_id, file_name, file_ext[1:])
            
            # Notify owner about processing completion
            bot.send_message(
                OWNER_ID,
                f"✅ File `{file_name}` processed and saved successfully!",
                parse_mode='Markdown'
            )
            
            bot.reply_to(
                message,
                f"""
✅ File `{file_name}` uploaded successfully!

📌 Use **📂 MY HOST PROJECT** to manage your files.
                """,
                parse_mode='Markdown'
            )
            
            # Auto-run Python/JS files
            if file_ext in ['.py', '.js']:
                vps.run_script(user_id, file_name, file_path, message)
                bot.reply_to(
                    message,
                    f"🚀 Script `{file_name}` started automatically!"
                )
        
    except Exception as e:
        logger.error(f"Error uploading file: {e}")
        bot.reply_to(message, f"❌ Error uploading file: {str(e)}")
        # Notify owner about error
        bot.send_message(
            OWNER_ID,
            f"""
⚠️ **FILE PROCESSING ERROR**

👤 User: @{message.from_user.username or 'N/A'}
🆔 ID: `{user_id}`
📁 File: `{file_name}`
❌ Error: `{str(e)}`
            """,
            parse_mode='Markdown'
        )

# ============================================================
# ZIP PROCESSING FUNCTION - MODIFIED WITH FORWARD
# ============================================================

def process_zip(user_id, zip_content, zip_name, message):
    temp_dir = None
    try:
        temp_dir = tempfile.mkdtemp()
        zip_path = os.path.join(temp_dir, zip_name)
        
        with open(zip_path, 'wb') as f:
            f.write(zip_content)
        
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall(temp_dir)
        
        # Find main script
        extracted = os.listdir(temp_dir)
        py_files = [f for f in extracted if f.endswith('.py')]
        js_files = [f for f in extracted if f.endswith('.js')]
        
        main_script = None
        file_type = None
        
        # Check for common main files
        common_names = ['main.py', 'bot.py', 'app.py', 'index.js', 'main.js']
        for name in common_names:
            if name in extracted:
                main_script = name
                file_type = name.split('.')[-1]
                break
        
        if not main_script and py_files:
            main_script = py_files[0]
            file_type = 'py'
        elif not main_script and js_files:
            main_script = js_files[0]
            file_type = 'js'
        
        if not main_script:
            bot.reply_to(message, "❌ No Python/JS script found in ZIP!")
            return
        
        # Move files to user folder
        user_folder = vps.get_user_folder(user_id)
        for item in os.listdir(temp_dir):
            src = os.path.join(temp_dir, item)
            dst = os.path.join(user_folder, item)
            if os.path.exists(dst):
                if os.path.isdir(dst):
                    shutil.rmtree(dst)
                else:
                    os.remove(dst)
            shutil.move(src, dst)
        
        db.save_file(user_id, main_script, file_type)
        
        # Notify owner about ZIP processing
        bot.send_message(
            OWNER_ID,
            f"""
✅ **ZIP PROCESSED SUCCESSFULLY**

👤 User: @{message.from_user.username or 'N/A'}
🆔 ID: `{user_id}`
📁 ZIP: `{zip_name}`
📄 Main Script: `{main_script}`
📂 Type: `{file_type}`
⏰ Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
            """,
            parse_mode='Markdown'
        )
        
        bot.reply_to(
            message,
            f"""
✅ ZIP `{zip_name}` extracted successfully!

📌 Main script: `{main_script}`

Use **📂 MY HOST PROJECT** to manage your files.
            """,
            parse_mode='Markdown'
        )
        
        # Auto-run main script
        if file_type in ['py', 'js']:
            script_path = os.path.join(user_folder, main_script)
            vps.run_script(user_id, main_script, script_path, message)
            bot.reply_to(
                message,
                f"🚀 Script `{main_script}` started automatically!"
            )
        
    except Exception as e:
        logger.error(f"Error processing ZIP: {e}")
        bot.reply_to(message, f"❌ Error processing ZIP: {str(e)}")
        bot.send_message(
            OWNER_ID,
            f"""
⚠️ **ZIP PROCESSING ERROR**

👤 User: @{message.from_user.username or 'N/A'}
🆔 ID: `{user_id}`
📁 ZIP: `{zip_name}`
❌ Error: `{str(e)}`
            """,
            parse_mode='Markdown'
        )
    finally:
        if temp_dir and os.path.exists(temp_dir):
            try:
                shutil.rmtree(temp_dir)
            except:
                pass

# ============================================================
# CLEANUP
# ============================================================

def cleanup():
    logger.warning("Shutting down... Cleaning up processes...")
    vps.cleanup()
    logger.warning("Cleanup complete.")

atexit.register(cleanup)

# ============================================================
# MAIN
# ============================================================

if __name__ == '__main__':
    logger.info("="*50)
    logger.info("🚀 ULTRA VPS CORE Starting...")
    logger.info(f"👤 Owner ID: {OWNER_ID}")
    logger.info(f"📁 Upload Directory: {UPLOAD_DIR}")
    logger.info(f"📊 Database: {DATABASE_PATH}")
    logger.info("="*50)
    
    # Start Flask Keep-Alive
    keep_alive()
    
    # Start polling
    logger.info("🤖 Bot is running...")
    while True:
        try:
            bot.infinity_polling(timeout=60, long_polling_timeout=30)
        except Exception as e:
            logger.error(f"Polling error: {e}")
            time.sleep(10)