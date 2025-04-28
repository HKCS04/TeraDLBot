
import asyncio
import logging
import os
import re
import time
from uuid import uuid4
from telethon import TelegramClient
from io import BytesIO
from urllib.parse import parse_qs, urlparse

from pyrogram import Client, filters
from pyrogram.errors import FloodWait, MessageNotModified
from pyrogram.types import Message

from redis import Redis

def check_url_patterns(url):
    """
    Check if a given URL matches predefined patterns.
    """
    patterns = [
        r"mirrobox\.com",
        r"nephobox\.com",
        r"freeterabox\.com",
        r"1024tera\.com",
        r"4funbox\.com",
        r"terabox\.app",
        r"terabox\.com",
        r"momerybox\.com",
        r"tibibox\.com",
    ]

    return any(re.search(pattern, url) for pattern in patterns)


def extract_urls(string: str) -> list[str]:
    """
    Extract valid URLs from a given string.
    """
    pattern = r"(https?://\S+)"
    urls = re.findall(pattern, string)
    return [url for url in urls if check_url_patterns(url)]


def find_between(data: str, first: str, last: str) -> str | None:
    """
    Extract text between two substrings.
    """
    try:
        start = data.index(first) + len(first)
        end = data.index(last, start)
        return data[start:end]
    except ValueError:
        return None


def extract_surl_from_url(url: str) -> str | None:
    """
    Extract the 'surl' parameter from a URL.
    """
    parsed_url = urlparse(url)
    query_params = parse_qs(parsed_url.query)
    return query_params.get("surl", [None])[0]


def fetch_data(url: str):
    """
    Fetch and process data from a Terabox URL.
    """
    session = requests.Session()
    headers = {
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Encoding": "gzip, deflate, br",
        "Accept-Language": "en-US,en;q=0.9",
        "Connection": "keep-alive",
        "Cookie": COOKIE,
        "DNT": "1",
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"
        ),
    }

    # Make initial request
    response = session.get(url, headers=headers)
    if response.status_code != 200:
        return {"error": "Failed to fetch initial URL"}

    # Extract required parameters
    default_thumbnail = find_between(response.text, 'og:image" content="', '"')
    logid = find_between(response.text, "dp-logid=", "&")
    jsToken = find_between(response.text, "fn%28%22", "%22%29")
    bdstoken = find_between(response.text, 'bdstoken":"', '"')
    shorturl = extract_surl_from_url(response.url)

    if not shorturl or not logid or not jsToken:
        return {"error": "Missing required parameters"}

    api_url = (
        f"https://www.terabox.app/share/list?app_id=250528&web=1&channel=0"
        f"&jsToken={jsToken}&dp-logid={logid}&page=1&num=20&by=name&order=asc"
        f"&shorturl={shorturl}&root=1"
    )

    # Fetch file list from API
    response = session.get(api_url, headers=headers)
    if response.status_code != 200:
        return {"error": "Failed to fetch API data"}

    try:
        response_json = response.json()
    except ValueError:
        return {"error": "Invalid JSON response"}

    if response_json.get("errno"):
        return {"error": "API returned an error", "errno": response_json["errno"]}

    file_list = response_json.get("list", [])
    if not file_list:
        return {"error": "No files found"}

    file_info = file_list[0]
    direct_link_response = session.head(file_info["dlink"], headers=headers)

    # Compile result data
    data = {
        "file_name": file_info.get("server_filename"),
        "link": file_info.get("dlink"),
        "direct_link": direct_link_response.headers.get("location"),
        "thumb": file_info.get("thumbs", {}).get("url3", default_thumbnail),
        "size": get_formatted_size(file_info.get("size", 0)),
        "sizebytes": file_info.get("size", 0),
    }

    return data


class CanSend:
    def can_send(self):
        if not hasattr(self, "last_send_time"):
            self.last_send_time = time.time() - 20
        current_time = time.time()
        elapsed_time = current_time - self.last_send_time

        if elapsed_time >= 5:
            self.last_send_time = current_time
            return True
        else:
            return False


def check_url_patterns(url: str) -> bool:
    """
    Check if the given URL matches any of the known URL patterns for code hosting services.

    Parameters:
    url (str): The URL to be checked.

    Returns:
    bool: True if the URL matches a known pattern, False otherwise.
    """
    patterns = [
        r"ww\.mirrobox\.com",
        r"www\.nephobox\.com",
        r"freeterabox\.com",
        r"www\.freeterabox\.com",
        r"1024tera\.com",
        r"4funbox\.co",
        r"www\.4funbox\.com",
        r"mirrobox\.com",
        r"nephobox\.com",
        r"terabox\.app",
        r"terabox\.com",
        r"www\.terabox\.ap",
        r"www\.terabox\.com",
        r"www\.1024tera\.co",
        r"www\.momerybox\.com",
        r"teraboxapp\.com",
        r"momerybox\.com",
        r"tibibox\.com",
        r"www\.tibibox\.com",
        r"www\.teraboxapp\.com",
    ]

    for pattern in patterns:
        if re.search(pattern, url):
            return True

    return False


