import os
import json
import threading
import time
import asyncio
import urllib.request
import subprocess
import shutil
import re
import math
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse


# ============================================================
# CONFIGURATION
# ============================================================

BASE = Path(__file__).parent

DATA = BASE / "data"
DATA.mkdir(exist_ok=True)

CFG = DATA / "config.json"
QUEUE = DATA / "products.json"

DRAFTS = DATA / "drafts"
DRAFTS.mkdir(exist_ok=True)

ACTIVITY_LOG = DATA / "activity.log"


# ============================================================
# DEFAULT CONFIG
# ============================================================

DEFAULT_CFG = {
    "handle": "@waititsonsale",
    "posts_per_day": 3,
    "enabled": False,
    "mode": "draft",
    "voice": "en-IN-NeerjaNeural",

    "video_width": 720,
    "video_height": 1280,
    "video_fps": 24,

    "last_product_index": 0
}


# ============================================================
# DEFAULT PRODUCTS
# ============================================================

DEFAULT_PRODUCTS = [

    {
        "name": "Motion Sensor Night Light",
        "price": "₹349",
        "category": "Home",
        "why": "an instant visual before-and-after with a clear everyday use case",
        "image_url": ""
    },

    {
        "name": "Foldable Laptop Stand",
        "price": "₹399",
        "category": "Desk",
        "why": "a simple productivity upgrade that is easy to demonstrate",
        "image_url": ""
    },

    {
        "name": "Portable Mini Chopper",
        "price": "₹499",
        "category": "Kitchen",
        "why": "strong visual demo potential and broad household appeal",
        "image_url": ""
    },

    {
        "name": "Magnetic Cable Organizer",
        "price": "₹199",
        "category": "Tech",
        "why": "solves a common desk problem at a low price",
        "image_url": ""
    },

    {
        "name": "Mini Electric Cleaning Brush",
        "price": "₹299",
        "category": "Home",
        "why": "satisfying cleaning demonstration potential",
        "image_url": ""
    }

]


# ============================================================
# RUNTIME STATE
# ============================================================

STATE = {
    "created": 0,
    "last_run": None,
    "message": "Ready",
    "last_product": None,
    "last_package": None,
    "last_video": None,
    "worker_running": False,
    "creating": False
}


# ============================================================
# FILE HELPERS
# ============================================================

def load(path, default):

    if not path.exists():
        save(path, default)

    try:
        return json.loads(
            path.read_text(
                encoding="utf-8"
            )
        )

    except Exception:
        return default


def save(path, obj):

    path.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    path.write_text(
        json.dumps(
            obj,
            indent=2,
            ensure_ascii=False
        ),
        encoding="utf-8"
    )


# ============================================================
# LOGGING
# ============================================================

def log(message):

    STATE["message"] = message

    timestamp = datetime.now().strftime(
        "%Y-%m-%d %H:%M:%S"
    )

    try:

        with ACTIVITY_LOG.open(
            "a",
            encoding="utf-8"
        ) as f:

            f.write(
                f"[{timestamp}] {message}\n"
            )

    except Exception:
        pass


# ============================================================
# UTILITIES
# ============================================================

def clean_filename(value):

    value = str(value)

    value = re.sub(
        r"[^a-zA-Z0-9_\-]+",
        "_",
        value
    )

    return value[:80].strip("_")


def wrap_text(text, width=25):

    words = str(text).split()

    lines = []
    current = ""

    for word in words:

        if not current:

            current = word

        elif len(current) + len(word) + 1 <= width:

            current += " " + word

        else:

            lines.append(current)
            current = word

    if current:
        lines.append(current)

    return "\n".join(lines)


def escape_ffmpeg_text(text):

    text = str(text)

    text = text.replace(
        "\\",
        "\\\\"
    )

    text = text.replace(
        ":",
        "\\:"
    )

    text = text.replace(
        "'",
        "\\'"
    )

    text = text.replace(
        "%",
        "\\%"
    )

    text = text.replace(
        "[",
        "\\["
    )

    text = text.replace(
        "]",
        "\\]"
    )

    text = text.replace(
        "\n",
        " "
    )

    return text


def ffmpeg_available():

    return shutil.which("ffmpeg") is not None


# ============================================================
# PRODUCT HOOK
# ============================================================

def random_hook(product):

    price = product.get(
        "price",
        ""
    )

    hooks = [

        f"WAIT… THIS IS ONLY {price}?",

        f"I found this for {price}.",

        "Okay… this is actually useful.",

        "Why did I not know about this sooner?",

        "This might be the most useful thing you see today.",

        f"Would you buy this for {price}?",

        "One of those products you didn't know you needed."

    ]

    import random

    return random.choice(hooks)


# ============================================================
# DOWNLOAD PRODUCT IMAGE
# ============================================================

