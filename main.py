import asyncio
import os
import sys
import logging
import subprocess
import shutil
import zipfile
import sqlite3
import json
import psutil
import signal
import traceback
from pathlib import Path
from datetime import datetime, timedelta
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, FSInputFile, CallbackQuery
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError

load_dotenv()

# Logging setup
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# --- CONFIGURATION ---
LD = "8980448040:AAFHqpQDt8wriL7EI4gfD2yaOIYBB9bhu_w"
ADMIN_ID = 7326248826
MAX_BOTS_PER_USER = 5

# Force Join Channels
CHANNEL_1_ID = "@SEMY_FF"  # Replace with your channel username or ID
CHANNEL_1_LINK = "https://t.me/SEMY_FF"
CHANNEL_2_ID = -1003885062938  # Replace with your channel username or ID
CHANNEL_2_LINK = "https://t.me/+n0W7fc-r35JjNDRl"

BASE_DIR = Path(__file__).parent.absolute()
SERVERS_DIR = BASE_DIR / 'vps_hosted_bots'
DATABASE_PATH = BASE_DIR / 'vps_manager.db'

SERVERS_DIR.mkdir(exist_ok=True)

bot = Bot(token=LD)
dp = Dispatcher(storage=MemoryStorage())

# Active processes track
active_processes = {}

