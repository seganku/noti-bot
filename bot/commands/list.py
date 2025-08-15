import nextcord
from bot_context import db, noti_group
from utils import log_message, get_name
from datetime import datetime, UTC, timedelta

@noti_group.subcommand(name="list", description="List all scheduled notifications for this server")
async def list_notifications(interaction: nextcord.Interaction):
    """
    List all scheduled notifications for the current server, including next run time.
    """
    db.ensure_connection()
    try:
        cursor = db.conn.cursor()
        cursor.execute(
            '''
            SELECT id, channel_id, user_id, start_time, message,
                   is_repeating, interval_value, interval_unit, end_time,
                   max_occurrences, last_triggered
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

        def as_dt(val):
            if val is None:
                return None
            return datetime.fromisoformat(val) if isinstance(val, str) else val

        def interval_to_delta(val, unit):
            if not val or not unit:
                return None
            return {
                's': timedelta(seconds=val),
                'm': timedelta(minutes=val),
                'h': timedelta(hours=val),
                'd': timedelta(days=val),
                'w': timedelta(weeks=val),
            }.get(unit)

        def compute_next_run(start_time, is_repeating, iv_val, iv_unit, end_time, last_triggered, now):
            """
            Return the next scheduled datetime (UTC) or None if complete/past end.
            For repeating: base is last_triggered or start_time; we jump forward in
            whole intervals so the result is always >= now.
            """
            if not is_repeating:
                # One-off
                if last_triggered:
                    return None
                return start_time if start_time and start_time >= now else None

            delta = interval_to_delta(iv_val, iv_unit)
            if not delta:
                return None

            base = last_triggered or start_time
            if not base:
                return None

            if now <= base:
                nxt = base
            else:
                elapsed = now - base
                missed = elapsed // delta
                nxt = base + (missed + 1) * delta

            if end_time and nxt and nxt > end_time:
                return None
            return nxt

        embed = nextcord.Embed(
            title="📅 Scheduled Notifications",
            color=nextcord.Color.blue()
        )

        now = datetime.now(UTC)

        for (notif_id, channel_id, user_id, start_time, message,
             is_repeating, interval_value, interval_unit, end_time,
             max_occurrences, last_triggered) in notifications:

            st = as_dt(start_time)
            et = as_dt(end_time)
            lt = as_dt(last_triggered)

            channel_name = await get_name(interaction.client, 'channel', channel_id)
            user_name = await get_name(interaction.client, 'user', user_id, interaction.guild.id)

            time_str = st.strftime('%Y-%m-%d %H:%M UTC') if st else '—'
            next_run = compute_next_run(st, bool(is_repeating), interval_value, interval_unit, et, lt, now)
            next_str = next_run.strftime('%Y-%m-%d %H:%M UTC') if next_run else '—'

            preview = message[:100] + '...' if len(message) > 100 else message

            if is_repeating:
                field = (
                    f"**Channel:** {channel_name}\n"
                    f"**Scheduled by:** {user_name}\n"
                    f"**Start:** {time_str}\n"
                    f"**Interval:** every {interval_value}{interval_unit}\n"
                    f"**Next run:** {next_str}\n"
                )
                if et:
                    field += f"**Ends:** {et.strftime('%Y-%m-%d %H:%M UTC')}\n"
                if max_occurrences:
                    field += f"**Max runs:** {max_occurrences}\n"
                if lt:
                    field += f"**Last sent:** {lt.strftime('%Y-%m-%d %H:%M UTC')}\n"
                field += f"**Message:** {preview}"
                embed.add_field(name=f"🔁 ID {notif_id}", value=field, inline=False)
            else:
                embed.add_field(
                    name=f"📌 ID {notif_id}",
                    value=(
                        f"**Channel:** {channel_name}\n"
                        f"**Scheduled by:** {user_name}\n"
                        f"**Time:** {time_str}\n"
                        f"**Next run:** {next_str}\n"
                        f"**Message:** {preview}"
                    ),
                    inline=False
                )

        await interaction.response.send_message(embed=embed, ephemeral=True)

    except Exception as e:
        log_message(f"Error in /noti list command: {e}", "error")
        await interaction.response.send_message(
            "❌ An error occurred while fetching the notification list.", ephemeral=True
        )