def download_image(url, destination):

    if not url:
        return None

    try:

        request = urllib.request.Request(
            url,
            headers={
                "User-Agent": "Mozilla/5.0"
            }
        )

        with urllib.request.urlopen(
            request,
            timeout=20
        ) as response:

            data = response.read()

        if not data:
            return None

        destination.write_bytes(data)

        return destination

    except Exception as e:

        log(
            f"Image download failed: {e}"
        )

        return None


# ============================================================
# CREATE PRODUCT ARTWORK
# ============================================================

def create_product_artwork(
    product,
    output
):

    try:

        from PIL import Image
        from PIL import ImageDraw
        from PIL import ImageFont
        from PIL import ImageFilter

    except Exception as e:

        log(
            f"Pillow unavailable: {e}"
        )

        return None


    WIDTH = 720
    HEIGHT = 1280


    # --------------------------------------------------------
    # Background
    # --------------------------------------------------------

    image = Image.new(
        "RGB",
        (WIDTH, HEIGHT),
        (248, 248, 248)
    )

    draw = ImageDraw.Draw(image)


    # Soft top section

    for y in range(0, HEIGHT):

        ratio = y / HEIGHT

        r = int(250 - ratio * 8)
        g = int(250 - ratio * 8)
        b = int(250 - ratio * 5)

        draw.line(
            [(0, y), (WIDTH, y)],
            fill=(r, g, b)
        )


    # --------------------------------------------------------
    # Fonts
    # --------------------------------------------------------

    font_path_bold = (
        "/usr/share/fonts/truetype/"
        "dejavu/DejaVuSans-Bold.ttf"
    )

    font_path_regular = (
        "/usr/share/fonts/truetype/"
        "dejavu/DejaVuSans.ttf"
    )


    try:

        font_brand = ImageFont.truetype(
            font_path_bold,
            30
        )

        font_product = ImageFont.truetype(
            font_path_bold,
            42
        )

        font_category = ImageFont.truetype(
            font_path_regular,
            24
        )

    except Exception:

        font_brand = None
        font_product = None
        font_category = None


    # --------------------------------------------------------
    # Product information
    # --------------------------------------------------------

    name = product.get(
        "name",
        "Interesting Product"
    )

    price = product.get(
        "price",
        ""
    )

    category = product.get(
        "category",
        "Product"
    )


    # --------------------------------------------------------
    # Brand
    # --------------------------------------------------------

    draw.text(
        (40, 45),
        "@waititsonsale",
        fill=(20, 20, 20),
        font=font_brand
    )


    # --------------------------------------------------------
    # Product card
    # --------------------------------------------------------

    card = (
        35,
        250,
        WIDTH - 35,
        850
    )

    draw.rounded_rectangle(
        card,
        radius=40,
        fill=(255, 255, 255)
    )


    # --------------------------------------------------------
    # Try actual product image
    # --------------------------------------------------------

    image_url = product.get(
        "image_url",
        ""
    )

    product_image = None

    if image_url:

        try:

            temp_path = output.parent / "downloaded_product.jpg"

            downloaded = download_image(
                image_url,
                temp_path
            )

            if downloaded:

                product_image = Image.open(
                    downloaded
                ).convert("RGB")

        except Exception as e:

            log(
                f"Product image processing failed: {e}"
            )


    if product_image:

        try:

            product_image.thumbnail(
                (520, 450)
            )

            x = (
                WIDTH -
                product_image.width
            ) // 2

            y = 310

            image.paste(
                product_image,
                (x, y)
            )

        except Exception:

            pass

    else:

        # ----------------------------------------------------
        # Nice fallback product icon/card
        # ----------------------------------------------------

        cx = WIDTH // 2
        cy = 500

        draw.rounded_rectangle(
            (
                cx - 115,
                cy - 115,
                cx + 115,
                cy + 115
            ),
            radius=35,
            fill=(235, 235, 235)
        )

        draw.text(
            (
                cx - 70,
                cy - 25
            ),
            "FIND",
            fill=(35, 35, 35),
            font=font_category
        )


    # --------------------------------------------------------
    # Product name
    # --------------------------------------------------------

    wrapped = wrap_text(
        name,
        24
    )


    bbox = draw.multiline_textbbox(
        (0, 0),
        wrapped,
        font=font_product,
        spacing=6,
        align="center"
    )

    text_width = (
        bbox[2] - bbox[0]
    )


    draw.multiline_text(
        (
            (WIDTH - text_width) / 2,
            880
        ),
        wrapped,
        fill=(20, 20, 20),
        font=font_product,
        spacing=6,
        align="center"
    )


    # --------------------------------------------------------
    # Category + price
    # --------------------------------------------------------

    label = f"{category.upper()}  •  {price}"

    bbox = draw.textbbox(
        (0, 0),
        label,
        font=font_category
    )

    label_width = (
        bbox[2] - bbox[0]
    )

    draw.text(
        (
            (WIDTH - label_width) / 2,
            1010
        ),
        label,
        fill=(70, 70, 70),
        font=font_category
    )


    # --------------------------------------------------------
    # Bottom branding
    # --------------------------------------------------------

    draw.rounded_rectangle(
        (
            45,
            1110,
            WIDTH - 45,
            1195
        ),
        radius=28,
        fill=(20, 20, 20)
    )


    text = "SAVE THIS FIND"

    bbox = draw.textbbox(
        (0, 0),
        text,
        font=font_category
    )

    text_width = (
        bbox[2] - bbox[0]
    )

    draw.text(
        (
            (WIDTH - text_width) / 2,
            1138
        ),
        text,
        fill=(255, 255, 255),
        font=font_category
    )


    image.save(
        output,
        "JPEG",
        quality=90,
        optimize=True
    )


    return output


