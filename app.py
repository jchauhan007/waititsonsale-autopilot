import os
import json
import threading
import time
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
# PATHS
# ============================================================

BASE = Path(__file__).resolve().parent

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
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def save(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)

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

    line = f"[{timestamp}] {message}"

    print(line, flush=True)

    try:
        with ACTIVITY_LOG.open("a", encoding="utf-8") as f:
            f.write(line + "\n")
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


def escape_ffmpeg_text(text):
    text = str(text)

    text = text.replace("\\", "\\\\")
    text = text.replace(":", "\\:")
    text = text.replace("'", "\\'")
    text = text.replace("%", "\\%")
    text = text.replace("[", "\\[")
    text = text.replace("]", "\\]")
    text = text.replace("\n", " ")

    return text


# ============================================================
# FFMPEG
# ============================================================

def ffmpeg_available():
    return shutil.which("ffmpeg") is not None


def ffprobe_available():
    return shutil.which("ffprobe") is not None


def get_ffmpeg_version():
    if not ffmpeg_available():
        return "FFmpeg not found"

    try:
        result = subprocess.run(
            ["ffmpeg", "-version"],
            capture_output=True,
            text=True,
            timeout=10
        )

        first_line = result.stdout.splitlines()[0]

        return first_line

    except Exception as e:
        return f"FFmpeg version error: {e}"


# ============================================================
# PRODUCT HOOK
# ============================================================

def random_hook(product):
    import random

    price = product.get("price", "")

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
# IMAGE DOWNLOAD
# ============================================================

def download_image(url, destination):
    if not url:
        return None

    try:
        log("Downloading product image...")

        request = urllib.request.Request(
            url,
            headers={
                "User-Agent": "Mozilla/5.0"
            }
        )

        with urllib.request.urlopen(
            request,
            timeout=30
        ) as response:

            data = response.read()

        if not data:
            raise RuntimeError("Downloaded image is empty.")

        destination.write_bytes(data)

        if destination.stat().st_size < 100:
            raise RuntimeError("Downloaded image is invalid.")

        log(
            f"Product image downloaded: "
            f"{destination.stat().st_size} bytes"
        )

        return destination

    except Exception as e:
        log(f"Image download failed: {e}")
        return None


# ============================================================
# PLACEHOLDER IMAGE
# ============================================================

def create_placeholder_image(product, output):
    try:
        from PIL import Image, ImageDraw, ImageFont
    except Exception as e:
        log(f"Pillow unavailable: {e}")
        return None

    width = 720
    height = 1280

    try:
        image = Image.new(
            "RGB",
            (width, height),
            (245, 245, 245)
        )

        draw = ImageDraw.Draw(image)

        font_path = (
            "/usr/share/fonts/truetype/"
            "dejavu/DejaVuSans-Bold.ttf"
        )

        normal_path = (
            "/usr/share/fonts/truetype/"
            "dejavu/DejaVuSans.ttf"
        )

        try:
            font_large = ImageFont.truetype(
                font_path,
                50
            )

            font_medium = ImageFont.truetype(
                font_path,
                32
            )

            font_small = ImageFont.truetype(
                normal_path,
                26
            )

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
            (45, 70),
            "@waititsonsale",
            fill=(15, 15, 15),
            font=font_medium
        )

        draw.text(
            (45, 160),
            "USEFUL FIND",
            fill=(80, 80, 80),
            font=font_small
        )

        # Product card
        draw.rounded_rectangle(
            (40, 330, 680, 870),
            radius=35,
            fill=(255, 255, 255),
            outline=(220, 220, 220),
            width=3
        )

        wrapped = wrap_text(name, 20)

        bbox = draw.multiline_textbbox(
            (0, 0),
            wrapped,
            font=font_large,
            spacing=12,
            align="center"
        )

        text_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]

        draw.multiline_text(
            (
                (width - text_width) / 2,
                520 - text_height / 2
            ),
            wrapped,
            fill=(15, 15, 15),
            font=font_large,
            align="center",
            spacing=12
        )

        draw.text(
            (70, 760),
            f"{category}  •  {price}",
            fill=(60, 60, 60),
            font=font_medium
        )

        draw.text(
            (45, 970),
            "SAVE THIS REEL",
            fill=(15, 15, 15),
            font=font_medium
        )

        draw.text(
            (45, 1030),
            "More useful finds →",
            fill=(80, 80, 80),
            font=font_small
        )

        image.save(
            output,
            "JPEG",
            quality=90,
            optimize=True
        )

        if not output.exists():
            raise RuntimeError("Placeholder image was not created.")

        if output.stat().st_size < 1000:
            raise RuntimeError("Placeholder image is too small.")

        log(
            f"Placeholder image created: "
            f"{output.stat().st_size} bytes"
        )

        return output

    except Exception as e:
        log(f"Placeholder image failed: {e}")
        return None


