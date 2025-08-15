"""
Module: bot/commands/add.py

Defines the `/noti add` slash command, allowing users to add one‑off or repeating notifications.
Provides a confirmation prompt for unbounded repeating schedules.
"""
import nextcord
from nextcord import ui, ButtonStyle
from bot_context import db, scheduler, noti_group
from utils import log_message, parse_interval, validate_interval
from datetime import datetime, timedelta, UTC

class ConfirmView(ui.View):
    def __init__(self, user_id: int):
        super().__init__(timeout=60)
        self.user_id = user_id
        self.confirmed = False

    @ui.button(label="Confirm", style=ButtonStyle.danger)
    async def confirm(self, button: ui.Button, interaction: nextcord.Interaction):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("This prompt isn’t for you.", ephemeral=True)
            return
        self.confirmed = True
        self.stop()
        await interaction.response.edit_message(content="Confirmed. Scheduling...", view=None)

    @ui.button(label="Cancel", style=ButtonStyle.secondary)
    async def cancel(self, button: ui.Button, interaction: nextcord.Interaction):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("This prompt isn’t for you.", ephemeral=True)
            return
        self.stop()
        await interaction.response.edit_message(content="Cancelled scheduling.", view=None)

@noti_group.subcommand(
    name="add",
    description="Add a one‑off or repeating notification"
)
async def add_notification(
    interaction: nextcord.Interaction,
    channel: nextcord.TextChannel = nextcord.SlashOption(
        description="The channel for the notification", required=True
    ),
    time: str = nextcord.SlashOption(
        description="First occurrence (YYYY-mm-dd HH:MM UTC)", required=True
    ),
    message: str = nextcord.SlashOption(
        description="The message to send", required=True
    ),
    interval: str = nextcord.SlashOption(
        description="Optional interval (e.g., '30m','1h','2d','2w')", required=False
    ),
    end_time: str = nextcord.SlashOption(
        description="Optional end time (YYYY-mm-dd HH:MM UTC)", required=False
    ),
    max_occurrences: int = nextcord.SlashOption(
        description="Optional max repeats", required=False, min_value=1
    )
):
    """
    Handle `/noti add`.  Schedules one-off or repeating notifications.

    Parameters:
    - interaction: Interaction context.
    - channel, time, message: core schedule parameters.
    - interval, end_time, max_occurrences: optional repeat bounds.
    """
    db.ensure_connection()
    await interaction.response.send_message("⌛ Processing...", ephemeral=True)

    # Parse and validate time
    try:
        naive = datetime.strptime(time, "%Y-%m-%d %H:%M")
        start_time = naive.replace(tzinfo=UTC)
    except ValueError:
        return await interaction.edit_original_message(content="❌ Invalid time format.")

    # Determine repeating
    is_repeating = False
    iv_val = iv_unit = None
    if interval:
        iv_val, iv_unit = parse_interval(interval)
        if not iv_val or not iv_unit or not validate_interval(iv_val, iv_unit):
            return await interaction.edit_original_message(content="❌ Invalid interval.")
        is_repeating = True

    # Parse optional end_time
    end_dt = None
    if end_time:
        try:
            nd = datetime.strptime(end_time, "%Y-%m-%d %H:%M")
            end_dt = nd.replace(tzinfo=UTC)
        except ValueError:
            return await interaction.edit_original_message(content="❌ Invalid end time.")

    # Warning for unbounded repeats
    if is_repeating and not end_dt and not max_occurrences:
        warn = "⚠️ Unbounded repeating: confirm?"
        view = ConfirmView(interaction.user.id)
        await interaction.edit_original_message(content=warn, view=view)
        await view.wait()
        if not view.confirmed:
            return

    now = datetime.now(UTC)
    if start_time <= now + timedelta(seconds=5) and not is_repeating:
        return await interaction.edit_original_message(content="❌ Time must be in the future for non-repeating notifications.")

    # Insert DB
    cur = db.conn.cursor()
    if is_repeating:
        cur.execute(
            'INSERT INTO noti (guild_id,channel_id,user_id,start_time,message,'
            'is_repeating,interval_value,interval_unit,end_time,max_occurrences)'
            ' VALUES (?,?,?,?,?,?,?,?,?,?)',
            (interaction.guild.id, channel.id, interaction.user.id,
             start_time.isoformat(), message,
             True, iv_val, iv_unit,
             end_dt.isoformat() if end_dt else None,
             max_occurrences)
        )
    else:
        cur.execute(
            'INSERT INTO noti (guild_id,channel_id,user_id,start_time,message)'
            ' VALUES (?,?,?,?,?)',
            (interaction.guild.id, channel.id, interaction.user.id,
             start_time.isoformat(), message)
        )
    db.conn.commit()
    nid = cur.lastrowid

    log_message(
        f"User {interaction.user.display_name} added notif {nid} in {interaction.guild.name}/{channel.name}",
        "info"
    )

    # Schedule and respond
    row = cur.execute('SELECT id, guild_id, channel_id, user_id,'
                      'start_time,message,is_repeating,interval_value,'
                      'interval_unit,end_time,max_occurrences FROM noti WHERE id=?',(nid,)).fetchone()
    await scheduler.add_notification(*row)
    confirm_msg = f"✅ Scheduled (ID {nid}) notification in #{channel.name} at {start_time.strftime('%Y-%m-%d %H:%M UTC')}"
    if is_repeating:
        if max_occurrences:
            confirm_msg += f" repeating {max_occurrences}"
        if end_dt:
            confirm_msg += f" ending at {end_dt.strftime('%Y-%m-%d %H:%M UTC')}"
        confirm_msg += f" every {iv_val}{iv_unit}"
    confirm_msg += f": {message}"
    await interaction.edit_original_message(content=confirm_msg)