# ============================================================
# TEXT TO SPEECH
# ============================================================

async def generate_tts_async(
    text,
    output,
    voice
):

    try:

        import edge_tts

        communicate = edge_tts.Communicate(
            text,
            voice
        )

        await communicate.save(
            str(output)
        )

        return True

    except Exception as e:

        log(
            f"TTS error: {e}"
        )

        return False


def generate_voiceover(
    text,
    output,
    voice
):

    try:

        return asyncio.run(
            generate_tts_async(
                text,
                output,
                voice
            )
        )

    except Exception as e:

        log(
            f"TTS runtime error: {e}"
        )

        return False


# ============================================================
# GET AUDIO DURATION
# ============================================================

def get_audio_duration(audio_path):

    if not audio_path.exists():
        return 17.5

    try:

        result = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                str(audio_path)
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=20
        )

        value = result.stdout.decode().strip()

        duration = float(value)

        if duration > 1:
            return duration

    except Exception:
        pass

    return 17.5


# ============================================================
# CREATE VIDEO
# ============================================================

def create_video(
    image_path,
    audio_path,
    output_path,
    scenes
):

    cfg = load(
        CFG,
        DEFAULT_CFG
    )

    width = int(
        cfg.get(
            "video_width",
            720
        )
    )

    height = int(
        cfg.get(
            "video_height",
            1280
        )
    )

    fps = int(
        cfg.get(
            "video_fps",
            24
        )
    )


    # --------------------------------------------------------
    # Scene timing
    # --------------------------------------------------------

    durations = [
        3.5,
        3.5,
        3.5,
        3.5,
        3.5
    ]


    total_duration = sum(
        durations
    )


    if audio_path and audio_path.exists():

        audio_duration = get_audio_duration(
            audio_path
        )

        # Give the voiceover enough room.
        total_duration = max(
            total_duration,
            audio_duration + 0.25
        )


    # --------------------------------------------------------
    # Video background with subtle zoom
    # --------------------------------------------------------

    filter_parts = [

        f"scale={width}:{height}:force_original_aspect_ratio=decrease",

        f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2",

        "zoompan="
        f"z='min(zoom+0.0008,1.08)':"
        f"x='iw/2-(iw/zoom/2)':"
        f"y='ih/2-(ih/zoom/2)':"
        f"d=1:"
        f"s={width}x{height}:"
        f"fps={fps}"

    ]


    # --------------------------------------------------------
    # Text overlays
    #
    # IMPORTANT:
    # Each text has its own enable time.
    # This fixes the old overlapping-text problem.
    # --------------------------------------------------------

    current = 0


    for index, scene in enumerate(scenes):

        start = current

        end = current + durations[index]

        text = escape_ffmpeg_text(
            scene["on_screen_text"]
        )


        # Hook and normal scene text
        if index == 0:

            fontsize = 48
            y_position = "h*0.10"

        elif index == 4:

            fontsize = 40
            y_position = "h*0.82"

        else:

            fontsize = 38
            y_position = "h*0.14"


        filter_parts.append(

            "drawtext="

            "fontfile=/usr/share/fonts/"
            "truetype/dejavu/"
            "DejaVuSans-Bold.ttf:"

            f"text='{text}':"

            f"fontsize={fontsize}:"

            "fontcolor=white:"

            "borderw=4:"

            "bordercolor=black:"

            "shadowx=2:"

            "shadowy=2:"

            "shadowcolor=black@0.7:"

            "x=(w-text_w)/2:"

            f"y={y_position}:"

            f"enable='between(t,{start},{end})'"

        )


        current = end


    # --------------------------------------------------------
    # Small permanent brand
    # --------------------------------------------------------

    filter_parts.append(

        "drawtext="

        "fontfile=/usr/share/fonts/"
        "truetype/dejavu/"
        "DejaVuSans-Bold.ttf:"

        "text='@waititsonsale':"

        "fontsize=28:"

        "fontcolor=white:"

        "borderw=3:"

        "bordercolor=black:"

        "x=35:"

        "y=35"

    )


    filter_parts.append(
        "format=yuv420p"
    )


    filter_complex = ",".join(
        filter_parts
    )


    # --------------------------------------------------------
    # FFmpeg command
    # --------------------------------------------------------

    cmd = [

        "ffmpeg",

        "-y",

        "-threads",
        "1",

        "-loop",
        "1",

        "-i",
        str(image_path)

    ]


    if audio_path and audio_path.exists():

        cmd.extend([
            "-i",
            str(audio_path)
        ])


    cmd.extend([

        "-t",
        str(total_duration),

        "-filter_complex",
        filter_complex,

        "-r",
        str(fps),

        "-c:v",
        "libx264",

        "-preset",
        "ultrafast",

        "-crf",
        "29",

        "-pix_fmt",
        "yuv420p",

        "-threads",
        "1"

    ])


    if audio_path and audio_path.exists():

        cmd.extend([

            "-map",
            "0:v:0",

            "-map",
            "1:a:0",

            "-c:a",
            "aac",

            "-b:a",
            "96k",

            "-af",
            "aresample=async=1",

            "-shortest"

        ])

    else:

        cmd.extend([
            "-an"
        ])


    cmd.append(
        str(output_path)
    )


    log(
        "Rendering improved Reel..."
    )


    try:

        result = subprocess.run(

            cmd,

            check=True,

            stdout=subprocess.PIPE,

            stderr=subprocess.PIPE,

            timeout=300

        )


        if output_path.exists():

            size = output_path.stat().st_size

            if size > 10_000:

                log(
                    f"Video created successfully: "
                    f"{size / 1024 / 1024:.1f} MB"
                )

                return True


    except subprocess.TimeoutExpired:

        log(
            "FFmpeg timed out."
        )

    except subprocess.CalledProcessError as e:

        error_text = (

            e.stderr.decode(
                "utf-8",
                errors="ignore"
            )

            if e.stderr

            else

            "Unknown FFmpeg error"
        )


        log(
            "FFmpeg failed: "
            + error_text[-2000:]
        )

    except Exception as e:

        log(
            f"Video generation error: {e}"
        )


    return False