def extract_code_from_url(url: str) -> str | None:
    """
    Extracts the code from a URL.

    Parameters:
        url (str): The URL to extract the code from.

    Returns:
        str: The extracted code, or None if the URL does not contain a code.
    """
    pattern1 = r"/s/(\w+)"
    pattern2 = r"surl=(\w+)"

    match = re.search(pattern1, url)
    if match:
        return match.group(1)

    match = re.search(pattern2, url)
    if match:
        return match.group(1)

    return None


def get_urls_from_string(string: str) -> str | None:
    """
    Extracts all URLs from a given string.

    Parameters:
        string (str): The input string.

    Returns:
        str: The first URL found in the input string, or None if no URLs were found.
    """
    pattern = r"(https?://\S+)"
    urls = re.findall(pattern, string)
    urls = [url for url in urls if check_url_patterns(url)]
    if not urls:
        return
    return urls[0]


def extract_surl_from_url(url: str) -> str:
    """
    Extracts the surl from a URL.

    Parameters:
        url (str): The URL to extract the surl from.

    Returns:
        str: The extracted surl, or None if the URL does not contain a surl.
    """
    parsed_url = urlparse(url)
    query_params = parse_qs(parsed_url.query)
    surl = query_params.get("surl", [])

    if surl:
        return surl[0]
    else:
        return False


def get_formatted_size(size_bytes: int) -> str:
    """
    Returns a human-readable file size from the given number of bytes.

    Parameters:
        size_bytes (int): The number of bytes to be converted to a file size.

    Returns:
        str: The file size in a human-readable format.
    """
    if size_bytes >= 1024 * 1024:
        size = size_bytes / (1024 * 1024)
        unit = "MB"
    elif size_bytes >= 1024:
        size = size_bytes / 1024
        unit = "KB"
    else:
        size = size_bytes
        unit = "b"

    return f"{size:.2f} {unit}"


def convert_seconds(seconds: int) -> str:
    """
    Convert seconds into a human-readable format.

    Parameters:
        seconds (int): The number of seconds to convert.

    Returns:
        str: The seconds converted to a human-readable format.
    """
    seconds = int(seconds)
    hours = seconds // 3600
    remaining_seconds = seconds % 3600
    minutes = remaining_seconds // 60
    remaining_seconds_final = remaining_seconds % 60

    if hours > 0:
        return f"{hours}h:{minutes}m:{remaining_seconds_final}s"
    elif minutes > 0:
        return f"{minutes}m:{remaining_seconds_final}s"
    else:
        return f"{remaining_seconds_final}s"


async def is_user_on_chat(bot: TelegramClient, chat_id: int, user_id: int) -> bool:
    """
    Check if a user is present in a specific chat.

    Parameters:
        bot (TelegramClient): The Telegram client instance.
        chat_id (int): The ID of the chat.
        user_id (int): The ID of the user.

    Returns:
        bool: True if the user is present in the chat, False otherwise.
    """
    try:
        check = await bot.get_permissions(chat_id, user_id)
        return check
    except:
        return False


async def download_file(
    url: str,
    filename: str,
    callback=None,
) -> str | bool:
    """
    Download a file from a URL to a specified location.

    Args:
        url (str): The URL of the file to download.
        filename (str): The location to save the file to.
        callback (function, optional): A function that will be called
            with progress updates during the download. The function should
            accept three arguments: the number of bytes downloaded so far,
            the total size of the file, and a status message.

    Returns:
        str: The filename of the downloaded file, or False if the download
            failed.

    Raises:
        requests.exceptions.HTTPError: If the server returns an error.
        OSError: If there is an error opening or writing to the file.
    """
    try:
        response = requests.get(url, stream=True)
        response.raise_for_status()
        with open(filename, "wb") as file:
            for chunk in response.iter_content(chunk_size=1024):
                file.write(chunk)
                if callback:
                    downloaded_size = file.tell()
                    total_size = int(response.headers.get("content-length", 0))
                    await callback(downloaded_size, total_size, "Downloading")
        return filename

    except Exception as e:
        print(f"Error downloading file: {e}")
        return False


def download_image_to_bytesio(url: str, filename: str) -> BytesIO | None:
    """
    Downloads an image from a URL and returns it as a BytesIO object.

    Args:
        url (str): The URL of the image to download.
        filename (str): The filename to save the image as.

    Returns:
        BytesIO: The image data as a BytesIO object, or None if the download failed.
    """
    try:
        response = requests.get(url)
        if response.status_code == 200:
            image_bytes = BytesIO(response.content)
            image_bytes.name = filename
            return image_bytes
        else:
            return None
    except:
        return None

