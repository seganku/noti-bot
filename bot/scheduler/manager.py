"""
Module: bot/scheduler/manager.py

Defines NotificationScheduler: loads persisted notification configurations from the database,
initializes NotificationTask instances, and manages their lifecycle (add, remove, stop).
Includes catch-up for missed occurrences within a late-delivery window.
"""
from datetime import datetime, UTC
from config import DELIVER_LATE
from scheduler.config import NotificationConfig
from scheduler.task import NotificationTask

class NotificationScheduler:
    """
    Orchestrates scheduling, loading, and management of notification tasks.

    Responsibilities:
      - Load persisted notifications and dispatch missed occurrences (catch-up).
      - Start new tasks on schedule additions.
      - Cancel tasks on deletion.
      - Persist removals after one-off notifications complete.

    Attributes:
      bot: The nextcord.Bot instance for API interactions.
      db: Database wrapper instance for SQLite operations.
      tasks (dict): Mapping of notification IDs to asyncio.Task objects.
      loop: The asyncio event loop used for task scheduling.
    """
    def __init__(self, bot, db):
        """
        Initialize the NotificationScheduler.

        Args:
            bot: nextcord.Bot instance to use for Discord operations.
            db: Database instance with notification records.
        """
        self.bot = bot
        self.db = db
        self.tasks = {}
        self.loop = __import__('asyncio').get_event_loop()

    async def load_existing_notifications(self):
        """
        Load all notification records from the database and start tasks.
        Performs catch-up for any missed occurrences within the DELIVER_LATE window.

        Query Fields:
          id, guild_id, channel_id, user_id, start_time, message,
          is_repeating, interval_value, interval_unit, end_time,
          max_occurrences, last_triggered
        """
        self.db.ensure_connection()
        cursor = self.db.conn.cursor()
        cursor.execute(
            'SELECT id, guild_id, channel_id, user_id, start_time, message, '
            'is_repeating, interval_value, interval_unit, end_time, '
            'max_occurrences, last_triggered FROM noti'
        )
        rows = cursor.fetchall()
        now = datetime.now(UTC)
        for row in rows:
            # Unpack fields by name for clarity
            (nid, gid, cid, uid, st, msg, rep, iv, iu, et, mo, lt) = row
            config = NotificationConfig(
                notif_id=nid,
                guild_id=gid,
                channel_id=cid,
                user_id=uid,
                start_time_str=st,
                message=msg,
                is_repeating=rep,
                interval_value=iv,
                interval_unit=iu,
                end_time_str=et,
                max_occurrences=mo
            )
            # Attach last_triggered timestamp for catch-up logic
            if lt:
                if isinstance(lt, str):
                    config.last_triggered = datetime.fromisoformat(lt)
                else:
                    config.last_triggered = lt
            else:
                config.last_triggered = None
            task = NotificationTask(self, config)
            # Schedule the task
            self.tasks[nid] = self.loop.create_task(task.run())

    async def add_notification(self, *row):
        """
        Add a new notification by starting its task.

        Args:
            row: A tuple matching the first 11 fields of a notification record.
        """
        await self._start_task(row)

    async def remove_notification(self, notif_id):
        """
        Cancel and remove an active notification task.

        Args:
            notif_id (int): ID of the notification to remove.
        """
        task = self.tasks.pop(notif_id, None)
        if task:
            task.cancel()

    def delete_record(self, notif_id):
        from utils import log_message
        """
        Permanently delete a notification record from the database.

        Args:
            notif_id (int): ID of the completed or cancelled notification.
        """
        log_message(f"DELETE FROM noti WHERE ID = {notif_id}", 'debug')
        self.db.conn.cursor().execute(
            'DELETE FROM noti WHERE id = ?', (notif_id,)
        )
        self.db.conn.commit()

    async def _start_task(self, row):
        """
        Internal helper to unpack a row and start its NotificationTask.

        Args:
            row: Tuple of the first 11 notification record fields.
        """
        nid, gid, cid, uid, st, msg, rep, iv, iu, et, mo = row[:11]
        config = NotificationConfig(
            notif_id=nid,
            guild_id=gid,
            channel_id=cid,
            user_id=uid,
            start_time_str=st,
            message=msg,
            is_repeating=rep,
            interval_value=iv,
            interval_unit=iu,
            end_time_str=et,
            max_occurrences=mo
        )
        task = self.loop.create_task(NotificationTask(self, config).run())
        self.tasks[nid] = task

    async def stop(self):
        """
        Cancel all notification tasks and clear the scheduler.
        """
        for task in self.tasks.values():
            task.cancel()
        self.tasks.clear()

