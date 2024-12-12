import asyncio
import email
from imapclient import IMAPClient
from bs4 import BeautifulSoup
from discord.ext import commands
from discord import Intents
import os
import re  # Ensure this import is present

# Email credentials
IMAP_SERVER = "imap.mail.me.com"
IMAP_PORT = 993
EMAIL_ADDRESS = os.getenv("email")  # Replace with your email
EMAIL_PASSWORD = os.getenv("pass")  # Replace with your app-specific password
EMAIL_ADDRESS_2 = os.getenv("email2")  # Replace with your second email
EMAIL_PASSWORD_2 = os.getenv("pass2")  # Replace with your second app-specific password

# Discord bot token and channel ID
DISCORD_TOKEN = os.getenv("token")  # Replace with your bot token
DISCORD_CHANNEL_ID = 1315531675152809994  # Replace with your channel ID

# Discord bot setup
intents = Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)

# Keep track of processed email IDs
last_processed_email_id = None
last_processed_email_id_2 = None

async def fetch_new_email(email_address, email_password, last_email_id):
    """Fetch the latest email from the specified mailbox if it has not been processed."""
    try:
        with IMAPClient(IMAP_SERVER, port=IMAP_PORT) as client:
            client.login(email_address, email_password)
            client.select_folder("INBOX")

            # Fetch all emails sorted by date (newest first)
            messages = client.search(["ALL"])
            if not messages:
                return None, last_email_id  # No emails

            latest_email_id = messages[-1]  # Get the newest email ID

            if latest_email_id == last_email_id:
                return None, last_email_id  # No new email since the last check

            # Mark this email as processed
            last_email_id = latest_email_id

            # Fetch the content of the newest email
            response = client.fetch([latest_email_id], ["BODY[]", "ENVELOPE"])
            raw_email = response[latest_email_id][b"BODY[]"]

            # Extract the recipient email
            envelope = response[latest_email_id][b"ENVELOPE"]
            recipient_email = envelope.to[0].mailbox.decode() + "@" + envelope.to[0].host.decode()

            # Mask the recipient email
            masked_email = recipient_email[:6] + "******@" + envelope.to[0].host.decode()

            # Parse the email content
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
                if re.fullmatch(r"\d{4}", otp_text):  # Match exactly 4 digits
                    return f"Email: {masked_email}\nOTP: {otp_text}", last_email_id
                else:
                    # Log in command prompt only
                    print(f"Found text in <td>: {otp_text} (Not a 4-digit OTP)")

            return None, last_email_id  # No valid OTP found

    except Exception as e:
        print(f"Error fetching email: {e}")
        return None, last_email_id

async def email_monitor():
    """Monitor for new emails from both mailboxes and send updates to Discord."""
    await bot.wait_until_ready()
    channel = bot.get_channel(DISCORD_CHANNEL_ID)
    if not channel:
        print("Invalid Discord channel ID.")
        return

    global last_processed_email_id, last_processed_email_id_2

    while not bot.is_closed():
        email_content_1, last_processed_email_id = await fetch_new_email(
            EMAIL_ADDRESS, EMAIL_PASSWORD, last_processed_email_id
        )
        email_content_2, last_processed_email_id_2 = await fetch_new_email(
            EMAIL_ADDRESS_2, EMAIL_PASSWORD_2, last_processed_email_id_2
        )

        if email_content_1:
            await channel.send(email_content_1)
        if email_content_2:
            await channel.send(email_content_2)

        await asyncio.sleep(5)  # Check every 5 seconds

async def keep_imap_alive():
    """Send NOOP command periodically to keep the IMAP connection alive."""
    try:
        # Persistent connection for the first email
        print("Connecting to IMAP server for mailbox 1...")
        client1 = IMAPClient(IMAP_SERVER, port=IMAP_PORT)
        client1.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
        client1.select_folder("INBOX")
        print("IMAP connection for mailbox 1 established.")

        # Persistent connection for the second email
        print("Connecting to IMAP server for mailbox 2...")
        client2 = IMAPClient(IMAP_SERVER, port=IMAP_PORT)
        client2.login(EMAIL_ADDRESS_2, EMAIL_PASSWORD_2)
        client2.select_folder("INBOX")
        print("IMAP connection for mailbox 2 established.")

        while True:
            try:
                # Send NOOP commands
                print("Sending NOOP for mailbox 1...")
                client1.noop()
                print("NOOP for mailbox 1 successful.")

                print("Sending NOOP for mailbox 2...")
                client2.noop()
                print("NOOP for mailbox 2 successful.")
            except Exception as e:
                print(f"Error during NOOP: {e}")

            # Sleep for 5 minutes
            await asyncio.sleep(60)

    except Exception as e:
        print(f"Error establishing IMAP connections: {e}")
    finally:
        # Close connections
        try:
            print("Logging out mailbox 1...")
            client1.logout()
        except Exception as e:
            print(f"Error logging out mailbox 1: {e}")

        try:
            print("Logging out mailbox 2...")
            client2.logout()
        except Exception as e:
            print(f"Error logging out mailbox 2: {e}")
            
@bot.event
async def on_ready():
    """Triggered when the bot is ready."""
    print(f"Logged in as {bot.user}")
    # Start both the email monitor and IMAP keep-alive tasks
    bot.loop.create_task(email_monitor())
    bot.loop.create_task(keep_imap_alive())  # Keep the IMAP connection alive

# Run the bot
bot.run(DISCORD_TOKEN)