db = redis.Redis(
    host=HOST,
    port=PORT,
    password=PASSWORD,
    decode_responses=True,
)

PREMIUM_USERS_KEY = "premium_users"
GIFT_CODES_KEY = "gift_codes"

REDIS_CONFIG = {
    "HOST": "redis-12345.c16.us-east-1-2.ec2.cloud.redislabs.com",
    "PORT": 17713,
    "USERNAME": "default",
    "PASSWORD": "password",
    "DATABASE": "NTM"
}

PRIVATE_CHAT_ID = -1002313550165
ADMINS = 8083702486
NTMPRO_CHANNEL = "@AstroBotz"
NTMCHAT_CHANNEL = "@AstroBotzSupport"
REQUEST_LIMIT = 5
REQUEST_LIMIT_WINDOW = 60  # Seconds
MAX_FILE_SIZE = 4294967296

# Authentication cookie
COOKIE = {
    "COOKIE": """browserid=ECp8myR7LciVVyrKxhjseu5DsPlsBGfcO2llDtQXqlF9ol1xSxrOyu-zQOo=; __bid_n=18de05eca9a9ef426f4207; _ga=GA1.1.993333438.1714196932; ndus=Ye4ozFx5eHuiHedfAOmdECQ1cUYjXwfZF6VF4QbD; TSID=JmuRgIKcaPqMjlzvZE5wXOJD96SkO594; PANWEB=1; csrfToken=8nN5Q8Y5H71nPyC8NHxBYAcr; lang=en; __bid_n=18de05eca9a9ef426f4207; ndut_fmt=A66A9E7BD20D40C268FB5C44A4E512FB76288B038CE8454BBB5B6BA0DB474814; ab_sr=1.0.1_OWVhNGFjZjk2MTJjMjE4MWViNzJhZDZhYTFmYzc4YmU3YmM4YmE2YzM4OTlkNGFiYTgwMTU5YjExYzVkMmYyOWU3NjQ2MGY4OGU2NWFlN2VhMDVhM2EzMGFlNmVlY2YzODY4YWNlNTdiYzdkODllZGQyNzRmODFiMmYxMTA2NGQyYWM2NGQxN2UxNDA3YzlhMDZkNDJiNWE4YmM5NTkxOA==; ab_ymg_result={"data":"97e606d2561336895e6c204c4cefdda3f92fcb3da76591b45dff12f3686fa1cad214e650165788b6b308134b9d9630b87d3b7b925e4d6eff5c376d2a0616a7d075d125397d73a7d649719f13489133194f2afd96fe712df4def2120f7e123df403d77144b1fb1f7ef9cd2b2c34feda576a824304a7c66bc9bbf9482618a92b59","key_id":"66","sign":"a8e92f31"}; _ga_06ZNKL8C2E=GS1.1.1714281215.2.0.1714281219.56.0.0"""
}

# Define /info and /id commands to display user information
@Client.on(filters.command(["info"]) & filters.private)
async def user_info(client: Client, message: Message):
    try:
        user_id = message.from_user.id
        name = message.from_user.first_name
        username = message.from_user.username if message.from_user.username else "-"
        plan = "Premium" if db.sismember(PREMIUM_USERS_KEY, user_id) else "Free"
        info_text = f"<b> ⍟ Name: {name}\n⍟ Username: @{username}\n⍟ User ID: `{user_id}`\n⍟ Plan: {plan} </b>"
        await message.reply_text(info_text, parse_mode="markdown", disable_web_page_preview=True)
    except Exception as e:
        print(f"Error in user_info: {e}")
        await message.reply_text("An error occurred while processing your request.")


@Client.on(filters.command(["help"]) & filters.private)
async def command_help(client: Client, message: Message):
    help_text = """
┏━━━━━━━━━━⍟
┃ 𝘼𝙫𝙖𝙞𝙡𝙖𝙗𝙡𝙚 𝘾𝙤𝙢𝙢𝙖𝙣𝙙𝙨
┗━━━━━━━━━━━━━━━━━⍟

/start - Start the bot and receive a welcome message.
/info - Get your user information.
/redeem <gift_code> - Redeem a gift code for premium access.
/help to view available cmds 
/plan - To check availabe plan

Directly share me the link i will share you the video with direct link

For premium contact @YadhuTG
"""

    await message.reply_text(
        help_text,
        parse_mode="markdown",
    )


