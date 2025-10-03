import discord
from discord.ext import commands, tasks
from discord import app_commands
import json
import os
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Set
import asyncio
import pytz

# File to store channel schedules
SCHEDULE_FILE = 'daily_channel_schedules.json'

def load_schedules() -> Dict:
    """Load channel schedules from file"""
    try:
        with open(SCHEDULE_FILE, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        return {}

def save_schedules(schedules: Dict) -> None:
    """Save channel schedules to file"""
    with open(SCHEDULE_FILE, 'w') as f:
        json.dump(schedules, f, indent=2)

class DailyChannelAccess(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.schedules = load_schedules()
        self.channel_schedules: Dict[str, Dict] = {}
        
        # Convert string keys to int for channel IDs
        for channel_id_str, schedule in self.schedules.items():
            self.channel_schedules[int(channel_id_str)] = schedule
        
        # Start the background task
        self.update_channel_permissions.start()
        logging.info("DailyChannelAccess cog initialized")

    def cog_unload(self):
        """Clean up when cog is unloaded"""
        self.update_channel_permissions.cancel()

    @tasks.loop(minutes=1)  # Check every minute
    async def update_channel_permissions(self):
        """Background task to update channel permissions based on schedule"""
        current_time = datetime.now(timezone.utc)
        
        for channel_id, schedule in self.channel_schedules.items():
            try:
                # Find the channel
                channel = self.bot.get_channel(channel_id)
                if not channel:
                    continue
                
                guild = channel.guild
                if not guild:
                    continue
                
                # Get the role ID from schedule
                role_id = schedule.get('role_id')
                if not role_id:
                    continue
                
                role = guild.get_role(role_id)
                if not role:
                    continue
                
                # Get timezone and convert current time
                tz_name = schedule.get('timezone', 'UTC')
                try:
                    tz = pytz.timezone(tz_name)
                    local_time = current_time.astimezone(tz)
                except Exception as e:
                    logging.warning(f"Failed to convert timezone {tz_name}: {e}")
                    local_time = current_time
                
                current_day = local_time.strftime('%A').lower()  # monday, tuesday, etc.
                current_hour = local_time.hour
                
                # Check if today is in the allowed days
                allowed_days = schedule.get('days', [])
                if not allowed_days:
                    continue
                
                # Check if current time is within the allowed hours
                start_hour = schedule.get('start_hour', 0)
                end_hour = schedule.get('end_hour', 23)
                
                is_allowed_day = current_day in [day.lower() for day in allowed_days]
                is_allowed_time = start_hour <= current_hour <= end_hour
                
                # Get current permissions for the role
                current_overwrites = channel.overwrites_for(role)
                
                # Always allow viewing and reading, but control sending messages
                if not current_overwrites.view_channel or current_overwrites.view_channel is False:
                    # Enable viewing and reading (always)
                    await channel.set_permissions(role, view_channel=True, read_messages=True)
                    logging.info(f"Enabled viewing access to {channel.name} for role {role.name}")
                
                if is_allowed_day and is_allowed_time:
                    # Channel should be writable
                    if current_overwrites.send_messages is False:
                        # Enable sending messages
                        await channel.set_permissions(role, send_messages=True)
                        logging.info(f"Enabled sending messages in {channel.name} for role {role.name}")
                        
                        # Send notification if enabled
                        if schedule.get('notifications', False):
                            try:
                                embed = discord.Embed(
                                    title="📢 Channel Now Open for Chat",
                                    description=f"The channel {channel.mention} is now open for chatting for {role.mention}",
                                    color=discord.Color.green(),
                                    timestamp=current_time
                                )
                                embed.add_field(name="Schedule", value=f"Days: {', '.join(allowed_days)}\nTime: {start_hour}:00 - {end_hour}:00 ({tz_name})", inline=False)
                                
                                # Try to send to a logs channel or the channel itself
                                logs_channel_id = os.getenv('LOGS_CHANNEL_ID')
                                if logs_channel_id:
                                    logs_channel = guild.get_channel(int(logs_channel_id))
                                    if logs_channel:
                                        await logs_channel.send(embed=embed)
                            except Exception as e:
                                logging.error(f"Failed to send channel open notification: {e}")
                
                else:
                    # Channel should be read-only
                    if current_overwrites.send_messages is True:
                        # Disable sending messages
                        await channel.set_permissions(role, send_messages=False)
                        logging.info(f"Disabled sending messages in {channel.name} for role {role.name}")
                        
                        # Send notification if enabled
                        if schedule.get('notifications', False):
                            try:
                                embed = discord.Embed(
                                    title="🔒 Channel Now Read-Only",
                                    description=f"The channel {channel.mention} is now read-only for {role.mention}",
                                    color=discord.Color.orange(),
                                    timestamp=current_time
                                )
                                embed.add_field(name="Schedule", value=f"Days: {', '.join(allowed_days)}\nTime: {start_hour}:00 - {end_hour}:00 ({tz_name})", inline=False)
                                
                                # Try to send to a logs channel
                                logs_channel_id = os.getenv('LOGS_CHANNEL_ID')
                                if logs_channel_id:
                                    logs_channel = guild.get_channel(int(logs_channel_id))
                                    if logs_channel:
                                        await logs_channel.send(embed=embed)
                            except Exception as e:
                                logging.error(f"Failed to send channel read-only notification: {e}")
            
            except Exception as e:
                logging.error(f"Error updating permissions for channel {channel_id}: {e}")
                
                # Report critical error to owners
                try:
                    await self.report_critical_error("Daily Access Error", f"Error updating permissions for channel {channel_id}: {e}")
                except Exception as report_error:
                    logging.error(f"Failed to report critical error: {report_error}")

    async def report_critical_error(self, error_type, error_message):
        """Report critical errors to owners via logs and DM"""
        try:
            # Import the error reporting function
            from .verification import report_critical_error
            await report_critical_error(error_type, error_message, self.bot)
        except Exception as e:
            logging.error(f"Error in daily access cog error reporting: {e}")

    @update_channel_permissions.before_loop
    async def before_update_permissions(self):
        """Wait until bot is ready before starting the task"""
        await self.bot.wait_until_ready()

async def setup(bot):
    await bot.add_cog(DailyChannelAccess(bot)) 