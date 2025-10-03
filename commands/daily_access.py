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
SCHEDULE_FILE = "daily_channel_schedules.json"


def load_schedules() -> Dict:
    """Load channel schedules from file"""
    try:
        with open(SCHEDULE_FILE, "r") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}


def save_schedules(schedules: Dict) -> None:
    """Save channel schedules to file"""
    with open(SCHEDULE_FILE, "w") as f:
        json.dump(schedules, f, indent=2)


async def timezone_autocomplete(
    interaction: discord.Interaction, current: str
) -> list[app_commands.Choice[str]]:
    """Autocomplete for timezone choices"""
    timezone_choices = [
        app_commands.Choice(name="US East (EST/EDT)", value="America/New_York"),
        app_commands.Choice(name="US West (PST/PDT)", value="America/Los_Angeles"),
        app_commands.Choice(name="London (GMT/BST)", value="Europe/London"),
        app_commands.Choice(name="Asia (IST)", value="Asia/Kolkata"),
        app_commands.Choice(name="Tokyo (JST)", value="Asia/Tokyo"),
        app_commands.Choice(name="UTC", value="UTC"),
    ]

    if not current:
        return timezone_choices[:5]

    filtered = [
        choice for choice in timezone_choices if current.lower() in choice.name.lower()
    ]
    return filtered[:5]


async def days_autocomplete(
    interaction: discord.Interaction, current: str
) -> list[app_commands.Choice[str]]:
    """Autocomplete for days choices with multiple day options"""
    days_choices = [
        # Single days
        app_commands.Choice(name="Monday", value="monday"),
        app_commands.Choice(name="Tuesday", value="tuesday"),
        app_commands.Choice(name="Wednesday", value="wednesday"),
        app_commands.Choice(name="Thursday", value="thursday"),
        app_commands.Choice(name="Friday", value="friday"),
        app_commands.Choice(name="Saturday", value="saturday"),
        app_commands.Choice(name="Sunday", value="sunday"),
        # Common combinations
        app_commands.Choice(
            name="Weekdays (Mon-Fri)", value="monday,tuesday,wednesday,thursday,friday"
        ),
        app_commands.Choice(name="Weekends (Sat-Sun)", value="saturday,sunday"),
        app_commands.Choice(
            name="All Days",
            value="monday,tuesday,wednesday,thursday,friday,saturday,sunday",
        ),
        # Business week combinations
        app_commands.Choice(name="Mon-Wed", value="monday,tuesday,wednesday"),
        app_commands.Choice(name="Wed-Fri", value="wednesday,thursday,friday"),
        app_commands.Choice(name="Mon-Thu", value="monday,tuesday,wednesday,thursday"),
        app_commands.Choice(name="Tue-Fri", value="tuesday,wednesday,thursday,friday"),
        # Weekend combinations
        app_commands.Choice(name="Fri-Sun", value="friday,saturday,sunday"),
        app_commands.Choice(name="Sat-Mon", value="saturday,sunday,monday"),
        # Custom combinations
        app_commands.Choice(name="Mon, Wed, Fri", value="monday,wednesday,friday"),
        app_commands.Choice(name="Tue, Thu, Sat", value="tuesday,thursday,saturday"),
        app_commands.Choice(name="Mon, Tue, Thu", value="monday,tuesday,thursday"),
        app_commands.Choice(name="Wed, Fri, Sun", value="wednesday,friday,sunday"),
    ]

    # If current input contains commas, show suggestions for additional days
    if "," in current:
        # Split by comma and get the last part (what user is currently typing)
        parts = current.split(",")
        existing_days = [part.strip().lower() for part in parts[:-1] if part.strip()]
        current_part = parts[-1].strip().lower()

        # Filter out days that are already selected
        available_days = [
            choice for choice in days_choices if choice.value not in existing_days
        ]

        # Filter based on current part
        if current_part:
            filtered = [
                choice
                for choice in available_days
                if current_part in choice.name.lower()
            ]
        else:
            filtered = available_days

        # Add the existing selection as a suggestion
        if existing_days:
            existing_value = ",".join(existing_days)
            existing_name = ", ".join([day.title() for day in existing_days])
            filtered.insert(
                0,
                app_commands.Choice(
                    name=f"Keep: {existing_name}", value=existing_value
                ),
            )

        return filtered[:15]

    # Normal autocomplete for single day selection
    if not current:
        return days_choices[:15]  # Show first 15 options when no search

    # Filter based on current input
    filtered = [
        choice for choice in days_choices if current.lower() in choice.name.lower()
    ]

    # If no matches, show some default options
    if not filtered:
        return days_choices[:8]

    return filtered[:15]  # Return up to 15 filtered results