@Client.on(filters.command("ping"))
async def ping_pong(client: Client, message: Message):
    start_time = time.time()
    msg = await message.reply_text("🖥️ Connection Status\nCommand: `/ping`\nResponse Time: Calculating...")
    end_time = time.time()
    latency = end_time - start_time  # Calculate latency in seconds
    latency_str = "{:.2f}".format(latency)  # Format latency with two decimal places
    await msg.edit_text(f"🖥️ Connection Status\nCommand: `/ping`\nResponse Time: {latency_str} seconds")

# Generate gift codes
@Client.on_message(filters.command("gc") & filters.user(ADMINS) & filters.regex(r"^/gc (\d+)$"))
async def generate_gift_codes(client: Client, m: Message):
    """Generates gift codes and saves them to Redis."""
    try:
        quantity = int(m.matches[0].group(1)) # Use m.matches

        gift_codes = [f"Astro-{str(uuid4())[:8]}" for _ in range(quantity)]
        db.sadd(GIFT_CODES_KEY, *gift_codes)

        # Send a reply confirming the generation of gift codes
        await m.reply_text(f"{quantity} gift codes generated. Here they are:")

        # Send each gift code as a separate message with some interval (e.g., 1 second)
        for code in gift_codes:
            await asyncio.sleep(1)  # Introduce a delay to avoid rate limiting
            await m.reply_text(code)
    except Exception as e:
        logging.exception(f"Error generating gift codes: {e}")
        await m.reply_text("An error occurred while generating gift codes.")


@Client.on_message(filters.command("redeem") & filters.regex(r"^/redeem (.*)$"))
async def redeem_gift_code(client: Client, m: Message):
    """Redeems a gift code and grants premium access to the user."""
    try:
        gift_code = m.matches[0].group(1)  # Use m.matches

        if db.sismember(GIFT_CODES_KEY, gift_code):
            user_id = m.from_user.id
            user = await client.get_users(user_id) # Using client.get_users for pyrogram
            name = user.first_name
            username = user.username if user.username else "-"
            db.sadd(PREMIUM_USERS_KEY, user_id)
            db.srem(GIFT_CODES_KEY, gift_code)
            admin_message = f"Gift code redeemed by:\nName: {name}\nUsername: @{username}\nUser ID: {user_id}"
            for admin_id in ADMINS:
                try:
                    await client.send_message(admin_id, admin_message)
                except FloodWait as e:
                    logging.warning(f"FloodWait encountered: {e}")
                    await asyncio.sleep(e.value)  # Wait before retrying
                except Exception as e:
                    logging.exception(f"Error sending message to admin {admin_id}: {e}")

            await m.reply_text("Gift code redeemed successfully. You are now a premium user!")
        else:
            await m.reply_text("Invalid or expired gift code.")
    except Exception as e:
        logging.exception(f"Error redeeming gift code: {e}")
        await m.reply_text("An error occurred while redeeming the gift code.")


@Client.on_message(filters.command("broadcast") & filters.user(ADMINS))
async def broadcast_message(client: Client, m: Message):
    """Allows admins to send broadcast messages to all users in a group."""
    try:
        broadcast_text = m.text.split("/broadcast", 1)[1].strip()

        #This get_chat_members do not need group id.
        async for member in client.get_chat_members(-1001336746488):  # Iterate through all users and send the broadcast message
            try:
                await client.send_message(member.user.id, broadcast_text)
            except FloodWait as e:
                logging.warning(f"FloodWait encountered: {e}")
                await asyncio.sleep(e.value)  # Wait before retrying
            except Exception as e:
                logging.exception(f"Failed to send broadcast to user {member.user.id}: {e}")

        await m.reply_text("Broadcast sent successfully!")
    except Exception as e:
        logging.exception(f"Error sending broadcast message: {e}")
        await m.reply_text("An error occurred while sending the broadcast message.")

