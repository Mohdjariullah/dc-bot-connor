import discord
from discord.ext import commands
import logging
import re
from datetime import datetime, timezone
from utils import safe_json_write, safe_json_read
from config import (
    UNVERIFIED_ROLE_ID, VIP_ROLE_ID, HUNDRED_K_ROLE_ID, SUBMISSION_LOGS_CHANNEL_ID,
    CALENDLY_LINK, get_verification_complete_embed
)


class WebhookHandler(commands.Cog):
    """Handle Typeform webhook messages and automatic user verification"""
    
    def __init__(self, bot):
        self.bot = bot
        
    @commands.Cog.listener()
    async def on_message(self, message):
        """Handle incoming messages, including Typeform webhook notifications"""
        # Skip bot messages and non-guild messages
        if message.author.bot or not message.guild:
            return
            
        # Check for Typeform webhook messages
        await self.handle_typeform_webhook(message)

    async def handle_typeform_webhook(self, message):
        """Handle Typeform webhook messages and automatically verify users"""
        try:
            # Debug logging
            logging.info(f"Processing message from {message.author.name} in channel {message.channel.name} ({message.channel.id})")
            logging.info(f"Message content: {message.content}")
            
            # Check if this is a Typeform webhook message
            if not self.is_typeform_webhook_message(message):
                logging.debug("Message is not a Typeform webhook message")
                return
                
            logging.info("Typeform webhook message detected!")
                
            # Extract auth_code from the message
            auth_code = self.extract_auth_code_from_message(message)
            if not auth_code:
                logging.warning("Typeform webhook message detected but no auth_code found")
                logging.debug(f"Message content: {message.content}")
                if message.embeds:
                    logging.debug(f"Embed fields: {[f'{f.name}: {f.value}' for f in message.embeds[0].fields]}")
                return
            
            logging.info(f"Extracted auth_code: {auth_code} from Typeform webhook")
                
            # Verify the user automatically
            await self.auto_verify_user(message.guild, auth_code, message)
            
        except Exception as e:
            logging.error(f"Error handling Typeform webhook: {e}")

    def is_typeform_webhook_message(self, message):
        """Check if message is from a Typeform webhook"""
        # Check message content for Typeform webhook indicators
        content = message.content or ""
        content_lower = content.lower()
        
        # Check for Typeform webhook indicators in content
        typeform_indicators = [
            "new typeform submission",
            "typeform submission details", 
            "form:",
            "submitted:",
            "auth code:",
            "answers:"
        ]
        
        has_content_indicators = any(indicator in content_lower for indicator in typeform_indicators)
        
        # Also check embeds if they exist
        has_embed_indicators = False
        if message.embeds:
            embed = message.embeds[0]
            title = embed.title or ""
            description = embed.description or ""
            embed_content = f"{title} {description}".lower()
            has_embed_indicators = any(indicator in embed_content for indicator in typeform_indicators)
        
        # Check if it's from a webhook or app
        is_from_app = message.author.name.lower() in ["verify logs submission", "typeform", "webhook"]
        
        return has_content_indicators or has_embed_indicators or is_from_app

    def extract_auth_code_from_message(self, message):
        """Extract auth_code from Typeform webhook message"""
        try:
            # Look for auth_code in embed fields first (most common case)
            if message.embeds:
                embed = message.embeds[0]
                
                # Check embed fields for auth_code
                for field in embed.fields:
                    if field.name and field.value:
                        field_text = f"{field.name} {field.value}".lower()
                        
                        # Look for "Auth Code" field specifically (plain text, no backticks)
                        if "auth code" in field_text:
                            # Extract the value - it's plain text, no formatting
                            auth_code_value = field.value.strip()
                            
                            # Check if it's a Discord user ID (17-19 digits)
                            user_id_match = re.search(r'(\d{17,19})', auth_code_value)
                            if user_id_match:
                                logging.info(f"Found auth_code in embed field: {user_id_match.group(1)}")
                                return user_id_match.group(1)
                        
                        # Also check for URLs with auth_code parameter
                        url_match = re.search(r'auth_code[=:](\d{17,19})', field.value)
                        if url_match:
                            return url_match.group(1)
                
                # Check description for auth_code patterns
                if embed.description:
                    # Look for "Auth Code: xxxxx" pattern in description
                    auth_code_match = re.search(r'Auth Code:\s*`?(\d{17,19})`?', embed.description)
                    if auth_code_match:
                        return auth_code_match.group(1)
                    
                    # Look for auth_code in description
                    auth_code_match = re.search(r'auth_code[=:](\d{17,19})', embed.description)
                    if auth_code_match:
                        return auth_code_match.group(1)
                    
                    # Look for any Discord user ID in description
                    user_id_match = re.search(r'\b(\d{17,19})\b', embed.description)
                    if user_id_match:
                        return user_id_match.group(1)
                
                # Check embed title
                if embed.title:
                    title_match = re.search(r'\b(\d{17,19})\b', embed.title)
                    if title_match:
                        return title_match.group(1)
                        
            # Check message content for auth_code patterns
            if message.content:
                # Look for "Auth Code: xxxxx" pattern in content (with backticks)
                auth_code_match = re.search(r'\*\*Auth Code:\*\*\s*`(\d{17,19})`', message.content)
                if auth_code_match:
                    logging.info(f"Found auth_code in message content (with backticks): {auth_code_match.group(1)}")
                    return auth_code_match.group(1)
                
                # Look for "Auth Code: xxxxx" pattern in content (plain text, no backticks)
                auth_code_match = re.search(r'\*\*Auth Code:\*\*\s*(\d{17,19})', message.content)
                if auth_code_match:
                    logging.info(f"Found auth_code in message content: {auth_code_match.group(1)}")
                    return auth_code_match.group(1)
                
                # Also try without the bold formatting
                auth_code_match = re.search(r'Auth Code:\s*(\d{17,19})', message.content)
                if auth_code_match:
                    logging.info(f"Found auth_code in message content (no bold): {auth_code_match.group(1)}")
                    return auth_code_match.group(1)
                
                # Look for auth_code in content
                auth_code_match = re.search(r'auth_code[=:](\d{17,19})', message.content)
                if auth_code_match:
                    return auth_code_match.group(1)
                
                # Look for any Discord user ID in content
                user_id_match = re.search(r'\b(\d{17,19})\b', message.content)
                if user_id_match:
                    return user_id_match.group(1)
                    
            # Check for URLs in the entire message (including embeds)
            full_text = message.content or ""
            if message.embeds:
                for embed in message.embeds:
                    full_text += f" {embed.title or ''} {embed.description or ''}"
                    for field in embed.fields:
                        full_text += f" {field.name or ''} {field.value or ''}"
            
            # Look for Typeform URLs with auth_code
            typeform_url_match = re.search(r'https?://[^\s]*typeform[^\s]*auth_code[=:](\d{17,19})', full_text)
            if typeform_url_match:
                return typeform_url_match.group(1)
                    
            return None
            
        except Exception as e:
            logging.error(f"Error extracting auth_code: {e}")
            return None

    async def auto_verify_user(self, guild, user_id, webhook_message, skip_logs_check=False):
        """Automatically verify premium user based on auth_code from Typeform webhook"""
        try:
            # Step 1: Extract auth_code (already done in calling function)
            logging.info(f"Processing Typeform submission for user {user_id}")
            
            # Step 2: Verify auth_code exists in SUBMISSION_LOGS_CHANNEL_ID (unless skipped)
            if not skip_logs_check:
                logging.info(f"Checking auth_code {user_id} in submission logs channel {SUBMISSION_LOGS_CHANNEL_ID}")
                if not await self.verify_auth_code_in_logs(guild, user_id):
                    logging.warning(f"Auth code {user_id} not found in submission logs channel")
                    return
                logging.info(f"Auth code {user_id} found in submission logs - proceeding with verification")
            else:
                logging.info(f"Skipping logs check for user {user_id}")
            
            # Check if user exists in the guild
            user = guild.get_member(int(user_id))
            if not user:
                logging.warning(f"User {user_id} not found in guild {guild.id}")
                return
                
            # Load user data
            user_data = safe_json_read('user_data.json', {})
            
            if user_id not in user_data:
                logging.warning(f"User {user_id} not found in user data - not a premium user")
                return
                
            user_info = user_data[user_id]
            
            # Check if already verified
            if user_info.get('survey_status') == 'verified':
                logging.info(f"User {user_id} already verified, skipping")
                return
            
            # Check if this is a premium user
            premium_role_id = user_info.get('premium_role_id')
            premium_role_name = user_info.get('premium_role_name')
            if not premium_role_id or not premium_role_name:
                logging.warning(f"User {user_id} has no premium role stored - not a premium user")
                return
                
            # Mark as verified
            user_info['survey_status'] = 'verified'
            user_data[user_id] = user_info
            safe_json_write('user_data.json', user_data)
            
            # Remove unverified role
            if UNVERIFIED_ROLE_ID:
                unverified_role = guild.get_role(UNVERIFIED_ROLE_ID)
                if unverified_role and unverified_role in user.roles:
                    await user.remove_roles(unverified_role)
                    logging.info(f"Removed unverified role from user {user_id}")
            
            # Action 1: Restore premium role using stored role ID
            premium_role = guild.get_role(premium_role_id)
            
            if premium_role:
                await user.add_roles(premium_role)
                logging.info(f"Restored premium role '{premium_role_name}' (ID: {premium_role_id}) to user {user_id}")
                
                # Action 2: Send DM with verification complete message and call link
                embed = get_verification_complete_embed(premium_role_name)
            else:
                logging.error(f"Premium role with ID {premium_role_id} ('{premium_role_name}') not found in guild")
                embed = discord.Embed(
                    title="⚠️ Verification Complete",
                    description=(
                        f"Your survey has been submitted, but we couldn't find your **{premium_role_name}** role.\n\n"
                        "Please contact support to restore your premium access.\n\n"
                        "Thank you for completing the verification!"
                    ),
                    color=0xffa500
                )
            
            # Send confirmation DM to user
            try:
                await user.send(embed=embed)
            except discord.Forbidden:
                logging.warning(f"Could not send DM to user {user_id}")
                
            # Log the auto-verification
            logging.info(f"Auto-verified premium user {user_id} ({user.display_name}) via Typeform webhook")
            
            # Add reaction to the webhook message to indicate processing
            try:
                await webhook_message.add_reaction("✅")
            except:
                pass
                
        except Exception as e:
            logging.error(f"Error in auto_verify_user: {e}")

    async def verify_auth_code_in_logs(self, guild, auth_code):
        """Verify that auth_code exists in SUBMISSION_LOGS_CHANNEL_ID"""
        try:
            # Get the submission logs channel
            if not SUBMISSION_LOGS_CHANNEL_ID:
                logging.warning("SUBMISSION_LOGS_CHANNEL_ID not set in environment variables")
                return True  # Skip verification if not configured
            
            logs_channel = guild.get_channel(SUBMISSION_LOGS_CHANNEL_ID)
            if not logs_channel:
                logging.error(f"Submission logs channel {SUBMISSION_LOGS_CHANNEL_ID} not found")
                return False
            
            # Search for the auth_code in recent messages (last 100 messages)
            async for message in logs_channel.history(limit=100):
                # Check message content for auth_code
                if auth_code in message.content:
                    logging.info(f"Found auth_code {auth_code} in submission logs")
                    return True
                
                # Check embed fields for auth_code
                if message.embeds:
                    for embed in message.embeds:
                        # Check embed description
                        if embed.description and auth_code in embed.description:
                            logging.info(f"Found auth_code {auth_code} in embed description")
                            return True
                        
                        # Check embed fields
                        for field in embed.fields:
                            if field.value and auth_code in field.value:
                                logging.info(f"Found auth_code {auth_code} in embed field")
                                return True
            
            logging.warning(f"Auth_code {auth_code} not found in submission logs channel")
            return False
            
        except Exception as e:
            logging.error(f"Error verifying auth_code in logs: {e}")
            return False

    @commands.command(name="test_webhook")
    @commands.has_permissions(administrator=True)
    async def test_webhook(self, ctx, user_id: str = None):
        """Test webhook detection and verification flow"""
        if not user_id:
            user_id = str(ctx.author.id)
        
        # Create a test message that matches the actual Typeform webhook format
        test_content = f"""🎯 **New Typeform Submission**

**Form:** 1 - 1 Mentorship
**Submitted:** {datetime.now().strftime('%A, %B %d, %Y at %I:%M %p')}
**Auth Code:** `{user_id}`

**Answers:**
**Question 1:** Test answer"""
        
        # Create a test embed
        test_embed = discord.Embed(
            title="Typeform Submission Details",
            description=f"Form ID: VkuOahlj\nTotal Answers: 1\nSubmitted At: {datetime.now().strftime('%m/%d/%Y, %I:%M:%S %p')}",
            color=0x00ff00
        )
        
        test_embed.add_field(name="Auth Code", value=user_id, inline=True)
        
        await ctx.send(
            f"🧪 **Test Webhook Message**\nThis simulates a Typeform webhook to test verification:\n\n{test_content}",
            embed=test_embed
        )
        
        # Test the extraction
        auth_code = self.extract_auth_code_from_message(ctx.message)
        if auth_code:
            await ctx.send(f"✅ Auth code extracted: `{auth_code}`")
        else:
            await ctx.send("❌ No auth code found in test message")

async def setup(bot):
    await bot.add_cog(WebhookHandler(bot))
