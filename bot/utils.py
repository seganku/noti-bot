"""
Module: bot/utils.py

Provides utility functions for logging and parsing intervals.
"""
import inspect, os, re
from datetime import datetime, timedelta, UTC
from colorama import init, Fore, Style

init(autoreset=True)

def log_message(message, level="info"):  
    """
    Print a timestamped, colored log message with the caller's relative source path.

    Parameters:
    - message: The log message string.
    - level: One of "info", "debug", "warning", or "error" for coloring.
    """

    frame    = inspect.currentframe().f_back
    fullpath = frame.f_code.co_filename
    cwd      = os.getcwd()
    if fullpath.startswith(cwd + os.sep):
        filename = fullpath[len(cwd)+1:]
    else:
        filename = fullpath
    lineno   = frame.f_lineno

    timestamp = f"[{datetime.now(UTC).strftime('%Y-%m-%d %H:%M:%S')}]"
    color_map = {
        "info": Fore.GREEN,
        "debug": Fore.BLUE,
        "warning": Fore.YELLOW,
        "error": Fore.RED
    }
    level_prefix = f"{level.upper():<7}"
    level_color = color_map.get(level.lower(), Fore.WHITE)

    prefix = f"[{timestamp}] {filename}({lineno}):"
    print(f"{prefix} {level_color}{level_prefix} {message}{Style.RESET_ALL}")


def parse_interval(interval_str):
    """
    Parse an interval string into a (value, unit) tuple.

    Supported formats: digits + unit, where unit is one of
    s, m, h, d, w, optionally with suffixes like "hours", "days".

    Returns (int(value), str(unit)) if valid, otherwise (None, None).
    """
    pattern = r'^(\d+)\s*([smhdw])(?:ec(?:ond)?|in(?:ute)?|our|ay|(?:ee)?k)?s?$'
    match = re.match(pattern, interval_str, re.IGNORECASE)
    if not match:
        return None, None
    return int(match.group(1)), match.group(2).lower()


def validate_interval(value, unit):
    """
    Validate that the interval value is positive and meets minimum thresholds.

    - Seconds (s): >=1
    - Minutes (m): >=1
    - Hours (h): >=1
    - Days (d): >=1
    - Weeks (w): >=1
    """
    if value <= 0:
        return False
    return value >= {
        's': 1,
        'm': 1,
        'h': 1,
        'd': 1,
        'w': 1
    }.get(unit, 1)

async def get_name(bot, obj_type, obj_id, guild_id=None):
    """
    Fetch a human-friendly name for a Discord object by ID, with caching and
    guild-specific nickname support for users.

    Parameters:
      bot (nextcord.Bot): The bot instance.
      obj_type (str): One of 'user', 'channel', or 'guild'.
      obj_id (int): The Discord ID to resolve.
      guild_id (int, optional): Guild context for user nicknames.

    Returns:
      str: The resolved name, or an 'Unknown ...' fallback.
    """
    # Avoid circular imports by doing this at runtime
    from bot_context import user_cache, channel_cache, guild_cache, db
    from datetime import datetime

    # 1) In‑memory cache
    if obj_type == 'user':
        # We key user_cache by (guild_id, user_id) for nick, or (None, user_id) for global
        nick_key = (guild_id, obj_id)
        global_key = (None, obj_id)
        if nick_key in user_cache:
            return user_cache[nick_key]
        if global_key in user_cache:
            return user_cache[global_key]
    elif obj_type == 'channel':
        if obj_id in channel_cache:
            return channel_cache[obj_id]
    elif obj_type == 'guild':
        if obj_id in guild_cache:
            return guild_cache[obj_id]

    # 2) DB cache
    cursor = db.conn.cursor()
    cursor.execute(
        "SELECT name FROM id_cache WHERE id = ? AND obj_type = ?",
        (obj_id, obj_type)
    )
    row = cursor.fetchone()
    if row:
        name = row[0]
        # refill in‑memory
        if obj_type == 'user':
            if guild_id and (guild_id, obj_id) in user_cache:
                return user_cache[(guild_id, obj_id)]
            if (None, obj_id) in user_cache:
                return user_cache[(None, obj_id)]
        elif obj_type == 'channel':
            channel_cache[obj_id] = name
        else:
            guild_cache[obj_id] = name
        return name

    # 3) Live lookup
    try:
        if obj_type == 'user':
            name = None
            # Try guild nickname first
            if guild_id:
                guild = bot.get_guild(guild_id)
                if guild:
                    member = guild.get_member(obj_id)
                    if member:
                        name = member.display_name
                        user_cache[(guild_id, obj_id)] = name
            # Fallback to global display_name
            if not name:
                user = await bot.fetch_user(obj_id)
                name = user.display_name
                user_cache[(None, obj_id)] = name

        elif obj_type == 'channel':
            ch = bot.get_channel(obj_id)
            if ch:
                name = f"#{ch.name}"
                channel_cache[obj_id] = name
            else:
                return "Unknown Channel"

        else:  # guild
            g = bot.get_guild(obj_id)
            if g:
                name = g.name
                guild_cache[obj_id] = name
            else:
                return "Unknown Guild"

    except Exception:
        return f"Unknown {obj_type.capitalize()}"

    # 4) Persist into DB cache
    now = datetime.now(UTC).isoformat()
    cursor.execute("""
        INSERT INTO id_cache(id,obj_type,name,last_updated)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
          name=excluded.name, last_updated=excluded.last_updated
    """, (obj_id, obj_type, name, now))
    db.conn.commit()

    return name

def interval_to_timedelta(value, unit):
    """
    Convert an interval value and unit into a timedelta.

    Supported units:
      s - seconds
      m - minutes
      h - hours
      d - days
      w - weeks

    Returns a datetime.timedelta or None if the unit is invalid.
    """

    # Guard against missing or invalid inputs
    if value is None or unit is None:
        return None

    delta_map = {
        's': timedelta(seconds=value),
        'm': timedelta(minutes=value),
        'h': timedelta(hours=value),
        'd': timedelta(days=value),
        'w': timedelta(weeks=value)
    }
    return delta_map.get(unit)