@Client.on(filters.command("start") & filters.private)
async def start(client: Client, message: Message):
    user_id = message.from_user.id
    try:
        user = await client.get_users(user_id)  # Use client.get_users
        name = user.first_name
        username = user.username if user.username else "-"

        admin_message = f"User started the bot:\nName: {name}\nUsername: @{username}\nUser ID: {user_id}"
        for admin_id in ADMINS:
            try:
                await client.send_message(admin_id, admin_message)
            except Exception as e:
                print(f"Error sending admin message to {admin_id}: {e}")

        if db.sismember(PREMIUM_USERS_KEY, user_id):
            # Premium user
            reply_text = """
┏━━━━━━━━━━⍟
┃ 𝐍𝐓𝐌 𝐓𝐞𝐫𝐚 𝐁𝐨𝐱 𝐃𝐨𝐰𝐧𝐥𝐨𝐚𝐝𝐞𝐫 𝐁𝐨𝐭
┗━━━━━━━━━━━━━━━━━⍟
╔══════════⍟
┃🌟 Welcome! 🌟
┃
┃Excited to introduce Tera Box video downloader bot! 🤖 
┃Simply share the terabox link, and voila! 
┃Your desired video will swiftly start downloading. 
┃It's that easy! 🚀
╚═════════════════⍟
Do /help - Display available commands.

『 𝗡⋆𝗧⋆𝗠 』 
"""
        else:
            # Free user
            reply_text = """
┏━━━━━━━━━━⍟
┃ 𝐅𝐑𝐄𝐄 𝐔𝐒𝐄𝐑 
┗━━━━━━━━━━━━━━━━━⍟
╔══════════⍟ 
┃ As a free user, 
┃ you're not approved to access the full capabilities of this bot.
┃
┃ Upgrade to premium or utilize.
┃
┃ /cmds, or /help to view available cmds 
┃ /id or /info - To check your details
┃ /plan - To check availabe plan 
╚═════════════════⍟
For subscription inquiries, contact @abdul97233.
"""
        await message.reply_text(
            reply_text,
            disable_web_page_preview=True,
            parse_mode="markdown"
        )
    except Exception as e:
        print(f"Error in start command: {e}")
        await message.reply_text("An error occurred. Please try again later.")
# Handler for when a user joins the chat
@Client.on(filters.chat_member_updated)  # Use chat_member_updated filter
async def user_joined(client: Client, message):
    if message.new_chat_member and message.new_chat_member.status in ["member", "administrator", "creator"]:
        user_id = message.new_chat_member.user.id
        try:
            user = await client.get_users(user_id)
            name = user.first_name
            username = user.username if user.username else "-"
            
            admin_message = f"User joined the bot:\nName: {name}\nUsername: @{username}\nUser ID: {user_id}"
            for admin_id in ADMINS:
                try:
                    await client.send_message(admin_id, admin_message)
                except Exception as e:
                    print(f"Error sending admin message to {admin_id}: {e}")
        except Exception as e:
            print(f"Error in user_joined: {e}")

@Client.on(filters.command("remove") & filters.user(ADMINS) & filters.private) # Added private
async def remove(client: Client, message: Message):
    try:
        user_id = message.text.split(None, 1)[1]  # Get user ID from command
        if db.get(f"check_{user_id}"):
            db.delete(f"check_{user_id}")
            await message.reply_text(f"Removed {user_id} from the list.")
        else:
            await message.reply_text(f"{user_id} is not in the list.")
    except IndexError:
        await message.reply_text("Please specify a user ID to remove.")
    except Exception as e:
        print(f"Error in remove: {e}")
        await message.reply_text("An error occurred while removing the user.")

# Define /plan command to display premium plans and payment methods
@Client.on(filters.command("plan") & filters.private)
async def display_plan(client: Client, message: Message):
    plan_text = """
┏━━━━━━━━━━⍟
┃ 𝐓𝐄𝐑𝐀 𝐁𝐎𝐗 𝐏𝐑𝐄𝐌𝐈𝐔𝐌 𝐁𝐎𝐓 𝐩𝐥𝐚𝐧
┗━━━━━━━━━━━━━━━━━⍟

Membership Plans:
1. Rs. 100 for 10 days
2. Rs. 60 for 4 days
3. Rs. 30 for 2 days
4. Rs. 20 for 1 day

Payment Methods Available:
- UPI
- Esewa
- Khalti
- Phone Pay
- Fone Pay
- PayPal

Note: Nepal and India all payment accepted.

To purchase premium, send a message to @Abdul97233.
"""
    await message.reply_text(plan_text, parse_mode="markdown")
# Define premium user promotion command
@Client.on(filters.command("pre") & filters.user(ADMINS) & filters.private)
async def pre(client: Client, message: Message):
    try:
        user_id = message.text.split(None, 1)[1]
        if not db.sismember(PREMIUM_USERS_KEY, user_id):
            db.sadd(PREMIUM_USERS_KEY, user_id)
            await message.reply_text(f"Promoted {user_id} to premium.")
        else:
            await message.reply_text(f"{user_id} is already a premium user.")
    except IndexError:
        await message.reply_text("Please specify a user ID to promote.")
    except Exception as e:
        print(f"Error in pre: {e}")
        await message.reply_text("An error occurred while promoting the user.")

# Command to check all premium users with name, username, and user ID
@Client.on(filters.command("premium_users") & filters.user(ADMINS) & filters.private)
async def premium_users(client: Client, message: Message):
    premium_users = db.smembers(PREMIUM_USERS_KEY)
    if premium_users:
        users_info = []
        for user_id in premium_users:
            try:
                user = await client.get_users(int(user_id))  # get_users takes an int
                name = user.first_name
                username = user.username if user.username else "-"
                users_info.append(f"\nName: {name}, \nUsername: @{username}, \nUser ID: {user_id}")
            except Exception as e:
                print(f"Error getting user info for {user_id}: {e}")
                users_info.append(f"\nError getting info for User ID: {user_id}")  # Inform about the error
        users_text = "\n".join(users_info)
        await message.reply_text(f"Premium Users:\n{users_text}")
    else:
        await message.reply_text("No premium users found.")

