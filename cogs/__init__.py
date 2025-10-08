import logging
from discord.ext import commands

# Import all cog modules
from . import verification
from . import welcome
from . import ai_channel
from . import webhook_handler
from . import role_monitor

async def setup(bot: commands.Bot) -> None:
    """Add all cogs to the bot."""
    logger = logging.getLogger(__name__)
    msg = "Loaded cogs.{}"
    await verification.setup(bot)
    logger.debug(msg.format("verification"))
    await welcome.setup(bot)
    logger.debug(msg.format("welcome"))
    await ai_channel.setup(bot)
    logger.debug(msg.format("ai_channel"))
    await webhook_handler.setup(bot)
    logger.debug(msg.format("webhook_handler"))
    await role_monitor.setup(bot)
    logger.debug(msg.format("role_monitor")) 