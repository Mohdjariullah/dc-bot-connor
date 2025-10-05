import discord
from discord import ui
import json
import logging
from datetime import datetime, timezone
import os
import time
from utils import safe_json_write, safe_json_read, report_critical_error

USER_DATA_FILE = 'user_data.json'
COOLDOWN_FILE = 'button_cooldowns.json'
LEAD_DATA_FILE = 'lead_data.json'
RATE_LIMIT_SECONDS = 10  # 10 second rate limit


class OnboardingButton(ui.Button):
    def __init__(self):
        super().__init__(
            style=discord.ButtonStyle.green,
            label="🔒 Book Your Onboarding Call",
            custom_id="book_onboarding"
        )
        # Load cooldowns from file
        self.button_cooldowns = self.load_cooldowns()

    def load_cooldowns(self):
        """Load cooldowns from file"""
        try:
            data = safe_json_read(COOLDOWN_FILE, {})
            # Filter out expired cooldowns
            current_time = time.time()
            cooldowns = {}
            for user_id_str, last_click in data.items():
                if current_time - last_click < RATE_LIMIT_SECONDS:
                    cooldowns[user_id_str] = last_click
            return cooldowns
        except Exception as e:
            logging.error(f"Error loading cooldowns: {e}")
            return {}

    def save_cooldowns(self):
        """Save cooldowns to file"""
        safe_json_write(COOLDOWN_FILE, self.button_cooldowns)

    def cleanup_expired_cooldowns(self):
        """Remove expired cooldowns from memory and file"""
        current_time = time.time()
        expired_users = []
        
        for user_id, last_click in self.button_cooldowns.items():
            if current_time - last_click >= RATE_LIMIT_SECONDS:
                expired_users.append(user_id)
        
        for user_id in expired_users:
            del self.button_cooldowns[user_id]
        
        if expired_users:
            self.save_cooldowns()
            logging.debug(f"Cleaned up {len(expired_users)} expired cooldowns")

    async def callback(self, interaction: discord.Interaction):
        """Handle button click with rate limiting"""
        user_id = str(interaction.user.id)
        current_time = time.time()
        
        # Clean up expired cooldowns periodically
        if len(self.button_cooldowns) > 100:  # Clean up when we have many cooldowns
            self.cleanup_expired_cooldowns()
        
        # Check rate limit
        last_click = self.button_cooldowns.get(user_id, 0)
        if current_time - last_click < RATE_LIMIT_SECONDS:
            remaining_time = int(RATE_LIMIT_SECONDS - (current_time - last_click))
            try:
                if not interaction.response.is_done():
                    await interaction.response.send_message(
                        f"⏳ Please wait **{remaining_time} seconds** before trying again.",
                        ephemeral=True
                    )
            except Exception as e:
                logging.error(f"Error sending rate limit response: {e}")
            logging.info(f"Rate limited user {user_id} - {remaining_time}s remaining")
            return
        
        logging.info(f"Button callback triggered for user {interaction.user.id}")
        
        try:
            # Load user data
            user_data = safe_json_read(USER_DATA_FILE, {})
            
            # Check roles
            member_role_id = int(os.getenv('MEMBER_ROLE_ID', 0))
            unverified_role_id = int(os.getenv('UNVERIFIED_ROLE_ID', 0))
            
            has_member_role = False
            has_unverified_role = False
            
            if interaction.guild:
                if member_role_id:
                    member_role = interaction.guild.get_role(member_role_id)
                    if member_role and member_role in interaction.user.roles:
                        has_member_role = True
                
                if unverified_role_id:
                    unverified_role = interaction.guild.get_role(unverified_role_id)
                    if unverified_role and unverified_role in interaction.user.roles:
                        has_unverified_role = True
            
            # Check if user already has member role
            if has_member_role:
                embed = discord.Embed(
                    title="✅ Already Verified!",
                    description="You already have access to the community.",
                    color=0x00ff00
                )
                try:
                    if not interaction.response.is_done():
                        await interaction.response.send_message(embed=embed, ephemeral=True)
                except Exception as e:
                    logging.error(f"Error sending already verified response: {e}")
                logging.info(f"User {user_id} already has member role")
                return
            
            # Check if user has premium role stored (only premium users should use this button)
            existing_data = user_data.get(user_id, {})
            premium_role_id = existing_data.get('premium_role_id')
            premium_role_name = existing_data.get('premium_role_name')
            
            if not premium_role_id or not premium_role_name:
                # User doesn't have premium role stored - they shouldn't be using this button
                embed = discord.Embed(
                    title="❌ Access Denied",
                    description="This verification is only for premium users. Please contact support if you believe this is an error.",
                    color=0xff0000
                )
                try:
                    if not interaction.response.is_done():
                        await interaction.response.send_message(embed=embed, ephemeral=True)
                except Exception as e:
                    logging.error(f"Error sending access denied response: {e}")
                logging.info(f"Non-premium user {user_id} tried to use verification button")
                return
            
            # If user doesn't have unverified role, add it
            if not has_unverified_role and unverified_role_id and interaction.guild:
                unverified_role = interaction.guild.get_role(unverified_role_id)
                if unverified_role:
                    try:
                        await interaction.user.add_roles(unverified_role)
                        has_unverified_role = True
                        logging.info(f"Added unverified role to user {user_id}")
                    except Exception as e:
                        logging.error(f"Error adding unverified role to user {user_id}: {e}")
                        # Continue processing even if role assignment fails
            
            # Update user data to mark as having clicked the button (waiting for Typeform submission)
            user_data = safe_json_read(USER_DATA_FILE, {})
            existing_data = user_data.get(user_id, {})
            user_data[user_id] = {
                'joined_at': existing_data.get('joined_at', 0),
                'button_clicked_at': current_time,
                'has_access': False,
                'role_assigned': False,
                'unverified_role_assigned': existing_data.get('unverified_role_assigned', False),
                'lead_captured': False  # Will be set to True when webhook confirms Typeform submission
            }
            safe_json_write(USER_DATA_FILE, user_data)
            
            # Update cooldown AFTER successful processing
            self.button_cooldowns[user_id] = current_time
            self.save_cooldowns()
            
            # Show Typeform link with user ID parameter
            embed = discord.Embed(
                title="📋 Complete Your Survey to Get Started",
                description=(
                    "Ready to take the next step? Complete our quick survey to get started with The VoCreations Mentorship!\n\n"
                    "This survey will help us understand your goals and tailor the experience to your needs.\n\n"
                    "👉 **Click the link below to complete the survey**\n\n"
                    "**What happens next?**\n"
                    "1. Complete the survey using the link below\n"
                    "2. We'll automatically verify you once we receive your submission\n"
                    "3. You'll get access to the community shortly after!"
                ),
                color=0x00ff00
            )
            
            # Add Typeform link with user ID parameter
            typeform_link = f"https://form.typeform.com/to/VkuOahlj#auth_code={user_id}"
            embed.add_field(
                name="🔗 Complete Survey",
                value=f"[Click here to fill out the survey]({typeform_link})",
                inline=False
            )
            
            # Add user ID info for debugging
            embed.add_field(
                name="📋 Your User ID",
                value=f"`{user_id}` (keep this for reference)",
                inline=False
            )
            
            embed.set_footer(text="We'll automatically verify you once you submit the survey!")
            
            await interaction.response.send_message(embed=embed, ephemeral=True)
            
            logging.info(f"Showed Typeform link to user {user_id}")
            
        except Exception as e:
            logging.error(f"Error in button callback: {e}")
            
            # Report critical error to owners
            try:
                # Get bot instance from interaction
                bot = interaction.client if hasattr(interaction, 'client') else None
                await report_critical_error("Button Callback Error", f"Error in onboarding button callback: {e}", bot, interaction)
            except Exception as report_error:
                logging.error(f"Failed to report critical error: {report_error}")
            
            # Try to send user-friendly error message
            try:
                if not interaction.response.is_done():
                    await interaction.response.send_message(
                        "❌ An error occurred. Please try again later.", 
                        ephemeral=True
                    )
            except Exception as response_error:
                logging.error(f"Error sending error response: {response_error}")

