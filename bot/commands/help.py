"""
Module: bot/commands/help.py

Provides the `/noti help` slash command for displaying usage information
for all notification scheduler commands (add, list, delete).
"""
import nextcord
from utils import log_message
from bot_context import noti_group

@noti_group.subcommand(name="help", description="Get help with scheduling commands")
async def schedule_help(
    interaction: nextcord.Interaction,
    command: str = None
):
    """
    Display help information for scheduling commands.

    When called without arguments, lists all commands with usage summaries.
    When called with a command name ("add", "list", "del"), shows
    detailed examples and parameter descriptions for that command.

    Parameters:
    - interaction: The slash command interaction context.
    - command: Optional specific command name for detailed help.
    """
    help_data = {
        None: {
            "title": "📚 Schedule Help",
            "description": "Here are the available scheduling commands:",
            "fields": [
                ("/noti add <channel> <YYYY-mm-dd HH:MM> <message>", "Add a one‑off notification"),
                ("/noti add <channel> <YYYY-mm-dd HH:MM> <message> [interval] [end_time] [max_occurrences]", "Add one‑off or repeating notifications"),
                ("/noti list", "List all scheduled notifications for this server"),
                ("/noti del <ID>", "Delete a scheduled notification"),
                ("/noti help [command]", "Get help with scheduling commands")
            ]
        },
        "add": {
            "title": "➕ Add Command Help",
            "description": "Add a one‑off or repeating notification in a channel",
            "example": "/noti add #general 2025-06-01 09:00 Standup meeting [1d] [2025-06-30 09:00] [30]",
            "details": (
                "This command schedules messages to be sent at specified times.\n\n"
                "Parameters:\n"
                "- channel: Target channel for the notification.\n"
                "- time: First occurrence in UTC (YYYY-mm-dd HH:MM).\n"
                "- message: The content to send (mentions allowed).\n"
                "- interval (optional): Repeat interval (e.g., '30m', '1h', '2d', '1w').\n"
                "- end_time (optional): When to stop repeating (YYYY-mm-dd HH:MM UTC).\n"
                "- max_occurrences (optional): Maximum number of repeats.\n\n"
                "If no interval is set, the notification runs only once. Otherwise, it repeats until the end_time or max_occurrences is reached."
            )
        },
        "list": {
            "title": "📋 List Command Help",
            "description": "List all scheduled notifications for this server",
            "example": "/noti list",
            "details": "Displays each notification's ID, channel, next run time, and message preview."
        },
        "del": {
            "title": "❌ Delete Command Help",
            "description": "Delete a scheduled notification",
            "example": "/noti del 5",
            "details": (
                "Deletes the notification with the given ID.\n"
                "You can only delete your own notifications unless you have manage messages permission."
            )
        }
    }

    if command and command not in help_data:
        await interaction.response.send_message(f"❌ Unknown command: {command}", ephemeral=True)
        return

    data = help_data[command] if command else help_data[None]
    embed = nextcord.Embed(
        title=data["title"],
        description=data["description"],
        color=nextcord.Color.green()
    )

    if command and "example" in data:
        embed.add_field(name="📝 Example", value=data["example"], inline=False)
        embed.add_field(name="ℹ️ Details", value=data["details"], inline=False)
    else:
        for name, value in data.get("fields", []):
            embed.add_field(name=name, value=value, inline=False)

    log_message(
        f"User {interaction.user.name} ({interaction.user.id}) accessed help: {command or 'general'}",
        "info"
    )
    await interaction.response.send_message(embed=embed, ephemeral=True)
