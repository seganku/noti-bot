# === ./bot/config.py === #
import os
from dotenv import load_dotenv
from datetime import timedelta
from utils import parse_interval, interval_to_timedelta, log_message

load_dotenv()

RAW_GUILD_IDS = os.getenv("GUILD_IDS", "")
GUILD_IDS = [int(gid.strip()) for gid in RAW_GUILD_IDS.split(",") if gid.strip().isdigit()]
GUILD_MODE = bool(GUILD_IDS)

DISCORD_BOT_TOKEN = os.getenv('DISCORD_BOT_TOKEN')
DISCORD_APPLICATION_ID = os.getenv('DISCORD_APPLICATION_ID')

if not DISCORD_BOT_TOKEN or not DISCORD_APPLICATION_ID:
    raise EnvironmentError("Missing DISCORD_BOT_TOKEN or DISCORD_APPLICATION_ID in .env file")

DELIVER_LATE = interval_to_timedelta(
    *parse_interval(os.getenv('DELIVER_LATE', '2min'))
) or timedelta(minutes=2)

PREFETCH_BUFFER = interval_to_timedelta(
    *parse_interval(os.getenv('PREFETCH_BUFFER', '5s'))
) or timedelta(seconds=3)

RAW_REFRESH = os.getenv("REFRESH_MAPPINGS", "5min")
REFRESH_MAPPINGS = interval_to_timedelta(*parse_interval(RAW_REFRESH))

# for `/noti about`
SUPPORT_GUILD_ID   = int(os.getenv("SUPPORT_GUILD_ID", "0")) or None
SUPPORT_CHANNEL_ID = int(os.getenv("SUPPORT_CHANNEL_ID", "0")) or None
SUPPORT_INVITE_URL = os.getenv("SUPPORT_INVITE_URL")  # optional pre-made invite
MAINTAINER_USER_ID = int(os.getenv("MAINTAINER_USER_ID", "0")) or None