# Command to directly demote all premium users
@Client.on(filters.command("demote_all_premium") & filters.user(ADMINS) & filters.private)
async def demote_all_premium(client: Client, message: Message):
    db.delete(PREMIUM_USERS_KEY)
    await message.reply_text("All premium users demoted successfully.")


# Define premium user demotion command
@Client.on(filters.command("de") & filters.user(ADMINS) & filters.private)
async def de(client: Client, message: Message):
    try:
        user_id = message.text.split(None, 1)[1]
        if db.sismember(PREMIUM_USERS_KEY, user_id):
            db.srem(PREMIUM_USERS_KEY, user_id)
            await message.reply_text(f"Demoted {user_id} from premium.")
        else:
            await message.reply_text(f"{user_id} is not a premium user.")
    except IndexError:
        await message.reply_text("Please specify a user ID to demote.")
    except Exception as e:
        print(f"Error in de: {e}")
        await message.reply_text("An error occurred while demoting the user.")


# Add premium user check for handling message
def get_urls_from_string(text):
    """Extracts URLs from a string using regex."""
    urls = re.findall(
        r"(?P<url>https?://[^\s]+)", text
    )  # More robust URL matching
    return urls if urls else None  # Return None if no URLs found


def is_valid_url(url):
    """Checks if a URL is well-formed."""
    try:
        result = urlparse(url)
        return all([result.scheme, result.netloc])  # Requires scheme and netloc
    except:
        return False


async def is_user_on_chat(bot: Client, channel_username: str, user_id: int) -> bool:
    """Checks if a user is a member of a Telegram channel using Pyrogram."""
    try:
        chat = await bot.get_chat(channel_username)
        await bot.get_chat_member(chat.id, user_id)  # Raises an exception if not a member
        return True
    except Exception as e:
        logging.error(f"Error checking channel membership for {channel_username}: {e}")
        return False


def extract_code_from_url(url):
    """Extracts a code from the URL (implementation depends on the URL structure)."""
    # Example implementation (modify based on your URL format):
    try:
        parsed_url = urlparse(url)
        query_params = dict(qc.split("=") for qc in parsed_url.query.split("&") if "=" in qc)
        if "code" in query_params:
            code = query_params["code"]
            return code
        else:
            return None

    except Exception as e:
        logging.exception(f"Error extracting code from URL: {url}.  Error: {e}")
        return None


def get_data(url):
    # In real implementation you should implement the code to get the metadata from the URL here.
    # It is not possible to provide such implementation without more context.
    # Example:
    # import requests
    # try:
    #     response = requests.get(url, stream=True)
    #     response.raise_for_status() # Raises HTTPError for bad requests (4XX, 5XX)
    #     # Extract file name and size from headers or content
    #     file_name = response.headers.get("Content-Disposition", "filename=unknown").split("filename=")[1]
    #     sizebytes = response.headers.get("Content-Length")
    #     size = sizebytes
    #
    #     return {"file_name": file_name, "sizebytes": sizebytes, "size": size }
    # except Exception as e:
    #     logging.error(f"Error getting data from url: {url}: {e}")
    return {"file_name": "test.mp4", "sizebytes": 1024, "size": "1KB", "direct_link": "http://test.com/file.mp4", "thumb": "http://test.com/thumbnail.jpg" } #Replace with your implementation.

def get_formatted_size(size_bytes):
    """Formats bytes into human-readable format."""
    if size_bytes == 0:
        return "0B"
    size_name = ("B", "KB", "MB", "GB", "TB", "PB", "EB", "ZB", "YB")
    i = int(math.floor(math.log(size_bytes, 1024)))
    p = math.pow(1024, i)
    s = round(size_bytes / p, 2)
    return f"{s} {size_name[i]}"

def convert_seconds(seconds):
    """Converts seconds into HH:MM:SS format."""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    remaining_seconds = int(seconds % 60)
    return f"{hours:02}:{minutes:02}:{remaining_seconds:02}"

async def download_file(url, filename, progress_callback):
    #This function's implementation is up to you. Pyrogram's implementation does not have callback for this.

    logging.info(f"Downloading {url} to {filename}")

    # In a real scenario, you would download the file chunk by chunk and call the progress_callback.
    # For the sample, let's simulate the download with a sleep.
    total_size = int(get_data(url)['sizebytes'])
    chunk_size = 1024*1024 # 1MB chunks
    downloaded = 0
    while downloaded < total_size:
        await asyncio.sleep(1) # Simulate downloading
        downloaded += chunk_size
        if downloaded > total_size:
            downloaded = total_size
        await progress_callback(downloaded, total_size)
    return "local/path/to/downloaded/file"