# ============================================================
# TTS
# ============================================================

async def generate_tts_async(text, output, voice):
    try:
        import edge_tts

        communicate = edge_tts.Communicate(
            text,
            voice
        )

        await communicate.save(
            str(output)
        )

        if not output.exists():
            return False

        if output.stat().st_size < 1000:
            log("TTS file was created but is too small.")
            return False

        return True

    except Exception as e:
        log(f"TTS error: {e}")
        return False


def generate_voiceover(text, output, voice):
    try:
        return asyncio.run(
            generate_tts_async(
                text,
                output,
                voice
            )
        )

    except Exception as e:
        log(f"TTS runtime error: {e}")
        return False


# ============================================================
# VERIFY VIDEO
# ============================================================

def verify_video(path):
    if not path.exists():
        log("VIDEO VERIFY: file does not exist.")
        return False

    size = path.stat().st_size

    log(
        f"VIDEO VERIFY: file size = {size} bytes"
    )

    if size < 10_000:
        log("VIDEO VERIFY: file is too small.")
        return False

    if not ffprobe_available():
        log(
            "ffprobe unavailable; file-size verification passed."
        )
        return True

    try:
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
            capture_output=True,
            text=True,
            timeout=30
        )

        if result.returncode != 0:
            log(
                "VIDEO VERIFY: ffprobe failed: "
                + result.stderr[-1000:]
            )
            return False

        data = json.loads(result.stdout)

        duration = float(
            data["format"].get(
                "duration",
                0
            )
        )

        reported_size = int(
            float(
                data["format"].get(
                    "size",
                    0
                )
            )
        )

        log(
            f"VIDEO VERIFY: duration={duration:.2f}s "
            f"size={reported_size}"
        )

        if duration <= 0:
            return False

        return True

    except Exception as e:
        log(
            f"VIDEO VERIFY error: {e}"
        )
        return False


