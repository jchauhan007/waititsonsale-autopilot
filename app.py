import os
import json
import threading
import time
import random
import asyncio
import urllib.request
import subprocess
import shutil
import re
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse


# ============================================================
# CONFIGURATION
# ============================================================

BASE = Path(__file__).parent

DATA = BASE / "data"
DATA.mkdir(parents=True, exist_ok=True)

CFG = DATA / "config.json"
QUEUE = DATA / "products.json"

DRAFTS = DATA / "drafts"
DRAFTS.mkdir(parents=True, exist_ok=True)

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
            path.read_text(encoding="utf-8")
        )

    except Exception as e:

        log(
            f"Could not load {path.name}: {e}"
        )

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

    STATE["message"] = str(message)

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
# UTILITY
# ============================================================

def clean_filename(value):

    value = str(value)

    value = re.sub(
        r"[^a-zA-Z0-9_\-]+",
        "_",
        value
    )

    return value[:80].strip("_")


def escape_ffmpeg_text(text):

    """
    Safely escape text for FFmpeg drawtext.

    FFmpeg drawtext is extremely sensitive to:
    :
    ,
    '
    \
    %
    [
    ]
    ;
    """

    text = str(text)

    replacements = [
        ("\\", r"\\"),
        (":", r"\:"),
        (",", r"\,"),
        ("'", r"\'"),
        ("%", r"\%"),
        ("[", r"\["),
        ("]", r"\]"),
        (";", r"\;"),
        ("\n", " "),
        ("\r", " ")
    ]

    for old, new in replacements:
        text = text.replace(old, new)

    return text


def wrap_text(text, width=28):

    words = str(text).split()

    lines = []

    current = ""

    for word in words:

        if len(current) + len(word) + 1 <= width:

            if current:
                current += " "

            current += word

        else:

            if current:
                lines.append(current)

            current = word

    if current:
        lines.append(current)

    return "\n".join(lines)


# ============================================================
# FFMPEG / FFPROBE
# ============================================================

def ffmpeg_available():

    return shutil.which("ffmpeg") is not None


def ffprobe_available():

    return shutil.which("ffprobe") is not None


def find_font():

    possible_fonts = [

        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",

        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",

        "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf",

        "/usr/share/fonts/dejavu/DejaVuSans.ttf",

        "/usr/share/fonts/truetype/liberation2/"
        "LiberationSans-Bold.ttf",

        "/usr/share/fonts/truetype/liberation/"
        "LiberationSans-Bold.ttf"

    ]

    for font in possible_fonts:

        if Path(font).exists():
            return font

    return None


def verify_video(path):

    """
    Make sure the file is actually a usable MP4.
    """

    try:

        if not path.exists():
            return False

        size = path.stat().st_size

        if size < 10_000:
            log(
                f"Video validation failed: file only {size} bytes."
            )
            return False

        if not ffprobe_available():

            # Basic MP4 signature check.
            with path.open("rb") as f:
                header = f.read(32)

            if b"ftyp" not in header:
                log(
                    "Video validation failed: MP4 header missing."
                )
                return False

            return True

        result = subprocess.run(

            [
                "ffprobe",

                "-v",
                "error",

                "-show_entries",
                "format=duration,size",

                "-of",
                "json",

                str(path)
            ],

            stdout=subprocess.PIPE,

            stderr=subprocess.PIPE,

            timeout=30

        )

        if result.returncode != 0:

            error = result.stderr.decode(
                "utf-8",
                errors="ignore"
            )

            log(
                "ffprobe validation failed: "
                + error[-1000:]
            )

            return False

        data = json.loads(
            result.stdout.decode(
                "utf-8",
                errors="ignore"
            )
        )

        fmt = data.get(
            "format",
            {}
        )

        duration = float(
            fmt.get(
                "duration",
                0
            )
        )

        filesize = float(
            fmt.get(
                "size",
                0
            )
        )

        if duration <= 0:
            log(
                "Video validation failed: duration is zero."
            )
            return False

        if filesize < 10_000:
            log(
                "Video validation failed: file size is too small."
            )
            return False

        log(
            f"Video verified: {duration:.2f}s / "
            f"{filesize / 1024:.1f} KB"
        )

        return True

    except Exception as e:

        log(
            f"Video verification error: {e}"
        )

        return False


# ============================================================
# PRODUCT HOOK
# ============================================================

