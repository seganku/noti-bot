"""
Module: bot/scheduler/task.py

Defines NotificationTask: orchestrates dispatch cycles including catch-up for missed runs,
pre-fetching resources, precise timing, and retry-within-deadline logic with fallback.
"""
import asyncio
import nextcord
from datetime import datetime, UTC
from utils import log_message, get_name
from config import DELIVER_LATE, PREFETCH_BUFFER

class NotificationTask:
    """
    Handles the execution of a single notification's delivery schedule.

    Responsibilities:
      - Perform catch-up dispatches for missed occurrences within the late-delivery window.
      - Pre-fetch required resources (user info, webhooks) ahead of each scheduled time.
      - Dispatch notifications at precise times, retrying transient failures until a deadline.
      - Fallback to channel.send on permission errors or after deadline expiry.

    Attributes:
      scheduler: NotificationScheduler managing this task.
      config: NotificationConfig with scheduling parameters.
      run_count: Number of times this task has successfully dispatched.
    """
    def __init__(self, scheduler, config):
        """
        Initialize a NotificationTask.

        Args:
            scheduler: The NotificationScheduler instance controlling tasks.
            config: NotificationConfig containing schedule details.
        """
        self.scheduler = scheduler
        self.config = config
        self.run_count = 0

    async def run(self):
        """
        Main entry point to execute all dispatches for this notification.

        Flow:
        1. Catch up on any occurrences missed while offline, up to DELIVER_LATE.
        2. Loop through scheduled occurrences, performing:
           a) Pre-fetch buffer sleep
           b) Resource pre-fetch (user and webhook handles)
           c) Precise wait until scheduled_time
           d) Dispatch with retry logic
        3. Stop when one-off is done, max occurrences reached, or past end_time.
        4. Cleanup database record for completed notifications.

        Errors and cancellations are logged, and do not crash the scheduler.
        """
        now = datetime.now(UTC)
        if self.config.is_repeating and self.config.interval_delta:
            # Base off last_triggered if present, else start_time
            base = getattr(self.config, 'last_triggered', None) or self.config.start_time
            diff = now - base
            if diff.total_seconds() < 0:
                # Next is still before the first run
                next_sched = base
            else:
                # Calculate how many intervals have elapsed
                missed = diff // self.config.interval_delta
                next_sched = base + (missed + 1) * self.config.interval_delta
        else:
            # One-off notification or no interval
            next_sched = self.config.start_time
        log_message(
            f"Restoring notification {self.config.notif_id}, next run at {next_sched.strftime('%Y-%m-%d %H:%M UTC')}",
            "info"
        )
        try:
            now = datetime.now(UTC)
            # Catch-up missed occurrences
            if self.config.is_repeating and self.config.interval_delta:
                last = getattr(self.config, 'last_triggered', None) or self.config.start_time
                next_time = last + self.config.interval_delta
                while next_time <= now and (now - next_time) <= DELIVER_LATE:
                    try:
                        await self._dispatch(next_time)
                        self.run_count += 1
                    except Exception as e:
                        log_message(
                            f"Error dispatching missed notification {self.config.notif_id} at {next_time}: {e}",
                            "error"
                        )
                    last = next_time
                    next_time = last + self.config.interval_delta

            # Scheduled occurrences loop
            # Determine next scheduled_time based on last_triggered if reconnecting
            if getattr(self.config, 'last_triggered', None) and self.config.is_repeating and self.config.interval_delta:
                scheduled_time = self.config.last_triggered + self.config.interval_delta
            else:
                scheduled_time = self.config.start_time
            occurrence_count = 0
            while True:
                # Pre-fetch buffer
                prefetch_time = scheduled_time - PREFETCH_BUFFER
                if prefetch_time > datetime.now(UTC):
                    await self._wait_until(prefetch_time)
                                # Pre-fetch lookups
                channel = self.scheduler.bot.get_channel(self.config.channel_id)
                # Pre-fetch user info
                try:
                    _ = await self.scheduler.bot.fetch_user(self.config.user_id)
                except Exception as e:
                    log_message(
                        f"User pre-fetch failed for {self.config.user_id}: {e}",
                        "warning"
                    )
                # Pre-fetch webhook list
                if channel:
                    try:
                        await channel.webhooks()
                    except nextcord.Forbidden as e:
                        log_message(
                            f"Cannot list webhooks for {channel.id}, continuing: {e}",
                            "warning"
                        )
                    except Exception as e:
                        log_message(
                            f"Error fetching webhooks for {channel.id}: {e}",
                            "error"
                        )
                # Wait until dispatch time
                await self._wait_until(scheduled_time)
                # Dispatch this occurrence at its scheduled time
                await self._dispatch(scheduled_time)
                occurrence_count += 1

                # Stop conditions
                if not self.config.is_repeating:
                    break
                if self.config.max_occurrences and occurrence_count >= self.config.max_occurrences:
                    break
                next_time = scheduled_time + self.config.interval_delta
                if self.config.end_time and next_time > self.config.end_time:
                    break
                scheduled_time = next_time

            # Cleanup after final dispatch
            self.scheduler.delete_record(self.config.notif_id)

        except asyncio.CancelledError:
            log_message(f"Cancelled task {self.config.notif_id}", "warning")
        except Exception as e:
            log_message(f"Error in NotificationTask {self.config.notif_id}: {e}", "error")

    async def _wait_until(self, target_time):
        """
        Sleep until the specified UTC datetime.

        Args:
            target_time: The datetime to wait for.
        """
        now = datetime.now(UTC)
        delay = (target_time - now).total_seconds()
        if delay > 0:
            await asyncio.sleep(delay)

    async def _dispatch(self, when):
        from bot_context import avatar_cache
        """
        Send the notification using a webhook, retrying up to DELIVER_LATE.
        Falls back to channel.send() on permission errors or after deadline.

        Details:
          - Attempts webhook.send(wait=True) for immediate feedback.
          - Retries every 5 seconds until deadline.
          - Catches nextcord.Forbidden to fallback immediately.
          - Updates last_triggered in the database on success.
        """
        channel = self.scheduler.bot.get_channel(self.config.channel_id)
        if not channel:
            return

        # Compute deadline relative to THIS occurrence's scheduled time
        deadline = when + DELIVER_LATE
        now = datetime.now(UTC)
        if now < deadline:
            #try:
            #    webhooks = await channel.webhooks()
            #    webhook = next((w for w in webhooks if w.name=='NotiWebhook'), None)
            #    if webhook is None:
            #        webhook = await channel.create_webhook(name='NotiWebhook')
            #    # Resolve display_name from cache (or API) with guild context
            #    display_name = await get_name(
            #        self.scheduler.bot,
            #        'user',
            #        self.config.user_id,
            #        self.config.guild_id
            #    )
            #    # Still fetch the User object for avatar_url
            #    user = await self.scheduler.bot.fetch_user(self.config.user_id)

            #    # Try to get avatar_url from cache, otherwise fetch and cache it
            #    avatar_url = avatar_cache.get(self.config.user_id)
            #    if avatar_url is None:
            #        try:
            #            user_obj = await self.scheduler.bot.fetch_user(self.config.user_id)
            #            avatar_url = user_obj.avatar.url if getattr(user_obj, 'avatar', None) else None
            #            avatar_cache[self.config.user_id] = avatar_url
            #        except Exception as e:
            #            log_message(f"Failed to fetch avatar for {self.config.user_id}: {e}", "warning")
            #            avatar_url = None

            #    await webhook.send(
            #        content=self.config.message,
            #        username=display_name,
            #        avatar_url=avatar_url,
            #        wait=True
            #    )
            #    log_message( f"Dispatched notification {self.config.notif_id} via webhook as {display_name}", "info")

            #    cur = self.scheduler.db.conn.cursor()
            #    cur.execute('UPDATE noti SET last_triggered = ? WHERE id = ?',
            #                (self.config.start_time.isoformat(), self.config.notif_id))
            #    self.scheduler.db.conn.commit()
            #    return
            #except nextcord.Forbidden as e:
            #    log_message(f"Webhook forbidden, falling back: {e}","warning")
            #    try:
            #        await channel.send(self.config.message)
            #        log_message(f"Dispatched notification {self.config.notif_id} via channel","info")
            #    except Exception as exc:
            #        log_message(f"Channel send failed: {exc}","error")
            #    cur = self.scheduler.db.conn.cursor()
            #    cur.execute('UPDATE noti SET last_triggered = ? WHERE id = ?',
            #                (self.config.start_time.isoformat(), self.config.notif_id))
            #    self.scheduler.db.conn.commit()
            #    return
            #except Exception as e:
            #    log_message(f"Webhook error, retrying: {e}","warning")
            #    await asyncio.sleep(5)
            try:
                await channel.send(self.config.message)
                log_message(
                    f"Dispatched notification {self.config.notif_id} at {when.strftime('%Y-%m-%d %H:%M UTC')} via channel",
                    "info"
                )
            except Exception as exc:
                log_message(f"Channel send failed: {exc}","error")
            # Update last_triggered to THIS occurrence time and return
            cur = self.scheduler.db.conn.cursor()
            cur.execute(
                'UPDATE noti SET last_triggered = ? WHERE id = ?',
                (when.isoformat(), self.config.notif_id)
            )
            self.scheduler.db.conn.commit()
            return

        # No action after deadline; skip too‑late notifications
        # 1) Mark it as “triggered” so we don’t retry this occurrence
        cursor = self.scheduler.db.conn.cursor()
        cursor.execute(
            'UPDATE noti SET last_triggered = ? WHERE id = ?',
            (when.isoformat(), self.config.notif_id)
        )

        # 2) If a max_occurrences limit exists, consume one slot
        if self.config.max_occurrences is not None:
            new_max = self.config.max_occurrences - 1
            cursor.execute(
                'UPDATE noti SET max_occurrences = ? WHERE id = ?',
                (new_max, self.config.notif_id)
            )
            # Keep the in‑memory config in sync
            self.config.max_occurrences = new_max

        # Persist both updates
        self.scheduler.db.conn.commit()

        # 3) If max_occurrences is now zero or negative, delete the DB record
        if self.config.max_occurrences is not None and self.config.max_occurrences <= 0:
            self.scheduler.delete_record(self.config.notif_id)

        # Finally, bail out—no send after the deadline
        log_message(
            f"Skipping notification {self.config.notif_id} scheduled for {when.strftime('%Y-%m-%d %H:%M UTC')} (past DELIVER_LATE).",
            "warning"
        )
        return
