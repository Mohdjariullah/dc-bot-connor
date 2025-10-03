import json
import os
import logging
import threading
from datetime import datetime, timezone
import traceback

# Cross-platform file locking
_file_locks = {}

def get_file_lock(filename):
    """Get a file lock for thread safety"""
    if filename not in _file_locks:
        _file_locks[filename] = threading.Lock()
    return _file_locks[filename]

def safe_json_write(filename, data):
    """Safely write JSON data with file locking and atomic operations"""
    lock = get_file_lock(filename)
    with lock:
        try:
            # Use atomic write operation for better safety
            temp_filename = f"{filename}.tmp"
            with open(temp_filename, 'w') as f:
                json.dump(data, f, indent=2)
            
            # Atomic rename (works on both Windows and Unix)
            if os.path.exists(filename):
                os.replace(temp_filename, filename)
            else:
                os.rename(temp_filename, filename)
                
        except Exception as e:
            logging.error(f"Error writing to {filename}: {e}")
            # Clean up temp file if it exists
            try:
                if os.path.exists(temp_filename):
                    os.remove(temp_filename)
            except:
                pass
            raise

def safe_json_read(filename, default=None):
    """Safely read JSON data with file locking"""
    if default is None:
        default = {}
    lock = get_file_lock(filename)
    with lock:
        try:
            with open(filename, 'r') as f:
                data = json.load(f)
                return data
        except FileNotFoundError:
            return default
        except Exception as e:
            logging.error(f"Error reading from {filename}: {e}")
            return default

async def report_critical_error(error_type, error_message, bot=None, interaction=None):
    """Report critical errors to owners via logs and DM"""
    try:
        # Get owner IDs from environment or main.py
        owner_ids = []
        try:
            from main import OWNER_USER_IDS
            owner_ids = list(OWNER_USER_IDS)
        except ImportError:
            # Fallback to environment variable
            owner_str = os.getenv('OWNER_USER_IDS', '')
            if owner_str:
                owner_ids = [int(id.strip()) for id in owner_str.split(',') if id.strip().isdigit()]
        
        if not owner_ids:
            logging.error("No owner IDs configured for error reporting")
            return
        
        # Create error embed
        import discord
        error_embed = discord.Embed(
            title=f"🚨 CRITICAL ERROR: {error_type}",
            description=f"**Error:** {error_message}",
            color=0xff0000,
            timestamp=datetime.now(timezone.utc)
        )
        
        # Add context information
        if interaction:
            error_embed.add_field(name="User", value=f"{interaction.user.mention} (`{interaction.user.id}`)", inline=True)
            error_embed.add_field(name="Guild", value=f"{interaction.guild.name if interaction.guild else 'DM'} (`{interaction.guild.id if interaction.guild else 'N/A'}`)", inline=True)
            error_embed.add_field(name="Channel", value=f"{interaction.channel.mention if interaction.channel else 'N/A'}", inline=True)
        
        # Add stack trace for debugging
        stack_trace = traceback.format_exc()
        if stack_trace and stack_trace != "NoneType: None\n":
            # Truncate if too long
            if len(stack_trace) > 1000:
                stack_trace = stack_trace[:1000] + "..."
            error_embed.add_field(name="Stack Trace", value=f"```{stack_trace}```", inline=False)
        
        error_embed.set_footer(text="UGC Mastery Bot - Critical Error Report")
        
        # Send to logs channel
        logs_channel_id = int(os.getenv('LOGS_CHANNEL_ID', 0))
        if logs_channel_id and bot:
            try:
                logs_channel = bot.get_channel(logs_channel_id)
                if logs_channel:
                    # Ping owners in logs
                    owner_mentions = " ".join([f"<@{owner_id}>" for owner_id in owner_ids])
                    await logs_channel.send(f"🚨 **CRITICAL ERROR DETECTED** {owner_mentions}", embed=error_embed)
                    logging.error(f"Critical error reported to logs channel: {error_type} - {error_message}")
            except Exception as e:
                logging.error(f"Failed to send error to logs channel: {e}")
        
        # DM owners
        if bot:
            for owner_id in owner_ids:
                try:
                    owner = await bot.fetch_user(owner_id)
                    if owner:
                        await owner.send(embed=error_embed)
                        logging.info(f"Critical error DM sent to owner {owner_id}")
                except Exception as e:
                    logging.error(f"Failed to DM owner {owner_id}: {e}")
        
        # Also log to console for immediate visibility
        logging.critical(f"CRITICAL ERROR: {error_type} - {error_message}")
        
    except Exception as e:
        logging.error(f"Error in error reporting system: {e}")
        # Fallback to basic logging
        logging.critical(f"CRITICAL ERROR: {error_type} - {error_message}")