async def download_image_to_bytesio(url, filename):

    return # this function is up to you.

# Dummy class for CanSend
class CanSend:
    def can_send(self):
        return True

import math

@Client.on_message(filters.private & filters.incoming & filters.text)
async def get_message(client: Client, m: Message):
    """Handles incoming messages containing URLs in private chats."""
    if get_urls_from_string(m.text) and db.sismember(PREMIUM_USERS_KEY, m.from_user.id):
        asyncio.create_task(handle_message(client, m))


async def handle_message(client: Client, m: Message):
    """Processes the message, checks channel membership, and forwards media."""
    urls = get_urls_from_string(m.text)
    if not urls:
        return await m.reply_text("Please enter a valid URL.")

    # Use the first URL only
    url = urls[0]

    if not is_valid_url(url):
        return await m.reply_text("The provided URL is not valid.")

    try:
        check_ntmpro = await is_user_on_chat(client, NTMPRO_CHANNEL, m.from_user.id)
        if not check_ntmpro:
            return await m.reply_text(
                f"Please join {NTMPRO_CHANNEL} then send me the link again."
            )

        check_ntmchat = await is_user_on_chat(client, NTMCHAT_CHANNEL, m.from_user.id)
        if not check_ntmchat:
            return await m.reply_text(
                f"Please join {NTMCHAT_CHANNEL} then send me the link again."
            )
    except Exception as e:
        logging.error(f"Error checking channel membership: {e}")
        return await m.reply_text(
            "An error occurred while checking channel membership. Please try again later."
        )

    # Spam Protection
    is_spam = db.exists(m.from_user.id)  # Use exists
    if is_spam and m.from_user.id != ADMIN_USER_ID:
        if db.sismember(PREMIUM_USERS_KEY, m.from_user.id):
            return await m.reply_text(
                "You are sending messages too quickly. Please wait 30 seconds and try again."
            )
        else:
            return await m.reply_text(
                "You are sending messages too quickly. Please wait 1 minute and try again."
            )
    else:
        # Set the spam flag with TTL.  The TTL is 60 or 30 seconds, depending on if it is premium.
        if db.sismember(PREMIUM_USERS_KEY, m.from_user.id):
            db.setex(m.from_user.id, 30, "spam")
        else:
            db.setex(m.from_user.id, 60, "spam")

    # Usage Limit
    request_count = db.get(f"check_{m.from_user.id}")
    if request_count:
        request_count = int(request_count)

    hm = await m.reply_text("Sending you the media, please wait...")  # Immediate feedback

    # The count will be incremented no matter what for rate limiting purposes.
    # Note that now the user will not be limited immediately, as it will allow them to send the message, but the
    # subsequent message will be restricted based on whether the limit is exceeded.
    db.set(
        m.from_user.id, time.monotonic(), ex=60
    )  # Set a timeout (ex) of 60 seconds. time.monotonic is the correct implementation

    # Increment and update the counter on Redis
    db.set(f"check_{m.from_user.id}", request_count + 1 if request_count else 1, ex=7200)

    data = get_data(url)
    if not data:
        return await hm.edit_text("Sorry! API is dead or maybe your link is broken.")
    db.set(m.from_user.id, time.monotonic(), ex=60)
    if (
        not data["file_name"].endswith(".mp4")
        and not data["file_name"].endswith(".mkv")
        and not data["file_name"].endswith(".Mkv")
        and not data["file_name"].endswith(".webm")
    ):
        return await hm.edit_text(
            f"Sorry! File is not supported for now. I can download only .mp4, .mkv and .webm files."
        )
    if int(data["sizebytes"]) > MAX_FILE_SIZE and m.from_user.id != ADMIN_USER_ID:
        return await hm.edit_text(
            f"Sorry! File is too big. I can download only 4GB and this file is of {data['size']} ."
        )

    start_time = time.time()
    end_time = time.time()  # Record the end time
    total_time = end_time - start_time  # Calculate the total time taken
    user_first_name = m.from_user.first_name
    user_username = m.from_user.username
    cansend = CanSend()

    async def progress_bar(current_downloaded, total_downloaded, state="Sending"):
        """Displays a progress bar in the Telegram message."""
        try:
            if not cansend.can_send():
                return

            bar_length = 20
            percent = current_downloaded / total_downloaded
            arrow = "█" * int(percent * bar_length)
            spaces = "░" * (bar_length - len(arrow))

            elapsed_time = time.time() - start_time

            head_text = f"{state} `{data['file_name']}`"
            progress_bar = f"[{arrow + spaces}] {percent:.2%}"
            upload_speed = current_downloaded / elapsed_time if elapsed_time > 0 else 0
            speed_line = f"Speed: **{get_formatted_size(upload_speed)}/s**"

            time_remaining = (
                (total_downloaded - current_downloaded) / upload_speed
                if upload_speed > 0
                else 0
            )
            time_line = f"Time Remaining: `{convert_seconds(time_remaining)}`"

            size_line = f"Size: {get_formatted_size(current_downloaded)} / **{get_formatted_size(total_downloaded)}**"

            await hm.edit_text(
                f"{head_text}\n{progress_bar}\n{speed_line}\n{time_line}\n{size_line}",
                parse_mode="markdown",
            )

        except Exception as e:
            logging.exception(f"Error in progress_bar: {e}")

    uuid_str = str(uuid4()) # use a string for uuid.
    thumbnail = await download_image_to_bytesio(data["thumb"], f"thumbnail_{uuid_str}.png")

    try:

        file_path = data["direct_link"] # Assume it points to a local file directly.
        # This is assuming send_document accepts a URL directly. Pyrogram's documentation does not say it does.
        # but in this example we are passing the "direct_link" as if it is a local path.
        if not os.path.exists(file_path): # download if the file doesn't exist
           file_path = await download_file(data["direct_link"], data["file_name"], progress_bar)


        file = await client.send_document(
            chat_id=PRIVATE_CHAT_ID,  # Send to private chat. Not to the user.
            document=file_path,  # You may have to download the file if it is not already here.
            thumb=thumbnail,  # Use the downloaded thumbnail, if available
            caption=f"""
┏━━━━━━━━━━⍟
┃ 𝐍𝐓𝐌 𝐓𝐞𝐫𝐚 𝐁𝐨𝐱 𝐃𝐨𝐰𝐧𝐥𝐨𝐚𝐝𝐞𝐫 𝐁𝐨𝐭
┗━━━━━━━━━━━━━━━━━⍟
╔══════════⍟
╟➣𝙁𝙞𝙡𝙚 𝙉𝙖𝙢𝙚: {data['file_name']}
╟➣𝙎𝙞𝙯𝙚: {data["size"]}
╟➣𝗗𝗶𝗿𝗲𝗰𝘁 𝗗𝗼𝘄𝗻𝗹𝗼𝗮𝗱 𝗟𝗶𝗻𝗸 : Click here
╟➣𝗙𝗶𝗿𝘀𝘁 𝗡𝗮𝗺𝗲: {user_first_name}
╟➣𝗨𝘀𝗲𝗿𝗻𝗮𝗺𝗲: {user_username}
╟➣𝐓𝐨𝐭𝐚𝐥 𝐓𝐢𝐦𝐞 𝐓𝐚𝐤𝐞𝐧: {total_time} sec
╚═════════════════⍟
         @NTMpro
""",
            supports_streaming=True,  # Does nothing.
            spoiler=True,  # May have to implement this manually as a filter/check
            progress=progress_bar  # pyrogram's `send_document` uses progress as keyword argument.
        )
        try:
            if os.path.exists(file_path):
                os.unlink(file_path)
        except Exception as e:
            logging.exception(f"Error unlinking file: {e}")

    except Exception as e: # You must not catch a generic expression. Implement individual implementations.
        await hm.edit_text(
            f"Sorry! Download Failed but you can download it from here.",

        )

    try:
        if os.path.exists(file_path):
            os.unlink(file_path)
    except Exception as e:
        logging.exception(f"Error unlinking file: {e}")
        pass
    try:
        await hm.delete()
    except Exception as e:
        logging.exception(f"Error deleting message: {e}")

    if shorturl:
        db.set(shorturl, file.id)
    if file:
        db.set(uuid_str, file.id)  # use the string version.

        try:
            await client.copy_message(
                chat_id=m.chat.id,  # Users private chat.
                from_chat_id=PRIVATE_CHAT_ID, # from the private channel
                message_id=file.id,
            )
        except FloodWait as e:
            logging.warning(f"FloodWait encountered: {e}")
            await asyncio.sleep(e.value)  # Wait before retrying

            await client.copy_message(
                chat_id=m.chat.id,  # Users private chat.
                from_chat_id=PRIVATE_CHAT_ID,  # from the private channel
                message_id=file.id,
            )
        except Exception as e:
            logging.exception(f"Error forwarding message: {e}")


        db.set(m.from_user.id, time.monotonic(), ex=60)
        db.set(
            f"check_{m.from_user.id}",
            request_count + 1 if request_count else 1,
            ex=7200,
        )