# ============================================================
# CREATE REEL PACKAGE
# ============================================================

def create_reel_package(product):

    STATE["creating"] = True

    try:

        cfg = load(
            CFG,
            DEFAULT_CFG
        )


        handle = cfg.get(
            "handle",
            "@waititsonsale"
        )


        name = product.get(
            "name",
            "Interesting Product"
        )


        price = product.get(
            "price",
            "Check current price"
        )


        category = product.get(
            "category",
            "General"
        )


        why = product.get(
            "why",
            "a useful everyday product"
        )


        hook = random_hook(
            product
        )


        # ====================================================
        # SCENES
        # ====================================================

        scenes = [

            {
                "time": "0-3.5s",

                "visual":
                    "Start with the strongest product view.",

                "voiceover":
                    hook,

                "on_screen_text":
                    hook
            },

            {
                "time": "3.5-7s",

                "visual":
                    "Show the product clearly.",

                "voiceover":
                    f"This is the {name}.",

                "on_screen_text":
                    name.upper()
            },

            {
                "time": "7-10.5s",

                "visual":
                    "Show how the product solves a common problem.",

                "voiceover":
                    f"It solves {why}.",

                "on_screen_text":
                    "USEFUL. SIMPLE. PRACTICAL."
            },

            {
                "time": "10.5-14s",

                "visual":
                    "Bring attention to the price.",

                "voiceover":
                    f"And the example price is just {price}.",

                "on_screen_text":
                    f"AROUND {price}"
            },

            {
                "time": "14-17.5s",

                "visual":
                    "Finish with the product and a call to action.",

                "voiceover":
                    f"Save this find and follow {handle} for more.",

                "on_screen_text":
                    f"SAVE • FOLLOW {handle}"
            }

        ]


        voiceover = " ".join(
            scene["voiceover"]
            for scene in scenes
        )


        # ====================================================
        # CAPTION
        # ====================================================

        caption = f"""WAIT, IT'S ON SALE 👀

{name}

💰 Example price: {price}

Why this caught our attention:

• {why}
• Simple to understand
• Useful everyday product
• Easy to demonstrate

Before buying, always check:

✓ Current price
✓ Seller rating
✓ Recent reviews
✓ Warranty
✓ Return policy

Save this Reel so you can find it later.

Follow {handle} for more useful finds.

#waititsonsale
#usefulproducts
#budgetfinds
#shoppingfinds
#reelsindia
#productfinds
#homefinds
#amazonfinds

Disclosure:
Product links may be affiliate links.
Prices and availability can change.
"""


        # ====================================================
        # PACKAGE DIRECTORY
        # ====================================================

        timestamp = datetime.now().strftime(
            "%Y%m%d_%H%M%S"
        )


        safe_name = clean_filename(
            name
        )


        package_dir = (
            DRAFTS /
            f"{timestamp}_{safe_name}"
        )


        package_dir.mkdir(
            parents=True,
            exist_ok=True
        )


        # ====================================================
        # SCRIPT
        # ====================================================

        script_lines = [

            f"REEL: {name}",

            "=" * 60,

            f"CATEGORY: {category}",

            f"EXAMPLE PRICE: {price}",

            "",

            "CONCEPT",

            f"Fast-paced product discovery Reel for {name}.",

            "",

            "SCENE PLAN",

            "-" * 60

        ]


        for scene in scenes:

            script_lines.extend([

                "",

                f"{scene['time']} — VISUAL",

                scene["visual"],

                "",

                "VOICEOVER:",

                scene["voiceover"],

                "",

                "ON-SCREEN TEXT:",

                scene["on_screen_text"]

            ])


        script_lines.extend([

            "",

            "FULL VOICEOVER",

            "-" * 60,

            voiceover,

            "",

            "CAPTION",

            "-" * 60,

            caption

        ])


        script_text = "\n".join(
            script_lines
        )


        (package_dir / "script.txt").write_text(
            script_text.strip(),
            encoding="utf-8"
        )


        (package_dir / "caption.txt").write_text(
            caption.strip(),
            encoding="utf-8"
        )


        (package_dir / "voiceover.txt").write_text(
            voiceover.strip(),
            encoding="utf-8"
        )


        save(
            package_dir / "reel_plan.json",
            {
                "product": product,
                "duration_seconds": 17.5,
                "format": "9:16",
                "resolution": "720x1280",
                "scenes": scenes
            }
        )


        save(
            package_dir / "metadata.json",
            {
                "created_at":
                    datetime.now().isoformat(),

                "handle":
                    handle,

                "product":
                    product,

                "reel":
                    {
                        "duration_seconds": 17.5,
                        "format": "9:16",
                        "resolution": "720x1280",
                        "hook": hook,
                        "voiceover": voiceover,
                        "scenes": scenes
                    },

                "caption":
                    caption,

                "status":
                    "ready",

                "publishing":
                    {
                        "instagram": False,
                        "published": False
                    }
            }
        )


        # ====================================================
        # README
        # ====================================================

        readme = f"""@waititsonsale
REEL PACKAGE

Product:
{name}

Category:
{category}

Example price:
{price}

Created:
{datetime.now().strftime("%Y-%m-%d %H:%M:%S")}

Files:

script.txt
Complete Reel script.

caption.txt
Instagram caption.

voiceover.txt
Voiceover-only version.

reel_plan.json
Scene-by-scene production plan.

metadata.json
Machine-readable information.

product.jpg
Product artwork/image.

voiceover.mp3
Generated voiceover.

video.mp4
Final 9:16 Reel.

IMPORTANT:

Check current price and availability before publishing.
"""


        (package_dir / "README.txt").write_text(
            readme,
            encoding="utf-8"
        )


        # ====================================================
        # IMAGE
        # ====================================================

        image_path = (
            package_dir /
            "product.jpg"
        )


        artwork = create_product_artwork(
            product,
            image_path
        )


        if not artwork:

            log(
                "Could not create product artwork."
            )

            return package_dir


        # ====================================================
        # VOICEOVER
        # ====================================================

        audio_path = (
            package_dir /
            "voiceover.mp3"
        )


        voice = cfg.get(
            "voice",
            "en-IN-NeerjaNeural"
        )


        tts_success = generate_voiceover(

            voiceover,

            audio_path,

            voice

        )


        if tts_success:

            log(
                "Voiceover generated."
            )

        else:

            log(
                "Voiceover unavailable. "
                "Creating video without audio."
            )


        # ====================================================
        # VIDEO
        # ====================================================

        video_path = (
            package_dir /
            "video.mp4"
        )


        if not ffmpeg_available():

            log(
                "FFmpeg unavailable."
            )

            return package_dir


        success = create_video(

            image_path=artwork,

            audio_path=(
                audio_path
                if tts_success
                else None
            ),

            output_path=video_path,

            scenes=scenes

        )


        if not success:

            log(
                "Video generation failed."
            )

        return package_dir


    finally:

        STATE["creating"] = False


