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

    # Meta / Instagram API
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
        "why": "an instant visual before/after with a clear everyday use case"
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
    "message": "Ready"
}


# ============================================================
# FILE HELPERS
# ============================================================

def load(path, default):
    """
    Load JSON file.
    If it doesn't exist, create it using the supplied default.
    """

    if not path.exists():
        path.write_text(
            json.dumps(
                default,
                indent=2,
                ensure_ascii=False
            ),
            encoding="utf-8"
        )

    try:
        return json.loads(
            path.read_text(encoding="utf-8")
        )

    except Exception:
        return default


def save(path, obj):
    """
    Save JSON safely.
    """

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
    Update dashboard state and write to activity.log.
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
# DRAFT GENERATOR
# ============================================================

def create_draft(product):
    """
    Generate a Reel script + caption.
    """

    cfg = load(
        CFG,
        DEFAULT_CFG
    )

    handle = cfg.get(
        "handle",
        "@waititsonsale"
    )

    hook = random.choice(
        [
            f"WAIT… why is this only {product['price']}? 👀",

            f"I found something actually useful "
            f"for {product['price']}.",

            "This is the kind of thing you don't know "
            "you need… until you see it.",

            "Okay, this might actually be worth buying 👀",

            "Why did nobody tell me about this before?"
        ]
    )

    text = f"""
REEL: {product['name']}

CATEGORY
{product['category']}


0–3s — HOOK

{hook}


3–8s — SHOW

Show the product being used.

Use 2–3 quick close-ups.

Focus on the most visually satisfying part.


8–12s — VALUE

"This {product['name'].lower()} "
f"{product['why']}."


12–15s — CTA

"Save this for later and follow "
f"{handle} for more finds."


CAPTION

WAIT, IT'S ON SALE 👀

{product['name']}

Example price: {product['price']}


Why it caught our attention:

• {product['why']}
• Easy to understand quickly
• Good candidate for a visual product demo


Before buying:

Verify the current price, seller,
reviews, warranty and return policy.


Follow {handle} for more useful finds.


#waititsonsale
#usefulproducts
#budgetfinds
#shoppingfinds
#reelsindia
#amazonfinds
#homefinds


Disclosure:

Product links may be affiliate links.
Prices and availability can change.
"""


    safe_name = (
        product["name"]
        .replace(" ", "_")
        .replace("/", "_")
        .replace("\\", "_")
    )

    filename = (
        f"{datetime.now():%Y%m%d_%H%M%S}"
        f"_{safe_name}.txt"
    )

    filepath = DRAFTS / filename

    filepath.write_text(
        text.strip(),
        encoding="utf-8"
    )

    return filepath


# ============================================================
# DAILY AUTOPILOT
# ============================================================

def cycle():
    """
    Background scheduler.

    When enabled:
    - Loads products
    - Creates the configured number of drafts
    - Waits approximately 24 hours / posts_per_day
    - Repeats
    """

    log("Autopilot worker started.")

    while True:

        try:
            cfg = load(
                CFG,
                DEFAULT_CFG
            )

            enabled = bool(
                cfg.get("enabled", False)
            )

            if not enabled:
                time.sleep(2)
                continue


            # ------------------------------------------------
            # Load products
            # ------------------------------------------------

            products = load(
                QUEUE,
                DEFAULT_PRODUCTS
            )

            if not products:
                log("No products available.")
                time.sleep(10)
                continue


            # ------------------------------------------------
            # Number of posts
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
            # Select products
            # ------------------------------------------------

            number_to_create = min(
                posts_per_day,
                len(products)
            )

            selected_products = random.sample(
                products,
                number_to_create
            )


            # ------------------------------------------------
            # Create drafts
            # ------------------------------------------------

            created_now = 0

            for product in selected_products:

                try:

                    filepath = create_draft(
                        product
                    )

                    created_now += 1

                    STATE["created"] += 1

                    log(
                        f"Draft created: "
                        f"{filepath.name}"
                    )

                except Exception as e:

                    log(
                        f"Draft creation error: {e}"
                    )


            # ------------------------------------------------
            # Update state
            # ------------------------------------------------

            STATE["last_run"] = (
                datetime.now().strftime(
                    "%Y-%m-%d %H:%M:%S"
                )
            )

            log(
                f"Created {created_now} "
                f"Reel draft(s)."
            )


            # ------------------------------------------------
            # Calculate interval
            # ------------------------------------------------

            interval = int(
                86400 /
                max(
                    1,
                    posts_per_day
                )
            )

            # Check every second so STOP works quickly.

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
# FASTAPI APP
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

    <h2>How it works</h2>

    <p>
        <b>Draft mode</b> creates Reel scripts
        automatically using the products in your
        product queue.
    </p>

    <p>
        <b>Publish mode</b> is reserved for the
        official Meta/Instagram publishing API.
    </p>

    <p class="small">
        The system will never use your Instagram
        password or attempt to bypass Instagram
        permissions.
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
            "Drafts created: "
            + data.created
            + "<br>"
            + "Last run: "
            + (data.last_run || "—")
            + "<br>"
            + data.message;

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


    alert("Settings saved.");

    getStatus();

}


getStatus();

setInterval(
    getStatus,
    2000
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
                )
        }
    )


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

        log("START pressed.")

    else:

        log("STOP pressed.")


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


    # Validate posts per day

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


    # Validate mode

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
        "service": "waititsonsale-autopilot"


# ============================================================
# STARTUP
# ============================================================

@app.on_event("startup")
def startup():

    # Make sure files exist
    load(
        CFG,
        DEFAULT_CFG
    )

    load(
        QUEUE,
        DEFAULT_PRODUCTS
    )

    # Start background autopilot worker
    worker = threading.Thread(
        target=cycle,
        daemon=True
    )

    worker.start()

    log("Autopilot worker started.")


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
