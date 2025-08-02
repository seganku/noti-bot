"""
Module: bot/commands/list.py

Defines the `/noti list` slash command to display all scheduled notifications for a guild.
"""
import nextcord
from bot_context import db, noti_group
from utils import log_message, get_name
from datetime import datetime

@noti_group.subcommand(name="list", description="List all scheduled notifications for this server")
async def list_notifications(interaction: nextcord.Interaction):
    """
    List all scheduled notifications for the current server.

    Retrieves notifications from the database and displays their details,
    including one-off and repeating messages.

    Parameters:
    - interaction: The slash command interaction context.
    """
    db.ensure_connection()
    try:
        cursor = db.conn.cursor()
        cursor.execute(
            '''
            SELECT id, channel_id, user_id, start_time, message,
                   is_repeating, interval_value, interval_unit, end_time,
                   max_occurrences
            FROM noti
            WHERE guild_id = ?
            ORDER BY start_time
            ''',
            (interaction.guild.id,)
        )
        notifications = cursor.fetchall()

        if not notifications:
            await interaction.response.send_message(
                "ℹ️ No scheduled notifications for this server.", ephemeral=True
            )
            return

        embed = nextcord.Embed(
            title="📅 Scheduled Notifications",
            color=nextcord.Color.blue()
        )
        for (notif_id, channel_id, user_id, start_time, message,
             is_repeating, interval_value, interval_unit, end_time,
             max_occurrences) in notifications:

            channel_name = await get_name(interaction.client, 'channel', channel_id)
            user_name    = await get_name(
                interaction.client,
                'user',
                user_id,
                interaction.guild.id
            )
            st = (
                datetime.fromisoformat(start_time)
                if isinstance(start_time, str) else start_time
            )
            time_str = st.strftime('%Y-%m-%d %H:%M UTC')

            if is_repeating:
                field = (
                    f"**Channel:** {channel_name}\n"
                    f"**Scheduled by:** {user_name}\n"
                    f"**Start:** {time_str}\n"
                    f"**Interval:** every {interval_value}{interval_unit}\n"
                )
                if end_time:
                    et = (
                        datetime.fromisoformat(end_time)
                        if isinstance(end_time, str) else end_time
                    )
                    field += f"**Ends:** {et.strftime('%Y-%m-%d %H:%M UTC')}\n"
                if max_occurrences:
                    field += f"**Max runs:** {max_occurrences}\n"
                field += f"**Message:** {message[:100] + '...' if len(message) > 100 else message}"
                embed.add_field(name=f"🔁 ID {notif_id}", value=field, inline=False)
            else:
                embed.add_field(
                    name=f"📌 ID {notif_id}",
                    value=(
                        f"**Channel:** {channel_name}\n"
                        f"**Scheduled by:** {user_name}\n"
                        f"**Time:** {time_str}\n"
                        f"**Message:** {message[:100] + '...' if len(message) > 100 else message}"
                    ),
                    inline=False
                )

        await interaction.response.send_message(embed=embed, ephemeral=True)
    except Exception as e:
        log_message(f"Error in /noti list command: {e}", "error")
        await interaction.response.send_message(
            "❌ An error occurred while fetching the notification list.", ephemeral=True
        )

