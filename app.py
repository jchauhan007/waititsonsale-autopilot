import os
import json
import threading
import time
import random
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse


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

    "meta_access_token": "",
    "instagram_business_account_id": ""
}


# ============================================================
# DEFAULT PRODUCTS
# ============================================================

DEFAULT_PRODUCTS = [
    {
        "name": "Motion Sensor Night Light",
        "price": "₹349",
        "category": "Home",
        "why": "an instant visual before-and-after with a clear everyday use case"
    },
    {
        "name": "Foldable Laptop Stand",
        "price": "₹399",
        "category": "Desk",
        "why": "a simple productivity upgrade that is easy to demonstrate"
    },
    {
        "name": "Portable Mini Chopper",
        "price": "₹499",
        "category": "Kitchen",
        "why": "strong visual demo potential and broad household appeal"
    },
    {
        "name": "Magnetic Cable Organizer",
        "price": "₹199",
        "category": "Tech",
        "why": "solves a common desk problem at a low price"
    },
    {
        "name": "Mini Electric Cleaning Brush",
        "price": "₹299",
        "category": "Home",
        "why": "satisfying cleaning demonstration potential"
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
    "last_package": None
}


# ============================================================
# FILE HELPERS
# ============================================================

def load(path, default):
    """
    Load JSON.
    Creates the file automatically if it does not exist.
    """

    if not path.exists():
        save(path, default)

    try:
        return json.loads(
            path.read_text(encoding="utf-8")
        )

    except Exception:
        return default


def save(path, obj):
    """
    Save JSON using UTF-8.
    """

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
    """
    Update dashboard state and write activity log.
    """

    STATE["message"] = message

    timestamp = datetime.now().strftime(
        "%Y-%m-%d %H:%M:%S"
    )

    with ACTIVITY_LOG.open(
        "a",
        encoding="utf-8"
    ) as f:

        f.write(
            f"[{timestamp}] {message}\n"
        )


# ============================================================
# TEXT HELPERS
# ============================================================

def clean_filename(value):
    """
    Convert product name into a safe folder/file name.
    """

    result = (
        value
        .replace(" ", "_")
        .replace("/", "_")
        .replace("\\", "_")
        .replace(":", "_")
        .replace("?", "")
        .replace("*", "")
        .replace('"', "")
        .replace("<", "")
        .replace(">", "")
        .replace("|", "")
    )

    return result[:80]


def random_hook(product):
    """
    Generate a hook from several templates.
    """

    hooks = [
        f"WAIT… why is this only {product['price']}? 👀",

        f"I found something actually useful "
        f"for {product['price']}.",

        "Okay, this might actually be worth buying 👀",

        "Why did nobody tell me about this before?",

        "This is one of those products you don't know "
        "you need until you see it.",

        "POV: you find something genuinely useful "
        "for under ₹500.",

        f"Would you buy this for {product['price']}?",

        "This little product solves a surprisingly "
        "annoying problem."
    ]

    return random.choice(hooks)


# ============================================================
# REEL PACKAGE GENERATOR
# ============================================================

def create_reel_package(product):
    """
    Creates a complete Reel content package.

    No external AI API is required for this stage.
    """

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
        "useful everyday product"
    )

    hook = random_hook(product)


    # --------------------------------------------------------
    # REEL CONCEPT
    # --------------------------------------------------------

    concept = (
        f"Fast-paced product discovery Reel showing "
        f"why the {name} is useful and worth considering."
    )


    # --------------------------------------------------------
    # SCENES
    # --------------------------------------------------------

    scenes = [

        {
            "time": "0-3s",
            "visual": (
                f"Start with a close-up of the {name}. "
                "Use a quick movement or reveal."
            ),
            "voiceover": hook,
            "on_screen_text": hook
        },

        {
            "time": "3-6s",
            "visual": (
                f"Show the {name} clearly from 2-3 angles. "
                "Keep the shots quick."
            ),
            "voiceover": (
                f"This is the {name}, and it solves "
                f"{why}."
            ),
            "on_screen_text": name
        },

        {
            "time": "6-10s",
            "visual": (
                f"Demonstrate the {name} being used. "
                "Focus on the most satisfying or useful action."
            ),
            "voiceover": (
                f"The best part is how simple it is to use."
            ),
            "on_screen_text": "Simple. Useful. Practical."
        },

        {
            "time": "10-13s",
            "visual": (
                "Show the result after using the product. "
                "Use a clean close-up."
            ),
            "voiceover": (
                f"And at around {price}, "
                "it could be worth checking out."
            ),
            "on_screen_text": f"Example price: {price}"
        },

        {
            "time": "13-17s",
            "visual": (
                "End with a clean product shot and "
                "your account handle."
            ),
            "voiceover": (
                f"Save this for later and follow "
                f"{handle} for more useful finds."
            ),
            "on_screen_text": (
                f"Follow {handle}"
            )
        }
    ]


    # --------------------------------------------------------
    # VOICEOVER
    # --------------------------------------------------------

    voiceover = "\n".join(
        [
            scene["voiceover"]
            for scene in scenes
        ]
    )


    # --------------------------------------------------------
    # CAPTION
    # --------------------------------------------------------

    caption = f"""WAIT, IT'S ON SALE 👀

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

Save this for later 🔖

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


    # --------------------------------------------------------
    # FULL SCRIPT
    # --------------------------------------------------------

    script_lines = []

    script_lines.append(
        f"REEL: {name}"
    )

    script_lines.append(
        "=" * 60
    )

    script_lines.append(
        f"CATEGORY: {category}"
    )

    script_lines.append(
        f"EXAMPLE PRICE: {price}"
    )

    script_lines.append("")

    script_lines.append(
        "CONCEPT"
    )

    script_lines.append(
        concept
    )

    script_lines.append("")

    script_lines.append(
        "SCENE PLAN"
    )

    script_lines.append(
        "-" * 60
    )

    for scene in scenes:

        script_lines.append(
            f"\n{scene['time']} — VISUAL"
        )

        script_lines.append(
            scene["visual"]
        )

        script_lines.append(
            "\nVOICEOVER:"
        )

        script_lines.append(
            scene["voiceover"]
        )

        script_lines.append(
            "\nON-SCREEN TEXT:"
        )

        script_lines.append(
            scene["on_screen_text"]
        )

    script_lines.append("")

    script_lines.append(
        "FULL VOICEOVER"
    )

    script_lines.append(
        "-" * 60
    )

    script_lines.append(
        voiceover
    )

    script_lines.append("")

    script_lines.append(
        "CAPTION"
    )

    script_lines.append(
        "-" * 60
    )

    script_lines.append(
        caption
    )


    script_text = "\n".join(
        script_lines
    )


    # --------------------------------------------------------
    # METADATA
    # --------------------------------------------------------

    metadata = {

        "created_at":
            datetime.now().isoformat(),

        "handle":
            handle,

        "product": {
            "name": name,
            "price": price,
            "category": category,
            "why": why
        },

        "reel": {
            "duration_seconds": 17,
            "format": "9:16",
            "concept": concept,
            "hook": hook,
            "voiceover": voiceover,
            "scenes": scenes
        },

        "caption": caption,

        "status": "draft",

        "publishing": {
            "instagram": False,
            "published": False
        }
    }


    # --------------------------------------------------------
    # CREATE PACKAGE FOLDER
    # --------------------------------------------------------

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


    # --------------------------------------------------------
    # WRITE SCRIPT
    # --------------------------------------------------------

    (package_dir / "script.txt").write_text(
        script_text.strip(),
        encoding="utf-8"
    )


    # --------------------------------------------------------
    # WRITE CAPTION
    # --------------------------------------------------------

    (package_dir / "caption.txt").write_text(
        caption.strip(),
        encoding="utf-8"
    )


    # --------------------------------------------------------
    # WRITE VOICEOVER
    # --------------------------------------------------------

    (package_dir / "voiceover.txt").write_text(
        voiceover.strip(),
        encoding="utf-8"
    )


    # --------------------------------------------------------
    # WRITE REEL PLAN
    # --------------------------------------------------------

    save(
        package_dir / "reel_plan.json",
        {
            "product": product,
            "duration_seconds": 17,
            "format": "9:16",
            "scenes": scenes
        }
    )


    # --------------------------------------------------------
    # WRITE METADATA
    # --------------------------------------------------------

    save(
        package_dir / "metadata.json",
        metadata
    )


    # --------------------------------------------------------
    # CREATE README
    # --------------------------------------------------------

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
Scene-by-scene Reel production plan.

metadata.json
Machine-readable Reel information.

NEXT STEP:

Generate the actual 9:16 video using the
scene plan and voiceover.

IMPORTANT:

Price and availability must be checked before publishing.
"""

    (package_dir / "README.txt").write_text(
        readme,
        encoding="utf-8"
    )


    return package_dir


