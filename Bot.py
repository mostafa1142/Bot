# استضافة بوتات بايثون - بلاك تيك  (نسخة مُصلّحة)
# المطور: BLACK TECH 👨‍💻
# البلد: مصر 🇪🇬

import sys
import telebot
from telebot import types
import os
import subprocess
import time
from datetime import datetime, timedelta
import threading
from collections import defaultdict
import tempfile
import shutil
import re
import sqlite3
import hashlib
import logging
import secrets
import requests
from io import BytesIO
import json
import traceback

# --------------------------------------------------
# 🔑 مفاتيح البوت والخدمات (محفوظة كما في الملف الأصلي)
# --------------------------------------------------
BOT_TOKEN = '8398552528:AAFw5DwGFJbkF-Ci2lGcIW9odY4ODueTpBI'
ADMIN_ID = 6346921239
DEVELOPER_USERNAME = '@BL_TH'
DEVELOPER_CHANNEL = '@S_S_H_44'

HOSTING_API_KEY = 'f01a191f1bd5b9c6ca83e7f45b6e2e7abbbd60d6'
VIRUSTOTAL_API_KEY = '0adcf14015013fe10c1eab029a4b2f81054499497cd991fc252dd965f6240a37'
FILESCAN_API_KEY = 'ywkQyze9b_qZAlCOAObVP_FXserwH7IXHLz_Kvv3'

bot = telebot.TeleBot(BOT_TOKEN)

# Logger بسيط
logging.basicConfig(level=logging.INFO, format='%(asctime)s | %(levelname)s | %(message)s')

# --------------------------------------------------
# SQLite helper (thread-safe-ish usage with check_same_thread=False)
# --------------------------------------------------
DB_PATH = 'bot_database.db'

def get_db_connection():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False, timeout=30)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    conn.execute("PRAGMA synchronous=NORMAL")
    return conn

# --------------------------------------------------
# تهيئة قاعدة البيانات -- ملاحظة هامة: لا نمسح DB عند كل تشغيل
# --------------------------------------------------
def init_database():
    try:
        first_time = not os.path.exists(DB_PATH)
        conn = get_db_connection()
        cursor = conn.cursor()

        # جدول المستخدمين مع جميع الأعمدة
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                points INTEGER DEFAULT 0,
                is_vip INTEGER DEFAULT 0,
                vip_expiry TEXT,
                is_banned INTEGER DEFAULT 0,
                join_date TEXT,
                last_active TEXT,
                referral_code TEXT UNIQUE,
                referred_by INTEGER,
                total_referred INTEGER DEFAULT 0,
                welcome_sent INTEGER DEFAULT 0,
                is_admin INTEGER DEFAULT 0
            )
        ''')

        # جدول الإعدادات
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        ''')

        # جدول القنوات الإجبارية
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS force_subscribe (
                channel_id TEXT PRIMARY KEY,
                channel_username TEXT,
                channel_name TEXT
            )
        ''')

        # جدول البوتات النشطة
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS active_bots (
                user_id INTEGER,
                bot_name TEXT,
                file_path TEXT,
                process_id INTEGER,
                start_time TEXT,
                status TEXT DEFAULT 'running'
            )
        ''')

        # الإعدادات الافتراضية
        default_settings = [
            ('welcome_message', '🎉 أهلاً وسهلاً بك في بوت استضافة البوتات!'),
            ('protection_level', 'medium'),
            ('bot_enabled', '1'),
            ('vip_enabled', '1'),
            ('force_subscription', '0'),
            ('points_per_file', '2'),
            ('points_per_referral', '2'),
            ('referral_enabled', '1'),
            ('new_user_notification', '1'),
            ('vip_price_week', '50'),
            ('vip_price_month', '150'),
            ('vip_price_year', '500')
        ]

        cursor.executemany('INSERT OR IGNORE INTO settings VALUES (?, ?)', default_settings)

        # إضافة الأدمن الأساسي
        cursor.execute('INSERT OR IGNORE INTO users (user_id, username, first_name, is_admin, join_date, last_active) VALUES (?, ?, ?, ?, ?, ?)',
                      (ADMIN_ID, 'BLACK_TECH', 'المطور', 1, datetime.now().strftime('%Y-%m-%d %H:%M:%S'), datetime.now().strftime('%Y-%m-%d %H:%M:%S')))

        conn.commit()
        conn.close()

        if first_time:
            logging.info("✅ تم إنشاء قاعدة البيانات الجديدة بنجاح")
        else:
            logging.info("ℹ️ قاعدة البيانات موجودة — لم يتم حذفها")

    except Exception as e:
        logging.error(f"❌ خطأ في إنشاء أو تهيئة قاعدة البيانات: {e}")
        logging.error(traceback.format_exc())

init_database()

# --------------------------------------------------
# دوال مساعدة للوصول للإعدادات والمستخدمين
# --------------------------------------------------
def get_setting(key):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT value FROM settings WHERE key = ?', (key,))
        result = cursor.fetchone()
        conn.close()
        return result[0] if result else None
    except Exception as e:
        logging.exception("get_setting error")
        return None

def update_setting(key, value):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('INSERT OR REPLACE INTO settings VALUES (?, ?)', (key, value))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        logging.exception("update_setting error")
        return False

def get_user(user_id):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
        result = cursor.fetchone()
        conn.close()
        return result
    except Exception as e:
        logging.exception("get_user error")
        return None

def is_admin(user_id):
    try:
        user_data = get_user(user_id)
        return bool(user_data and user_data[13] == 1)
    except Exception as e:
        logging.exception("is_admin error")
        return False

def add_admin(user_id, username, first_name):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT OR REPLACE INTO users 
            (user_id, username, first_name, join_date, last_active, is_admin) 
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (user_id, username, first_name, datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
              datetime.now().strftime('%Y-%m-%d %H:%M:%S'), 1))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        logging.exception("add_admin error")
        return False

def remove_admin(user_id):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('UPDATE users SET is_admin = 0 WHERE user_id = ?', (user_id,))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        logging.exception("remove_admin error")
        return False

def get_all_admins():
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT user_id, username, first_name FROM users WHERE is_admin = 1')
        results = cursor.fetchall()
        conn.close()
        return results
    except Exception as e:
        logging.exception("get_all_admins error")
        return []