# ============================================================
# AUTOPILOT WORKER
# ============================================================

def cycle():

    STATE["worker_running"] = True

    log(
        "Autopilot worker started."
    )


    while True:

        try:

            cfg = load(
                CFG,
                DEFAULT_CFG
            )


            if not cfg.get(
                "enabled",
                False
            ):

                time.sleep(2)

                continue


            products = load(
                QUEUE,
                DEFAULT_PRODUCTS
            )


            if not products:

                log(
                    "No products available."
                )

                time.sleep(10)

                continue


            try:

                posts_per_day = int(
                    cfg.get(
                        "posts_per_day",
                        3
                    )
                )

            except Exception:

                posts_per_day = 3


            posts_per_day = max(
                1,
                min(
                    10,
                    posts_per_day
                )
            )


            try:

                last_index = int(
                    cfg.get(
                        "last_product_index",
                        0
                    )
                )

            except Exception:

                last_index = 0


            product = products[
                last_index %
                len(products)
            ]


            cfg[
                "last_product_index"
            ] = (
                last_index + 1
            ) % len(products)


            save(
                CFG,
                cfg
            )


            log(
                "Starting Reel: "
                + product.get(
                    "name",
                    "Unknown"
                )
            )


            try:

                package_dir = create_reel_package(
                    product
                )


                STATE["created"] += 1


                STATE["last_product"] = (
                    product.get(
                        "name",
                        "Unknown"
                    )
                )


                STATE["last_package"] = (
                    package_dir.name
                )


                video_file = (
                    package_dir /
                    "video.mp4"
                )


                if video_file.exists():

                    STATE["last_video"] = (
                        package_dir.name
                        + "/video.mp4"
                    )


                log(
                    "Reel package created: "
                    + package_dir.name
                )


            except Exception as e:

                log(
                    "Reel creation error: "
                    + str(e)
                )


            STATE["last_run"] = (
                datetime.now().strftime(
                    "%Y-%m-%d %H:%M:%S"
                )
            )


            interval = int(
                86400 /
                max(
                    1,
                    posts_per_day
                )
            )


            log(
                "Next Reel approximately "
                + str(interval // 3600)
                + " hour(s) from now."
            )


            for _ in range(interval):

                time.sleep(1)


                current_cfg = load(
                    CFG,
                    DEFAULT_CFG
                )


                if not current_cfg.get(
                    "enabled",
                    False
                ):

                    log(
                        "Autopilot stopped."
                    )

                    break


        except Exception as e:

            log(
                "Autopilot error: "
                + str(e)
            )

            time.sleep(10)


# ============================================================
# FASTAPI
# ============================================================

app = FastAPI(
    title="WaitItsOnSale Cloud Autopilot"
)


# ============================================================
# DASHBOARD
# ============================================================

@app.get(
    "/",
    response_class=HTMLResponse
)
def home():

    return HTMLResponse(
        """
<!doctype html>

<html>

<head>

<meta name="viewport"
content="width=device-width,initial-scale=1">

<title>WaitItsOnSale</title>

<style>

* {
    box-sizing:border-box;
}

body {
    margin:0;
    font-family:system-ui,-apple-system,BlinkMacSystemFont,sans-serif;
    background:#f4f4f4;
    color:#111;
}

.container {
    max-width:720px;
    margin:auto;
    padding:22px;
}

h1 {
    font-size:42px;
    margin:15px 0 25px;
}

.card {
    background:white;
    padding:25px;
    border-radius:25px;
    margin:18px 0;
    box-shadow:0 3px 20px rgba(0,0,0,.08);
}

.status {
    font-size:32px;
    font-weight:900;
}

button {
    padding:15px 22px;
    border:0;
    border-radius:15px;
    font-size:16px;
    font-weight:800;
    margin:5px;
}

.start {
    background:#111;
    color:white;
}

.stop {
    background:#ddd;
}

.save {
    background:#111;
    color:white;
    width:100%;
    margin-top:10px;
}

input,
select {
    width:100%;
    padding:15px;
    border:1px solid #ddd;
    border-radius:13px;
    font-size:16px;
    margin:8px 0 18px;
}

.label {
    font-weight:800;
}

.package {
    background:#f6f6f6;
    padding:16px;
    border-radius:15px;
    margin-top:12px;
    word-break:break-word;
}

.badge {
    display:inline-block;
    padding:6px 11px;
    border-radius:20px;
    background:#e8e8e8;
    font-weight:800;
    font-size:13px;
}

.video {
    width:100%;
    margin-top:15px;
    border-radius:15px;
    background:#000;
}

.download {
    display:block;
    text-align:center;
    text-decoration:none;
    background:#111;
    color:white;
    padding:14px;
    border-radius:13px;
    margin-top:12px;
    font-weight:800;
}

.small {
    color:#666;
    font-size:14px;
}

</style>

</head>

<body>

<div class="container">

<h1>⚡ WaitItsOnSale</h1>

<div class="card">

<div id="s"
class="status">
Loading…
</div>

<p id="x">
Loading status...
</p>

<button
class="start"
onclick="run(1)">
▶ START
</button>

<button
class="stop"
onclick="run(0)">
■ STOP
</button>

</div>


<div class="card">

<h2>Settings</h2>

<div class="label">
Reels per day
</div>

<input
id="p"
type="number"
min="1"
max="10"
value="3">

<div class="label">
Mode
</div>

<select id="m">

<option value="draft">
Draft — generate videos
</option>

<option value="publish">
Publish — reserved for future API
</option>

</select>


<div class="label">
Voice
</div>

<select id="v">

<option value="en-IN-NeerjaNeural">
Indian English — Female
</option>

<option value="en-IN-PrabhatNeural">
Indian English — Male
</option>

<option value="en-US-AriaNeural">
US English — Female
</option>

<option value="en-US-GuyNeural">
US English — Male
</option>

</select>


<button
class="save"
onclick="saveSettings()">

SAVE SETTINGS

</button>

</div>


<div class="card">

<h2>Latest Reel</h2>

<div id="latest">
No Reel created yet.
</div>

</div>


<div class="card">

<h2>How it works</h2>

<p>
<b>1.</b> Selects the next product.
</p>

<p>
<b>2.</b> Creates the Reel artwork.
</p>

<p>
<b>3.</b> Creates the script and caption.
</p>

<p>
<b>4.</b> Creates the voiceover.
</p>

<p>
<b>5.</b> Creates the final 9:16 video.
</p>

<p class="small">
Optimized for a low-memory Render instance.
</p>

</div>

</div>


<script>

async function getStatus() {

    try {

        const response =
            await fetch("/api/status");

        const data =
            await response.json();


        document.getElementById("s")
            .textContent =
            data.enabled
            ? "🟢 RUNNING"
            : "⚪ STOPPED";


        document.getElementById("x")
            .innerHTML =
            "Reels created: "
            + data.created
            + "<br>"
            + "Last run: "
            + (data.last_run || "—")
            + "<br>"
            + "Last product: "
            + (data.last_product || "—")
            + "<br>"
            + "Worker: "
            + (data.worker_running ? "Running" : "Stopped")
            + "<br><br>"
            + data.message;


        document.getElementById("p")
            .value =
            data.posts_per_day || 3;


        document.getElementById("m")
            .value =
            data.mode || "draft";


        document.getElementById("v")
            .value =
            data.voice || "en-IN-NeerjaNeural";


        if (data.last_package) {

            let html =

                '<div class="package">'
                +
                '<span class="badge">READY</span>'
                +
                '<br><br>'
                +
                data.last_package;


            if (data.last_video) {

                html +=

                    '<video '
                    +
                    'class="video" '
                    +
                    'controls '
                    +
                    'playsinline '
                    +
                    'src="/api/video?path='
                    +
                    encodeURIComponent(
                        data.last_video
                    )
                    +
                    '"></video>';


                html +=

                    '<a '
                    +
                    'class="download" '
                    +
                    'href="/api/video?path='
                    +
                    encodeURIComponent(
                        data.last_video
                    )
                    +
                    '&download=1">'
                    +
                    '⬇ DOWNLOAD REEL'
                    +
                    '</a>';
            }


            html += '</div>';


            document.getElementById("latest")
                .innerHTML =
                html;
        }

    }

    catch(error) {

        document.getElementById("s")
            .textContent =
            "🔴 CONNECTION ERROR";

    }

}


async function run(value) {

    try {

        await fetch(
            "/api/run",
            {
                method:"POST",

                headers:{
                    "Content-Type":
                        "application/json"
                },

                body:JSON.stringify({
                    enabled:value
                })
            }
        );

        setTimeout(
            getStatus,
            500
        );

    }

    catch(error) {

        alert(
            "Could not contact server."
        );

    }

}


async function saveSettings() {

    const posts =
        Number(
            document.getElementById("p").value
        );


    const mode =
        document.getElementById("m").value;


    const voice =
        document.getElementById("v").value;


    await fetch(
        "/api/config",
        {
            method:"POST",

            headers:{
                "Content-Type":
                    "application/json"
                },

            body:JSON.stringify({

                posts_per_day:
                    posts,

                mode:
                    mode,

                voice:
                    voice

            })
        }
    );


    alert(
        "Settings saved."
    );


    getStatus();

}


getStatus();

setInterval(
    getStatus,
    3000
);

</script>

</body>

</html>
"""
    )


# ============================================================
# STATUS
# ============================================================

@app.get("/api/status")
def status():

    cfg = load(
        CFG,
        DEFAULT_CFG
    )

    return JSONResponse({

        **STATE,

        "enabled":
            bool(
                cfg.get(
                    "enabled",
                    False
                )
            ),

        "handle":
            cfg.get(
                "handle",
                "@waititsonsale"
            ),

        "mode":
            cfg.get(
                "mode",
                "draft"
            ),

        "voice":
            cfg.get(
                "voice",
                "en-IN-NeerjaNeural"
            ),

        "posts_per_day":
            cfg.get(
                "posts_per_day",
                3
            )

    })


# ============================================================
# VIDEO
# ============================================================

@app.get("/api/video")
def video(
    path: str,
    download: int = 0
):

    requested = (
        DRAFTS /
        path
    ).resolve()


    drafts_root = (
        DRAFTS.resolve()
    )


    try:

        requested.relative_to(
            drafts_root
        )

    except ValueError:

        return JSONResponse(
            {
                "error":
                    "Invalid path"
            },
            status_code=403
        )


    if not requested.exists():

        return JSONResponse(
            {
                "error":
                    "Video not found"
            },
            status_code=404
        )


    return FileResponse(
        requested,
        media_type="video/mp4",
        filename=(
            requested.name
            if download
            else None
        )
    )


# ============================================================
# DRAFTS
# ============================================================

@app.get("/api/drafts")
def drafts():

    packages = []


    if DRAFTS.exists():

        for folder in sorted(
            DRAFTS.iterdir(),
            reverse=True
        ):

            if folder.is_dir():

                video_file = (
                    folder /
                    "video.mp4"
                )


                packages.append({

                    "name":
                        folder.name,

                    "path":
                        str(folder),

                    "video":
                        video_file.exists(),

                    "files":
                        [
                            file.name
                            for file in folder.iterdir()
                            if file.is_file()
                        ]

                })


    return {

        "count":
            len(packages),

        "packages":
            packages[:50]

    }


# ============================================================
# START / STOP
# ============================================================

@app.post("/api/run")
async def run(
    req: Request
):

    body = await req.json()

    cfg = load(
        CFG,
        DEFAULT_CFG
    )


    enabled = bool(
        body.get(
            "enabled",
            False
        )
    )


    cfg["enabled"] = enabled


    save(
        CFG,
        cfg
    )


    if enabled:

        log(
            "START pressed. Autopilot enabled."
        )

    else:

        log(
            "STOP pressed. Autopilot disabled."
        )


    return {

        "ok":
            True,

        "enabled":
            enabled

    }


# ============================================================
# CONFIG
# ============================================================

@app.post("/api/config")
async def config(
    req: Request
):

    body = await req.json()

    cfg = load(
        CFG,
        DEFAULT_CFG
    )


    if "posts_per_day" in body:

        try:

            posts = int(
                body["posts_per_day"]
            )

            cfg["posts_per_day"] = max(
                1,
                min(
                    10,
                    posts
                )
            )

        except Exception:

            cfg["posts_per_day"] = 3


    if "mode" in body:

        if body["mode"] in [
            "draft",
            "publish"
        ]:

            cfg["mode"] = body["mode"]


    if "voice" in body:

        cfg["voice"] = str(
            body["voice"]
        )


    save(
        CFG,
        cfg
    )


    log(
        "Settings saved."
    )


    return {
        "ok": True
    }


# ============================================================
# ADD PRODUCT
# ============================================================

@app.post("/api/product")
async def add_product(
    req: Request
):

    body = await req.json()

    products = load(
        QUEUE,
        DEFAULT_PRODUCTS
    )


    product = {

        "name":
            str(
                body.get(
                    "name",
                    "New Product"
                )
            ),

        "price":
            str(
                body.get(
                    "price",
                    "Check price"
                )
            ),

        "category":
            str(
                body.get(
                    "category",
                    "General"
                )
            ),

        "why":
            str(
                body.get(
                    "why",
                    "useful everyday product"
                )
            ),

        "image_url":
            str(
                body.get(
                    "image_url",
                    ""
                )
            )

    }


    products.append(
        product
    )


    save(
        QUEUE,
        products
    )


    log(
        f"Product added: {product['name']}"
    )


    return {

        "ok":
            True,

        "product":
            product

    }


# ============================================================
# PRODUCTS
# ============================================================

@app.get("/api/products")
def products():

    products = load(
        QUEUE,
        DEFAULT_PRODUCTS
    )

    return {

        "count":
            len(products),

        "products":
            products

    }


# ============================================================
# HEALTH
# ============================================================

@app.get("/health")
def health():

    return {

        "ok":
            True,

        "service":
            "waititsonsale-autopilot",

        "version":
            "6.0-reel-layout",

        "ffmpeg":
            ffmpeg_available(),

        "worker_running":
            STATE["worker_running"],

        "creating":
            STATE["creating"]

    }


# ============================================================
# START WORKER
# ============================================================

def start_worker():

    worker = threading.Thread(
        target=cycle,
        daemon=True
    )

    worker.start()

    return worker


# ============================================================
# INITIALIZE
# ============================================================

load(
    CFG,
    DEFAULT_CFG
)

load(
    QUEUE,
    DEFAULT_PRODUCTS
)

start_worker()


# ============================================================
# LOCAL DEVELOPMENT
# ============================================================

if __name__ == "__main__":

    import uvicorn

    uvicorn.run(
        app,
        host="0.0.0.0",
        port=int(
            os.getenv(
                "PORT",
                "8080"
            )
        )
    )
