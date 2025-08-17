"""
Module: bot/main.py

Entry point for the Noti Discord Bot.
Initializes the bot, registers commands, and defines event handlers
for bot lifecycle, guild membership, disconnection, reconnection, and command logging.
"""
import nextcord
from config import DISCORD_BOT_TOKEN, GUILD_IDS, GUILD_MODE, DISCORD_APPLICATION_ID
from utils import log_message
from bot_context import bot, db, scheduler, noti_group, refresh_id_cache

# Import command modules to register slash commands
import commands.add
import commands.list
import commands.delete  # alias for delete command
import commands.help
import commands.about

@bot.event
async def on_ready():
    """
    Handler for the bot's ready event.

    Logs bot identity, loads existing notifications, and syncs slash commands.
    """
    log_message(f'Logged in as {bot.user.name} ({bot.user.id})', "info")
    await scheduler.load_existing_notifications()

    if GUILD_MODE:
        for guild_id in GUILD_IDS:
            try:
                synced = await bot.sync_application_commands(guild_id=guild_id)
                count = len(synced) if synced is not None else None
                guild = bot.get_guild(guild_id)
                guild_name = guild.name if guild else str(guild_id)
                if count is not None:
                    log_message(f"Synced {count} commands to guild {guild_name} ({guild_id})", "info")
                else:
                    log_message(f"Synced commands to guild {guild_name} ({guild_id})", "info")
            except nextcord.errors.Forbidden:
                guild = bot.get_guild(guild_id)
                guild_name = guild.name if guild else str(guild_id)
                log_message(
                    f"Failed to sync commands for guild {guild_name} ({guild_id}): Missing Access", "warning"
                )
            except Exception as e:
                guild = bot.get_guild(guild_id)
                guild_name = guild.name if guild else str(guild_id)
                log_message(
                    f"Error syncing commands for guild {guild_name} ({guild_id}): {e}", "error"
                )

    if not refresh_id_cache.is_running():
        refresh_id_cache.start()

    from datetime import datetime, UTC
    from colorama import Fore, Style

    perms = nextcord.Permissions()
    perms.manage_webhooks = True
    perms.send_messages = True
    perms.view_channel = True
    perms.read_message_history = True
    perms.mention_everyone = True

    invite_url = nextcord.utils.oauth_url(
        client_id=DISCORD_APPLICATION_ID,
        permissions=perms,
        scopes=["bot", "applications.commands"]
    )
    print(f"{Fore.CYAN}Bot invite URL: {Fore.YELLOW}{invite_url}{Style.RESET_ALL}")

@bot.event
async def on_application_command_error(interaction, error):
    """
    Handler for errors during slash command execution.

    Logs the error and notifies the user of an internal failure.
    """
    log_message(f"Slash command error: {error}", "error")
    try:
        await interaction.response.send_message("❌ An internal error occurred.", ephemeral=True)
    except:
        pass

@bot.event
async def on_error(event_method, *args, **kwargs):
    """
    Catch-all handler for unhandled errors in any event.

    Logs the event method name and full traceback when an error occurs.
    """
    import traceback
    tb = traceback.format_exc()
    log_message(f"Unhandled error in event {event_method}: {tb}", "error")

@bot.event
async def on_guild_join(guild):
    """
    Handler for when the bot joins a new guild.

    Logs the guild information and synchronizes slash commands to the guild.
    """
    log_message(f"Joined new guild: {guild.name} ({guild.id})", "info")
    try:
        synced = await bot.sync_application_commands(guild_id=guild.id)
        log_message(f"Synced {len(synced)} commands to new guild {guild.id}", "info")
    except Exception as e:
        log_message(f"Failed to sync commands for guild {guild.id}: {e}", "error")

@bot.event
async def on_guild_remove(guild):
    """
    Handler for when the bot is removed from a guild.

    Logs the removal event.
    """
    log_message(f"Removed from guild: {guild.name} ({guild.id})", "warning")

@bot.event
async def on_disconnect():
    """
    Handler for bot disconnection.

    Logs the disconnect and closes the database connection without stopping scheduler
    to preserve scheduled tasks.
    """
    log_message("Bot disconnected from Discord, pausing notifications.", "warning")
    # Cancel any existing tasks to prevent duplicates
    await scheduler.stop()
    try:
        db.conn.close()
    except Exception as e:
        log_message(f"Failed to close database: {e}", "error")

@bot.event
async def on_resumed():
    """
    Handler for bot reconnection after a disconnect.

    Reconnects the database and reloads all scheduled notifications.
    """
    log_message("Bot resumed connection, reconnecting DB and reloading notifications.", "info")
    try:
        db.connect()
        log_message("Database reconnected successfully.", "debug")
    except Exception as e:
        log_message(f"Failed to reconnect database: {e}", "error")
    # Reload notifications from the database
    await scheduler.load_existing_notifications()

# Log raw `/noti` commands for easy replay
@bot.listen()
async def on_interaction(interaction: nextcord.Interaction):
    """
    Listener for all `/noti` slash command interactions.

    Filters to the `/noti` command group, reconstructs the raw command with
    argument names and values (quoting as needed), and logs it along with
    guild, channel, and user context for easy replay.
    Catches and logs any errors during reconstruction.
    """
    try:
        # Only handle slash commands
        if interaction.type != nextcord.InteractionType.application_command:
            return
        data = interaction.data
        # Filter to our command group
        if data.get('name') != 'noti':
            return
        # Reconstruct raw command string
        cmd = f"/{data['name']}"
        for opt in data.get('options', []):
            if opt.get('type') == 1:
                # subcommand
                cmd += f" {opt['name']}"
                for subopt in opt.get('options', []):
                    name = subopt['name']
                    val = subopt['value']
                    val_str = str(val)
                    if isinstance(val, str) and (' ' in val_str or ':' in val_str):
                        val_str = f'"{val_str}"'
                    cmd += f" {name}:{val_str}"
            else:
                name = opt['name']
                val = opt['value']
                val_str = str(val)
                if isinstance(val, str) and (' ' in val_str or ':' in val_str):
                    val_str = f'"{val_str}"'
                cmd += f" {name}:{val_str}"
        log_message(
            f"Slash command invoked: {cmd} | Guild: {interaction.guild.name} ({interaction.guild.id}) | Channel: #{interaction.channel.name} ({interaction.channel.id}) | User: {interaction.user.name} ({interaction.user.id})",
            "info"
        )
    except Exception as e:
        log_message(f"Error in on_interaction: {e}", "error")

# Bot startup
log_message("Bot is starting up...")
bot.add_application_command(noti_group)
bot.run(DISCORD_BOT_TOKEN)