def update_user(user_id, username, first_name):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute('SELECT user_id FROM users WHERE user_id = ?', (user_id,))
        existing_user = cursor.fetchone()

        is_new_user = not existing_user

        if is_new_user:
            referral_code = generate_referral_code(user_id)
            cursor.execute('''
                INSERT INTO users 
                (user_id, username, first_name, join_date, last_active, referral_code, welcome_sent, is_admin) 
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (user_id, username, first_name,
                  datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                  datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                  referral_code, 0, 0))
        else:
            cursor.execute('''
                UPDATE users SET 
                username = ?, first_name = ?, last_active = ?
                WHERE user_id = ?
            ''', (username, first_name, datetime.now().strftime('%Y-%m-%d %H:%M:%S'), user_id))

        conn.commit()
        conn.close()
        return is_new_user

    except Exception as e:
        logging.exception("update_user error")
        return False

def mark_welcome_sent(user_id):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('UPDATE users SET welcome_sent = 1 WHERE user_id = ?', (user_id,))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        logging.exception("mark_welcome_sent error")
        return False

def update_user_points(user_id, points):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('UPDATE users SET points = points + ? WHERE user_id = ?', (points, user_id))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        logging.exception("update_user_points error")
        return False

def set_user_points(user_id, points):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('UPDATE users SET points = ? WHERE user_id = ?', (points, user_id))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        logging.exception("set_user_points error")
        return False

def ban_user(user_id):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('UPDATE users SET is_banned = 1 WHERE user_id = ?', (user_id,))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        logging.exception("ban_user error")
        return False

def unban_user(user_id):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('UPDATE users SET is_banned = 0 WHERE user_id = ?', (user_id,))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        logging.exception("unban_user error")
        return False

def set_vip(user_id, days):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        expiry_date = (datetime.now() + timedelta(days=days)).strftime('%Y-%m-%d %H:%M:%S')
        cursor.execute('UPDATE users SET is_vip = 1, vip_expiry = ? WHERE user_id = ?', (expiry_date, user_id))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        logging.exception("set_vip error")
        return False

def remove_vip(user_id):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('UPDATE users SET is_vip = 0, vip_expiry = NULL WHERE user_id = ?', (user_id,))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        logging.exception("remove_vip error")
        return False

def get_all_users():
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM users ORDER BY join_date DESC')
        results = cursor.fetchall()
        conn.close()
        return results
    except Exception as e:
        logging.exception("get_all_users error")
        return []

def get_user_stats():
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute('SELECT COUNT(*) FROM users')
        total_users = cursor.fetchone()[0]

        cursor.execute('SELECT COUNT(*) FROM users WHERE is_vip = 1')
        vip_users = cursor.fetchone()[0]

        cursor.execute('SELECT COUNT(*) FROM users WHERE is_banned = 1')
        banned_users = cursor.fetchone()[0]

        cursor.execute('SELECT COUNT(*) FROM users WHERE is_admin = 1')
        admin_users = cursor.fetchone()[0]

        cursor.execute('SELECT COUNT(*) FROM users WHERE date(last_active) = date("now")')
        active_today = cursor.fetchone()[0]

        cursor.execute('SELECT COUNT(*) FROM users WHERE date(join_date) = date("now")')
        new_today = cursor.fetchone()[0]

        conn.close()

        return {
            'total_users': total_users,
            'vip_users': vip_users,
            'banned_users': banned_users,
            'admin_users': admin_users,
            'active_today': active_today,
            'new_today': new_today
        }
    except Exception as e:
        logging.exception("get_user_stats error")
        return {'total_users': 0, 'vip_users': 0, 'banned_users': 0, 'admin_users': 0, 'active_today': 0, 'new_today': 0}

# --------------------------------------------------
# نظام البوتات النشطة
# --------------------------------------------------
def add_active_bot(user_id, bot_name, file_path, process_id):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO active_bots (user_id, bot_name, file_path, process_id, start_time)
            VALUES (?, ?, ?, ?, ?)
        ''', (user_id, bot_name, file_path, process_id, datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        logging.exception("add_active_bot error")
        return False

def get_user_bots(user_id):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM active_bots WHERE user_id = ?', (user_id,))
        results = cursor.fetchall()
        conn.close()
        return results
    except Exception as e:
        logging.exception("get_user_bots error")
        return []

def stop_user_bots(user_id):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT process_id FROM active_bots WHERE user_id = ?', (user_id,))
        bots = cursor.fetchall()

        for bot_item in bots:
            pid = bot_item[0]
            try:
                # محاولة إيقاف العملية بأمان
                os.kill(pid, 9)
            except Exception:
                # قد لا يكون PID صالحاً أو لا تسمح Render بذلك
                logging.warning(f"Could not kill PID {pid} (ignored).")

        cursor.execute('DELETE FROM active_bots WHERE user_id = ?', (user_id,))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        logging.exception("stop_user_bots error")
        return False

# --------------------------------------------------
# نظام الاشتراك الإجباري
# --------------------------------------------------
def add_force_subscribe(channel_id, channel_username, channel_name):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('INSERT OR REPLACE INTO force_subscribe VALUES (?, ?, ?)',
                      (channel_id, channel_username, channel_name))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        logging.exception("add_force_subscribe error")
        return False

def remove_force_subscribe(channel_id):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('DELETE FROM force_subscribe WHERE channel_id = ?', (channel_id,))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        logging.exception("remove_force_subscribe error")
        return False

def get_force_subscribe_channels():
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM force_subscribe')
        results = cursor.fetchall()
        conn.close()
        return results
    except Exception as e:
        logging.exception("get_force_subscribe_channels error")
        return []

def check_subscription(user_id):
    try:
        channels = get_force_subscribe_channels()
        if not channels:
            return True

        for channel in channels:
            try:
                chat_member = bot.get_chat_member(channel[0], user_id)
                if chat_member.status in ['left', 'kicked']:
                    return False
            except Exception:
                return False
        return True
    except Exception as e:
        logging.exception("check_subscription error")
        return True

# --------------------------------------------------
# المتغيرات العامة
# --------------------------------------------------
approved_users = set()
pending_requests = {}
uploaded_files_dir = "uploaded_files"

if not os.path.exists(uploaded_files_dir):
    os.makedirs(uploaded_files_dir, exist_ok=True)

# --------------------------------------------------
# واجهة البداية / handlers
# --------------------------------------------------
@bot.message_handler(commands=['start'])
def start(message):
    try:
        user_id = message.from_user.id

        # التحقق من الاشتراك الإجباري
        if get_setting('force_subscription') == '1' and not check_subscription(user_id):
            channels = get_force_subscribe_channels()
            if channels:
                markup = types.InlineKeyboardMarkup()
                for channel in channels:
                    btn = types.InlineKeyboardButton(
                        f"📢 {channel[2]}",
                        url=f"https://t.me/{channel[1].replace('@', '')}"
                    )
                    markup.add(btn)

                check_btn = types.InlineKeyboardButton("✅ تحقق من الاشتراك", callback_data="check_subscription")
                markup.add(check_btn)

                bot.send_message(
                    message.chat.id,
                    "🔔 يجب الاشتراك في القنوات التالية أولاً:\n\n" +
                    "\n".join([f"• {channel[2]}" for channel in channels]),
                    reply_markup=markup
                )
                return

        command_parts = message.text.split()
        is_new_user = update_user(user_id, message.from_user.username, message.from_user.first_name)

        user_data = get_user(user_id)
        if user_data and user_data[6] == 1:
            bot.send_message(message.chat.id, "❌ تم حظرك من استخدام البوت")
            return

        if get_setting('bot_enabled') != '1':
            bot.send_message(message.chat.id, "⏸️ البوت متوقف حاليًا")
            return

        # إرسال إشعار للمطور مع صورة المستخدم الجديد
        if is_new_user and user_id != ADMIN_ID and get_setting('new_user_notification') == '1':
            send_user_notification_with_photo(user_id, message.from_user.first_name, message.from_user.username)
            mark_welcome_sent(user_id)

        if is_admin(user_id):
            show_admin_choice(message)
        elif user_id in approved_users or (user_data and user_data[4] == 1):
            send_user_welcome_with_photo(message)
        elif user_id in pending_requests:
            send_waiting_message(message.chat.id)
        else:
            user_info = {
                'first_name': message.from_user.first_name,
                'username': message.from_user.username or 'غير متوفر',
                'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            }
            request_approval(user_id, user_info)
            send_waiting_message(message.chat.id)

    except Exception as e:
        logging.exception("Error in start")
        bot.send_message(message.chat.id, "❌ حدث خطأ، يرجى المحاولة مرة أخرى")

# --------------------------------------------------
# إشعارات وصور المستخدم
# --------------------------------------------------
def send_user_notification_with_photo(user_id, first_name, username):
    try:
        # الحصول على صورة المستخدم
        user_profile_photos = bot.get_user_profile_photos(user_id, limit=1)

        caption = f"""
👤 مستخدم جديد انضم للبوت:

🆔 الآيدي: `{user_id}`
👤 الاسم: {first_name}
📌 اليوزر: @{username or 'غير متوفر'}
⏰ الوقت: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
        """

        if user_profile_photos.photos:
            # إذا كان لدى المستخدم صورة بروفايل
            file_id = user_profile_photos.photos[0][-1].file_id
            file_info = bot.get_file(file_id)
            downloaded_file = bot.download_file(file_info.file_path)

            photo = BytesIO(downloaded_file)
            photo.name = 'profile.jpg'

            bot.send_photo(
                ADMIN_ID,
                photo,
                caption=caption,
                parse_mode='Markdown'
            )
        else:
            # إذا لم يكن لدى المستخدم صورة بروفايل
            bot.send_message(ADMIN_ID, caption, parse_mode='Markdown')

    except Exception as e:
        logging.exception("send_user_notification_with_photo error")
        # إذا فشل إرسال الصورة، نرسل رسالة عادية
        try:
            bot.send_message(
                ADMIN_ID,
                f"👤 مستخدم جديد:\n🆔 {user_id}\n👤 {first_name}\n📌 @{username or 'غير متوفر'}"
            )
        except:
            pass

def send_user_welcome_with_photo(message):
    try:
        user_id = message.from_user.id
        user_data = get_user(user_id)
        points = user_data[3] if user_data else 0

        welcome_text = f"""
✨ • ━━━━━━ • ✦ • ━━━━━━ • ✨

🎊 أهلاً وسهلاً بك
╰┈➤ {message.from_user.first_name} 👑

🚀 في بوت استضافة البوتات المتقدم
╰┈➤ أقوى نظام استضافة على التليجرام 💫

💎 نقاطك الحالية: {points} نقطة
⭐ حسابك: {'🎖️ VIP' if user_data and user_data[4] == 1 else '👤 عادي'}

📊 اختر من القائمة أدناه: ⬇️
        """

        # محاولة الحصول على صورة المستخدم
        try:
            user_profile_photos = bot.get_user_profile_photos(user_id, limit=1)

            if user_profile_photos.photos:
                file_id = user_profile_photos.photos[0][-1].file_id
                file_info = bot.get_file(file_id)
                downloaded_file = bot.download_file(file_info.file_path)

                photo = BytesIO(downloaded_file)
                photo.name = 'profile.jpg'

                bot.send_photo(
                    message.chat.id,
                    photo,
                    caption=welcome_text,
                    reply_markup=create_user_menu_buttons(),
                    parse_mode='Markdown'
                )
                return
        except Exception:
            pass

        # إذا فشل إرسال الصورة، نرسل رسالة عادية
        bot.send_message(
            message.chat.id,
            welcome_text,
            reply_markup=create_user_menu_buttons(),
            parse_mode='Markdown'
        )

    except Exception as e:
        logging.exception("send_user_welcome_with_photo error")
        try:
            bot.send_message(
                message.chat.id,
                "🎊 أهلاً وسهلاً بك في بوت استضافة البوتات!",
                reply_markup=create_user_menu_buttons()
            )
        except:
            pass

# --------------------------------------------------
# لوحات وأزرار
# --------------------------------------------------
def show_admin_choice(message):
    markup = types.InlineKeyboardMarkup()

    user_panel_btn = types.InlineKeyboardButton("👤 لوحة المستخدم", callback_data='user_panel')
    admin_panel_btn = types.InlineKeyboardButton("👑 لوحة الأدمن", callback_data='admin_panel_main')
    markup.add(user_panel_btn, admin_panel_btn)

    bot.send_message(
        message.chat.id,
        """🎯 مرحباً بالأدمن

✨ يمكنك الاختيار بين:

👤 لوحة المستخدم - للاستخدام العادي
👑 لوحة الأدمن - لإدارة البوت

🎊 اختر ما يناسبك:""",
        reply_markup=markup
    )

def create_user_menu_buttons():
    markup = types.InlineKeyboardMarkup(row_width=2)

    buttons = [
        ("🤖 بوتاتي", "my_bots"),
        ("📤 رفع ملف", "upload_file"),
        ("📚 تثبيت مكتبة", "install_library"),
        ("⚡ قياس السرعة", "speed_test"),
        ("🛑 إيقاف البوتات", "stop_active_bots"),
        ("💎 نقاطي", "my_points"),
        ("🎁 زيادة النقاط", "increase_points"),
        ("👥 دعوة الأصدقاء", "referral_system"),
        ("🔄 تحويل النقاط", "transfer_points"),
        ("📋 القوانين", "bot_rules"),
        ("❓ المساعدة", "help_page"),
        ("👨‍💻 المطور", "developer"),
        ("📢 قناة البوت", "bot_channel")
    ]

    row = []
    for i, (text, callback) in enumerate(buttons):
        btn = types.InlineKeyboardButton(text, callback_data=callback)
        row.append(btn)
        if len(row) == 2 or i == len(buttons) - 1:
            markup.add(*row)
            row = []

    return markup

def create_admin_panel_buttons():
    markup = types.InlineKeyboardMarkup(row_width=2)

    buttons = [
        ("📊 الإحصائيات", "admin_stats"),
        ("👥 إدارة المستخدمين", "manage_users"),
        ("⚙️ الإعدادات", "admin_settings"),
        ("🛡️ نظام الحماية", "protection_settings"),
        ("📢 الإذاعة", "broadcast_message"),
        ("🔔 التنبيهات", "notifications_settings"),
        ("💎 إدارة النقاط", "points_management"),
        ("🚫 إدارة الحظر", "ban_management"),
        ("⭐ نظام VIP", "vip_management"),
        ("👑 إدارة الأدمن", "admin_management"),
        ("📝 رسالة الترحيب", "welcome_message_edit"),
        ("🔧 إعدادات البوت", "bot_settings"),
        ("📁 الملفات المعلقة", "pending_files_admin"),
        ("📢 الاشتراك الإجباري", "force_subscribe_management")
    ]

    row = []
    for i, (text, callback) in enumerate(buttons):
        btn = types.InlineKeyboardButton(text, callback_data=callback)
        row.append(btn)
        if len(row) == 2 or i == len(buttons) - 1:
            markup.add(*row)
            row = []

    back_btn = types.InlineKeyboardButton("🔙 رجوع", callback_data='back_to_main')
    markup.add(back_btn)

    return markup

# --------------------------------------------------
# معالجة الاستجابات (callbacks)
# --------------------------------------------------
@bot.callback_query_handler(func=lambda call: True)
def handle_callback_queries(call):
    try:
        data = call.data or ''
        # المدير العام للأزرار - استدعاء الدوال المناسبة
        if data == 'admin_panel_main':
            admin_panel_main(call)
        elif data == 'user_panel':
            user_panel(call)
        elif data == 'admin_stats':
            admin_stats(call)
        elif data == 'admin_management':
            admin_management(call)
        elif data == 'force_subscribe_management':
            force_subscribe_management(call)
        elif data == 'add_admin':
            add_admin_handler(call)
        elif data == 'remove_admin':
            remove_admin_handler(call)
        elif data == 'add_force_subscribe':
            add_force_subscribe_handler(call)
        elif data == 'remove_force_subscribe':
            remove_force_subscribe_handler(call)
        elif data == 'toggle_force_subscribe':
            toggle_force_subscribe_handler(call)
        elif data == 'bot_channel':
            bot_channel_handler(call)
        elif data == 'check_subscription':
            check_subscription_handler(call)
        elif data == 'back_to_main':
            back_to_main(call)
        elif data.startswith('approve_') or data.startswith('reject_'):
            handle_user_approval(call)
        elif data == 'manage_users':
            manage_users_menu(call)
        elif data == 'points_management':
            points_management_menu(call)
        elif data == 'vip_management':
            vip_management_menu(call)
        elif data == 'admin_settings':
            admin_settings_menu(call)
        elif data == 'broadcast_message':
            broadcast_message_handler(call)
        elif data == 'bot_settings':
            bot_settings_menu(call)
        elif data == 'welcome_message_edit':
            welcome_message_edit_handler(call)
        elif data == 'protection_settings':
            protection_settings_menu(call)
        elif data == 'notifications_settings':
            notifications_settings_menu(call)

        # ========== أزرار المستخدمين ==========
        elif data == 'my_bots':
            my_bots_handler(call)
        elif data == 'upload_file':
            upload_file_handler(call)
        elif data == 'install_library':
            install_library_handler(call)
        elif data == 'speed_test':
            speed_test_handler(call)
        elif data == 'stop_active_bots':
            stop_active_bots_handler(call)
        elif data == 'my_points':
            my_points_handler(call)
        elif data == 'increase_points':
            increase_points_handler(call)
        elif data == 'referral_system':
            referral_system_handler(call)
        elif data == 'transfer_points':
            transfer_points_handler(call)
        elif data == 'bot_rules':
            bot_rules_handler(call)
        elif data == 'help_page':
            help_page_handler(call)
        elif data == 'developer':
            developer_handler(call)

        # ========== أزرار الأدمن الإضافية ==========
        elif data == 'view_users':
            view_users_handler(call)
        elif data == 'ban_user_menu':
            ban_user_menu_handler(call)
        elif data == 'unban_user_menu':
            unban_user_menu_handler(call)
        elif data == 'search_user':
            search_user_handler(call)
        elif data == 'pending_users':
            pending_users_handler(call)
        elif data == 'add_points':
            add_points_handler(call)
        elif data == 'remove_points':
            remove_points_handler(call)
        elif data == 'reset_points':
            reset_points_handler(call)
        elif data == 'points_stats':
            points_stats_handler(call)
        elif data == 'add_vip':
            add_vip_handler(call)
        elif data == 'remove_vip':
            remove_vip_handler(call)
        elif data == 'vip_list':
            vip_list_handler(call)
        elif data == 'edit_vip_prices':
            edit_vip_prices_handler(call)
        elif data == 'toggle_bot':
            toggle_bot_handler(call)
        elif data == 'toggle_vip':
            toggle_vip_handler(call)
        elif data == 'toggle_referral':
            toggle_referral_handler(call)
        elif data.startswith('remove_channel_'):
            remove_channel_handler(call)
        else:
            bot.answer_callback_query(call.id, "⚙️ هذه الخاصية قيد التطوير")

    except Exception as e:
        logging.exception("Error in callback")
        try:
            bot.answer_callback_query(call.id, "❌ حدث خطأ في المعالجة")
        except:
            pass

# --------------------------------------------------
# ======== دوال الأدمن الرئيسية =========
# --------------------------------------------------
@bot.callback_query_handler(func=lambda call: call.data == 'admin_panel_main')
def admin_panel_main(call):
    try:
        if not is_admin(call.from_user.id):
            bot.answer_callback_query(call.id, "❌ ليس لديك صلاحية")
            return

        stats = get_user_stats()

        admin_text = f"""
👑 لوحة تحكم الأدمن

📊 الإحصائيات الحالية:
• 👥 إجمالي المستخدمين: {stats['total_users']}
• ⭐ مستخدمين VIP: {stats['vip_users']}
• 🚫 المستخدمين المحظورين: {stats['banned_users']}
• 🔥 النشطين اليوم: {stats['active_today']}
• 🆕 الجدد اليوم: {stats['new_today']}

🎯 اختر الإدارة المطلوبة:"""

        bot.edit_message_text(
            admin_text,
            call.message.chat.id,
            call.message.message_id,
            reply_markup=create_admin_panel_buttons(),
            parse_mode='Markdown'
        )
    except Exception as e:
        logging.exception("admin_panel_main error")
        try:
            bot.answer_callback_query(call.id, "❌ حدث خطأ")
        except:
            pass

@bot.callback_query_handler(func=lambda call: call.data == 'admin_stats')
def admin_stats(call):
    try:
        if not is_admin(call.from_user.id):
            bot.answer_callback_query(call.id, "❌ ليس لديك صلاحية")
            return

        stats = get_user_stats()

        stats_text = f"""
📊 إحصائيات البوت التفصيلية:

👥 المستخدمين:
• الإجمالي: {stats['total_users']}
• 🎖️ VIP: {stats['vip_users']}
• 🚫 المحظورين: {stats['banned_users']}
• 👑 الأدمن: {stats['admin_users']}
• 🔥 النشطين اليوم: {stats['active_today']}
• 🆕 الجدد اليوم: {stats['new_today']}

⚙️ إعدادات البوت:
• حالة البوت: {'✅ نشط' if get_setting('bot_enabled') == '1' else '❌ متوقف'}
• نظام VIP: {'✅ مفعل' if get_setting('vip_enabled') == '1' else '❌ معطل'}
• الاشتراك الإجباري: {'✅ مفعل' if get_setting('force_subscription') == '1' else '❌ معطل'}
• إشعارات المستخدمين الجدد: {'✅ مفعل' if get_setting('new_user_notification') == '1' else '❌ معطل'}
• نظام الدعوة: {'✅ مفعل' if get_setting('referral_enabled') == '1' else '❌ معطل'}
        """

        markup = types.InlineKeyboardMarkup()
        refresh_btn = types.InlineKeyboardButton("🔄 تحديث", callback_data='admin_stats')
        back_btn = types.InlineKeyboardButton("🔙 رجوع", callback_data='admin_panel_main')
        markup.add(refresh_btn, back_btn)

        bot.edit_message_text(
            stats_text,
            call.message.chat.id,
            call.message.message_id,
            reply_markup=markup,
            parse_mode='Markdown'
        )
    except Exception as e:
        logging.exception("admin_stats error")
        try:
            bot.answer_callback_query(call.id, "❌ حدث خطأ")
        except:
            pass

# --------------------------------------------------
# إدارة المستخدمين
# --------------------------------------------------
def manage_users_menu(call):
    try:
        if not is_admin(call.from_user.id):
            bot.answer_callback_query(call.id, "❌ ليس لديك صلاحية")
            return

        markup = types.InlineKeyboardMarkup(row_width=2)

        buttons = [
            ("👀 عرض المستخدمين", "view_users"),
            ("🚫 حظر مستخدم", "ban_user_menu"),
            ("✅ فك حظر مستخدم", "unban_user_menu"),
            ("🔍 بحث عن مستخدم", "search_user"),
            ("📋 المستخدمين المعلقين", "pending_users")
        ]

        for text, callback in buttons:
            btn = types.InlineKeyboardButton(text, callback_data=callback)
            markup.add(btn)

        back_btn = types.InlineKeyboardButton("🔙 رجوع", callback_data="admin_panel_main")
        markup.add(back_btn)

        bot.edit_message_text(
            "👥 إدارة المستخدمين\n\nاختر الإجراء المطلوب:",
            call.message.chat.id,
            call.message.message_id,
            reply_markup=markup
        )
    except Exception as e:
        logging.exception("manage_users_menu error")
        try:
            bot.answer_callback_query(call.id, "❌ حدث خطأ")
        except:
            pass

def view_users_handler(call):
    try:
        if not is_admin(call.from_user.id):
            bot.answer_callback_query(call.id, "❌ ليس لديك صلاحية")
            return

        users = get_all_users()
        if not users:
            bot.answer_callback_query(call.id, "❌ لا يوجد مستخدمين")
            return

        users_text = "👥 قائمة المستخدمين:\n\n"
        for user in users[:10]:  # عرض أول 10 مستخدمين فقط
            status = "🚫 محظور" if user[6] == 1 else "✅ نشط"
            vip_status = "🎖️ VIP" if user[4] == 1 else "👤 عادي"
            users_text += f"🆔 {user[0]}\n👤 {user[2]}\n📌 @{user[1] or 'غير متوفر'}\n{status} | {vip_status}\n\n"

        if len(users) > 10:
            users_text += f"📊 ... وعرض {len(users) - 10} مستخدم إضافي"

        markup = types.InlineKeyboardMarkup()
        back_btn = types.InlineKeyboardButton("🔙 رجوع", callback_data="manage_users")
        markup.add(back_btn)

        bot.edit_message_text(
            users_text,
            call.message.chat.id,
            call.message.message_id,
            reply_markup=markup
        )
    except Exception as e:
        logging.exception("view_users_handler error")
        try:
            bot.answer_callback_query(call.id, "❌ حدث خطأ")
        except:
            pass

def ban_user_menu_handler(call):
    try:
        if not is_admin(call.from_user.id):
            bot.answer_callback_query(call.id, "❌ ليس لديك صلاحية")
            return

        msg = bot.send_message(
            call.message.chat.id,
            "أرسل معرف المستخدم الذي تريد حظره:"
        )
        bot.register_next_step_handler(msg, process_ban_user)
    except Exception as e:
        logging.exception("ban_user_menu_handler error")
        try:
            bot.answer_callback_query(call.id, "❌ حدث خطأ")
        except:
            pass

def process_ban_user(message):
    try:
        user_id = int(message.text)
        if ban_user(user_id):
            bot.send_message(message.chat.id, f"✅ تم حظر المستخدم {user_id}")
        else:
            bot.send_message(message.chat.id, "❌ فشل في حظر المستخدم")
    except Exception:
        bot.send_message(message.chat.id, "❌ المعرف غير صحيح")

def unban_user_menu_handler(call):
    try:
        if not is_admin(call.from_user.id):
            bot.answer_callback_query(call.id, "❌ ليس لديك صلاحية")
            return

        msg = bot.send_message(
            call.message.chat.id,
            "أرسل معرف المستخدم الذي تريد فك حظره:"
        )
        bot.register_next_step_handler(msg, process_unban_user)
    except Exception as e:
        logging.exception("unban_user_menu_handler error")
        try:
            bot.answer_callback_query(call.id, "❌ حدث خطأ")
        except:
            pass

def process_unban_user(message):
    try:
        user_id = int(message.text)
        if unban_user(user_id):
            bot.send_message(message.chat.id, f"✅ تم فك حظر المستخدم {user_id}")
        else:
            bot.send_message(message.chat.id, "❌ فشل في فك حظر المستخدم")
    except Exception:
        bot.send_message(message.chat.id, "❌ المعرف غير صحيح")

def search_user_handler(call):
    try:
        if not is_admin(call.from_user.id):
            bot.answer_callback_query(call.id, "❌ ليس لديك صلاحية")
            return

        msg = bot.send_message(
            call.message.chat.id,
            "أرسل معرف المستخدم للبحث عنه:"
        )
        bot.register_next_step_handler(msg, process_search_user)
    except Exception as e:
        logging.exception("search_user_handler error")
        try:
            bot.answer_callback_query(call.id, "❌ حدث خطأ")
        except:
            pass

def process_search_user(message):
    try:
        user_id = int(message.text)
        user_data = get_user(user_id)

        if user_data:
            status = "🚫 محظور" if user_data[6] == 1 else "✅ نشط"
            vip_status = "🎖️ VIP" if user_data[4] == 1 else "👤 عادي"
            admin_status = "👑 أدمن" if user_data[13] == 1 else "👤 مستخدم"

            user_info = f"""
🔍 معلومات المستخدم:

🆔 الآيدي: {user_data[0]}
👤 الاسم: {user_data[2]}
📌 اليوزر: @{user_data[1] or 'غير متوفر'}
💎 النقاط: {user_data[3]}
⭐ الحالة: {vip_status}
🚫 الحظر: {status}
{admin_status}
📅 تاريخ الانضمام: {user_data[7]}
⏰ آخر نشاط: {user_data[8]}
            """

            bot.send_message(message.chat.id, user_info)
        else:
            bot.send_message(message.chat.id, "❌ المستخدم غير موجود")
    except Exception:
        bot.send_message(message.chat.id, "❌ المعرف غير صحيح")

def pending_users_handler(call):
    try:
        if not is_admin(call.from_user.id):
            bot.answer_callback_query(call.id, "❌ ليس لديك صلاحية")
            return

        if not pending_requests:
            bot.answer_callback_query(call.id, "✅ لا توجد طلبات معلقة")
            return

        pending_text = "📋 طلبات الانضمام المعلقة:\n\n"
        for user_id, user_info in list(pending_requests.items())[:10]:
            pending_text += f"🆔 {user_id}\n👤 {user_info['first_name']}\n📌 @{user_info['username']}\n⏰ {user_info['timestamp']}\n\n"

        markup = types.InlineKeyboardMarkup()
        back_btn = types.InlineKeyboardButton("🔙 رجوع", callback_data="manage_users")
        markup.add(back_btn)

        bot.edit_message_text(
            pending_text,
            call.message.chat.id,
            call.message.message_id,
            reply_markup=markup
        )
    except Exception as e:
        logging.exception("pending_users_handler error")
        try:
            bot.answer_callback_query(call.id, "❌ حدث خطأ")
        except:
            pass

# --------------------------------------------------
# نقاط وVIP
# --------------------------------------------------
def points_management_menu(call):
    try:
        if not is_admin(call.from_user.id):
            bot.answer_callback_query(call.id, "❌ ليس لديك صلاحية")
            return

        markup = types.InlineKeyboardMarkup(row_width=2)

        buttons = [
            ("➕ إضافة نقاط", "add_points"),
            ("➖ خصم نقاط", "remove_points"),
            ("🔄 تصفير النقاط", "reset_points"),
            ("📊 إحصائيات النقاط", "points_stats")
        ]

        for text, callback in buttons:
            btn = types.InlineKeyboardButton(text, callback_data=callback)
            markup.add(btn)

        back_btn = types.InlineKeyboardButton("🔙 رجوع", callback_data="admin_panel_main")
        markup.add(back_btn)

        bot.edit_message_text(
            "💎 إدارة النقاط\n\nاختر الإجراء المطلوب:",
            call.message.chat.id,
            call.message.message_id,
            reply_markup=markup
        )
    except Exception as e:
        logging.exception("points_management_menu error")
        try:
            bot.answer_callback_query(call.id, "❌ حدث خطأ")
        except:
            pass

def add_points_handler(call):
    try:
        if not is_admin(call.from_user.id):
            bot.answer_callback_query(call.id, "❌ ليس لديك صلاحية")
            return

        msg = bot.send_message(
            call.message.chat.id,
            "أرسل معرف المستخدم وعدد النقاط للإضافة:\nمثال: 123456789 100"
        )
        bot.register_next_step_handler(msg, process_add_points)
    except Exception as e:
        logging.exception("add_points_handler error")
        try:
            bot.answer_callback_query(call.id, "❌ حدث خطأ")
        except:
            pass

def process_add_points(message):
    try:
        parts = message.text.split()
        user_id = int(parts[0])
        points = int(parts[1])

        if update_user_points(user_id, points):
            bot.send_message(message.chat.id, f"✅ تم إضافة {points} نقطة للمستخدم {user_id}")
        else:
            bot.send_message(message.chat.id, "❌ فشل في إضافة النقاط")
    except Exception:
        bot.send_message(message.chat.id, "❌ الإدخال غير صحيح")

def remove_points_handler(call):
    try:
        if not is_admin(call.from_user.id):
            bot.answer_callback_query(call.id, "❌ ليس لديك صلاحية")
            return

        msg = bot.send_message(
            call.message.chat.id,
            "أرسل معرف المستخدم وعدد النقاط للخصم:\nمثال: 123456789 50"
        )
        bot.register_next_step_handler(msg, process_remove_points)
    except Exception as e:
        logging.exception("remove_points_handler error")
        try:
            bot.answer_callback_query(call.id, "❌ حدث خطأ")
        except:
            pass

def process_remove_points(message):
    try:
        parts = message.text.split()
        user_id = int(parts[0])
        points = int(parts[1])

        if update_user_points(user_id, -points):
            bot.send_message(message.chat.id, f"✅ تم خصم {points} نقطة من المستخدم {user_id}")
        else:
            bot.send_message(message.chat.id, "❌ فشل في خصم النقاط")
    except Exception:
        bot.send_message(message.chat.id, "❌ الإدخال غير صحيح")

def reset_points_handler(call):
    try:
        if not is_admin(call.from_user.id):
            bot.answer_callback_query(call.id, "❌ ليس لديك صلاحية")
            return

        msg = bot.send_message(
            call.message.chat.id,
            "أرسل معرف المستخدم لتصفير نقاطه:"
        )
        bot.register_next_step_handler(msg, process_reset_points)
    except Exception as e:
        logging.exception("reset_points_handler error")
        try:
            bot.answer_callback_query(call.id, "❌ حدث خطأ")
        except:
            pass

def process_reset_points(message):
    try:
        user_id = int(message.text)
        if set_user_points(user_id, 0):
            bot.send_message(message.chat.id, f"✅ تم تصفير نقاط المستخدم {user_id}")
        else:
            bot.send_message(message.chat.id, "❌ فشل في تصفير النقاط")
    except Exception:
        bot.send_message(message.chat.id, "❌ المعرف غير صحيح")

def points_stats_handler(call):
    try:
        if not is_admin(call.from_user.id):
            bot.answer_callback_query(call.id, "❌ ليس لديك صلاحية")
            return

        users = get_all_users()
        total_points = sum(user[3] for user in users) if users else 0
        avg_points = total_points / len(users) if users else 0

        stats_text = f"""
📊 إحصائيات النقاط:

💰 إجمالي النقاط: {total_points}
👥 متوسط النقاط: {avg_points:.2f}
📈 أعلى نقاط: {max(user[3] for user in users) if users else 0}
📉 أقل نقاط: {min(user[3] for user in users) if users else 0}
        """

        markup = types.InlineKeyboardMarkup()
        back_btn = types.InlineKeyboardButton("🔙 رجوع", callback_data="points_management")
        markup.add(back_btn)

        bot.edit_message_text(
            stats_text,
            call.message.chat.id,
            call.message.message_id,
            reply_markup=markup
        )
    except Exception as e:
        logging.exception("points_stats_handler error")
        try:
            bot.answer_callback_query(call.id, "❌ حدث خطأ")
        except:
            pass

# --------------------------------------------------
# إدارة VIP
# --------------------------------------------------
def vip_management_menu(call):
    try:
        if not is_admin(call.from_user.id):
            bot.answer_callback_query(call.id, "❌ ليس لديك صلاحية")
            return

        markup = types.InlineKeyboardMarkup(row_width=2)

        buttons = [
            ("⭐ إضافة VIP", "add_vip"),
            ("🚫 إزالة VIP", "remove_vip"),
            ("📋 قائمة VIP", "vip_list"),
            ("💰 تعديل أسعار VIP", "edit_vip_prices")
        ]

        for text, callback in buttons:
            btn = types.InlineKeyboardButton(text, callback_data=callback)
            markup.add(btn)

        back_btn = types.InlineKeyboardButton("🔙 رجوع", callback_data="admin_panel_main")
        markup.add(back_btn)

        bot.edit_message_text(
            "⭐ إدارة نظام VIP\n\nاختر الإجراء المطلوب:",
            call.message.chat.id,
            call.message.message_id,
            reply_markup=markup
        )
    except Exception as e:
        logging.exception("vip_management_menu error")
        try:
            bot.answer_callback_query(call.id, "❌ حدث خطأ")
        except:
            pass

def add_vip_handler(call):
    try:
        if not is_admin(call.from_user.id):
            bot.answer_callback_query(call.id, "❌ ليس لديك صلاحية")
            return

        msg = bot.send_message(
            call.message.chat.id,
            "أرسل معرف المستخدم وعدد الأيام:\nمثال: 123456789 30"
        )
        bot.register_next_step_handler(msg, process_add_vip)
    except Exception as e:
        logging.exception("add_vip_handler error")
        try:
            bot.answer_callback_query(call.id, "❌ حدث خطأ")
        except:
            pass

def process_add_vip(message):
    try:
        parts = message.text.split()
        user_id = int(parts[0])
        days = int(parts[1])

        if set_vip(user_id, days):
            bot.send_message(message.chat.id, f"✅ تم إضافة VIP للمستخدم {user_id} لمدة {days} يوم")
        else:
            bot.send_message(message.chat.id, "❌ فشل في إضافة VIP")
    except Exception:
        bot.send_message(message.chat.id, "❌ الإدخال غير صحيح")

def remove_vip_handler(call):
    try:
        if not is_admin(call.from_user.id):
            bot.answer_callback_query(call.id, "❌ ليس لديك صلاحية")
            return

        msg = bot.send_message(
            call.message.chat.id,
            "أرسل معرف المستخدم لإزالة VIP:"
        )
        bot.register_next_step_handler(msg, process_remove_vip)
    except Exception as e:
        logging.exception("remove_vip_handler error")
        try:
            bot.answer_callback_query(call.id, "❌ حدث خطأ")
        except:
            pass

def process_remove_vip(message):
    try:
        user_id = int(message.text)
        if remove_vip(user_id):
            bot.send_message(message.chat.id, f"✅ تم إزالة VIP من المستخدم {user_id}")
        else:
            bot.send_message(message.chat.id, "❌ فشل في إزالة VIP")
    except Exception:
        bot.send_message(message.chat.id, "❌ المعرف غير صحيح")

def vip_list_handler(call):
    try:
        if not is_admin(call.from_user.id):
            bot.answer_callback_query(call.id, "❌ ليس لديك صلاحية")
            return

        users = get_all_users()
        vip_users = [user for user in users if user[4] == 1]

        if not vip_users:
            bot.answer_callback_query(call.id, "❌ لا يوجد مستخدمين VIP")
            return

        vip_text = "⭐ قائمة مستخدمين VIP:\n\n"
        for user in vip_users[:10]:
            vip_text += f"🆔 {user[0]}\n👤 {user[2]}\n📌 @{user[1] or 'غير متوفر'}\n⏰ انتهاء: {user[5] or 'غير محدد'}\n\n"

        markup = types.InlineKeyboardMarkup()
        back_btn = types.InlineKeyboardButton("🔙 رجوع", callback_data="vip_management")
        markup.add(back_btn)

        bot.edit_message_text(
            vip_text,
            call.message.chat.id,
            call.message.message_id,
            reply_markup=markup
        )
    except Exception as e:
        logging.exception("vip_list_handler error")
        try:
            bot.answer_callback_query(call.id, "❌ حدث خطأ")
        except:
            pass

def edit_vip_prices_handler(call):
    try:
        if not is_admin(call.from_user.id):
            bot.answer_callback_query(call.id, "❌ ليس لديك صلاحية")
            return

        current_prices = f"""
💰 الأسعار الحالية:

أسبوع: {get_setting('vip_price_week')} نقطة
شهر: {get_setting('vip_price_month')} نقطة
سنة: {get_setting('vip_price_year')} نقطة

أرسل الأسعار الجديدة بالشكل:
أسبوع شهر سنة
مثال: 50 150 500
        """

        msg = bot.send_message(call.message.chat.id, current_prices)
        bot.register_next_step_handler(msg, process_edit_vip_prices)
    except Exception as e:
        logging.exception("edit_vip_prices_handler error")
        try:
            bot.answer_callback_query(call.id, "❌ حدث خطأ")
        except:
            pass

def process_edit_vip_prices(message):
    try:
        parts = message.text.split()
        week_price = parts[0]
        month_price = parts[1]
        year_price = parts[2]

        update_setting('vip_price_week', week_price)
        update_setting('vip_price_month', month_price)
        update_setting('vip_price_year', year_price)

        bot.send_message(
            message.chat.id,
            f"✅ تم تحديث أسعار VIP:\nأسبوع: {week_price}\nشهر: {month_price}\nسنة: {year_price}"
        )
    except Exception:
        bot.send_message(message.chat.id, "❌ الإدخال غير صحيح")

# --------------------------------------------------
# إعدادات الأدمن والاذاعة (موجودة)
# --------------------------------------------------
def admin_settings_menu(call):
    try:
        if not is_admin(call.from_user.id):
            bot.answer_callback_query(call.id, "❌ ليس لديك صلاحية")
            return

        markup = types.InlineKeyboardMarkup(row_width=2)

        buttons = [
            ("🔧 إعدادات البوت", "bot_settings"),
            ("📝 رسالة الترحيب", "welcome_message_edit"),
            ("🛡️ مستوى الحماية", "protection_settings"),
            ("🔔 الإشعارات", "notifications_settings")
        ]

        for text, callback in buttons:
            btn = types.InlineKeyboardButton(text, callback_data=callback)
            markup.add(btn)

        back_btn = types.InlineKeyboardButton("🔙 رجوع", callback_data="admin_panel_main")
        markup.add(back_btn)

        bot.edit_message_text(
            "⚙️ إعدادات الأدمن\n\nاختر الإعداد المطلوب:",
            call.message.chat.id,
            call.message.message_id,
            reply_markup=markup
        )
    except Exception as e:
        logging.exception("admin_settings_menu error")
        try:
            bot.answer_callback_query(call.id, "❌ حدث خطأ")
        except:
            pass

def broadcast_message_handler(call):
    try:
        if not is_admin(call.from_user.id):
            bot.answer_callback_query(call.id, "❌ ليس لديك صلاحية")
            return

        msg = bot.send_message(
            call.message.chat.id,
            "📢 أرسل الرسالة التي تريد إذاعتها لجميع المستخدمين:"
        )
        bot.register_next_step_handler(msg, process_broadcast_message)
    except Exception as e:
        logging.exception("broadcast_message_handler error")
        try:
            bot.answer_callback_query(call.id, "❌ حدث خطأ")
        except:
            pass

def process_broadcast_message(message):
    try:
        users = get_all_users()
        success = 0
        failed = 0

        bot.send_message(message.chat.id, "⏳ جاري إرسال الرسالة لجميع المستخدمين...")

        for user in users:
            try:
                if user[6] == 0:  # إذا لم يكن محظوراً
                    bot.send_message(user[0], message.text)
                    success += 1
                    time.sleep(0.1)  # تجنب حظر التليجرام
            except Exception:
                failed += 1

        bot.send_message(
            message.chat.id,
            f"✅ تم الانتهاء من الإذاعة:\n\n✅ تم الإرسال: {success}\n❌ فشل الإرسال: {failed}"
        )
    except Exception as e:
        logging.exception("process_broadcast_message error")
        bot.send_message(message.chat.id, f"❌ حدث خطأ في الإذاعة: {e}")

# --------------------------------------------------
# إعدادات البوت / toggle handlers
# --------------------------------------------------
def bot_settings_menu(call):
    try:
        if not is_admin(call.from_user.id):
            bot.answer_callback_query(call.id, "❌ ليس لديك صلاحية")
            return

        bot_status = "✅ مفعل" if get_setting('bot_enabled') == '1' else "❌ معطل"
        vip_status = "✅ مفعل" if get_setting('vip_enabled') == '1' else "❌ معطل"
        referral_status = "✅ مفعل" if get_setting('referral_enabled') == '1' else "❌ معطل"

        settings_text = f"""
🔧 إعدادات البوت:

• حالة البوت: {bot_status}
• نظام VIP: {vip_status}
• نظام الدعوة: {referral_status}

اختر الإعداد الذي تريد تعديله:
        """

        markup = types.InlineKeyboardMarkup(row_width=2)

        buttons = [
            ("🔧 تفعيل/تعطيل البوت", "toggle_bot"),
            ("⭐ تفعيل/تعطيل VIP", "toggle_vip"),
            ("👥 تفعيل/تعطيل الدعوة", "toggle_referral"),
            ("🔙 رجوع", "admin_panel_main")
        ]

        for text, callback in buttons:
            btn = types.InlineKeyboardButton(text, callback_data=callback)
            markup.add(btn)

        bot.edit_message_text(
            settings_text,
            call.message.chat.id,
            call.message.message_id,
            reply_markup=markup
        )
    except Exception as e:
        logging.exception("bot_settings_menu error")
        try:
            bot.answer_callback_query(call.id, "❌ حدث خطأ")
        except:
            pass

def toggle_bot_handler(call):
    try:
        if not is_admin(call.from_user.id):
            bot.answer_callback_query(call.id, "❌ ليس لديك صلاحية")
            return

        current = get_setting('bot_enabled')
        new_value = '0' if current == '1' else '1'
        update_setting('bot_enabled', new_value)

        bot.answer_callback_query(call.id, f"✅ تم {'تعطيل' if new_value == '0' else 'تفعيل'} البوت")
        bot_settings_menu(call)
    except Exception as e:
        logging.exception("toggle_bot_handler error")
        try:
            bot.answer_callback_query(call.id, "❌ حدث خطأ")
        except:
            pass

def toggle_vip_handler(call):
    try:
        if not is_admin(call.from_user.id):
            bot.answer_callback_query(call.id, "❌ ليس لديك صلاحية")
            return

        current = get_setting('vip_enabled')
        new_value = '0' if current == '1' else '1'
        update_setting('vip_enabled', new_value)

        bot.answer_callback_query(call.id, f"✅ تم {'تعطيل' if new_value == '0' else 'تفعيل'} نظام VIP")
        bot_settings_menu(call)
    except Exception as e:
        logging.exception("toggle_vip_handler error")
        try:
            bot.answer_callback_query(call.id, "❌ حدث خطأ")
        except:
            pass

def toggle_referral_handler(call):
    try:
        if not is_admin(call.from_user.id):
            bot.answer_callback_query(call.id, "❌ ليس لديك صلاحية")
            return

        current = get_setting('referral_enabled')
        new_value = '0' if current == '1' else '1'
        update_setting('referral_enabled', new_value)

        bot.answer_callback_query(call.id, f"✅ تم {'تعطيل' if new_value == '0' else 'تفعيل'} نظام الدعوة")
        bot_settings_menu(call)
    except Exception as e:
        logging.exception("toggle_referral_handler error")
        try:
            bot.answer_callback_query(call.id, "❌ حدث خطأ")
        except:
            pass

# --------------------------------------------------
# دوال مساعدة متفرقة
# --------------------------------------------------
def handle_user_approval(call):
    try:
        if not is_admin(call.from_user.id):
            bot.answer_callback_query(call.id, "❌ ليس لديك صلاحية")
            return

        user_id = int(call.data.split('_')[1])

        if call.data.startswith('approve_'):
            approved_users.add(user_id)
            bot.answer_callback_query(call.id, "✅ تم قبول المستخدم")
            try:
                bot.send_message(user_id, "🎉 تم قبول طلبك! يمكنك الآن استخدام البوت.")
            except Exception:
                pass
            bot.edit_message_text(
                f"✅ تم قبول المستخدم: {user_id}",
                call.message.chat.id,
                call.message.message_id
            )
        else:
            bot.answer_callback_query(call.id, "❌ تم رفض المستخدم")
            try:
                bot.send_message(user_id, "❌ تم رفض طلبك للانضمام للبوت.")
            except Exception:
                pass
            bot.edit_message_text(
                f"❌ تم رفض المستخدم: {user_id}",
                call.message.chat.id,
                call.message.message_id
            )
    except Exception as e:
        logging.exception("handle_user_approval error")
        try:
            bot.answer_callback_query(call.id, "❌ حدث خطأ")
        except:
            pass

def add_admin_handler(call):
    try:
        if not is_admin(call.from_user.id):
            bot.answer_callback_query(call.id, "❌ ليس لديك صلاحية")
            return

        msg = bot.send_message(
            call.message.chat.id,
            "أرسل معرف المستخدم لإضافته كأدمن:"
        )
        bot.register_next_step_handler(msg, process_add_admin)
    except Exception as e:
        logging.exception("add_admin_handler error")

def process_add_admin(message):
    try:
        user_id = int(message.text)
        try:
            user = bot.get_chat(user_id)
            if add_admin(user_id, getattr(user, 'username', None), getattr(user, 'first_name', None)):
                bot.send_message(message.chat.id, f"✅ تم إضافة {getattr(user, 'first_name', user_id)} كأدمن")
            else:
                bot.send_message(message.chat.id, "❌ فشل في إضافة الأدمن")
        except Exception:
            bot.send_message(message.chat.id, "❌ لم أتمكن من العثور على هذا المستخدم")
    except Exception:
        bot.send_message(message.chat.id, "❌ المعرف غير صحيح")

def remove_admin_handler(call):
    try:
        if not is_admin(call.from_user.id):
            bot.answer_callback_query(call.id, "❌ ليس لديك صلاحية")
            return

        msg = bot.send_message(
            call.message.chat.id,
            "أرسل معرف المستخدم لإزالته من الأدمن:"
        )
        bot.register_next_step_handler(msg, process_remove_admin)
    except Exception as e:
        logging.exception("remove_admin_handler error")

def process_remove_admin(message):
    try:
        user_id = int(message.text)
        if user_id == ADMIN_ID:
            bot.send_message(message.chat.id, "❌ لا يمكن حذف الأدمن الأساسي")
            return

        if remove_admin(user_id):
            bot.send_message(message.chat.id, "✅ تم إزالة المستخدم من الأدمن")
        else:
            bot.send_message(message.chat.id, "❌ فشل في إزالة الأدمن")
    except Exception:
        bot.send_message(message.chat.id, "❌ المعرف غير صحيح")

def bot_channel_handler(call):
    try:
        markup = types.InlineKeyboardMarkup()
        channel_btn = types.InlineKeyboardButton("📢 قناة البوت", url=f"https://t.me/{DEVELOPER_CHANNEL.replace('@', '')}")
        markup.add(channel_btn)

        bot.edit_message_text(
            "📢 تابع قناتنا للحصول على آخر التحديثات:",
            call.message.chat.id,
            call.message.message_id,
            reply_markup=markup
        )
    except Exception:
        try:
            bot.answer_callback_query(call.id, "❌ حدث خطأ")
        except:
            pass

def check_subscription_handler(call):
    try:
        if check_subscription(call.from_user.id):
            bot.answer_callback_query(call.id, "✅ أنت مشترك في جميع القنوات")
            start(call.message)
        else:
            bot.answer_callback_query(call.id, "❌ يجب الاشتراك في جميع القنوات أولاً")
    except Exception:
        try:
            bot.answer_callback_query(call.id, "❌ حدث خطأ")
        except:
            pass

def user_panel(call):
    try:
        send_user_welcome_with_photo(call.message)
    except Exception:
        try:
            bot.answer_callback_query(call.id, "❌ حدث خطأ")
        except:
            pass

def back_to_main(call):
    try:
        if is_admin(call.from_user.id):
            show_admin_choice(call.message)
        else:
            send_user_welcome_with_photo(call.message)
    except Exception:
        try:
            bot.answer_callback_query(call.id, "❌ حدث خطأ")
        except:
            pass

def request_approval(user_id, user_info):
    try:
        pending_requests[user_id] = user_info

        markup = types.InlineKeyboardMarkup()
        approve_button = types.InlineKeyboardButton("✅ قبول المستخدم", callback_data=f'approve_{user_id}')
        reject_button = types.InlineKeyboardButton("❌ رفض المستخدم", callback_data=f'reject_{user_id}')
        markup.add(approve_button, reject_button)

        bot.send_message(
            ADMIN_ID,
            f"📋 طلب اشتراك جديد:\n\n👤 {user_info['first_name']}\n🆔 {user_id}\n📌 @{user_info.get('username', 'غير متوفر')}",
            reply_markup=markup
        )
    except Exception:
        logging.exception("request_approval error")

def send_waiting_message(chat_id):
    try:
        bot.send_message(chat_id, "⏳ تم إرسال طلب اشتراكك للأدمن، جاري المراجعة...")
    except Exception:
        pass

def generate_referral_code(user_id):
    try:
        return f"REF{user_id}{secrets.token_hex(3).upper()}"
    except Exception:
        return f"REF{user_id}"

# --------------------------------------------------
# نظام الاشتراك الإجباري: إضافة/حذف/قوائم
# --------------------------------------------------
@bot.callback_query_handler(func=lambda call: call.data == 'force_subscribe_management')
def force_subscribe_management(call):
    try:
        if not is_admin(call.from_user.id):
            bot.answer_callback_query(call.id, "❌ ليس لديك صلاحية")
            return

        channels = get_force_subscribe_channels()
        channels_text = "📢 قنوات الاشتراك الإجباري:\n\n"

        if channels:
            for channel in channels:
                channels_text += f"📢 {channel[2]}\n🆔 @{channel[1]}\n\n"
        else:
            channels_text += "❌ لا توجد قنوات مضافة\n\n"

        channels_text += f"🔧 حالة النظام: {'✅ مفعل' if get_setting('force_subscription') == '1' else '❌ معطل'}"

        markup = types.InlineKeyboardMarkup(row_width=2)
        add_btn = types.InlineKeyboardButton("➕ إضافة قناة", callback_data="add_force_subscribe")
        remove_btn = types.InlineKeyboardButton("➖ حذف قناة", callback_data="remove_force_subscribe")
        toggle_btn = types.InlineKeyboardButton("🔔 تفعيل/تعطيل", callback_data="toggle_force_subscribe")
        back_btn = types.InlineKeyboardButton("🔙 رجوع", callback_data="admin_panel_main")

        markup.add(add_btn, remove_btn)
        markup.add(toggle_btn)
        markup.add(back_btn)

        bot.edit_message_text(
            channels_text,
            call.message.chat.id,
            call.message.message_id,
            reply_markup=markup
        )
    except Exception:
        logging.exception("force_subscribe_management error")
        try:
            bot.answer_callback_query(call.id, "❌ حدث خطأ")
        except:
            pass

def add_force_subscribe_handler(call):
    try:
        if not is_admin(call.from_user.id):
            bot.answer_callback_query(call.id, "❌ ليس لديك صلاحية")
            return

        msg = bot.send_message(
            call.message.chat.id,
            "أرسل معرف القناة أو اليوزر:\nمثال: @channel_username أو -100123456789"
        )
        bot.register_next_step_handler(msg, process_add_force_subscribe)
    except Exception:
        logging.exception("add_force_subscribe_handler error")

def process_add_force_subscribe(message):
    try:
        channel_input = message.text.strip()
        try:
            chat = bot.get_chat(channel_input)
            username = f"@{chat.username}" if getattr(chat, 'username', None) else str(chat.id)
            if add_force_subscribe(chat.id, username, getattr(chat, 'title', str(chat.id))):
                bot.send_message(message.chat.id, f"✅ تم إضافة قناة: {getattr(chat, 'title', username)}")
            else:
                bot.send_message(message.chat.id, "❌ فشل في إضافة القناة")
        except Exception as e:
            bot.send_message(message.chat.id, f"❌ لم أتمكن من إضافة القناة: {e}")
    except Exception:
        bot.send_message(message.chat.id, "❌ الإدخال غير صحيح")

def remove_force_subscribe_handler(call):
    try:
        if not is_admin(call.from_user.id):
            bot.answer_callback_query(call.id, "❌ ليس لديك صلاحية")
            return

        channels = get_force_subscribe_channels()
        if not channels:
            bot.answer_callback_query(call.id, "❌ لا توجد قنوات مضافة")
            return

        markup = types.InlineKeyboardMarkup()
        for channel in channels:
            btn = types.InlineKeyboardButton(f"❌ {channel[2]}", callback_data=f"remove_channel_{channel[0]}")
            markup.add(btn)

        back_btn = types.InlineKeyboardButton("🔙 رجوع", callback_data="force_subscribe_management")
        markup.add(back_btn)

        bot.edit_message_text(
            "اختر القناة التي تريد حذفها:",
            call.message.chat.id,
            call.message.message_id,
            reply_markup=markup
        )
    except Exception:
        logging.exception("remove_force_subscribe_handler error")
        try:
            bot.answer_callback_query(call.id, "❌ حدث خطأ")
        except:
            pass

def remove_channel_handler(call):
    try:
        if not is_admin(call.from_user.id):
            bot.answer_callback_query(call.id, "❌ ليس لديك صلاحية")
            return

        channel_id = call.data.replace('remove_channel_', '')
        if remove_force_subscribe(channel_id):
            bot.answer_callback_query(call.id, "✅ تم حذف القناة")
            force_subscribe_management(call)
        else:
            bot.answer_callback_query(call.id, "❌ فشل في حذف القناة")
    except Exception:
        logging.exception("remove_channel_handler error")
        try:
            bot.answer_callback_query(call.id, "❌ حدث خطأ")
        except:
            pass

def toggle_force_subscribe_handler(call):
    try:
        if not is_admin(call.from_user.id):
            bot.answer_callback_query(call.id, "❌ ليس لديك صلاحية")
            return

        current = get_setting('force_subscription')
        new_value = '0' if current == '1' else '1'
        if update_setting('force_subscription', new_value):
            bot.answer_callback_query(call.id, f"✅ تم {'تفعيل' if new_value == '1' else 'تعطيل'} الاشتراك الإجباري")
            force_subscribe_management(call)
        else:
            bot.answer_callback_query(call.id, "❌ فشل في التحديث")
    except Exception:
        logging.exception("toggle_force_subscribe_handler error")
        try:
            bot.answer_callback_query(call.id, "❌ حدث خطأ")
        except:
            pass

# --------------------------------------------------
# دوال مستخدمين: بوتاتي, رفع ملف, تثبيت مكتبة, الخ...
# --------------------------------------------------
def my_bots_handler(call):
    try:
        user_id = call.from_user.id
        bots = get_user_bots(user_id)

        if not bots:
            bot.answer_callback_query(call.id, "🤖 لا توجد بوتات نشطة")
            return

        bots_text = "🤖 بوتاتك النشطة:\n\n"
        for bot_data in bots:
            bots_text += f"🔹 {bot_data[1]}\n⏰ {bot_data[4]}\n🟢 {bot_data[5]}\n\n"

        markup = types.InlineKeyboardMarkup()
        stop_btn = types.InlineKeyboardButton("🛑 إيقاف الكل", callback_data="stop_active_bots")
        back_btn = types.InlineKeyboardButton("🔙 رجوع", callback_data="user_panel")
        markup.add(stop_btn, back_btn)

        bot.edit_message_text(
            bots_text,
            call.message.chat.id,
            call.message.message_id,
            reply_markup=markup
        )
    except Exception:
        logging.exception("my_bots_handler error")
        try:
            bot.answer_callback_query(call.id, "❌ حدث خطأ")
        except:
            pass

def upload_file_handler(call):
    try:
        bot.answer_callback_query(call.id, "📤 أرسل ملف البوت الآن")
        bot.send_message(
            call.message.chat.id,
            "📤 أرسل ملف البوت (بايثون) الآن:\n\n⏰ سيتم فحص الملف أمنياً قبل التشغيل"
        )
    except Exception:
        logging.exception("upload_file_handler error")
        try:
            bot.answer_callback_query(call.id, "❌ حدث خطأ")
        except:
            pass

def install_library_handler(call):
    try:
        bot.answer_callback_query(call.id, "📚 أرسل اسم المكتبة")
        bot.send_message(
            call.message.chat.id,
            "📚 أرسل اسم المكتبة التي تريد تثبيتها:\nمثال: telebot requests numpy"
        )
    except Exception:
        logging.exception("install_library_handler error")
        try:
            bot.answer_callback_query(call.id, "❌ حدث خطأ")
        except:
            pass

def speed_test_handler(call):
    try:
        start_time = time.time()
        msg = bot.send_message(call.message.chat.id, "⚡ جاري قياس السرعة...")
        end_time = time.time()

        speed = end_time - start_time
        bot.edit_message_text(
            f"⚡ نتائج قياس السرعة:\n\n⏱️ وقت الاستجابة: {speed:.2f} ثانية\n📊 الحالة: {'🟢 ممتاز' if speed < 1 else '🟡 جيد' if speed < 2 else '🔴 بطيء'}",
            call.message.chat.id,
            msg.message_id
        )
    except Exception:
        logging.exception("speed_test_handler error")
        try:
            bot.answer_callback_query(call.id, "❌ حدث خطأ")
        except:
            pass

def stop_active_bots_handler(call):
    try:
        user_id = call.from_user.id
        if stop_user_bots(user_id):
            bot.answer_callback_query(call.id, "✅ تم إيقاف جميع البوتات")
            my_bots_handler(call)
        else:
            bot.answer_callback_query(call.id, "❌ لا توجد بوتات نشطة")
    except Exception:
        logging.exception("stop_active_bots_handler error")
        try:
            bot.answer_callback_query(call.id, "❌ حدث خطأ")
        except:
            pass

def my_points_handler(call):
    try:
        user_id = call.from_user.id
        user_data = get_user(user_id)
        points = user_data[3] if user_data else 0

        points_text = f"""
💎 نقاطك الحالية:

💰 الرصيد: {points} نقطة
⭐ حالة الحساب: {'🎖️ VIP' if user_data and user_data[4] == 1 else '👤 عادي'}

🎯 يمكنك استخدام النقاط ل:
• ترقية حسابك إلى VIP
• تشغيل بوتات إضافية
• مزايا حصرية أخرى
        """

        markup = types.InlineKeyboardMarkup()
        increase_btn = types.InlineKeyboardButton("🎁 زيادة النقاط", callback_data="increase_points")
        back_btn = types.InlineKeyboardButton("🔙 رجوع", callback_data="user_panel")
        markup.add(increase_btn, back_btn)

        bot.edit_message_text(
            points_text,
            call.message.chat.id,
            call.message.message_id,
            reply_markup=markup
        )
    except Exception:
        logging.exception("my_points_handler error")
        try:
            bot.answer_callback_query(call.id, "❌ حدث خطأ")
        except:
            pass

def increase_points_handler(call):
    try:
        points_text = """
🎁 طرق زيادة النقاط:

1. 👥 دعوة الأصدقاء
2. 📤 رفع ملفات بوتات
3. ⭐ شراء نقاط
4. 🎯 إكمال المهام

اختر الطريقة المناسبة:
        """

        markup = types.InlineKeyboardMarkup(row_width=2)
        referral_btn = types.InlineKeyboardButton("👥 الدعوة", callback_data="referral_system")
        transfer_btn = types.InlineKeyboardButton("🔄 التحويل", callback_data="transfer_points")
        back_btn = types.InlineKeyboardButton("🔙 رجوع", callback_data="my_points")
        markup.add(referral_btn, transfer_btn, back_btn)

        bot.edit_message_text(
            points_text,
            call.message.chat.id,
            call.message.message_id,
            reply_markup=markup
        )
    except Exception:
        logging.exception("increase_points_handler error")
        try:
            bot.answer_callback_query(call.id, "❌ حدث خطأ")
        except:
            pass

def referral_system_handler(call):
    try:
        user_id = call.from_user.id
        user_data = get_user(user_id)
        referral_code = user_data[9] if user_data else generate_referral_code(user_id)

        # تحصّل على username البوت بأمان (قد يستغرق طلب API)
        try:
            me = bot.get_me()
            bot_username = me.username
        except Exception:
            bot_username = None

        referral_text = f"""
👥 نظام الدعوة:

🎯 رابط دعوتك:
`https://t.me/{bot_username or ''}?start={referral_code}`

💰 المكافآت:
• أنت تحصل على {get_setting('points_per_referral')} نقطة
• صديقك يحصل على {get_setting('points_per_referral')} نقطة

📊 إحصائياتك:
• عدد المدعوين: {user_data[11] if user_data else 0}
        """

        markup = types.InlineKeyboardMarkup()
        back_btn = types.InlineKeyboardButton("🔙 رجوع", callback_data="my_points")
        markup.add(back_btn)

        bot.edit_message_text(
            referral_text,
            call.message.chat.id,
            call.message.message_id,
            reply_markup=markup,
            parse_mode='Markdown'
        )
    except Exception:
        logging.exception("referral_system_handler error")
        try:
            bot.answer_callback_query(call.id, "❌ حدث خطأ")
        except:
            pass

def transfer_points_handler(call):
    try:
        bot.answer_callback_query(call.id, "⚠️ هذه الميزة قيد التطوير")
    except:
        pass

def bot_rules_handler(call):
    try:
        text = "📋 قوانين البوت:\n1. ممنوع السب.\n2. احترم الآخرين.\n3. لا ترفع ملفات ضارة."
        bot.answer_callback_query(call.id, text)
    except:
        pass

def help_page_handler(call):
    try:
        text = "❓ للمساعدة تواصل مع المطور: " + DEVELOPER_USERNAME
        bot.answer_callback_query(call.id, text)
    except:
        pass

def developer_handler(call):
    try:
        bot.answer_callback_query(call.id, f"👨‍💻 للمطور: {DEVELOPER_USERNAME}")
    except:
        pass

# --------------------------------------------------
# باقي دوال الأدمن والإدارات (اختصار/ستب)
# تقليد للملف الأصلي: نترك بعض المزايا كـ "قيد التطوير" إن لزم
# --------------------------------------------------
def admin_management(call):
    try:
        bot.answer_callback_query(call.id, "⚙️ قيد التطوير")
    except:
        pass

def protection_settings_menu(call):
    try:
        bot.answer_callback_query(call.id, "⚙️ قيد التطوير")
    except:
        pass

def notifications_settings_menu(call):
    try:
        bot.answer_callback_query(call.id, "⚙️ قيد التطوير")
    except:
        pass

def pending_files_admin(call):
    try:
        bot.answer_callback_query(call.id, "⚙️ قيد التطوير")
    except:
        pass

def welcome_message_edit_handler(call):
    try:
        bot.answer_callback_query(call.id, "⚙️ قيد التطوير")
    except:
        pass

def points_stats(call):
    try:
        bot.answer_callback_query(call.id, "⚙️ قيد التطوير")
    except:
        pass

# --------------------------------------------------
# دوال إضافية مطلوبة قبل التشغيل
# --------------------------------------------------
def add_file_record(user_id, filename, path):
    # تسجيل الملف في ملفات مرفوعة (اختياري)
    try:
        # هنا يمكن تسجيل ملف في DB لو مطلوب لاحقاً
        return True
    except Exception:
        return False

# --------------------------------------------------
# نقطة الدخول: تشغيل البوت
# --------------------------------------------------
if __name__ == "__main__":
    try:
        logging.info("🤖 Bot is starting...")
        # استخدام skip_pending=True لمنع إعادة معالجة الرسائل القديمة عند إعادة التشغيل
        bot.infinity_polling(skip_pending=True)
    except KeyboardInterrupt:
        logging.info("Bot stopped by user (KeyboardInterrupt).")
    except Exception:
        logging.exception("Fatal error in bot main loop")
