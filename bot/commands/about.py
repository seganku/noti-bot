"""
Module: bot/commands/about.py

Defines `/noti about` to show basic bot info, maintainer mention, and support links.
"""
import nextcord
from nextcord import ui, ButtonStyle
from utils import log_message
from bot_context import noti_group
from config import (
    GUILD_MODE, DELIVER_LATE, PREFETCH_BUFFER,
    SUPPORT_GUILD_ID, SUPPORT_CHANNEL_ID, SUPPORT_INVITE_URL,
    MAINTAINER_USER_ID,
)

REPO_URL = "https://github.com/seganku/noti-bot"

class AboutLinksView(ui.View):
    def __init__(self, support_channel_url: str | None, support_invite_url: str | None):
        super().__init__(timeout=60)
        # GitHub
        self.add_item(ui.Button(label="GitHub", style=ButtonStyle.link, url=REPO_URL))
        # Support channel (channel jump URL)
        if support_channel_url:
            self.add_item(ui.Button(label="Open Support Channel", style=ButtonStyle.link, url=support_channel_url))
        # Support server invite (optional)
        if support_invite_url:
            self.add_item(ui.Button(label="Join Support Server", style=ButtonStyle.link, url=support_invite_url))

@noti_group.subcommand(name="about", description="About this bot")
async def noti_about(interaction: nextcord.Interaction):
    """
    Show basic info about the bot with a maintainer mention and support links.
    - Mentions the maintainer if configured and you share a guild (clickable ping).
    - Adds link buttons for GitHub, support channel (jump link), and support server invite.
    """
    # Maintainer mention (clickable ping inside shared guilds)
    maintainer_text = ""
    if MAINTAINER_USER_ID:
        maintainer_text = f"<@{MAINTAINER_USER_ID}>"

    # Build a channel jump URL if we have a support channel
    support_channel_url = None
    if SUPPORT_GUILD_ID and SUPPORT_CHANNEL_ID:
        # Discord "jump" URL to a channel (works if viewer is in that guild)
        support_channel_url = f"https://discord.com/channels/{SUPPORT_GUILD_ID}/{SUPPORT_CHANNEL_ID}"

    # Prefer configured invite URL; don’t auto-create one (needs permissions)
    support_invite_url = SUPPORT_INVITE_URL

    desc_lines = [
        "A Discord bot for scheduling and managing notifications.",
        "",
        f"[View the source on GitHub]({REPO_URL})",
    ]
    if maintainer_text:
        desc_lines.append(f"Maintainer: {maintainer_text}")
    if support_channel_url:
        desc_lines.append("Support: see the button below for the channel link.")
    elif support_invite_url:
        desc_lines.append("Support: see the button below to join the support server.")

    embed = nextcord.Embed(
        title="Noti Bot",
        description="\n".join(desc_lines),
        color=nextcord.Color.blurple(),
    )

    embed.add_field(
        name="Status",
        value=(
            f"Guild mode: **{'ON' if GUILD_MODE else 'OFF'}**\n"
            f"Deliver-late window: **{DELIVER_LATE}**\n"
            f"Prefetch buffer: **{PREFETCH_BUFFER}**\n"
            f"Library: **nextcord {getattr(nextcord, '__version__', 'unknown')}**"
        ),
        inline=False,
    )
    embed.set_footer(text="Use /noti help for commands")

    view = AboutLinksView(support_channel_url, support_invite_url)

    log_message(
        f"User {interaction.user.display_name} ({interaction.user.id}) opened /noti about",
        "info"
    )
    await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