# ============================================================
# VIDEO CREATOR
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

    duration = 17

    if not ffmpeg_available():
        log("CRITICAL: FFmpeg is not installed.")
        return False

    if not image_path.exists():
        log("CRITICAL: input image does not exist.")
        return False

    if image_path.stat().st_size < 1000:
        log("CRITICAL: input image is invalid.")
        return False

    # --------------------------------------------------------
    # Output is first created as .tmp.mp4.
    # It will ONLY become video.mp4 after verification.
    # --------------------------------------------------------

    temp_output = output_path.with_suffix(".tmp.mp4")

    try:
        if temp_output.exists():
            temp_output.unlink()

        if output_path.exists():
            output_path.unlink()

    except Exception:
        pass

    # --------------------------------------------------------
    # Build drawtext filters
    # --------------------------------------------------------

    filters = []

    current = 0

    durations = [3, 3, 4, 3, 4]

    for i, scene in enumerate(scenes):

        start = current
        end = current + durations[i]

        text = escape_ffmpeg_text(
            scene.get(
                "on_screen_text",
                ""
            )
        )

        filters.append(
            "drawtext="
            "fontfile=/usr/share/fonts/"
            "truetype/dejavu/"
            "DejaVuSans-Bold.ttf:"
            f"text='{text}':"
            "fontcolor=white:"
            "fontsize=42:"
            "borderw=4:"
            "bordercolor=black:"
            "x=(w-text_w)/2:"
            "y=h*0.78:"
            f"enable='between(t,{start},{end})'"
        )

        current = end

    filters.append("format=yuv420p")

    filter_string = ",".join(filters)

    # --------------------------------------------------------
    # FFmpeg command
    # --------------------------------------------------------

    cmd = [
        "ffmpeg",
        "-y",

        "-hide_banner",

        "-loglevel",
        "warning",

        "-threads",
        "1",

        # Loop image forever.
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
        and audio_path.stat().st_size > 1000
    )

    if has_audio:
        cmd.extend([
            "-i",
            str(audio_path)
        ])

    cmd.extend([
        "-t",
        str(duration),

        "-vf",
        filter_string,

        "-s",
        f"{width}x{height}",

        "-r",
        str(fps),

        "-c:v",
        "libx264",

        "-preset",
        "ultrafast",

        "-crf",
        "28",

        "-pix_fmt",
        "yuv420p",

        "-movflags",
        "+faststart"
    ])

    if has_audio:

        cmd.extend([
            "-map",
            "0:v:0",

            "-map",
            "1:a:0",

            "-c:a",
            "aac",

            "-b:a",
            "96k",

            "-ar",
            "44100",

            "-ac",
            "2",

            # Make audio exactly fit the video.
            "-af",
            "apad",

            "-shortest"
        ])

    else:

        log(
            "No valid voiceover. Creating video without audio."
        )

    cmd.append(
        str(temp_output)
    )

    log(
        "Starting FFmpeg video generation..."
    )

    log(
        "Command: "
        + " ".join(cmd)
    )

    try:

        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=300
        )

        stderr = (
            result.stderr.decode(
                "utf-8",
                errors="replace"
            )
            if isinstance(result.stderr, bytes)
            else str(result.stderr)
        )

        if result.returncode != 0:

            log(
                "FFmpeg FAILED."
            )

            log(
                stderr[-5000:]
            )

            return False

        if not temp_output.exists():

            log(
                "FFmpeg returned success but "
                "temporary video does not exist."
            )

            return False

        temp_size = temp_output.stat().st_size

        log(
            f"Temporary video size: {temp_size} bytes"
        )

        if temp_size < 10_000:

            log(
                "Temporary video is too small."
            )

            return False

        # ----------------------------------------------------
        # Verify before making it visible as video.mp4
        # ----------------------------------------------------

        if not verify_video(temp_output):

            log(
                "Temporary video failed verification."
            )

            return False

        # ----------------------------------------------------
        # Atomic rename
        # ----------------------------------------------------

        temp_output.replace(
            output_path
        )

        if not output_path.exists():

            log(
                "Final video does not exist after rename."
            )

            return False

        final_size = output_path.stat().st_size

        log(
            f"FINAL VIDEO CREATED: {final_size} bytes"
        )

        if final_size < 10_000:

            log(
                "Final video is too small."
            )

            return False

        if not verify_video(output_path):

            log(
                "Final video failed verification."
            )

            try:
                output_path.unlink()
            except Exception:
                pass

            return False

        log(
            "VIDEO CREATION SUCCESS."
        )

        return True

    except subprocess.TimeoutExpired:

        log(
            "FFmpeg timed out after 300 seconds."
        )

        return False

    except Exception as e:

        log(
            f"FFmpeg exception: {e}"
        )

        return False

    finally:

        if temp_output.exists():

            try:
                temp_output.unlink()
            except Exception:
                pass


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
                "visual": f"Strong close-up of the {name}.",
                "voiceover": hook,
                "on_screen_text": hook
            },

            {
                "time": "3-6s",
                "visual": f"Show the {name} from different angles.",
                "voiceover": (
                    f"This is the {name}, "
                    f"and it solves {why}."
                ),
                "on_screen_text": name
            },

            {
                "time": "6-10s",
                "visual": "Show the product being used.",
                "voiceover": (
                    "The best part is how simple "
                    "it is to use."
                ),
                "on_screen_text": "Simple. Useful. Practical."
            },

            {
                "time": "10-13s",
                "visual": "Show the result after using the product.",
                "voiceover": (
                    f"And at around {price}, "
                    "it could be worth checking out."
                ),
                "on_screen_text": f"Example price: {price}"
            },

            {
                "time": "13-17s",
                "visual": "Clean final product shot.",
                "voiceover": (
                    f"Save this for later and follow "
                    f"{handle} for more useful finds."
                ),
                "on_screen_text": f"Follow {handle}"
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
        # PACKAGE
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
        # TEXT FILES
        # ====================================================

        script_lines = [
            f"REEL: {name}",
            "=" * 60,
            f"CATEGORY: {category}",
            f"EXAMPLE PRICE: {price}",
            "",
            "CONCEPT",
            f"Fast-paced product discovery Reel showing why "
            f"the {name} is useful and worth considering.",
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

        (package_dir / "script.txt").write_text(
            "\n".join(script_lines).strip(),
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
        # TTS
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
                "Voiceover created successfully."
            )

        else:

            log(
                "Voiceover failed. "
                "Continuing with silent video."
            )

            audio_path = None

        # ====================================================
        # VIDEO
        # ====================================================

        video_path = (
            package_dir /
            "video.mp4"
        )

        video_success = create_video(
            image_path=downloaded,
            audio_path=audio_path,
            output_path=video_path,
            scenes=scenes
        )

        # ====================================================
        # METADATA
        # ====================================================

        metadata = {
            "created_at": datetime.now().isoformat(),
            "handle": handle,
            "product": product,
            "reel": {
                "duration_seconds": 17,
                "format": "9:16",
                "resolution": "720x1280",
                "hook": hook,
                "voiceover": voiceover,
                "scenes": scenes
            },
            "caption": caption,
            "status": (
                "ready"
                if video_success
                else "video_failed"
            ),
            "video_verified": bool(
                video_success
            ),
            "publishing": {
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
Generated voiceover, if TTS succeeded.

video.mp4
Verified 9:16 Reel video.

IMPORTANT:

Price and availability must be checked before publishing.
"""

        (package_dir / "README.txt").write_text(
            readme,
            encoding="utf-8"
        )

        if video_success:

            log(
                f"REEL READY: {package_dir.name}"
            )

        else:

            log(
                f"REEL CREATED BUT VIDEO FAILED: "
                f"{package_dir.name}"
            )

        return package_dir

    finally:

        STATE["creating"] = False


# ============================================================
# AUTOPILOT
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

            # Do not start another generation
            # while one is already running.

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
                last_index % len(products)
            ]

            cfg["last_product_index"] = (
                last_index + 1
            ) % len(products)

            save(
                CFG,
                cfg
            )

            log(
                f"Starting Reel: "
                f"{product.get('name', 'Unknown')}"
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

                if (
                    video_file.exists()
                    and video_file.stat().st_size > 10_000
                    and verify_video(video_file)
                ):

                    STATE["last_video"] = (
                        package_dir.name
                        + "/video.mp4"
                    )

                    log(
                        "Verified video is ready."
                    )

                else:

                    STATE["last_video"] = None

                    log(
                        "No verified video was produced."
                    )

            except Exception as e:

                log(
                    f"Reel creation error: {e}"
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
                f"Next Reel in approximately "
                f"{interval // 3600} hour(s)."
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

    return HTMLResponse("""
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
    font-size:40px;
    margin:15px 0 25px;
}

.card {
    background:white;
    padding:24px;
    border-radius:25px;
    margin:18px 0;
    box-shadow:0 3px 20px rgba(0,0,0,.08);
}

.status {
    font-size:30px;
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

.error {
    background:#ffe5e5;
    color:#a00000;
    padding:12px;
    border-radius:12px;
    margin-top:12px;
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
Publish — reserved
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

<h2>System</h2>

<p id="system">
Checking...
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
            + (
                data.worker_running
                ? "Running"
                : "Stopped"
            )
            + "<br>"
            + "Creating: "
            + (
                data.creating
                ? "Yes"
                : "No"
            )
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
            data.voice ||
            "en-IN-NeerjaNeural";


        if (data.last_package) {

            let html =
                '<div class="package">'
                +
                '<span class="badge">PACKAGE</span>'
                +
                '<br><br>'
                +
                data.last_package;


            if (data.last_video) {

                const videoUrl =
                    "/api/video?path="
                    +
                    encodeURIComponent(
                        data.last_video
                    );

                html +=
                    '<video '
                    +
                    'class="video" '
                    +
                    'controls '
                    +
                    'playsinline '
                    +
                    'src="'
                    +
                    videoUrl
                    +
                    '"></video>';

                html +=
                    '<a '
                    +
                    'class="download" '
                    +
                    'href="'
                    +
                    videoUrl
                    +
                    '&download=1">'
                    +
                    '⬇ DOWNLOAD VERIFIED REEL'
                    +
                    '</a>';

            } else {

                html +=
                    '<div class="error">'
                    +
                    'Video generation failed. '
                    +
                    'Check activity.log.'
                    +
                    '</div>';
            }

            html += '</div>';

            document.getElementById("latest")
                .innerHTML =
                html;
        }


        try {

            const health =
                await fetch("/health");

            const h =
                await health.json();

            document.getElementById("system")
                .innerHTML =
                "FFmpeg: "
                +
                (
                    h.ffmpeg
                    ? "✅ Available"
                    : "❌ Missing"
                )
                +
                "<br>"
                +
                "ffprobe: "
                +
                (
                    h.ffprobe
                    ? "✅ Available"
                    : "❌ Missing"
                );

        } catch(e) {}

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
                posts_per_day:posts,
                mode:mode,
                voice:voice
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
""")


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
# VIDEO SERVING
# ============================================================

@app.get("/api/video")
def video(
    path: str,
    download: int = 0
):

    drafts_root = DRAFTS.resolve()

    requested = (
        DRAFTS /
        path
    ).resolve()

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
            status_code=422
        )

    if not verify_video(requested):

        return JSONResponse(
            {
                "error":
                    "Video failed verification"
            },
            status_code=422
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

            if not folder.is_dir():
                continue

            video_file = (
                folder /
                "video.mp4"
            )

            video_valid = False

            if video_file.exists():

                try:
                    video_valid = (
                        video_file.stat().st_size
                        > 10_000
                        and verify_video(video_file)
                    )
                except Exception:
                    video_valid = False

            packages.append({

                "name":
                    folder.name,

                "path":
                    str(folder),

                "video":
                    video_valid,

                "files":
                    [
                        file.name
                        for file in folder.iterdir()
                        if file.is_file()
                    ]
            })

    return {
        "count": len(packages),
        "packages": packages[:50]
    }


# ============================================================
# START / STOP
# ============================================================

@app.post("/api/run")
async def run(req: Request):

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
        "ok": True,
        "enabled": enabled
    }


# ============================================================
# CONFIG
# ============================================================

@app.post("/api/config")
async def config(req: Request):

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
async def add_product(req: Request):

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
        "ok": True,
        "product": product
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
        "count": len(products),
        "products": products
    }


# ============================================================
# HEALTH
# ============================================================

@app.get("/health")
def health():

    return {
        "ok": True,
        "service": "waititsonsale-autopilot",
        "version": "6.0-verified-video",
        "ffmpeg": ffmpeg_available(),
        "ffprobe": ffprobe_available(),
        "ffmpeg_version": get_ffmpeg_version(),
        "worker_running":
            STATE["worker_running"]
    }


# ============================================================
# START WORKER
# ============================================================

def start_worker():

    worker = threading.Thread(
        target=cycle,
        daemon=True,
        name="autopilot-worker"
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
