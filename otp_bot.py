import asyncio
import email
from imapclient import IMAPClient
from bs4 import BeautifulSoup
from discord.ext import commands
from discord import Intents
import os
import ssl
import re
import logging

# Configure logging
logging.basicConfig(level=logging.INFO, 
                    format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Email credentials
IMAP_SERVER = "imap.mail.me.com"
IMAP_PORT = 993
EMAIL_ADDRESS_1 = os.getenv("email")
EMAIL_PASSWORD_1 = os.getenv("pass")
EMAIL_ADDRESS_2 = os.getenv("email2")
EMAIL_PASSWORD_2 = os.getenv("pass2")

# Discord bot token and channel ID
DISCORD_TOKEN = os.getenv("token")
DISCORD_CHANNEL_ID = 1315531675152809994  # Replace with your channel ID

# Discord bot setup
intents = Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)

# Keep track of processed email IDs
last_processed_email_id_1 = None
last_processed_email_id_2 = None

SSL_CONTEXT = ssl.create_default_context()

class IMAPClientManager:
    def __init__(self, email_address, email_password):
        self.email_address = email_address
        self.email_password = email_password
        self.client = None

    async def get_client(self):
        """Create a new IMAP client or return existing client."""
        try:
            # If client exists and is logged in, return it
            if self.client and self._is_client_alive():
                return self.client

            # Create a new client
            self.client = IMAPClient(IMAP_SERVER, port=IMAP_PORT, ssl_context=SSL_CONTEXT)
            self.client.login(self.email_address, self.email_password)
            logger.info(f"Logged in to mailbox: {self.email_address[:6]}******")
            return self.client
        except Exception as e:
            logger.error(f"Error creating IMAP client for {self.email_address}: {e}")
            self.client = None
            return None

    def _is_client_alive(self):
        """Check if the current client is still alive."""
        try:
            # Try a simple NOOP command to check connection
            self.client.noop()
            return True
        except Exception:
            return False

    def close_client(self):
        """Close the IMAP client if it exists."""
        if self.client:
            try:
                self.client.logout()
                logger.info(f"Logged out of mailbox: {self.email_address[:6]}******")
            except Exception as e:
                logger.error(f"Error closing client for {self.email_address}: {e}")
            finally:
                self.client = None

async def fetch_new_email(imap_client, last_email_id):
    """Fetch the latest email from the IMAP client if it has not been processed."""
    if not imap_client:
        logger.error("IMAP client is None")
        return None, last_email_id

    try:
        imap_client.select_folder("INBOX")
        messages = imap_client.search(["ALL"])
        if not messages:
            logger.info("No messages in the inbox.")
            return None, last_email_id

        latest_email_id = messages[-1]
        if latest_email_id == last_email_id:
            logger.info("No new emails.")
            return None, last_email_id  # No new email

        last_email_id = latest_email_id
        response = imap_client.fetch([latest_email_id], ["BODY[]", "ENVELOPE"])
        raw_email = response[latest_email_id][b"BODY[]"]

        msg = email.message_from_bytes(raw_email)

        # Extract recipient email
        envelope = response[latest_email_id].get(b"ENVELOPE", None)
        if envelope:
            recipient_email = envelope.to[0].mailbox.decode() + "@" + envelope.to[0].host.decode()
            masked_email = recipient_email[:6] + "******" + recipient_email[recipient_email.index("@"):]
            logger.info(f"Extracted recipient email: {masked_email}")
        else:
            logger.warning("Failed to extract the recipient email.")
            return None, last_email_id

        # Extract email body
        if msg.is_multipart():
            body = None
            for part in msg.walk():
                if part.get_content_type() == "text/html":
                    body = part.get_payload(decode=True).decode()
                    break
            if not body:
                logger.warning("No HTML part found in the email.")
                return None, last_email_id
        else:
            body = msg.get_payload(decode=True).decode()

        # Extract OTP using BeautifulSoup
        soup = BeautifulSoup(body, "html.parser")
        otp_element = soup.find("td", class_="p2b")  # Adjust this selector if needed
        if otp_element:
            otp_text = otp_element.get_text(strip=True)
            if re.fullmatch(r"\d{4}", otp_text):
                logger.info(f"Extracted OTP: {otp_text}")
                return f"Email: {masked_email}\nOTP: {otp_text}", last_email_id
            else:
                logger.warning(f"Failed to match OTP format. Extracted text: {otp_text}")
        else:
            logger.warning("No OTP element found in the email body.")

        return None, last_email_id

    except Exception as e:
        logger.error(f"Error fetching email: {e}")
        return None, last_email_id

async def email_monitor():
    """Monitor new emails for both accounts and send the information to Discord."""
    await bot.wait_until_ready()
    channel = bot.get_channel(DISCORD_CHANNEL_ID)
    if not channel:
        logger.error(f"Invalid Discord channel ID: {DISCORD_CHANNEL_ID}")
        return

    # Create client managers
    client_manager1 = IMAPClientManager(EMAIL_ADDRESS_1, EMAIL_PASSWORD_1)
    client_manager2 = IMAPClientManager(EMAIL_ADDRESS_2, EMAIL_PASSWORD_2)

    global last_processed_email_id_1, last_processed_email_id_2

    while True:
        try:
            # Get clients (will reuse existing or create new if needed)
            client1 = await client_manager1.get_client()
            client2 = await client_manager2.get_client()

            if not client1 or not client2:
                logger.error("Failed to create IMAP clients")
                await asyncio.sleep(180)  # Wait 3 minutes before retrying
                continue

            # Check inbox 1
            email_content_1, last_processed_email_id_1 = await fetch_new_email(client1, last_processed_email_id_1)
            if email_content_1:
                logger.info(f"Sending to Discord (Inbox 1): {email_content_1}")
                await channel.send(email_content_1)

            # Check inbox 2
            email_content_2, last_processed_email_id_2 = await fetch_new_email(client2, last_processed_email_id_2)
            if email_content_2:
                logger.info(f"Sending to Discord (Inbox 2): {email_content_2}")
                await channel.send(email_content_2)

            # Wait longer between checks
            await asyncio.sleep(300)  # 1 minute between checks

        except Exception as e:
            logger.error(f"Error in email monitor main loop: {e}")
            await asyncio.sleep(180)  # Wait 3 minutes before retrying

@bot.event
async def on_ready():
    """Triggered when the bot is ready."""
    logger.info(f"Logged in as {bot.user}")
    bot.loop.create_task(email_monitor())

# Run the bot
bot.run(DISCORD_TOKEN)