# ============================================================
# AUTOPILOT WORKER
# ============================================================

def cycle():

    log(
        "Autopilot worker started."
    )

    while True:

        try:

            cfg = load(
                CFG,
                DEFAULT_CFG
            )

            enabled = bool(
                cfg.get(
                    "enabled",
                    False
                )
            )


            if not enabled:

                time.sleep(2)

                continue


            # ------------------------------------------------
            # LOAD PRODUCTS
            # ------------------------------------------------

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


            # ------------------------------------------------
            # POSTS PER DAY
            # ------------------------------------------------

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
            # SELECT PRODUCTS
            # ------------------------------------------------

            number_to_create = min(
                posts_per_day,
                len(products)
            )


            selected_products = random.sample(
                products,
                number_to_create
            )


            created_now = 0


            # ------------------------------------------------
            # CREATE REEL PACKAGES
            # ------------------------------------------------

            for product in selected_products:

                try:

                    package_dir = create_reel_package(
                        product
                    )

                    created_now += 1

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

                    log(
                        "Reel package created: "
                        f"{package_dir.name}"
                    )


                except Exception as e:

                    log(
                        "Reel package creation error: "
                        f"{e}"
                    )


            # ------------------------------------------------
            # UPDATE STATE
            # ------------------------------------------------

            STATE["last_run"] = (
                datetime.now().strftime(
                    "%Y-%m-%d %H:%M:%S"
                )
            )


            log(
                f"Created {created_now} "
                "Reel package(s)."
            )


            # ------------------------------------------------
            # DAILY INTERVAL
            # ------------------------------------------------

            interval = int(
                86400 /
                max(
                    1,
                    posts_per_day
                )
            )


            # ------------------------------------------------
            # WAIT
            # ------------------------------------------------

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
                f"{e}"
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

