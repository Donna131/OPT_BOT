import asyncio
import email
from imapclient import IMAPClient
from bs4 import BeautifulSoup
from discord.ext import commands
from discord import Intents
import os
import ssl
import re

# Email credentials
IMAP_SERVER = "imap.mail.me.com"
IMAP_PORT = 993
EMAIL_ADDRESS_1 = os.getenv("email")
EMAIL_PASSWORD_1 = os.getenv("pass")
EMAIL_ADDRESS_2 = os.getenv("email2")
EMAIL_PASSWORD_2 = os.getenv("pass2")

# Discord bot token and channel ID
DISCORD_TOKEN = os.getenv("token")
DISCORD_CHANNEL_ID = 123456789012345678  # Replace with your channel ID

# Discord bot setup
intents = Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)

# Keep track of processed email IDs
last_processed_email_id_1 = None
last_processed_email_id_2 = None

SSL_CONTEXT = ssl.create_default_context()

async def fetch_new_email(imap_client, last_email_id):
    """Fetch the latest email from the IMAP client if it has not been processed."""
    try:
        imap_client.select_folder("INBOX")
        messages = imap_client.search(["ALL"])
        if not messages:
            return None, last_email_id

        latest_email_id = messages[-1]
        if latest_email_id == last_email_id:
            return None, last_email_id  # No new email

        last_email_id = latest_email_id
        response = imap_client.fetch([latest_email_id], ["BODY[]", "ENVELOPE"])
        raw_email = response[latest_email_id][b"BODY[]"]

        msg = email.message_from_bytes(raw_email)
        if msg.is_multipart():
            for part in msg.walk():
                if part.get_content_type() == "text/html":
                    body = part.get_payload(decode=True).decode()
                    break
        else:
            body = msg.get_payload(decode=True).decode()

        # Extract OTP using BeautifulSoup
        soup = BeautifulSoup(body, "html.parser")
        otp_element = soup.find("td", class_="p2b")  # Adjust this selector if needed
        if otp_element:
            otp_text = otp_element.get_text(strip=True)
            if re.fullmatch(r"\d{4}", otp_text):
                return otp_text, last_email_id
        return None, last_email_id

    except Exception as e:
        print(f"Error fetching email: {e}")
        return None, last_email_id


async def email_monitor():
    """Monitor new emails for both accounts."""
    await bot.wait_until_ready()
    channel = bot.get_channel(DISCORD_CHANNEL_ID)
    if not channel:
        print("Invalid Discord channel ID.")
        return

    global last_processed_email_id_1, last_processed_email_id_2

    try:
        # Establish connections
        with IMAPClient(IMAP_SERVER, port=IMAP_PORT, ssl_context=SSL_CONTEXT) as client1, \
             IMAPClient(IMAP_SERVER, port=IMAP_PORT, ssl_context=SSL_CONTEXT) as client2:
            client1.login(EMAIL_ADDRESS_1, EMAIL_PASSWORD_1)
            client2.login(EMAIL_ADDRESS_2, EMAIL_PASSWORD_2)
            print("Logged in to both mailboxes.")

            while True:
                email_content_1, last_processed_email_id_1 = await fetch_new_email(client1, last_processed_email_id_1)
                email_content_2, last_processed_email_id_2 = await fetch_new_email(client2, last_processed_email_id_2)

                if email_content_1:
                    await channel.send(f"New OTP: {email_content_1}")
                if email_content_2:
                    await channel.send(f"New OTP: {email_content_2}")

                await asyncio.sleep(5)

    except Exception as e:
        print(f"Error in email monitor: {e}")


async def keep_imap_alive():
    """Send periodic NOOP commands to keep the IMAP connections alive."""
    try:
        # Persistent connections
        with IMAPClient(IMAP_SERVER, port=IMAP_PORT, ssl_context=SSL_CONTEXT) as client1, \
             IMAPClient(IMAP_SERVER, port=IMAP_PORT, ssl_context=SSL_CONTEXT) as client2:
            client1.login(EMAIL_ADDRESS_1, EMAIL_PASSWORD_1)
            client2.login(EMAIL_ADDRESS_2, EMAIL_PASSWORD_2)
            print("IMAP connections established for NOOP.")

            while True:
                try:
                    client1.noop()
                    print("NOOP successful for mailbox 1.")
                    client2.noop()
                    print("NOOP successful for mailbox 2.")
                except Exception as e:
                    print(f"Error during NOOP: {e}")
                await asyncio.sleep(600)

    except Exception as e:
        print(f"Error establishing NOOP connections: {e}")


@bot.event
async def on_ready():
    """Triggered when the bot is ready."""
    print(f"Logged in as {bot.user}")
    bot.loop.create_task(email_monitor())
    bot.loop.create_task(keep_imap_alive())


# Run the bot
bot.run(DISCORD_TOKEN)