class WelcomeVerifyButton(ui.Button):
    def __init__(self):
        super().__init__(
            style=discord.ButtonStyle.green,
            label="Confirm Your Survey",
            custom_id="confirm_survey"
        )
        # Load cooldowns from file
        self.button_cooldowns = self.load_cooldowns()

    def load_cooldowns(self):
        """Load cooldowns from file"""
        try:
            data = safe_json_read(COOLDOWN_FILE, {})
            # Filter out expired cooldowns
            current_time = time.time()
            cooldowns = {}
            for user_id_str, last_click in data.items():
                if current_time - last_click < RATE_LIMIT_SECONDS:
                    cooldowns[user_id_str] = last_click
            return cooldowns
        except Exception as e:
            logging.error(f"Error loading cooldowns: {e}")
            return {}

    def save_cooldowns(self):
        """Save cooldowns to file"""
        safe_json_write(COOLDOWN_FILE, self.button_cooldowns)

    async def callback(self, interaction: discord.Interaction):
        """Handle welcome verify button click with rate limiting"""
        user_id = str(interaction.user.id)
        current_time = time.time()
        
        # Clean up expired cooldowns periodically
        if len(self.button_cooldowns) > 100:  # Clean up when we have many cooldowns
            self.cleanup_expired_cooldowns()
        
        # Check rate limit
        last_click = self.button_cooldowns.get(user_id, 0)
        if current_time - last_click < RATE_LIMIT_SECONDS:
            remaining_time = int(RATE_LIMIT_SECONDS - (current_time - last_click))
            try:
                if not interaction.response.is_done():
                    await interaction.response.send_message(
                        f"⏳ Please wait **{remaining_time} seconds** before trying again.",
                        ephemeral=True
                    )
            except Exception as e:
                logging.error(f"Error sending rate limit response: {e}")
            logging.info(f"Rate limited user {user_id} - {remaining_time}s remaining")
            return
        
        logging.info(f"Welcome verify button callback triggered for user {interaction.user.id}")
        
        try:
            # Load user data
            user_data = safe_json_read(USER_DATA_FILE, {})
            user_info = user_data.get(user_id, {})
            
            # Get premium role info
            premium_role_name = user_info.get('premium_role_name', 'Premium')
            
            # User has premium role, mention it
            embed = discord.Embed(
                title="📋 Complete Your Survey to Restore Premium Access",
                description=(
                    f"Welcome back! We've detected your **{premium_role_name}** tier.\n\n"
                    "Complete this quick survey to restore your premium access and get started with The VoCreations Mentorship!\n\n"
                    "👉 **Click the link below to complete the survey**\n\n"
                    "**What happens next?**\n"
                    "1. Complete the survey using the link below\n"
                    "2. We'll automatically restore your premium role\n"
                    "3. You'll have full access to the community!"
                ),
                color=0x00ff00
            )
            
            # Add Typeform link with user ID parameter
            typeform_link = f"https://form.typeform.com/to/VkuOahlj#auth_code={user_id}"
            embed.add_field(
                name="🔗 Complete Survey",
                value=f"[Click here to fill out the survey]({typeform_link})",
                inline=False
            )
            
            # Add user ID info for debugging
            embed.add_field(
                name="📋 Your User ID",
                value=f"`{user_id}` (keep this for reference)",
                inline=False
            )
            
            embed.set_footer(text="We'll automatically verify you once you submit the survey!")
            
            await interaction.response.send_message(embed=embed, ephemeral=True)
            
            # Update user data to mark as having clicked the button (waiting for Typeform submission)
            user_data = safe_json_read(USER_DATA_FILE, {})
            existing_data = user_data.get(user_id, {})
            user_data[user_id] = {
                'premium_role_id': existing_data.get('premium_role_id'),
                'premium_role_name': existing_data.get('premium_role_name'),
                'survey_status': 'pending'  # Will be set to 'verified' when webhook confirms Typeform submission
            }
            safe_json_write(USER_DATA_FILE, user_data)
            
            # Update cooldown AFTER successful processing
            self.button_cooldowns[user_id] = current_time
            self.save_cooldowns()
            
            logging.info(f"Showed Typeform link to user {user_id} via welcome verify button")
            
        except Exception as e:
            logging.error(f"Error in welcome verify button callback: {e}")
            
            # Report critical error to owners
            try:
                # Get bot instance from interaction
                bot = interaction.client if hasattr(interaction, 'client') else None
                await report_critical_error("Welcome Verify Button Error", f"Error in welcome verify button callback: {e}", bot, interaction)
            except Exception as report_error:
                logging.error(f"Failed to report critical error: {report_error}")
            
            # Try to send user-friendly error message
            try:
                if not interaction.response.is_done():
                    await interaction.response.send_message(
                        "❌ An error occurred. Please try again later.", 
                        ephemeral=True
                    )
            except Exception as response_error:
                logging.error(f"Error sending error response: {response_error}")

    def cleanup_expired_cooldowns(self):
        """Remove expired cooldowns from memory and file"""
        current_time = time.time()
        expired_users = []
        
        for user_id, last_click in self.button_cooldowns.items():
            if current_time - last_click >= RATE_LIMIT_SECONDS:
                expired_users.append(user_id)
        
        for user_id in expired_users:
            del self.button_cooldowns[user_id]
        
        if expired_users:
            self.save_cooldowns()
            logging.debug(f"Cleaned up {len(expired_users)} expired cooldowns")
class VerificationView(ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(OnboardingButton())

class WelcomeVerifyView(ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(WelcomeVerifyButton())

async def setup(bot):
    # This cog doesn't need any setup, just the VerificationView class
    pass 