<title>@waititsonsale</title>

<style>

* {
    box-sizing: border-box;
}

body {
    font-family: system-ui, sans-serif;
    max-width: 720px;
    margin: auto;
    padding: 22px;
    background: #f4f4f4;
    color: #111;
}

h1 {
    font-size: 42px;
    margin-bottom: 25px;
}

.card {
    background: white;
    padding: 24px;
    border-radius: 22px;
    margin: 16px 0;
    box-shadow: 0 2px 15px rgba(0,0,0,.08);
}

.status {
    font-size: 30px;
    font-weight: 800;
}

button {
    padding: 14px 22px;
    border: 0;
    border-radius: 13px;
    font-size: 16px;
    font-weight: 800;
    cursor: pointer;
    margin-right: 6px;
}

.start {
    background: #111;
    color: white;
}

.stop {
    background: #ddd;
    color: #111;
}

.save {
    background: #111;
    color: white;
    width: 100%;
    margin-top: 10px;
}

input,
select {
    width: 100%;
    padding: 14px;
    margin: 7px 0 18px;
    border: 1px solid #ddd;
    border-radius: 12px;
    font-size: 16px;
}

.label {
    font-weight: 700;
}

.small {
    color: #666;
    font-size: 14px;
}

.package {
    background: #f7f7f7;
    padding: 15px;
    border-radius: 12px;
    margin-top: 12px;
    word-break: break-word;
}

.badge {
    display: inline-block;
    padding: 5px 10px;
    border-radius: 20px;
    background: #eee;
    font-size: 13px;
    font-weight: 700;
}

</style>

</head>


<body>

<h1>⚡ @waititsonsale</h1>


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
            Draft mode
        </option>

        <option value="publish">
            Publish mode
        </option>

    </select>


    <div class="label">
        Instagram Business Account ID
    </div>

    <input
        id="i"
        placeholder="Optional">


    <div class="label">
        Meta Access Token
    </div>

    <input
        id="t"
        type="password"
        placeholder="Optional">


    <button
        class="save"
        onclick="saveSettings()">

        Save Settings

    </button>

</div>


