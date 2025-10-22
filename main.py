import sys
import subprocess
import importlib.metadata  # Replace deprecated pkg_resources
import logging
import discord
from discord.ext import commands
import asyncio
from dotenv import load_dotenv
import os
from datetime import datetime, timezone
import json

# Load environment variables
load_dotenv()

# Security Configuration
OWNER_USER_IDS = {890323443252351046, 879714530769391686}
GUILD_ID = int(os.getenv('GUILD_ID', 0))
MEMBER_ROLE_ID = int(os.getenv('MEMBER_ROLE_ID', 0))
UNVERIFIED_ROLE_ID = int(os.getenv('UNVERIFIED_ROLE_ID', 0))
WELCOME_CHANNEL_ID = int(os.getenv('WELCOME_CHANNEL_ID', 0))
ROLE_ASSIGNMENT_DELAY = int(os.getenv('ROLE_ASSIGNMENT_DELAY', 10))
CHECK_INTERVAL = int(os.getenv('CHECK_INTERVAL', 30))
CALENDLY_LINK = os.getenv('CALENDLY_LINK', '')

def is_authorized_guild_or_owner(interaction):
    """Check if user is authorized to use commands"""
    if interaction.guild and interaction.guild.id == GUILD_ID:
        return True
    if interaction.user.id in OWNER_USER_IDS:
        return True
    return False

async def get_or_create_welcome_message(welcome_channel, embed, view):
    """Get message ID and edit it, or create new if needed."""
    from config import WELCOME_MESSAGE_FILE
    from utils import safe_json_read, safe_json_write
    
    data = safe_json_read(WELCOME_MESSAGE_FILE, {})
    msg_id = data.get('message_id')
    
    # If data is empty or corrupted, reset it
    if not isinstance(data, dict):
        data = {}
        msg_id = None
    
    if msg_id:
        try:
            msg = await welcome_channel.fetch_message(msg_id)
            await msg.edit(embed=embed, view=view)
            return msg
        except:
            pass
    
    # Create new message only if needed
    msg = await welcome_channel.send(embed=embed, view=view)
    safe_json_write(WELCOME_MESSAGE_FILE, {'message_id': msg.id, 'channel_id': welcome_channel.id})
    return msg

