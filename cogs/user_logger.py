"""
User Logger Cog - Monitors user logins and sends detailed information to logging channel
"""
import logging
import discord
from discord.ext import commands
import json
import os
from datetime import datetime, timezone
from config import USER_LOG_ID, TYPEFORM_LINK, GUILD_ID

class UserLogger(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.logged_users = set()
        self.verified_users = set()  # Track verified users to prevent reprocessing
        self.load_logged_users()

    def load_logged_users(self):
        """Load previously logged users from file"""
        try:
            with open('logged_members.json', 'r') as f:
                data = json.load(f)
                self.logged_users = set(data.get('logged_users', []))
                self.verified_users = set(data.get('verified_users', []))
        except (FileNotFoundError, json.JSONDecodeError):
            self.logged_users = set()
            self.verified_users = set()

    def save_logged_users(self):
        """Save logged users to file"""
        try:
            with open('logged_members.json', 'w') as f:
                json.dump({
                    'logged_users': list(self.logged_users),
                    'verified_users': list(self.verified_users)
                }, f)
        except Exception as e:
            logging.error(f"Error saving logged users: {e}")

    async def log_user_login(self, member):
        """Log user login with detailed information"""
        if member.id in self.logged_users:
            return  # Already logged this user
        
        # Add to logged users
        self.logged_users.add(member.id)
        self.save_logged_users()

        # Get the logging channel
        if not USER_LOG_ID:
            return
        
        try:
            channel = self.bot.get_channel(USER_LOG_ID)
            if not channel:
                return

            # Get user roles (excluding @everyone)
            roles = [role for role in member.roles if role.name != "@everyone"]
            role_names = [role.name for role in roles]
            role_mentions = [role.mention for role in roles]

            # Create form URL with user ID
            form_url = f"{TYPEFORM_LINK}#auth_code={member.id}"

            # Create embed
            embed = discord.Embed(
                title="🔍 User Login Detected",
                description=f"**{member.display_name}** has been logged and is now being monitored.",
                color=0x00ff00,
                timestamp=datetime.now(timezone.utc)
            )

            # Add user information
            embed.add_field(
                name="👤 User Information",
                value=(
                    f"**Name:** {member.display_name}\n"
                    f"**Username:** {member.name}\n"
                    f"**Mention:** {member.mention}\n"
                    f"**User ID:** `{member.id}`\n"
                    f"**Account Created:** <t:{int(member.created_at.timestamp())}:R>\n"
                    f"**Joined Server:** <t:{int(member.joined_at.timestamp())}:R>"
                ),
                inline=False
            )

            # Add roles information
            if role_names:
                embed.add_field(
                    name="🎭 Roles",
                    value=f"**Role Count:** {len(role_names)}\n**Roles:** {', '.join(role_mentions)}",
                    inline=False
                )
            else:
                embed.add_field(
                    name="🎭 Roles",
                    value="No roles assigned",
                    inline=False
                )

            # Add form URL
            embed.add_field(
                name="📋 Form URL",
                value=f"[Click here to view form]({form_url})",
                inline=False
            )

            # Add profile picture
            embed.set_thumbnail(url=member.display_avatar.url)

            # Add footer
            embed.set_footer(
                text=f"User ID: {member.id} | Logged at",
                icon_url=self.bot.user.display_avatar.url
            )

            await channel.send(embed=embed)

        except Exception as e:
            logging.error(f"Error logging user {member.id}: {e}")

    async def log_verification_click(self, member):
        """Log when a user clicks the verification button - NO LOGGING, just track"""
        # Don't log verification clicks, only track them
        # Users are already logged when they join with premium roles
        pass

    async def log_verification_complete(self, member, user_info):
        """Log when a user completes verification and remove them from user_data.json"""
        try:
            # Get the logging channel
            if not USER_LOG_ID:
                return
            
            channel = self.bot.get_channel(USER_LOG_ID)
            if not channel:
                return

            # Always log verification completion (don't check logged_users)
            # This ensures we properly track verified users

            # Get user roles (excluding @everyone)
            roles = [role for role in member.roles if role.name != "@everyone"]
            role_names = [role.name for role in roles]
            role_mentions = [role.mention for role in roles]

            # Create form URL with user ID
            form_url = f"{TYPEFORM_LINK}#auth_code={member.id}"

            # Create embed
            embed = discord.Embed(
                title="✅ User Verification Complete",
                description=f"**{member.display_name}** has completed verification and been removed from monitoring.",
                color=0x00ff00,
                timestamp=datetime.now(timezone.utc)
            )

            # Add user information
            embed.add_field(
                name="👤 User Information",
                value=(
                    f"**Name:** {member.display_name}\n"
                    f"**Username:** {member.name}\n"
                    f"**Mention:** {member.mention}\n"
                    f"**User ID:** `{member.id}`\n"
                    f"**Account Created:** <t:{int(member.created_at.timestamp())}:R>\n"
                    f"**Joined Server:** <t:{int(member.joined_at.timestamp())}:R>"
                ),
                inline=False
            )

            # Add verification details
            premium_role_name = user_info.get('premium_role_name', 'Premium')
            embed.add_field(
                name="🎯 Verification Details",
                value=(
                    f"**Premium Tier:** {premium_role_name}\n"
                    f"**Status:** ✅ Verified\n"
                    f"**Survey Status:** Completed"
                ),
                inline=False
            )

            # Add roles information
            if role_names:
                embed.add_field(
                    name="🎭 Current Roles",
                    value=f"**Role Count:** {len(role_names)}\n**Roles:** {', '.join(role_mentions)}",
                    inline=False
                )
            else:
                embed.add_field(
                    name="🎭 Current Roles",
                    value="No roles assigned",
                    inline=False
                )

            # Add profile picture
            embed.set_thumbnail(url=member.display_avatar.url)

            # Add footer
            embed.set_footer(
                text=f"User ID: {member.id} | Verification completed at",
                icon_url=self.bot.user.display_avatar.url
            )

            await channel.send(embed=embed)

            # Remove user from logged users, add to verified users, and remove from user_data.json
            self.logged_users.discard(member.id)
            self.verified_users.add(member.id)
            self.save_logged_users()
            await self.remove_user_from_data(member.id)

        except Exception as e:
            logging.error(f"Error logging verification completion for user {member.id}: {e}")

    async def remove_user_from_data(self, user_id):
        """Remove verified user from user_data.json"""
        try:
            from utils import safe_json_read, safe_json_write
            
            # Load current user data
            user_data = safe_json_read('user_data.json', {})
            
            # Remove user if they exist
            if str(user_id) in user_data:
                del user_data[str(user_id)]
                safe_json_write('user_data.json', user_data)
                logging.info(f"Removed verified user {user_id} from user_data.json")
            else:
                logging.info(f"User {user_id} not found in user_data.json")
                
        except Exception as e:
            logging.error(f"Error removing user {user_id} from user_data.json: {e}")

    @commands.Cog.listener()
    async def on_ready(self):
        """Setup when bot is ready"""
        if not USER_LOG_ID:
            logging.info("USER_LOG_ID not set - user logging disabled")
            return
        
        # Clean up any users who are already verified but still in user_data.json
        await self.cleanup_verified_users()

    async def cleanup_verified_users(self):
        """Clean up users who are already verified but still in user_data.json"""
        try:
            from utils import safe_json_read, safe_json_write
            
            # Load user data
            user_data = safe_json_read('user_data.json', {})
            if not user_data:
                return
            
            # Find users who are verified
            verified_user_ids = []
            for user_id_str, user_info in user_data.items():
                if user_info.get('survey_status') == 'verified':
                    verified_user_ids.append(user_id_str)
                    # Add to verified users set
                    self.verified_users.add(int(user_id_str))
            
            # Remove verified users from user_data.json
            for user_id_str in verified_user_ids:
                del user_data[user_id_str]
            
            # Save updated data
            if verified_user_ids:
                safe_json_write('user_data.json', user_data)
                self.save_logged_users()
                logging.info(f"Cleaned up {len(verified_user_ids)} verified users from user_data.json")
                
        except Exception as e:
            logging.error(f"Error cleaning up verified users: {e}")
        
async def setup(bot):
    await bot.add_cog(UserLogger(bot))
