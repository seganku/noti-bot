"""
Module: bot/scheduler/config.py

Provides the NotificationConfig class for parsing and validating notification settings
loaded from the database, with support for default values and type conversion.
"""
from datetime import datetime
from utils import interval_to_timedelta

class NotificationConfig:
    """
    Configuration for a scheduled notification.

    Attributes:
        notif_id (int): Unique auto-incremented notification ID.
        guild_id (int): Discord server (guild) ID.
        channel_id (int): Discord channel ID.
        user_id (int): ID of the user who scheduled the notification.
        start_time (datetime): Date/time for first execution (UTC).
        message (str): The content to send.
        is_repeating (bool): Whether the notification repeats (default False).
        interval_value (int or None): Numeric value for the repeat interval.
        interval_unit (str or None): Unit for repeat interval ('s','m','h','d','w').
        end_time (datetime or None): UTC datetime to stop repeating.
        max_occurrences (int or None): Maximum times to repeat.
        interval_delta (timedelta or None): Computed timedelta for repeats.
    """
    def __init__(
        self,
        notif_id,
        guild_id,
        channel_id,
        user_id,
        start_time_str,
        message,
        is_repeating=False,
        interval_value=None,
        interval_unit=None,
        end_time_str=None,
        max_occurrences=None
    ):
        """
        Initialize a NotificationConfig.

        Args:
            notif_id (int): Unique notification ID.
            guild_id (int): Discord guild ID.
            channel_id (int): Discord channel ID.
            user_id (int): ID of the user who scheduled.
            start_time_str (str or datetime): ISO timestamp or datetime for first run.
            message (str): Content to dispatch.
            is_repeating (bool, optional): Whether this notification repeats. Defaults to False.
            interval_value (int, optional): Repeat interval count if repeating.
            interval_unit (str, optional): Repeat unit ('s','m','h','d','w') if repeating.
            end_time_str (str or datetime, optional): When to stop repeating.
            max_occurrences (int, optional): Max number of repeats.
        """
        self.notif_id = notif_id
        self.guild_id = guild_id
        self.channel_id = channel_id
        self.user_id = user_id
        # Parse start time
        self.start_time = (
            datetime.fromisoformat(start_time_str)
            if isinstance(start_time_str, str) else start_time_str
        )
        self.message = message
        self.is_repeating = is_repeating
        self.interval_value = interval_value
        self.interval_unit = interval_unit
        # Parse end time
        self.end_time = (
            datetime.fromisoformat(end_time_str)
            if end_time_str and isinstance(end_time_str, str) else end_time_str
        )
        self.max_occurrences = max_occurrences
        # Compute repeat interval as timedelta
        if self.is_repeating and self.interval_value and self.interval_unit:
            self.interval_delta = interval_to_timedelta(
                self.interval_value, self.interval_unit
            )
        else:
            self.interval_delta = None