def random_hook(product):

    price = product.get(
        "price",
        ""
    )

    hooks = [

        f"WAIT… why is this only {price}?",

        f"I found something actually useful for {price}.",

        "Okay, this might actually be worth buying.",

        "Why did nobody tell me about this before?",

        "This is one of those products you don't know you need until you see it.",

        "POV: you find something genuinely useful for under ₹500.",

        f"Would you buy this for {price}?",

        "This little product solves a surprisingly annoying problem."

    ]

    return random.choice(hooks)


# ============================================================
# DOWNLOAD IMAGE
# ============================================================

def download_image(url, destination):

    if not url:
        return None

    try:

        request = urllib.request.Request(
            url,
            headers={
                "User-Agent":
                    "Mozilla/5.0"
            }
        )

        with urllib.request.urlopen(
            request,
            timeout=20
        ) as response:

            data = response.read()

        if not data:
            return None

        destination.write_bytes(
            data
        )

        if destination.stat().st_size < 100:
            destination.unlink(
                missing_ok=True
            )
            return None

        log(
            f"Product image downloaded: "
            f"{destination.stat().st_size} bytes"
        )

        return destination

    except Exception as e:

        log(
            f"Image download failed: {e}"
        )

        try:
            destination.unlink(
                missing_ok=True
            )
        except Exception:
            pass

        return None


# ============================================================
# CREATE PLACEHOLDER IMAGE
# ============================================================