async def setup(bot):
    """Setup function for the daily access commands"""

    @bot.tree.command(
        name="daily_access_channel",
        description="Set up daily chat access for a channel - users can always see but only chat on specified days",
    )
    @app_commands.describe(
        channel="The Discord channel to schedule",
        role="The role that will have access",
        timezone_name="Timezone for the schedule",
        days="Days of the week when channel should be open (use autocomplete or type: monday,tuesday,wednesday)",
        start_hour="Hour when access begins (0-23)",
        end_hour="Hour when access ends (0-23)",
    )
    @app_commands.autocomplete(
        timezone_name=timezone_autocomplete, days=days_autocomplete
    )
    @app_commands.default_permissions(administrator=True)
    async def daily_access_channel(
        interaction: discord.Interaction,
        channel: discord.TextChannel,
        role: discord.Role,
        timezone_name: str,
        days: str,
        start_hour: int = 9,
        end_hour: int = 17,
    ):
        """
        Set up daily chat access for a channel - users can always see the channel but only chat on specified days

        Examples:
        - /daily_access_channel #daily-bias @Members "US East" "Weekdays" 9 17
        - /daily_access_channel #weekend @VIP "London" "Weekends" 0 23
        - /daily_access_channel #business @Employees "Tokyo" "Monday" 8 18
        """

        # Respond immediately to prevent timeout
        await interaction.response.defer(ephemeral=True)

        # SECURITY: Check authorization
        from main import is_authorized_guild_or_owner

        if not is_authorized_guild_or_owner(interaction):
            return await interaction.followup.send(
                "❌ You are not authorized to use this command.", ephemeral=True
            )

        # Check permissions
        if not interaction.user.guild_permissions.administrator:
            await interaction.followup.send(
                "❌ You need Administrator permissions to use this command!",
                ephemeral=True,
            )
            return

        # Validate hours
        if not (0 <= start_hour <= 23 and 0 <= end_hour <= 23):
            await interaction.followup.send(
                "❌ Hours must be between 0 and 23!", ephemeral=True
            )
            return

        if start_hour >= end_hour:
            await interaction.followup.send(
                "❌ Start hour must be before end hour!", ephemeral=True
            )
            return

        # Parse days
        day_list = [day.strip().lower() for day in days.split(",")]
        valid_days = [
            "monday",
            "tuesday",
            "wednesday",
            "thursday",
            "friday",
            "saturday",
            "sunday",
        ]

        invalid_days = [day for day in day_list if day not in valid_days]
        if invalid_days:
            await interaction.followup.send(
                f"❌ Invalid days: {', '.join(invalid_days)}\nValid days: {', '.join(valid_days)}",
                ephemeral=True,
            )
            return

        # Create schedule
        schedule_data = {
            "role_id": role.id,
            "days": day_list,
            "start_hour": start_hour,
            "end_hour": end_hour,
            "timezone": timezone_name,
            "notifications": True,  # Default to true for better UX
            "created_by": interaction.user.id,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }

        # Save to memory and file
        cog = bot.get_cog("DailyChannelAccess")
        if cog:
            cog.channel_schedules[channel.id] = schedule_data
            cog.schedules[str(channel.id)] = schedule_data
            save_schedules(cog.schedules)

        # Get current time in the specified timezone
        tz = pytz.timezone(timezone_name)
        current_time = datetime.now(timezone.utc).astimezone(tz)

        # Create embed response
        embed = discord.Embed(
            title="✅ Daily Chat Access Configured",
            description=f"Channel {channel.mention} will be open for chatting by {role.mention} on the specified schedule.\n\n**Note:** Users can always see the channel, but can only send messages during the scheduled times.",
            color=discord.Color.green(),
        )
        embed.add_field(name="Days", value=", ".join(day_list), inline=True)
        embed.add_field(
            name="Time", value=f"{start_hour:02d}:00 - {end_hour:02d}:00", inline=True
        )
        embed.add_field(name="Timezone", value=timezone_name, inline=True)
        embed.add_field(
            name="Current Time",
            value=f"{current_time.strftime('%H:%M')} {timezone_name}",
            inline=True,
        )
        embed.add_field(name="Notifications", value="✅ Enabled", inline=True)
        embed.set_footer(text=f"Configured by {interaction.user.name}")

        await interaction.followup.send(embed=embed, ephemeral=True)

        # Log the action
        logging.info(
            f"Daily chat access configured for {channel.name} by {interaction.user.name}"
        )

    @bot.tree.command(
        name="remove_daily_channel",
        description="Remove daily access schedule from a channel",
    )
    @app_commands.default_permissions(administrator=True)
    async def remove_daily_channel(
        interaction: discord.Interaction, channel: discord.TextChannel
    ):
        """Remove daily access schedule from a channel"""

        # Respond immediately to prevent timeout
        await interaction.response.defer(ephemeral=True)

        # SECURITY: Check authorization
        from main import is_authorized_guild_or_owner

        if not is_authorized_guild_or_owner(interaction):
            return await interaction.followup.send(
                "❌ You are not authorized to use this command.", ephemeral=True
            )

        # Check permissions
        if not interaction.user.guild_permissions.administrator:
            await interaction.followup.send(
                "❌ You need Administrator permissions to use this command!",
                ephemeral=True,
            )
            return

        # Check if schedule exists
        cog = bot.get_cog("DailyChannelAccess")
        if not cog or channel.id not in cog.channel_schedules:
            await interaction.followup.send(
                f"❌ No daily schedule found for {channel.mention}!", ephemeral=True
            )
            return

        # Get schedule info for response
        schedule = cog.channel_schedules[channel.id]
        role = interaction.guild.get_role(schedule["role_id"])
        role_name = role.name if role else "Unknown Role"

        # Remove from memory and file
        del cog.channel_schedules[channel.id]
        del cog.schedules[str(channel.id)]
        save_schedules(cog.schedules)

        # Create embed response
        embed = discord.Embed(
            title="🗑️ Daily Chat Access Removed",
            description=f"Daily chat access schedule removed from {channel.mention}",
            color=discord.Color.orange(),
        )
        embed.add_field(name="Role", value=role_name, inline=True)
        embed.add_field(name="Days", value=", ".join(schedule["days"]), inline=True)
        embed.add_field(
            name="Time",
            value=f"{schedule['start_hour']:02d}:00 - {schedule['end_hour']:02d}:00",
            inline=True,
        )
        embed.add_field(
            name="Timezone", value=schedule.get("timezone", "UTC"), inline=True
        )
        embed.set_footer(text=f"Removed by {interaction.user.name}")

        await interaction.followup.send(embed=embed, ephemeral=True)

        # Log the action
        logging.info(
            f"Daily chat access removed from {channel.name} by {interaction.user.name}"
        )

    @bot.tree.command(
        name="list_daily_channels",
        description="List all channels with daily access schedules",
    )
    @app_commands.default_permissions(administrator=True)
    async def list_daily_channels(interaction: discord.Interaction):
        """List all channels with daily access schedules"""

        # Respond immediately to prevent timeout
        await interaction.response.defer(ephemeral=True)

        # SECURITY: Check authorization
        from main import is_authorized_guild_or_owner

        if not is_authorized_guild_or_owner(interaction):
            return await interaction.followup.send(
                "❌ You are not authorized to use this command.", ephemeral=True
            )

        # Check permissions
        if not interaction.user.guild_permissions.administrator:
            await interaction.followup.send(
                "❌ You need Administrator permissions to use this command!",
                ephemeral=True,
            )
            return

        cog = bot.get_cog("DailyChannelAccess")
        if not cog or not cog.channel_schedules:
            await interaction.followup.send(
                "📋 No daily channel schedules configured.", ephemeral=True
            )
            return

        embed = discord.Embed(
            title="📋 Daily Chat Schedules",
            description="Channels with configured daily chat access schedules:",
            color=discord.Color.blue(),
        )

        for channel_id, schedule in cog.channel_schedules.items():
            channel = interaction.guild.get_channel(channel_id)
            role = interaction.guild.get_role(schedule["role_id"])

            if channel and role:
                # Get current time in the schedule's timezone
                tz_name = schedule.get("timezone", "UTC")
                try:
                    tz = pytz.timezone(tz_name)
                    current_time = datetime.now(timezone.utc).astimezone(tz)
                    current_day = current_time.strftime("%A").lower()
                    current_hour = current_time.hour
                except Exception:
                    current_time = datetime.now(timezone.utc)
                    current_day = current_time.strftime("%A").lower()
                    current_hour = current_time.hour

                is_allowed_day = current_day in [
                    day.lower() for day in schedule["days"]
                ]
                is_allowed_time = (
                    schedule["start_hour"] <= current_hour <= schedule["end_hour"]
                )

                status = (
                    "🟢 Chat Open"
                    if (is_allowed_day and is_allowed_time)
                    else "🔴 Read-Only"
                )

                embed.add_field(
                    name=f"{status} {channel.name}",
                    value=f"**Role:** {role.mention}\n**Days:** {', '.join(schedule['days'])}\n**Time:** {schedule['start_hour']:02d}:00 - {schedule['end_hour']:02d}:00\n**Timezone:** {tz_name}\n**Notifications:** {'✅' if schedule.get('notifications', False) else '❌'}",
                    inline=False,
                )

        embed.set_footer(
            text=f"Total schedules: {len(cog.channel_schedules)} | Users can always see channels, but only chat during scheduled times"
        )

        await interaction.followup.send(embed=embed, ephemeral=True)

    @bot.tree.command(
        name="test_daily_channel",
        description="Test the current status of a channel's daily access",
    )
    @app_commands.default_permissions(administrator=True)
    async def test_daily_channel(
        interaction: discord.Interaction, channel: discord.TextChannel
    ):
        """Test the current status of a channel's daily access"""

        # Respond immediately to prevent timeout
        await interaction.response.defer(ephemeral=True)

        # SECURITY: Check authorization
        from main import is_authorized_guild_or_owner

        if not is_authorized_guild_or_owner(interaction):
            return await interaction.followup.send(
                "❌ You are not authorized to use this command.", ephemeral=True
            )

        # Check permissions
        if not interaction.user.guild_permissions.administrator:
            await interaction.followup.send(
                "❌ You need Administrator permissions to use this command!",
                ephemeral=True,
            )
            return

        cog = bot.get_cog("DailyChannelAccess")
        if not cog or channel.id not in cog.channel_schedules:
            await interaction.followup.send(
                f"❌ No daily schedule found for {channel.mention}!", ephemeral=True
            )
            return

        schedule = cog.channel_schedules[channel.id]
        role = interaction.guild.get_role(schedule["role_id"])

        if not role:
            await interaction.followup.send("❌ Role not found!", ephemeral=True)
            return

        # Get current time in the schedule's timezone
        tz_name = schedule.get("timezone", "UTC")
        try:
            tz = pytz.timezone(tz_name)
            current_time = datetime.now(timezone.utc).astimezone(tz)
            current_day = current_time.strftime("%A").lower()
            current_hour = current_time.hour
        except Exception:
            current_time = datetime.now(timezone.utc)
            current_day = current_time.strftime("%A").lower()
            current_hour = current_time.hour

        is_allowed_day = current_day in [day.lower() for day in schedule["days"]]
        is_allowed_time = schedule["start_hour"] <= current_hour <= schedule["end_hour"]

        # Check actual permissions
        overwrites = channel.overwrites_for(role)
        has_access = overwrites.view_channel is True

        embed = discord.Embed(
            title="🧪 Daily Chat Access Test",
            description=f"Testing chat access for {channel.mention}",
            color=discord.Color.blue(),
        )

        embed.add_field(name="Role", value=role.mention, inline=True)
        embed.add_field(name="Current Day", value=current_day.title(), inline=True)
        embed.add_field(
            name="Current Hour", value=f"{current_hour:02d}:00", inline=True
        )
        embed.add_field(name="Timezone", value=tz_name, inline=True)
        embed.add_field(
            name="Allowed Days", value=", ".join(schedule["days"]), inline=True
        )
        embed.add_field(
            name="Allowed Time",
            value=f"{schedule['start_hour']:02d}:00 - {schedule['end_hour']:02d}:00",
            inline=True,
        )
        embed.add_field(
            name="Schedule Status",
            value=(
                "✅ Chat Allowed"
                if (is_allowed_day and is_allowed_time)
                else "❌ Read-Only"
            ),
            inline=True,
        )
        embed.add_field(
            name="Actual Chat Access",
            value="✅ Can Send Messages" if has_access else "❌ Read-Only",
            inline=True,
        )

        if (is_allowed_day and is_allowed_time) != has_access:
            embed.color = discord.Color.red()
            embed.add_field(
                name="⚠️ Status Mismatch",
                value="Schedule and actual chat permissions don't match!",
                inline=False,
            )
        else:
            embed.color = discord.Color.green()
            embed.add_field(
                name="✅ Status Match",
                value="Schedule and actual chat permissions match!",
                inline=False,
            )

        await interaction.followup.send(embed=embed, ephemeral=True)
