import asyncio
import email
from imapclient import IMAPClient
from bs4 import BeautifulSoup
from discord.ext import commands
from discord import Intents
import re  # Ensure this import is present

# Email credentials
IMAP_SERVER = "imap.mail.me.com"
IMAP_PORT = 993
EMAIL_ADDRESS = "donna.131@icloud.com"  # Replace with your email
EMAIL_PASSWORD = "hbjp-qzrs-zmvi-gxut"  # Replace with your app-specific password

# Discord bot token and channel ID
DISCORD_TOKEN = "MTI5ODI5NDIxNjk4ODAzMzA1Ng.GaLZfL._meT4XOMPMj_3Guh7_Tt3coGnDQbEjDlh_lGiA"  # Replace with your bot token
DISCORD_CHANNEL_ID = 1315531675152809994  # Replace with your channel ID

# Discord bot setup
intents = Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)

# Keep track of processed email IDs
last_processed_email_id = None

async def fetch_new_email():
    """Fetch the latest email if it has not been processed."""
    global last_processed_email_id
    try:
        with IMAPClient(IMAP_SERVER, port=IMAP_PORT) as client:
            client.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
            client.select_folder("INBOX")

            # Fetch all emails sorted by date (newest first)
            messages = client.search(["ALL"])
            if not messages:
                return None  # No emails

            latest_email_id = messages[-1]  # Get the newest email ID

            if latest_email_id == last_processed_email_id:
                return None  # No new email since the last check

            # Mark this email as processed
            last_processed_email_id = latest_email_id

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
                    return f"Email: {masked_email}\nOTP: {otp_text}"
                else:
                    # Log in command prompt only
                    print(f"Found text in <td>: {otp_text} (Not a 4-digit OTP)")

            return None  # No valid OTP found

    except Exception as e:
        print(f"Error fetching email: {e}")
        return None


async def email_monitor():
    """Monitor for new emails and send updates to Discord."""
    await bot.wait_until_ready()
    channel = bot.get_channel(DISCORD_CHANNEL_ID)
    if not channel:
        print("Invalid Discord channel ID.")
        return

    while not bot.is_closed():
        email_content = await fetch_new_email()
        if email_content:
            await channel.send(email_content)
        await asyncio.sleep(5)  # Check every 5 seconds


async def keep_imap_alive():
    """Send NOOP command periodically to keep the IMAP connection alive."""
    while True:
        try:
            with IMAPClient(IMAP_SERVER, port=IMAP_PORT) as client:
                client.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
                client.select_folder("INBOX")  # Select the folder to keep the session active
                client.noop()  # NOOP command does nothing but keeps the connection alive
                print("Sent NOOP command to keep IMAP connection alive.")
        except Exception as e:
            print(f"Error keeping IMAP connection alive: {e}")

        # Wait 5 minutes before sending the next NOOP
        await asyncio.sleep(300)  # 5 minutes


@bot.event
async def on_ready():
    """Triggered when the bot is ready."""
    print(f"Logged in as {bot.user}")
    # Start both the email monitor and IMAP keep-alive tasks
    bot.loop.create_task(email_monitor())
    bot.loop.create_task(keep_imap_alive())  # Keep the IMAP connection alive


# Run the bot
bot.run(DISCORD_TOKEN)
