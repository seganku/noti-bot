"""
Module: bot/commands/delete.py

Defines the `/noti delete` (alias `/noti del`) slash command to remove scheduled notifications.
Provides an ephemeral confirmation prompt to the command invoker, preventing accidental or unauthorized deletions.
"""
import nextcord
from nextcord import ui, ButtonStyle
from bot_context import db, scheduler, noti_group
from utils import log_message

# Toggle global delete-all functionality
ENABLE_DELETE_ALL = True

class DeleteConfirmView(ui.View):
    """
    View for delete confirmation with Confirm and Cancel buttons.

    Ensures only the invoking user can confirm or cancel the deletion.

    Attributes:
        user_id (int): ID of the user permitted to interact.
        notif_id (int or None): Notification ID to delete, or None for bulk deletion.
        delete_all (bool): True when deleting all notifications.
        confirmed (bool): Whether the user has confirmed the action.
    """
    def __init__(self, user_id: int, notif_id=None, delete_all=False):
        super().__init__(timeout=30)
        self.user_id = user_id
        self.notif_id = notif_id
        self.delete_all = delete_all
        self.confirmed = False

    @ui.button(label="Confirm", style=ButtonStyle.danger)
    async def confirm(self, _, interaction: nextcord.Interaction):
        """
        Handler for the Confirm button.

        Only the original invoker (self.user_id) may confirm.
        Sets confirmed flag and updates the ephemeral message on success.
        """
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message("Not authorized.", ephemeral=True)
        self.confirmed = True
        self.stop()
        action = 'all notifications' if self.delete_all else f'notification {self.notif_id}'
        await interaction.response.edit_message(content=f"Confirmed deletion of {action}.", view=None)

    @ui.button(label="Cancel", style=ButtonStyle.secondary)
    async def cancel(self, _, interaction: nextcord.Interaction):
        """
        Handler for the Cancel button.

        Only the original invoker (self.user_id) may cancel.
        Stops the view and informs the user.
        """
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message("Not authorized.", ephemeral=True)
        self.stop()
        await interaction.response.edit_message(content="Deletion cancelled.", view=None)

@noti_group.subcommand(name="del", description="Delete a scheduled notification or all notifications")
async def delete_notification(
    interaction: nextcord.Interaction,
    notification_id: str = nextcord.SlashOption(
        description=("ID of the notification to delete, or 'all' to remove every scheduled notification" if ENABLE_DELETE_ALL else "The ID of the notification to delete"),
        required=True,
    )
):
    """
    Handle the `/noti del` slash command.

    - For `notification_id='all'`, prompts for bulk deletion (if enabled).
    - For a specific ID, validates ownership or permissions, then prompts for confirmation.
    The deletion only occurs after Confirm is pressed on the ephemeral prompt.
    """
    db.ensure_connection()

    # Handle delete-all
    delete_all = (notification_id.lower() == 'all')
    if delete_all:
        if not ENABLE_DELETE_ALL:
            return await interaction.response.send_message(
                "❌ Bulk delete is currently disabled.", ephemeral=True
            )
        view = DeleteConfirmView(interaction.user.id, delete_all=True)
        await interaction.response.send_message(
            "Are you sure you want to delete *all* notifications?", view=view, ephemeral=True
        )
        await view.wait()
        if not view.confirmed:
            return

        cursor = db.conn.cursor()
        cursor.execute('DELETE FROM noti')
        db.conn.commit()
        await scheduler.stop()
        log_message(f"User {interaction.user.name} deleted all notifications", "info")
        return await interaction.edit_original_message(content="✅ All notifications have been deleted.", view=None)

    # Single-notification path
    try:
        notif_id_int = int(notification_id)
    except ValueError:
        return await interaction.response.send_message("❌ Invalid ID format.", ephemeral=True)

    cursor = db.conn.cursor()
    cursor.execute('SELECT guild_id, user_id FROM noti WHERE id = ?', (notif_id_int,))
    result = cursor.fetchone()
    if not result:
        return await interaction.response.send_message("❌ Notification not found.", ephemeral=True)

    guild_id, owner_id = result
    if guild_id != interaction.guild.id:
        return await interaction.response.send_message("❌ Not in this guild.", ephemeral=True)
    if owner_id != interaction.user.id and not interaction.user.guild_permissions.manage_messages:
        return await interaction.response.send_message("❌ Not allowed to delete.", ephemeral=True)

    view = DeleteConfirmView(interaction.user.id, notif_id_int)
    await interaction.response.send_message(
        f"Are you sure you want to delete notification {notif_id_int}?",
        view=view,
        ephemeral=True
    )
    await view.wait()
    if not view.confirmed:
        return

    await scheduler.remove_notification(notif_id_int)
    cursor.execute('DELETE FROM noti WHERE id = ?', (notif_id_int,))
    db.conn.commit()
    log_message(f"User {interaction.user.name} deleted notification {notif_id_int}", "info")
    await interaction.edit_original_message(content=f"✅ Deleted notification {notif_id_int}.", view=None)

