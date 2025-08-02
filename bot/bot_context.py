"""
Module: bot/bot_context.py

Sets up the Discord bot, database, and scheduler, and defines the main slash command group `/noti`.
"""
import asyncio
from datetime import datetime, UTC
from typing import Dict

import nextcord
from nextcord.ext import commands, tasks

from database import Database
from scheduler.manager import NotificationScheduler
from config import GUILD_IDS, GUILD_MODE, REFRESH_MAPPINGS
from utils import log_message

# Initialize database connection and scheduler
db = Database()
intents = nextcord.Intents.default()
bot = commands.Bot(intents=intents)
scheduler = NotificationScheduler(bot, db)

user_cache: Dict[tuple[int,int], str] = {}
channel_cache: Dict[int, str] = {}
guild_cache: Dict[int, str]   = {}
avatar_cache: Dict[int, str]   = {}

@bot.slash_command(
    name="noti",
    description="Notification Scheduler Commands",
    guild_ids=GUILD_IDS if GUILD_MODE else None
)
async def noti_group(interaction: nextcord.Interaction):
    """
    Main command group for notification scheduler.
    Subcommands: add, list, del, help.
    This command itself is not directly invoked.
    """
    pass

@tasks.loop(seconds=REFRESH_MAPPINGS.total_seconds())
async def refresh_id_cache():
    db.ensure_connection()
    cursor = db.conn.cursor()
    # Get all IDs we care about
    cursor.execute("SELECT DISTINCT obj_type, id FROM id_cache "
                   "UNION SELECT 'user', user_id FROM noti "
                   "UNION SELECT 'channel', channel_id FROM noti "
                   "UNION SELECT 'guild', guild_id FROM noti")
    entries = cursor.fetchall()
    for obj_type, oid in entries:
        try:
            # First, load all (guild_id, user_id) pairs from scheduled notifications
            cursor.execute("SELECT DISTINCT guild_id, user_id FROM noti")
            user_pairs = cursor.fetchall()

            # Then for each pair, attempt guild‑specific display_name
            for guild_id, user_id in user_pairs:
                name = None
                guild = bot.get_guild(guild_id)
                if guild:
                    member = guild.get_member(user_id)
                    if member:
                        try:
                            name = member.display_name if member.display_name else member.name
                            user_cache[(guild_id, user_id)] = name
                        except Exception as e:
                            log_message(f"Failed global fetch for guild({guild_id}) user({user_id}): {e}", "warning")

                # If no guild display_name, use global display_name
                if not name:
                    if (None, user_id) not in user_cache:
                        try:
                            member = await bot.fetch_user(user_id)
                            name = member.display_name
                            user_cache[(None, user_id)] = name
                        except Exception as e:
                            log_message(f"Failed global fetch for user {user_id}: {e}", "warning")

                if name:
                    now = datetime.now(UTC).isoformat()
                    cursor.execute("""
                        INSERT INTO id_cache(id,guild_id,obj_type,name,last_updated)
                        VALUES (?,?,?,?,?)
                        ON CONFLICT(id,guild_id,obj_type) DO UPDATE SET
                          name=excluded.name, last_updated=excluded.last_updated
                    """, (user_id, guild_id, 'user', name, now))
                    db.conn.commit()

                await asyncio.sleep(2)


            if obj_type == "user":
                name = None
                # Try guild‐specific display_name in any guild the bot is in
                for g in bot.guilds:
                    member = g.get_member(oid)
                    if member:
                        name = member.display_name if member.display_name else member.name
                        break
                # Fallback to global display_name
                if not name:
                    user_id = oid
                    member = await bot.fetch_user(user_id)
                    name = member.display_name if member.display_name else member.name
                user_cache[(None, user_id)] = name
                # Cache the user’s avatar URL as well
                try:
                    user_obj = member if 'member' in locals() and member else user
                    avatar_url = user_obj.avatar.url if getattr(user_obj, 'avatar', None) else None
                    avatar_cache[oid] = avatar_url
                except Exception as e:
                    log_message(f"Failed to fetch avatar for user {oid}: {e}", "warning")


            elif obj_type == "channel":
                ch = bot.get_channel(oid)
                name = f"#{ch.name}" if ch else None
                if name:
                    channel_cache[oid] = name
            else:  # guild
                g = bot.get_guild(oid)
                name = g.name if g else None
                if name:
                    guild_cache[oid] = name
            if name:
                now = datetime.now(UTC).isoformat()
                cursor.execute("""
                  INSERT INTO id_cache(id, guild_id, obj_type, name, last_updated)
                  VALUES (?, 0, ?, ?, ?)
                  ON CONFLICT(id, guild_id, obj_type) DO UPDATE SET
                    name=excluded.name,
                    last_updated=excluded.last_updated
                """, (oid, obj_type, name, now))
                db.conn.commit()
                log_message(f"refresh_id_cache(): ({obj_type}) id={oid} name={name}", "debug")
        except Exception as e:
            log_message(f"Refresh cache failed for {obj_type} {oid}: {e}", "warning")
        await asyncio.sleep(2)       # throttle Discord API
    log_message("Completed id_cache refresh", "info")