def check_and_install_requirements():
    """Check and install required packages using modern importlib.metadata"""
    try:
        with open('requirements.txt') as f:
            requirements = [line.strip() for line in f if line.strip()]
        
        # Use importlib.metadata instead of deprecated pkg_resources
        try:
            installed = {dist.metadata['name'].lower().replace('-', '_') for dist in importlib.metadata.distributions()}
        except Exception:
            # Fallback for older Python versions
            import pkg_resources
            installed = {pkg.key for pkg in pkg_resources.working_set}
        
        missing = []
        for requirement in requirements:
            pkg_name = requirement.split('>=')[0].lower().replace('-', '_')
            if pkg_name not in installed:
                missing.append(requirement)
        
        if missing:
            print("📦 Installing missing packages...")
            subprocess.check_call([sys.executable, '-m', 'pip', 'install'] + missing, 
                                stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
            print("✅ All required packages installed!")
        else:
            print("✅ All required packages already installed!")
            
    except Exception as e:
        print(f"❌ Error checking/installing packages: {e}")
        sys.exit(1)

# Run the check at startup
print("🔍 Checking dependencies...", end=" ")
check_and_install_requirements()

def setup_logging():
    """Setup clean, production-ready logging"""
    # Clear any existing handlers
    for handler in logging.root.handlers[:]:
        logging.root.removeHandler(handler)
    
    # Create formatter
    formatter = logging.Formatter(
        '%(asctime)s | %(levelname)-8s | %(name)-15s | %(message)s',
        datefmt='%H:%M:%S'
    )
    
    # File handler
    file_handler = logging.FileHandler('bot.log', encoding='utf-8')
    file_handler.setFormatter(formatter)
    file_handler.setLevel(logging.WARNING)  # Only warnings and errors
    
    # Console handler (minimal output)
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(logging.Formatter('%(levelname)-8s | %(message)s'))
    console_handler.setLevel(logging.ERROR)  # Only errors to console
    
    # Setup root logger
    logging.basicConfig(
        level=logging.WARNING,
        handlers=[file_handler, console_handler]
    )
    
    # Reduce discord.py logging noise
    logging.getLogger('discord').setLevel(logging.ERROR)
    logging.getLogger('discord.http').setLevel(logging.ERROR)
    logging.getLogger('discord.gateway').setLevel(logging.ERROR)

setup_logging()

# Set up intents
intents = discord.Intents.default()
intents.members = True
intents.message_content = True
intents.guilds = True
intents.guild_messages = True

class ApexEcomGatekeeper(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix='!', intents=intents)
        self.startup_time = datetime.now(timezone.utc)
        
    async def setup_hook(self):
        print("🔧 Loading cogs...", end=" ")
        try:
            await self.load_extension('cogs')
            print(f"✅ All cogs loaded successfully!")
            logging.info("All cogs loaded via cogs/__init__.py loader")
        except Exception as e:
            print(f"❌ Failed to load cogs: {e}")
            logging.error(f"Failed to load cogs: {e}")

        print("🔧 Loading commands...", end=" ")
        try:
            await self.load_extension('commands')
            print(f"✅ All commands loaded successfully!")
            logging.info("All commands loaded via commands/__init__.py loader")
        except Exception as e:
            print(f"❌ Failed to load commands: {e}")
            logging.error(f"Failed to load commands: {e}")
        
        print("🔄 Syncing commands...", end=" ")
        
        # Sync commands globally
        try:
            synced = await self.tree.sync()
            print(f"✅ Synced {len(synced)} slash commands")
            logging.info(f"Synced {len(synced)} slash commands globally")
        except Exception as e:
            print(f"❌ Failed to sync commands: {e}")
            logging.error(f"Failed to sync commands: {e}")

    async def on_ready(self):
        print(f"\n🤖 {self.user} is now online!")
        print(f"📊 Connected to {len(self.guilds)} guild(s)")
        print(f"👥 Serving {sum(guild.member_count or 0 for guild in self.guilds)} members")
        
        # Set custom status
        try:
            await self.change_presence(
                status=discord.Status.dnd,
                activity=discord.Activity(
                    type=discord.ActivityType.watching,
                    name="Apex Ecom"
                )
            )
            print("✅ Status set: DND - Watching Apex Ecom")
        except Exception as e:
            print(f"❌ Failed to set status: {e}")
        
        # Fixed deprecation warning here
        current_time = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')
        print(f"\n🚀 Bot fully initialized at {current_time} UTC")
        print("=" * 60)
        
        logging.info(f"Bot started successfully as {self.user}")

    async def on_command_error(self, ctx, error):
        """Handle command errors"""
        if isinstance(error, commands.CommandNotFound):
            return
        elif isinstance(error, commands.MissingPermissions):
            await ctx.send("❌ You don't have permission to use this command!")
        else:
            logging.error(f"Command error: {error}")

    async def on_application_command_error(self, interaction, error):
        """Handle slash command errors"""
        error_id = f"ERR_{hash(str(error)) % 10000:04d}"
        
        if isinstance(error, discord.app_commands.MissingPermissions):
            try:
                if not interaction.response.is_done():
                    await interaction.response.send_message(
                        "❌ You don't have permission to use this command!", 
                        ephemeral=True
                    )
            except:
                pass
        else:
            logging.error(f"Slash command error [{error_id}]: {error}")
            
            try:
                if not interaction.response.is_done():
                    await interaction.response.send_message(
                        f"❌ An error occurred. Error ID: `{error_id}`", 
                        ephemeral=True
                    )
                else:
                    await interaction.followup.send(
                        f"❌ An error occurred. Error ID: `{error_id}`", 
                        ephemeral=True
                    )
            except Exception as e:
                logging.error(f"Failed to send error response: {e}")
                pass

    async def on_error(self, event, *args, **kwargs):
        """Handle general bot errors"""
        logging.error(f"Bot error in event {event}: {args}, {kwargs}")

    async def on_disconnect(self):
        """Handle bot disconnection"""
        print("⚠️  Bot disconnected. Attempting to reconnect...")
        logging.warning("Bot disconnected")

    async def on_resumed(self):
        """Handle bot reconnection"""
        print("✅ Bot reconnected successfully!")
        logging.info("Bot reconnected successfully")


# Create bot instance
bot = ApexEcomGatekeeper()

# Add a simple test command
@bot.tree.command(name="ping", description="Test if the bot is responding")
async def ping(interaction):
    """Simple ping command"""
    if not interaction.guild:
        return await interaction.response.send_message(
            "❌ This command can only be used in a server!", 
            ephemeral=True
        )
    
    latency = round(bot.latency * 1000)
    embed = discord.Embed(
        title="🏓 Pong!",
        description=f"Bot latency: {latency}ms",
        color=discord.Color.green()
    )
    await interaction.response.send_message(embed=embed, ephemeral=True)

if __name__ == "__main__":
    print("🚀 Starting Apex Ecom Bot...")
    print("=" * 60)
    
    token = os.getenv('TOKEN')
    if not token:
        print("❌ CRITICAL ERROR: TOKEN environment variable is not set!")
        print("   Please check your .env file and ensure TOKEN is properly configured.")
        logging.error("Bot startup failed: TOKEN environment variable missing")
        input("Press Enter to exit...")
        sys.exit(1)
    
    # Enhanced bot startup with retry logic
    max_retries = 5
    retry_count = 0
    
    while retry_count < max_retries:
        try:
            print(f"🔄 Starting bot (attempt {retry_count + 1}/{max_retries})...")
            bot.run(token, log_handler=None, reconnect=True)
            break  # If successful, exit the retry loop
            
        except discord.LoginFailure:
            print("❌ CRITICAL ERROR: Invalid bot token!")
            print("   Please check your TOKEN in the .env file.")
            logging.error("Bot startup failed: Invalid token")
            break  # Don't retry login failures
            
        except discord.ConnectionClosed as e:
            retry_count += 1
            print(f"⚠️  Connection closed: {e}")
            if retry_count < max_retries:
                wait_time = min(2 ** retry_count, 30)  # Exponential backoff, max 30 seconds
                print(f"🔄 Retrying in {wait_time} seconds...")
                import time
                time.sleep(wait_time)
            else:
                print("❌ Max retries reached. Bot failed to connect.")
                logging.error(f"Bot failed after {max_retries} retries")
                
        except Exception as e:
            retry_count += 1
            print(f"❌ Error: {e}")
            logging.error(f"Bot startup error: {e}")
            if retry_count < max_retries:
                wait_time = min(2 ** retry_count, 30)
                print(f"🔄 Retrying in {wait_time} seconds...")
                import time
                time.sleep(wait_time)
            else:
                print("❌ Max retries reached. Bot failed to start.")
                logging.error(f"Bot failed after {max_retries} retries")
    
    print("\n👋 Bot shutdown complete.")
    input("Press Enter to exit...")