def create_placeholder_image(
    product,
    output
):

    try:

        from PIL import Image
        from PIL import ImageDraw
        from PIL import ImageFont

    except Exception as e:

        log(
            f"Pillow unavailable: {e}"
        )

        return None


    width = 720
    height = 1280


    image = Image.new(
        "RGB",
        (width, height),
        (245, 245, 245)
    )

    draw = ImageDraw.Draw(
        image
    )


    font_path = find_font()


    try:

        if font_path:

            font_large = ImageFont.truetype(
                font_path,
                52
            )

            font_medium = ImageFont.truetype(
                font_path,
                34
            )

            font_small = ImageFont.truetype(
                font_path,
                28
            )

        else:

            font_large = None
            font_medium = None
            font_small = None

    except Exception:

        font_large = None
        font_medium = None
        font_small = None


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


    draw.text(
        (50, 80),
        "@waititsonsale",
        fill=(15, 15, 15),
        font=font_medium
    )


    card_x1 = 45
    card_y1 = 380
    card_x2 = 675
    card_y2 = 850


    draw.rounded_rectangle(
        (
            card_x1,
            card_y1,
            card_x2,
            card_y2
        ),
        radius=35,
        fill=(255, 255, 255)
    )


    wrapped = wrap_text(
        name,
        20
    )


    bbox = draw.multiline_textbbox(
        (0, 0),
        wrapped,
        font=font_large,
        spacing=10
    )

    text_width = bbox[2] - bbox[0]


    draw.multiline_text(
        (
            (width - text_width) / 2,
            500
        ),
        wrapped,
        fill=(15, 15, 15),
        font=font_large,
        align="center",
        spacing=10
    )


    draw.text(
        (70, 730),
        f"{category}  •  {price}",
        fill=(50, 50, 50),
        font=font_medium
    )


    draw.text(
        (50, 970),
        "USEFUL FINDS.",
        fill=(15, 15, 15),
        font=font_medium
    )


    draw.text(
        (50, 1025),
        "SAVE THIS REEL",
        fill=(15, 15, 15),
        font=font_medium
    )


    image.save(
        output,
        "JPEG",
        quality=88,
        optimize=True
    )


    if not output.exists():
        return None

    if output.stat().st_size < 1_000:
        return None

    log(
        f"Placeholder image created: "
        f"{output.stat().st_size} bytes"
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

        if output.exists() and output.stat().st_size > 1_000:

            log(
                f"Voiceover created: "
                f"{output.stat().st_size} bytes"
            )

            return True

        log(
            "TTS returned but audio file is empty."
        )

        return False

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
# VIDEO GENERATOR
# ============================================================

def create_video(
    image_path,
    audio_path,
    output_path,
    product,
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


    durations = [
        3,
        3,
        4,
        3,
        4
    ]


    total_duration = sum(
        durations
    )


    # --------------------------------------------------------
    # Validate image
    # --------------------------------------------------------

    if not image_path.exists():

        log(
            "FFmpeg stopped: image does not exist."
        )

        return False


    if image_path.stat().st_size < 1_000:

        log(
            "FFmpeg stopped: image is empty."
        )

        return False


    # --------------------------------------------------------
    # Find font
    # --------------------------------------------------------

    font = find_font()

    if not font:

        log(
            "WARNING: DejaVu font not found. "
            "Trying FFmpeg's default font handling."
        )


    # --------------------------------------------------------
    # Build video filter
    # --------------------------------------------------------

    filter_parts = [

        f"scale={width}:{height}:"
        "force_original_aspect_ratio=decrease",

        f"pad={width}:{height}:"
        "(ow-iw)/2:(oh-ih)/2",

        "setsar=1"

    ]


    current = 0


    for index, scene in enumerate(scenes):

        if index >= len(durations):
            break


        text = escape_ffmpeg_text(
            scene.get(
                "on_screen_text",
                ""
            )
        )


        start = current

        end = current + durations[index]


        if font:

            drawtext = (

                "drawtext="

                f"fontfile='{font}':"

                f"text='{text}':"

                "fontcolor=white:"

                "fontsize=42:"

                "borderw=3:"

                "bordercolor=black:"

                "x=(w-text_w)/2:"

                "y=h*0.78:"

                f"enable='between(t,{start},{end})'"

            )

        else:

            drawtext = (

                "drawtext="

                f"text='{text}':"

                "fontcolor=white:"

                "fontsize=42:"

                "borderw=3:"

                "bordercolor=black:"

                "x=(w-text_w)/2:"

                "y=h*0.78:"

                f"enable='between(t,{start},{end})'"

            )


        filter_parts.append(
            drawtext
        )


        current = end


    filter_parts.append(
        "format=yuv420p"
    )


    filter_complex = ",".join(
        filter_parts
    )


    # --------------------------------------------------------
    # IMPORTANT:
    #
    # Never write directly to video.mp4.
    #
    # FFmpeg writes to:
    #
    #     video.mp4.tmp
    #
    # Then we validate it.
    #
    # Only after successful validation:
    #
    #     video.mp4
    #
    # is created.
    # --------------------------------------------------------

    temp_output = output_path.with_suffix(
        ".mp4.tmp"
    )


    try:

        temp_output.unlink(
            missing_ok=True
        )

    except Exception:
        pass


    # --------------------------------------------------------
    # FFmpeg command
    # --------------------------------------------------------

    cmd = [

        "ffmpeg",

        "-hide_banner",

        "-loglevel",
        "error",

        "-y",

        "-threads",
        "1",

        "-loop",
        "1",

        "-framerate",
        str(fps),

        "-i",
        str(image_path)

    ]


    has_audio = (

        audio_path is not None
        and audio_path.exists()
        and audio_path.stat().st_size > 1_000

    )


    if has_audio:

        cmd.extend([

            "-i",
            str(audio_path)

        ])


    cmd.extend([

        "-t",
        str(total_duration),

        "-filter_complex",
        filter_complex,

        "-map",
        "0:v:0",

        "-r",
        str(fps),

        "-c:v",
        "libx264",

        "-preset",
        "ultrafast",

        "-crf",
        "30",

        "-pix_fmt",
        "yuv420p",

        "-movflags",
        "+faststart"

    ])


    if has_audio:

        cmd.extend([

            "-map",
            "1:a:0",

            "-c:a",
            "aac",

            "-b:a",
            "96k",

            "-ar",
            "44100",

            "-ac",
            "2"

        ])


    cmd.append(
        str(temp_output)
    )


    log(
        "Starting FFmpeg video generation..."
    )


    log(
        "FFmpeg command started."
    )


    try:

        result = subprocess.run(

            cmd,

            stdout=subprocess.PIPE,

            stderr=subprocess.PIPE,

            timeout=300

        )


        stderr = result.stderr.decode(
            "utf-8",
            errors="ignore"
        )


        stdout = result.stdout.decode(
            "utf-8",
            errors="ignore"
        )


        if result.returncode != 0:

            log(
                "FFmpeg FAILED:"
            )

            log(
                stderr[-4000:]
            )

            try:
                temp_output.unlink(
                    missing_ok=True
                )
            except Exception:
                pass

            return False


        if not temp_output.exists():

            log(
                "FFmpeg reported success but "
                "output file does not exist."
            )

            return False


        temp_size = temp_output.stat().st_size


        log(
            f"FFmpeg produced temporary file: "
            f"{temp_size} bytes"
        )


        if temp_size < 10_000:

            log(
                "FFmpeg produced an empty/tiny video."
            )

            try:
                temp_output.unlink(
                    missing_ok=True
                )
            except Exception:
                pass

            return False


        # ----------------------------------------------------
        # Validate before publishing as video.mp4
        # ----------------------------------------------------

        if not verify_video(temp_output):

            log(
                "Temporary video failed validation."
            )

            try:
                temp_output.unlink(
                    missing_ok=True
                )
            except Exception:
                pass

            return False


        # ----------------------------------------------------
        # Atomic rename
        # ----------------------------------------------------

        output_path.unlink(
            missing_ok=True
        )


        os.replace(
            temp_output,
            output_path
        )


        final_size = output_path.stat().st_size


        if final_size < 10_000:

            log(
                "Final video is unexpectedly small."
            )

            output_path.unlink(
                missing_ok=True
            )

            return False


        log(
            f"VIDEO CREATED SUCCESSFULLY: "
            f"{output_path.name} "
            f"({final_size / 1024 / 1024:.2f} MB)"
        )


        return True


    except subprocess.TimeoutExpired:

        log(
            "FFmpeg timed out after 300 seconds."
        )

        try:
            temp_output.unlink(
                missing_ok=True
            )
        except Exception:
            pass

        return False


    except Exception as e:

        log(
            f"Video generation error: {e}"
        )

        try:
            temp_output.unlink(
                missing_ok=True
            )
        except Exception:
            pass

        return False


# ============================================================
# GENERATE REEL PACKAGE
# ============================================================

def create_reel_package(product):

    if STATE["creating"]:

        log(
            "A Reel is already being created. Skipping."
        )

        return None


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


        image_url = product.get(
            "image_url",
            ""
        )


        hook = random_hook(
            product
        )


        # ====================================================
        # SCENES
        # ====================================================

        scenes = [

            {
                "time": "0-3s",

                "visual":
                    f"Show a strong close-up of the {name}.",

                "voiceover":
                    hook,

                "on_screen_text":
                    hook
            },

            {
                "time": "3-6s",

                "visual":
                    f"Show the {name} from multiple angles.",

                "voiceover":
                    f"This is the {name}, and it solves {why}.",

                "on_screen_text":
                    name
            },

            {
                "time": "6-10s",

                "visual":
                    "Show the product being used.",

                "voiceover":
                    "The best part is how simple it is to use.",

                "on_screen_text":
                    "Simple. Useful. Practical."
            },

            {
                "time": "10-13s",

                "visual":
                    "Show the result after using the product.",

                "voiceover":
                    f"And at around {price}, it could be worth checking out.",

                "on_screen_text":
                    f"Example price: {price}"
            },

            {
                "time": "13-17s",

                "visual":
                    "Finish with a clean product shot.",

                "voiceover":
                    f"Save this for later and follow {handle} for more useful finds.",

                "on_screen_text":
                    f"Follow {handle}"
            }

        ]


        voiceover = "\n".join(
            scene["voiceover"]
            for scene in scenes
        )


        # ====================================================
        # CAPTION
        # ====================================================

        caption = f"""WAIT, IT'S ON SALE

{name}

💰 Example price: {price}

Why it caught our attention:

• {why}
• Easy to understand quickly
• Strong visual demonstration potential
• Useful {category.lower()} product

Before buying, always verify:

✓ Current price
✓ Seller rating
✓ Reviews
✓ Warranty
✓ Return policy

Save this for later.

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
        # WRITE SCRIPT
        # ====================================================

        script_lines = [

            f"REEL: {name}",

            "=" * 60,

            f"CATEGORY: {category}",

            f"EXAMPLE PRICE: {price}",

            "",

            "CONCEPT",

            f"Fast-paced product discovery Reel showing why the "
            f"{name} is useful and worth considering.",

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
                "duration_seconds": 17,
                "format": "9:16",
                "resolution": "720x1280",
                "scenes": scenes
            }
        )


        metadata = {

            "created_at":
                datetime.now().isoformat(),

            "handle":
                handle,

            "product":
                product,

            "reel":
                {
                    "duration_seconds": 17,
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


        save(
            package_dir / "metadata.json",
            metadata
        )


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
Product image.

voiceover.mp3
Generated voiceover.

video.mp4
Generated 9:16 Reel video.

IMPORTANT:

Price and availability must be checked before publishing.
"""


        (package_dir / "README.txt").write_text(
            readme,
            encoding="utf-8"
        )


        # ====================================================
        # PRODUCT IMAGE
        # ====================================================

        image_path = (
            package_dir /
            "product.jpg"
        )


        downloaded = None


        if image_url:

            downloaded = download_image(
                image_url,
                image_path
            )


        if not downloaded:

            downloaded = create_placeholder_image(
                product,
                image_path
            )


        if not downloaded:

            log(
                "Could not create product image."
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


        # ====================================================
        # VIDEO
        # ====================================================

        video_path = (
            package_dir /
            "video.mp4"
        )


        if not ffmpeg_available():

            log(
                "FFmpeg is NOT installed."
            )

        else:

            success = create_video(

                image_path=downloaded,

                audio_path=(
                    audio_path
                    if tts_success
                    else None
                ),

                output_path=video_path,

                product=product,

                scenes=scenes

            )


            if not success:

                log(
                    "VIDEO CREATION FAILED."
                )

            else:

                log(
                    "VIDEO FILE READY."
                )


        # ====================================================
        # Update metadata after video creation
        # ====================================================

        metadata_path = (
            package_dir /
            "metadata.json"
        )


        metadata = load(
            metadata_path,
            {}
        )


        if video_path.exists():

            metadata["status"] = "ready"

            metadata["video"] = {

                "filename":
                    "video.mp4",

                "size_bytes":
                    video_path.stat().st_size,

                "valid":
                    verify_video(video_path)

            }

        else:

            metadata["status"] = "video_failed"


        save(
            metadata_path,
            metadata
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


            # ------------------------------------------------
            # WAIT UNTIL ENABLED
            # ------------------------------------------------

            if not cfg.get(
                "enabled",
                False
            ):

                time.sleep(2)

                continue


            # ------------------------------------------------
            # Prevent concurrent generation
            # ------------------------------------------------

            if STATE["creating"]:

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


            # ------------------------------------------------
            # SELECT PRODUCT
            # ------------------------------------------------

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


            last_index = (
                last_index + 1
            ) % len(products)


            cfg[
                "last_product_index"
            ] = last_index


            save(
                CFG,
                cfg
            )


            log(
                f"Starting Reel: "
                f"{product.get('name', 'Unknown')}"
            )


            # ------------------------------------------------
            # CREATE ONE REEL
            # ------------------------------------------------

            try:

                package_dir = create_reel_package(
                    product
                )


                if package_dir is not None:

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


                    if (
                        video_file.exists()
                        and
                        verify_video(video_file)
                    ):

                        STATE["last_video"] = (
                            package_dir.name
                            + "/video.mp4"
                        )

                        log(
                            "Reel package and video "
                            "created successfully."
                        )

                    else:

                        STATE["last_video"] = None

                        log(
                            "Package created but video "
                            "was not valid."
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


            # ------------------------------------------------
            # DISTRIBUTE POSTS THROUGH DAY
            # ------------------------------------------------

            interval = int(
                86400 /
                max(
                    1,
                    posts_per_day
                )
            )


            log(
                f"Next Reel scheduled in approximately "
                f"{interval // 3600} hour(s)."
            )


            for _ in range(
                interval
            ):

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
                f"Autopilot error: {e}"
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
<b>2.</b> Creates the script and caption.
</p>

<p>
<b>3.</b> Creates the voiceover.
</p>

<p>
<b>4.</b> Creates one memory-optimized 9:16 video.
</p>

<p>
<b>5.</b> Waits until the next scheduled Reel.
</p>

<p class="small">
Video generation is validated before it is marked READY.
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
            + "<br>"
            + "Creating: "
            + (data.creating ? "Yes" : "No")
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
                '<span class="badge">PACKAGE READY</span>'
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

            } else {

                html +=

                    '<p style="color:#b00020">'
                    +
                    'Video generation failed. '
                    +
                    'Check the activity log.'
                    +
                    '</p>';
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
# STATUS API
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
# VIDEO DOWNLOAD / STREAM
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


    if requested.suffix.lower() != ".mp4":

        return JSONResponse(
            {
                "error":
                    "Only MP4 files are allowed"
            },
            status_code=403
        )


    if requested.stat().st_size < 10_000:

        return JSONResponse(
            {
                "error":
                    "Video file is invalid or empty"
            },
            status_code=500
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
# LIST DRAFTS
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


                valid_video = False


                if video_file.exists():

                    valid_video = verify_video(
                        video_file
                    )


                packages.append({

                    "name":
                        folder.name,

                    "path":
                        str(folder),

                    "video":
                        valid_video,

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
# SAVE CONFIGURATION
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
# LOG
# ============================================================

@app.get("/api/log")
def activity_log():

    try:

        if not ACTIVITY_LOG.exists():

            return {
                "log": ""
            }


        text = ACTIVITY_LOG.read_text(
            encoding="utf-8"
        )


        return {
            "log": text[-15_000:]
        }


    except Exception as e:

        return {
            "log":
                f"Could not read log: {e}"
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
            "6.0-video-fixed",

        "ffmpeg":
            ffmpeg_available(),

        "ffprobe":
            ffprobe_available(),

        "font":
            bool(find_font()),

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
        daemon=True,
        name="waititsonsale-worker"
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