# --- DATABASE SETUP ---
def init_db():
    conn = sqlite3.connect(DATABASE_PATH)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS vps_bots
                 (server_id TEXT PRIMARY KEY, 
                  user_id INTEGER,
                  name TEXT, 
                  path TEXT, 
                  main_file TEXT, 
                  status TEXT,
                  created_at TIMESTAMP)''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS users
                 (user_id INTEGER PRIMARY KEY,
                  username TEXT,
                  first_name TEXT,
                  joined_at TIMESTAMP,
                  is_verified BOOLEAN DEFAULT 0)''')
    conn.commit()
    conn.close()

init_db()

# --- STATES ---
class BotStates(StatesGroup):
    waiting_for_bot_file = State()

# --- USER VERIFICATION ---
async def check_user_verification(user_id: int) -> bool:
    try:
        # Check Channel 1
        try:
            member1 = await bot.get_chat_member(CHANNEL_1_ID, user_id)
        except Exception:
            member1 = None
        
        # Check Channel 2
        try:
            member2 = await bot.get_chat_member(CHANNEL_2_ID, user_id)
        except Exception:
            member2 = None
        
        if member1 and member2 and \
           member1.status in ['member', 'administrator', 'creator'] and \
           member2.status in ['member', 'administrator', 'creator']:
            conn = sqlite3.connect(DATABASE_PATH)
            c = conn.cursor()
            c.execute("UPDATE users SET is_verified = 1 WHERE user_id = ?", (user_id,))
            conn.commit()
            conn.close()
            return True
        return False
    except Exception as e:
        logger.error(f"Verification check error: {e}")
        return False

def get_force_join_keyboard():
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📢 Join Channel 1", url=CHANNEL_1_LINK),
            InlineKeyboardButton(text="📢 Join Channel 2", url=CHANNEL_2_LINK)
        ],
        [InlineKeyboardButton(text="✅ I've Joined! Verify Now", callback_data="verify_user")]
    ])
    return keyboard

# --- KEYBOARDS ---
def get_main_keyboard(user_id: int = None):
    keyboard_buttons = [
        [InlineKeyboardButton(text="📤 Host New Bot", callback_data="host_new")],
        [InlineKeyboardButton(text="🤖 My Hosted Bots", callback_data="my_bots")],
        [InlineKeyboardButton(text="📊 System Status", callback_data="system_status")]
    ]
    
    if user_id == ADMIN_ID:
        keyboard_buttons.append([InlineKeyboardButton(text="🔧 Admin Panel", callback_data="admin_panel")])
    
    return InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)

def get_bot_control_keyboard(server_id: str, is_running: bool):
    buttons = []
    
    if is_running:
        buttons.append([InlineKeyboardButton(text="🛑 Stop Bot", callback_data=f"stop_bot:{server_id}")])
    else:
        buttons.append([InlineKeyboardButton(text="▶️ Start Bot", callback_data=f"start_bot:{server_id}")])
    
    buttons.append([
        InlineKeyboardButton(text="📄 View Logs", callback_data=f"view_logs:{server_id}"),
        InlineKeyboardButton(text="📁 Download Files", callback_data=f"download_files:{server_id}")
    ])
    buttons.append([
        InlineKeyboardButton(text="🔄 Restart Bot", callback_data=f"restart_bot:{server_id}"),
        InlineKeyboardButton(text="🗑️ Delete Bot", callback_data=f"delete_bot:{server_id}")
    ])
    buttons.append([InlineKeyboardButton(text="🔙 Back to List", callback_data="my_bots")])
    
    return InlineKeyboardMarkup(inline_keyboard=buttons)

# --- COMMANDS ---
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    user_id = message.from_user.id
    username = message.from_user.username or "No Username"
    first_name = message.from_user.first_name or "Unknown"
    
    # Save user to database
    conn = sqlite3.connect(DATABASE_PATH)
    c = conn.cursor()
    c.execute("INSERT OR IGNORE INTO users (user_id, username, first_name, joined_at, is_verified) VALUES (?, ?, ?, ?, 0)",
              (user_id, username, first_name, datetime.now()))
    conn.commit()
    conn.close()
    
    is_verified = await check_user_verification(user_id)
    
    if not is_verified:
        welcome_text = f"""
👋 <b>Welcome {first_name}!</b>

🔒 <b>Please Join Our Channels First!</b>

To use this bot, you must join both channels below:

📢 <b>Channel 1:</b> {CHANNEL_1_LINK}
📢 <b>Channel 2:</b> {CHANNEL_2_LINK}

👇 <b>Steps:</b>
1. Click both join buttons above
2. Join both channels
3. Click "I've Joined! Verify Now" button

After verification, you'll get full access to host and manage your bots!
"""
        await message.answer(welcome_text, reply_markup=get_force_join_keyboard(), parse_mode="HTML")
        return
    
    welcome_text = f"""
🖥️ <b>WELCOME TO VPS BOT HOSTING</b> 🖥️
-----------------------------------------

👋 Hello {first_name}!

🎯 <b>Features:</b>
• Host up to {MAX_BOTS_PER_USER} bots
• Each bot runs in isolated environment
• Real-time logs and error monitoring
• Easy start/stop/restart management
• Download bot files anytime

📊 <b>Your Stats:</b>
Total Bots: {get_user_bot_count(user_id)}/{MAX_BOTS_PER_USER}

Use the buttons below to get started!
"""
    await message.answer(welcome_text, reply_markup=get_main_keyboard(user_id), parse_mode="HTML")

# --- VERIFICATION CALLBACK ---
@dp.callback_query(F.data == "verify_user")
async def verify_user(callback: CallbackQuery):
    user_id = callback.from_user.id
    is_verified = await check_user_verification(user_id)
    
    if is_verified:
        conn = sqlite3.connect(DATABASE_PATH)
        c = conn.cursor()
        c.execute("UPDATE users SET is_verified = 1 WHERE user_id = ?", (user_id,))
        conn.commit()
        conn.close()
        
        await callback.message.delete()
        await callback.message.answer(
            "✅ <b>Verification Successful!</b>\n\nYou now have full access to the bot. Use the buttons below to get started!",
            reply_markup=get_main_keyboard(user_id),
            parse_mode="HTML"
        )
        await callback.answer("✅ Verified Successfully!")
    else:
        await callback.answer("❌ Please join both channels first!", show_alert=True)
        await callback.message.edit_text(
            "🔒 <b>Please Join Both Channels First!</b>\n\n"
            "Click the buttons below to join, then click verify.",
            reply_markup=get_force_join_keyboard(),
            parse_mode="HTML"
        )

# --- IMPROVED VENV CREATION ---
def create_virtual_environment(venv_path: Path) -> bool:
    """Create virtual environment with multiple fallback methods"""
    try:
        # Method 1: Try python3 -m venv
        logger.info(f"Creating venv at {venv_path} using python -m venv")
        result = subprocess.run(
            [sys.executable, "-m", "venv", str(venv_path)],
            capture_output=True,
            text=True,
            timeout=60
        )
        
        if result.returncode == 0:
            logger.info("✅ venv created with python -m venv")
            return True
        else:
            logger.warning(f"venv creation failed: {result.stderr}")
        
        # Method 2: Try virtualenv command
        logger.info("Trying with virtualenv...")
        result = subprocess.run(
            ["virtualenv", str(venv_path)],
            capture_output=True,
            text=True,
            timeout=60
        )
        
        if result.returncode == 0:
            logger.info("✅ venv created with virtualenv")
            return True
        else:
            logger.warning(f"virtualenv failed: {result.stderr}")
        
        # Method 3: Try python3 -m virtualenv
        logger.info("Trying with python -m virtualenv...")
        result = subprocess.run(
            [sys.executable, "-m", "virtualenv", str(venv_path)],
            capture_output=True,
            text=True,
            timeout=60
        )
        
        if result.returncode == 0:
            logger.info("✅ venv created with python -m virtualenv")
            return True
        
        logger.error("All venv creation methods failed")
        return False
        
    except subprocess.TimeoutExpired:
        logger.error("Timeout creating venv")
        return False
    except Exception as e:
        logger.error(f"Error creating venv: {e}")
        return False

# --- HOST NEW BOT ---
@dp.callback_query(F.data == "host_new")
async def host_new_bot(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    
    if not await check_user_verification(user_id):
        await callback.answer("❌ Please verify by joining channels first!", show_alert=True)
        return
    
    bot_count = get_user_bot_count(user_id)
    if bot_count >= MAX_BOTS_PER_USER:
        await callback.answer(f"❌ You've reached the limit of {MAX_BOTS_PER_USER} bots!", show_alert=True)
        return
    
    await state.set_state(BotStates.waiting_for_bot_file)
    
    text = f"""
📤 <b>HOST A NEW BOT</b>

📁 <b>Instructions:</b>
• Send a <code>.py</code> file OR a <code>.zip</code> file
• For ZIP: main file should be <code>bot.py</code> or <code>main.py</code>
• Include <code>requirements.txt</code> in ZIP for auto-install

📊 <b>Your Bots:</b> {bot_count}/{MAX_BOTS_PER_USER}

⚠️ <b>Note:</b> Your file will be forwarded to admin for verification.
"""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Cancel", callback_data="back_to_main")]
    ])
    
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
    await callback.answer()

# --- IMPROVED FILE HANDLING ---
@dp.message(BotStates.waiting_for_bot_file, F.document)
async def handle_bot_upload(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    
    if not await check_user_verification(user_id):
        await message.answer("❌ Please verify by joining channels first!")
        return
    
    if get_user_bot_count(user_id) >= MAX_BOTS_PER_USER:
        await message.answer(f"❌ You've reached the limit of {MAX_BOTS_PER_USER} bots!")
        return
    
    doc = message.document
    filename = doc.file_name
    
    if not (filename.endswith('.py') or filename.endswith('.zip')):
        await message.answer("❌ Only <code>.py</code> or <code>.zip</code> files are allowed!", parse_mode="HTML")
        return
    
    # Forward to admin (with error handling)
    try:
        await bot.forward_message(ADMIN_ID, message.chat.id, message.message_id)
        await bot.send_message(ADMIN_ID, f"📨 New bot upload from @{message.from_user.username or 'Unknown'}")
    except TelegramForbiddenError:
        logger.warning("Admin hasn't started the bot yet. Can't forward.")
    except Exception as e:
        logger.error(f"Error forwarding to admin: {e}")
    
    status_msg = await message.answer("⏳ Processing your bot... (This may take a few minutes)")
    
    server_id = f"bot_{user_id}_{int(datetime.now().timestamp())}"
    bot_dir = SERVERS_DIR / server_id
    bot_dir.mkdir(parents=True, exist_ok=True)
    
    file_path = bot_dir / filename
    await bot.download(doc, destination=file_path)
    
    try:
        await status_msg.edit_text("⚙️ Setting up isolated environment...")
        
        venv_path = bot_dir / "venv"
        use_venv = create_virtual_environment(venv_path)
        
        if use_venv:
            # Use venv
            if os.name == 'nt':
                python_exe = venv_path / "Scripts" / "python.exe"
                pip_exe = venv_path / "Scripts" / "pip.exe"
            else:
                python_exe = venv_path / "bin" / "python"
                pip_exe = venv_path / "bin" / "pip"
        else:
            # Fallback to system Python
            await status_msg.edit_text("⚠️ Using system Python (dependencies may conflict)")
            python_exe = sys.executable
            pip_exe = shutil.which("pip") or shutil.which("pip3")
        
        main_script = file_path
        
        # Handle ZIP files
        if filename.endswith('.zip'):
            await status_msg.edit_text("📦 Extracting files...")
            with zipfile.ZipFile(file_path, 'r') as zip_ref:
                zip_ref.extractall(bot_dir)
            
            # Find main file
            if (bot_dir / "main.py").exists():
                main_script = bot_dir / "main.py"
            elif (bot_dir / "bot.py").exists():
                main_script = bot_dir / "bot.py"
            else:
                py_files = list(bot_dir.glob("*.py"))
                if py_files:
                    main_script = py_files[0]
            
            # Install requirements
            req_file = bot_dir / "requirements.txt"
            if req_file.exists() and pip_exe:
                await status_msg.edit_text("📦 Installing dependencies...")
                try:
                    result = subprocess.run(
                        [str(pip_exe), "install", "--no-cache-dir", "-r", str(req_file)],
                        capture_output=True,
                        text=True,
                        timeout=300
                    )
                    if result.returncode != 0:
                        logger.error(f"Pip install error: {result.stderr}")
                        await status_msg.edit_text(
                            f"⚠️ Some dependencies failed to install. Bot may not work.\n\nError: {result.stderr[:200]}"
                        )
                except Exception as e:
                    logger.error(f"Pip install exception: {e}")
        
        # Create log files
        stdout_log = bot_dir / "output.log"
        stderr_log = bot_dir / "error.log"
        stdout_log.touch()
        stderr_log.touch()
        
        # Check if main script exists
        if not main_script.exists():
            await status_msg.edit_text("❌ Main script not found! Make sure you have bot.py or main.py")
            return
        
        # Start the bot
        await status_msg.edit_text("🚀 Starting your bot...")
        
        python_cmd = str(python_exe) if python_exe else sys.executable
        
        with open(stdout_log, 'w') as out, open(stderr_log, 'w') as err:
            process = subprocess.Popen(
                [python_cmd, str(main_script)],
                cwd=str(bot_dir),
                stdout=out,
                stderr=err,
                start_new_session=True
            )
        
        active_processes[server_id] = process
        
        # Save to database
        conn = sqlite3.connect(DATABASE_PATH)
        c = conn.cursor()
        c.execute(
            "INSERT INTO vps_bots (server_id, user_id, name, path, main_file, status, created_at) VALUES (?, ?, ?, ?, ?, 'RUNNING', ?)",
            (server_id, user_id, filename, str(bot_dir), str(main_script), datetime.now())
        )
        conn.commit()
        conn.close()
        
        await status_msg.edit_text(
            f"✅ <b>Bot Hosted Successfully!</b>\n\n"
            f"🆔 <b>ID:</b> <code>{server_id}</code>\n"
            f"📦 <b>Name:</b> {filename}\n"
            f"🟢 <b>Status:</b> RUNNING\n"
            f"📊 <b>Your Bots:</b> {get_user_bot_count(user_id)}/{MAX_BOTS_PER_USER}\n\n"
            f"Use the button below to manage your bot!",
            reply_markup=get_main_keyboard(user_id),
            parse_mode="HTML"
        )
        
    except subprocess.TimeoutExpired:
        await status_msg.edit_text("❌ Timeout: Installation took too long!")
    except Exception as e:
        logger.error(f"Error hosting bot: {traceback.format_exc()}")
        await status_msg.edit_text(f"❌ Failed to host bot: {str(e)[:200]}")
    
    await state.clear()

@dp.message(BotStates.waiting_for_bot_file)
async def handle_invalid_file(message: types.Message, state: FSMContext):
    await message.answer("❌ Please send a <code>.py</code> or <code>.zip</code> file only!", parse_mode="HTML")

# --- MY BOTS ---
@dp.callback_query(F.data == "my_bots")
async def my_bots(callback: CallbackQuery):
    user_id = callback.from_user.id
    
    if not await check_user_verification(user_id):
        await callback.answer("❌ Please verify by joining channels first!", show_alert=True)
        return
    
    conn = sqlite3.connect(DATABASE_PATH)
    c = conn.cursor()
    c.execute("SELECT server_id, name, status, created_at FROM vps_bots WHERE user_id = ? ORDER BY created_at DESC", (user_id,))
    rows = c.fetchall()
    conn.close()
    
    if not rows:
        text = "🤖 <b>You haven't hosted any bots yet!</b>\n\nClick 'Host New Bot' to get started."
        await callback.message.edit_text(text, reply_markup=get_main_keyboard(user_id), parse_mode="HTML")
        return
    
    text = f"🤖 <b>Your Hosted Bots</b> ({len(rows)}/{MAX_BOTS_PER_USER})\n\n"
    
    for srv_id, name, status, created_at in rows:
        is_running = srv_id in active_processes and active_processes[srv_id].poll() is None
        status_icon = "🟢" if is_running else "🔴"
        status_text = "RUNNING" if is_running else "STOPPED"
        
        created = datetime.strptime(created_at, '%Y-%m-%d %H:%M:%S.%f')
        days = (datetime.now() - created).days
        
        text += f"<b>📦 {name}</b>\n"
        text += f"🆔 <code>{srv_id}</code>\n"
        text += f"⚡ {status_icon} {status_text}\n"
        text += f"📅 {days} days ago\n"
        text += f"─" * 30 + "\n\n"
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 Refresh", callback_data="my_bots")],
        [InlineKeyboardButton(text="🔙 Main Menu", callback_data="back_to_main")]
    ])
    
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")

# --- BOT CONTROL ---
@dp.callback_query(F.data.startswith("bot_control:"))
async def bot_control(callback: CallbackQuery):
    server_id = callback.data.split(":")[1]
    user_id = callback.from_user.id
    
    conn = sqlite3.connect(DATABASE_PATH)
    c = conn.cursor()
    c.execute("SELECT name, status FROM vps_bots WHERE server_id = ? AND user_id = ?", (server_id, user_id))
    row = c.fetchone()
    conn.close()
    
    if not row:
        await callback.answer("❌ Bot not found!", show_alert=True)
        return
    
    name, _ = row
    is_running = server_id in active_processes and active_processes[server_id].poll() is None
    
    text = f"""
🛠️ <b>Bot Control Panel</b>

📦 <b>Name:</b> {name}
🆔 <b>ID:</b> <code>{server_id}</code>
⚡ <b>Status:</b> {"🟢 RUNNING" if is_running else "🔴 STOPPED"}

What would you like to do?
"""
    await callback.message.edit_text(text, reply_markup=get_bot_control_keyboard(server_id, is_running), parse_mode="HTML")

# --- START BOT ---
@dp.callback_query(F.data.startswith("start_bot:"))
async def start_bot(callback: CallbackQuery):
    server_id = callback.data.split(":")[1]
    user_id = callback.from_user.id
    
    if server_id in active_processes and active_processes[server_id].poll() is None:
        await callback.answer("⚠️ Bot is already running!", show_alert=True)
        return
    
    conn = sqlite3.connect(DATABASE_PATH)
    c = conn.cursor()
    c.execute("SELECT path, main_file FROM vps_bots WHERE server_id = ? AND user_id = ?", (server_id, user_id))
    row = c.fetchone()
    conn.close()
    
    if not row:
        await callback.answer("❌ Bot not found!", show_alert=True)
        return
    
    bot_dir, main_script = Path(row[0]), Path(row[1])
    
    try:
        # Get Python executable
        venv_path = bot_dir / "venv"
        if venv_path.exists():
            if os.name == 'nt':
                python_exe = venv_path / "Scripts" / "python.exe"
            else:
                python_exe = venv_path / "bin" / "python"
        else:
            python_exe = sys.executable
        
        stdout_log = bot_dir / "output.log"
        stderr_log = bot_dir / "error.log"
        
        with open(stdout_log, 'a') as out, open(stderr_log, 'a') as err:
            process = subprocess.Popen(
                [str(python_exe), str(main_script)],
                cwd=str(bot_dir),
                stdout=out,
                stderr=err,
                start_new_session=True
            )
        
        active_processes[server_id] = process
        
        conn = sqlite3.connect(DATABASE_PATH)
        c = conn.cursor()
        c.execute("UPDATE vps_bots SET status = 'RUNNING' WHERE server_id = ?", (server_id,))
        conn.commit()
        conn.close()
        
        await callback.answer("✅ Bot started successfully!", show_alert=True)
        await bot_control(callback)
        
    except Exception as e:
        logger.error(f"Error starting bot: {e}")
        await callback.answer(f"❌ Failed to start bot: {str(e)[:100]}", show_alert=True)

# --- STOP BOT ---
@dp.callback_query(F.data.startswith("stop_bot:"))
async def stop_bot(callback: CallbackQuery):
    server_id = callback.data.split(":")[1]
    user_id = callback.from_user.id
    
    if server_id not in active_processes:
        await callback.answer("⚠️ Bot is already stopped!", show_alert=True)
        return
    
    try:
        process = active_processes[server_id]
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
        del active_processes[server_id]
        
        conn = sqlite3.connect(DATABASE_PATH)
        c = conn.cursor()
        c.execute("UPDATE vps_bots SET status = 'STOPPED' WHERE server_id = ? AND user_id = ?", (server_id, user_id))
        conn.commit()
        conn.close()
        
        await callback.answer("✅ Bot stopped successfully!", show_alert=True)
        await bot_control(callback)
        
    except Exception as e:
        logger.error(f"Error stopping bot: {e}")
        await callback.answer(f"❌ Failed to stop bot: {str(e)[:100]}", show_alert=True)

# --- RESTART BOT ---
@dp.callback_query(F.data.startswith("restart_bot:"))
async def restart_bot(callback: CallbackQuery):
    await callback.answer("🔄 Restarting bot...", show_alert=True)
    await stop_bot(callback)
    await asyncio.sleep(2)
    await start_bot(callback)

# --- VIEW LOGS ---
@dp.callback_query(F.data.startswith("view_logs:"))
async def view_logs(callback: CallbackQuery):
    server_id = callback.data.split(":")[1]
    user_id = callback.from_user.id
    
    conn = sqlite3.connect(DATABASE_PATH)
    c = conn.cursor()
    c.execute("SELECT path FROM vps_bots WHERE server_id = ? AND user_id = ?", (server_id, user_id))
    row = c.fetchone()
    conn.close()
    
    if not row:
        await callback.answer("❌ Bot not found!", show_alert=True)
        return
    
    bot_dir = Path(row[0])
    err_log = bot_dir / "error.log"
    out_log = bot_dir / "output.log"
    
    logs_text = ""
    
    if err_log.exists():
        with open(err_log, 'r') as f:
            error_content = f.read().strip()
            if error_content:
                logs_text += f"🔴 <b>ERROR LOGS:</b>\n<code>{error_content[-2000:]}</code>\n\n"
            else:
                logs_text += "🟢 No errors found!\n\n"
    
    if out_log.exists():
        with open(out_log, 'r') as f:
            out_content = f.read().strip()
            if out_content:
                logs_text += f"📋 <b>OUTPUT LOGS:</b>\n<code>{out_content[-2000:]}</code>"
            else:
                logs_text += "📋 No output yet!"
    
    if not logs_text:
        logs_text = "📭 No logs available yet!"
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 Refresh Logs", callback_data=f"view_logs:{server_id}")],
        [InlineKeyboardButton(text="🔙 Back to Control", callback_data=f"bot_control:{server_id}")]
    ])
    
    try:
        await callback.message.edit_text(logs_text, reply_markup=keyboard, parse_mode="HTML")
    except TelegramBadRequest:
        await callback.message.edit_text("📝 Logs are too long! Here's the last part:", reply_markup=keyboard)
        await callback.message.answer(logs_text[:4000], parse_mode="HTML")

# --- DOWNLOAD FILES ---
@dp.callback_query(F.data.startswith("download_files:"))
async def download_files(callback: CallbackQuery):
    server_id = callback.data.split(":")[1]
    user_id = callback.from_user.id
    
    conn = sqlite3.connect(DATABASE_PATH)
    c = conn.cursor()
    c.execute("SELECT path, name FROM vps_bots WHERE server_id = ? AND user_id = ?", (server_id, user_id))
    row = c.fetchone()
    conn.close()
    
    if not row:
        await callback.answer("❌ Bot not found!", show_alert=True)
        return
    
    bot_dir, bot_name = Path(row[0]), row[1]
    
    await callback.answer("📁 Preparing files...")
    await callback.message.answer(f"📦 Downloading files for <code>{bot_name}</code>...", parse_mode="HTML")
    
    zip_path = bot_dir / f"{bot_name}_files.zip"
    file_count = 0
    
    try:
        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for file in bot_dir.rglob("*"):
                if "venv" not in str(file) and file.is_file() and file.name not in ['output.log', 'error.log']:
                    arcname = file.relative_to(bot_dir)
                    zipf.write(file, arcname)
                    file_count += 1
        
        if file_count > 0:
            await callback.message.reply_document(
                document=FSInputFile(str(zip_path)),
                caption=f"📦 <b>{bot_name}</b>\n📁 {file_count} files included",
                parse_mode="HTML"
            )
        else:
            await callback.message.answer("📭 No files to download!")
        
        zip_path.unlink(missing_ok=True)
        
    except Exception as e:
        logger.error(f"Error creating zip: {e}")
        await callback.message.answer(f"❌ Error creating zip: {str(e)[:100]}")

# --- DELETE BOT ---
@dp.callback_query(F.data.startswith("delete_bot:"))
async def delete_bot(callback: CallbackQuery):
    server_id = callback.data.split(":")[1]
    user_id = callback.from_user.id
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Yes, Delete", callback_data=f"confirm_delete:{server_id}"),
            InlineKeyboardButton(text="❌ Cancel", callback_data=f"bot_control:{server_id}")
        ]
    ])
    
    await callback.message.edit_text(
        "⚠️ <b>Are you sure you want to delete this bot?</b>\n\n"
        "This action cannot be undone! All files and data will be permanently removed.",
        reply_markup=keyboard,
        parse_mode="HTML"
    )

@dp.callback_query(F.data.startswith("confirm_delete:"))
async def confirm_delete(callback: CallbackQuery):
    server_id = callback.data.split(":")[1]
    user_id = callback.from_user.id
    
    if server_id in active_processes:
        try:
            process = active_processes[server_id]
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
            del active_processes[server_id]
        except:
            pass
    
    conn = sqlite3.connect(DATABASE_PATH)
    c = conn.cursor()
    c.execute("SELECT path FROM vps_bots WHERE server_id = ? AND user_id = ?", (server_id, user_id))
    row = c.fetchone()
    
    if row:
        bot_dir = Path(row[0])
        try:
            if bot_dir.exists():
                shutil.rmtree(bot_dir)
        except Exception as e:
            logger.error(f"Error deleting directory: {e}")
        
        c.execute("DELETE FROM vps_bots WHERE server_id = ? AND user_id = ?", (server_id, user_id))
        conn.commit()
    
    conn.close()
    
    await callback.answer("🗑️ Bot deleted successfully!", show_alert=True)
    await my_bots(callback)

# --- SYSTEM STATUS ---
@dp.callback_query(F.data == "system_status")
async def system_status(callback: CallbackQuery):
    user_id = callback.from_user.id
    
    if not await check_user_verification(user_id):
        await callback.answer("❌ Please verify by joining channels first!", show_alert=True)
        return
    
    cpu_percent = psutil.cpu_percent(interval=1)
    memory = psutil.virtual_memory()
    disk = psutil.disk_usage('/')
    
    total_bots = get_total_bots()
    running_bots = len(active_processes)
    user_bots = get_user_bot_count(user_id)
    
    status_text = f"""
📊 <b>SYSTEM STATUS</b>
-----------------------------------------

🖥️ <b>System Resources:</b>
• CPU Usage: {cpu_percent}%
• RAM Usage: {memory.percent}% ({memory.used // (1024**3)}GB/{memory.total // (1024**3)}GB)
• Disk Usage: {disk.percent}% ({disk.used // (1024**3)}GB/{disk.total // (1024**3)}GB)

🤖 <b>Bot Statistics:</b>
• Total Bots: {total_bots}
• Running Bots: {running_bots}
• Your Bots: {user_bots}/{MAX_BOTS_PER_USER}

⏱️ <b>System Uptime:</b>
{get_uptime()}
"""
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 Refresh", callback_data="system_status")],
        [InlineKeyboardButton(text="🔙 Main Menu", callback_data="back_to_main")]
    ])
    
    await callback.message.edit_text(status_text, reply_markup=keyboard, parse_mode="HTML")

# --- ADMIN PANEL ---
@dp.callback_query(F.data == "admin_panel")
async def admin_panel(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("❌ Admin only!", show_alert=True)
        return
    
    conn = sqlite3.connect(DATABASE_PATH)
    c = conn.cursor()
    
    total_users = c.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    total_bots = c.execute("SELECT COUNT(*) FROM vps_bots").fetchone()[0]
    running_bots = len(active_processes)
    
    conn.close()
    
    text = f"""
🔧 <b>ADMIN PANEL</b>
-----------------------------------------

📊 <b>Statistics:</b>
• Total Users: {total_users}
• Total Bots: {total_bots}
• Running Bots: {running_bots}

🛠️ <b>Admin Actions:</b>
"""
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👥 All Users", callback_data="admin_users")],
        [InlineKeyboardButton(text="🤖 All Bots", callback_data="admin_bots")],
        [InlineKeyboardButton(text="🔄 Restart All Bots", callback_data="admin_restart_all")],
        [InlineKeyboardButton(text="🔙 Main Menu", callback_data="back_to_main")]
    ])
    
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")

@dp.callback_query(F.data == "admin_users")
async def admin_users(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        return
    
    conn = sqlite3.connect(DATABASE_PATH)
    c = conn.cursor()
    users = c.execute("SELECT user_id, username, first_name, joined_at, is_verified FROM users ORDER BY joined_at DESC LIMIT 20").fetchall()
    conn.close()
    
    if not users:
        await callback.message.edit_text("No users found!")
        return
    
    text = "👥 <b>Recent Users:</b>\n\n"
    for user_id, username, first_name, joined_at, is_verified in users:
        text += f"🆔 <code>{user_id}</code>\n"
        text += f"👤 {first_name} (@{username or 'No Username'})\n"
        text += f"✅ {'Verified' if is_verified else 'Not Verified'}\n"
        text += f"📅 {joined_at[:10]}\n"
        text += "-" * 30 + "\n\n"
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Back to Admin", callback_data="admin_panel")]
    ])
    
    await callback.message.edit_text(text[:4000], reply_markup=keyboard, parse_mode="HTML")

@dp.callback_query(F.data == "admin_bots")
async def admin_bots(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        return
    
    conn = sqlite3.connect(DATABASE_PATH)
    c = conn.cursor()
    bots = c.execute("SELECT server_id, user_id, name, status, created_at FROM vps_bots ORDER BY created_at DESC LIMIT 20").fetchall()
    conn.close()
    
    if not bots:
        await callback.message.edit_text("No bots found!")
        return
    
    text = "🤖 <b>All Bots:</b>\n\n"
    for srv_id, user_id, name, status, created_at in bots:
        is_running = srv_id in active_processes
        status_icon = "🟢" if is_running else "🔴"
        
        text += f"📦 {name}\n"
        text += f"🆔 <code>{srv_id}</code>\n"
        text += f"👤 User: <code>{user_id}</code>\n"
        text += f"⚡ {status_icon} {'RUNNING' if is_running else 'STOPPED'}\n"
        text += "-" * 30 + "\n\n"
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Back to Admin", callback_data="admin_panel")]
    ])
    
    await callback.message.edit_text(text[:4000], reply_markup=keyboard, parse_mode="HTML")

@dp.callback_query(F.data == "admin_restart_all")
async def admin_restart_all(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        return
    
    await callback.answer("🔄 Restarting all bots...", show_alert=True)
    
    restarted = 0
    for server_id in list(active_processes.keys()):
        try:
            process = active_processes[server_id]
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
            del active_processes[server_id]
            restarted += 1
        except:
            pass
    
    await callback.message.edit_text(f"✅ {restarted} bots have been restarted!")

# --- BACK TO MAIN ---
@dp.callback_query(F.data == "back_to_main")
async def back_to_main(callback: CallbackQuery):
    user_id = callback.from_user.id
    
    if not await check_user_verification(user_id):
        await callback.message.edit_text(
            "🔒 <b>Please Join Our Channels!</b>",
            reply_markup=get_force_join_keyboard(),
            parse_mode="HTML"
        )
        return
    
    welcome_text = f"""
🖥️ <b>WELCOME TO VPS BOT HOSTING</b> 🖥️
-----------------------------------------

👋 Hello {callback.from_user.first_name}!

🎯 <b>Features:</b>
• Host up to {MAX_BOTS_PER_USER} bots
• Each bot runs in isolated environment
• Real-time logs and error monitoring
• Easy start/stop/restart management
• Download bot files anytime

📊 <b>Your Stats:</b>
Total Bots: {get_user_bot_count(user_id)}/{MAX_BOTS_PER_USER}

Use the buttons below to get started!
"""
    await callback.message.edit_text(welcome_text, reply_markup=get_main_keyboard(user_id), parse_mode="HTML")

# --- HELPER FUNCTIONS ---
def get_user_bot_count(user_id: int) -> int:
    conn = sqlite3.connect(DATABASE_PATH)
    c = conn.cursor()
    count = c.execute("SELECT COUNT(*) FROM vps_bots WHERE user_id = ?", (user_id,)).fetchone()[0]
    conn.close()
    return count

def get_total_bots() -> int:
    conn = sqlite3.connect(DATABASE_PATH)
    c = conn.cursor()
    count = c.execute("SELECT COUNT(*) FROM vps_bots").fetchone()[0]
    conn.close()
    return count

def get_uptime() -> str:
    try:
        with open('/proc/uptime', 'r') as f:
            uptime_seconds = float(f.readline().split()[0])
            days = int(uptime_seconds // 86400)
            hours = int((uptime_seconds % 86400) // 3600)
            minutes = int((uptime_seconds % 3600) // 60)
            return f"{days}d {hours}h {minutes}m"
    except:
        return "N/A"

# --- MAIN ---
async def main():
    logger.info("🚀 VPS Bot Master Started!")
    logger.info(f"👤 Admin ID: {ADMIN_ID}")
    logger.info(f"📁 Base Directory: {BASE_DIR}")
    
    # Clean up zombie processes
    for process in list(active_processes.values()):
        try:
            if process.poll() is None:
                process.terminate()
        except:
            pass
    
    try:
        await dp.start_polling(bot)
    finally:
        for process in list(active_processes.values()):
            try:
                process.terminate()
            except:
                pass
        logger.info("🛑 Bot Shutting Down...")

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("👋 Bot stopped by user")
    except Exception as e:
        logger.error(f"Fatal error: {e}")