<div class="card">

    <h2>Latest Reel</h2>

    <div id="latest">
        No Reel package created yet.
    </div>

</div>


<div class="card">

    <h2>How it works</h2>

    <p>
        <b>Draft mode</b> automatically creates
        complete Reel content packages from your
        product queue.
    </p>

    <p>
        Every package contains the script,
        caption, voiceover, scene plan and metadata.
    </p>

    <p>
        <b>Next stage:</b> connect a video-generation
        service to turn these production plans into
        actual 9:16 Reel videos.
    </p>

    <p class="small">
        Instagram publishing will use the official
        Meta/Instagram API. The system will not use
        your Instagram password.
    </p>

</div>


<script>


async function getStatus() {

    try {

        const response =
            await fetch("/api/status");

        const data =
            await response.json();


        if (data.enabled) {

            document.getElementById("s")
                .textContent =
                "🟢 RUNNING";

        } else {

            document.getElementById("s")
                .textContent =
                "⚪ STOPPED";
        }


        document.getElementById("x")
            .innerHTML =
            "Packages created: "
            + data.created
            + "<br>"
            + "Last run: "
            + (data.last_run || "—")
            + "<br>"
            + "Last product: "
            + (data.last_product || "—")
            + "<br>"
            + data.message;


        if (data.last_package) {

            document.getElementById("latest")
                .innerHTML =
                '<div class="package">'
                + '<span class="badge">READY</span>'
                + '<br><br>'
                + data.last_package
                + '</div>';

        }


        document.getElementById("p")
            .value =
            data.posts_per_day || 3;


        document.getElementById("m")
            .value =
            data.mode || "draft";

    }

    catch (error) {

        document.getElementById("s")
            .textContent =
            "🔴 ERROR";

    }

}


async function run(value) {

    await fetch(
        "/api/run",
        {
            method: "POST",

            headers: {
                "Content-Type":
                    "application/json"
            },

            body: JSON.stringify({
                enabled: value
            })
        }
    );

    getStatus();

}


async function saveSettings() {

    const posts =
        Number(
            document.getElementById("p").value
        );


    const mode =
        document.getElementById("m").value;


    const account =
        document.getElementById("i").value;


    const token =
        document.getElementById("t").value;


    await fetch(
        "/api/config",
        {
            method: "POST",

            headers: {
                "Content-Type":
                    "application/json"
            },

            body: JSON.stringify({

                posts_per_day: posts,

                mode: mode,

                instagram_business_account_id:
                    account,

                meta_access_token:
                    token

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

    return JSONResponse(
        {
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

            "posts_per_day":
                cfg.get(
                    "posts_per_day",
                    3
                )
        }
    )


# ============================================================
# LIST DRAFT PACKAGES
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

                packages.append(
                    {
                        "name": folder.name,
                        "path": str(folder),
                        "files": [
                            file.name
                            for file in folder.iterdir()
                            if file.is_file()
                        ]
                    }
                )


    return {
        "count": len(packages),
        "packages": packages[:50]
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
            "START pressed."
        )

    else:

        log(
            "STOP pressed."
        )


    return {
        "ok": True,
        "enabled": enabled
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


    allowed_keys = [

        "posts_per_day",

        "mode",

        "instagram_business_account_id",

        "meta_access_token"

    ]


    for key in allowed_keys:

        if key in body:

            cfg[key] = body[key]


    # --------------------------------------------------------
    # Validate posts per day
    # --------------------------------------------------------

    try:

        posts = int(
            cfg.get(
                "posts_per_day",
                3
            )
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


    # --------------------------------------------------------
    # Validate mode
    # --------------------------------------------------------

    if cfg.get("mode") not in [
        "draft",
        "publish"
    ]:

        cfg["mode"] = "draft"


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
# HEALTH CHECK
# ============================================================

@app.get("/health")
def health():

    return {
        "ok": True,
        "service":
            "waititsonsale-autopilot",
        "version":
            "2.0"
    }


# ============================================================
# STARTUP
# ============================================================

def start_worker():

    worker = threading.Thread(
        target=cycle,
        daemon=True
    )

    worker.start()

    return worker


# Initialize required files.

load(
    CFG,
    DEFAULT_CFG
)

load(
    QUEUE,
    DEFAULT_PRODUCTS
)


# Start worker when the application is loaded.

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
