import os, json, threading, time, random
from datetime import datetime
from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

BASE=Path(__file__).parent
DATA=BASE/"data"; DATA.mkdir(exist_ok=True)
CFG=DATA/"config.json"; QUEUE=DATA/"products.json"; DRAFTS=DATA/"drafts"; DRAFTS.mkdir(exist_ok=True)
DEFAULT_CFG={
    "handle":"@waititsonsale",
    "posts_per_day":3,
    "enabled":False,
    "mode":"draft",
    "meta_access_token":"",
    "instagram_business_account_id":""
}
DEFAULT_PRODUCTS=[
 {"name":"Motion Sensor Night Light","price":"₹349","category":"Home","why":"an instant visual before/after with a clear everyday use case"},
 {"name":"Foldable Laptop Stand","price":"₹399","category":"Desk","why":"a simple productivity upgrade that is easy to demonstrate"},
 {"name":"Portable Mini Chopper","price":"₹499","category":"Kitchen","why":"strong visual demo potential and broad household appeal"},
 {"name":"Magnetic Cable Organizer","price":"₹199","category":"Tech","why":"solves a common desk problem at a low price"},
 {"name":"Mini Electric Cleaning Brush","price":"₹299","category":"Home","why":"satisfying cleaning demonstration potential"}
]
STATE={"created":0,"last_run":None,"message":"Ready"}

def load(path, default):
    if not path.exists(): path.write_text(json.dumps(default,indent=2,ensure_ascii=False))
    return json.loads(path.read_text(encoding="utf-8"))
def save(path, obj): path.write_text(json.dumps(obj,indent=2,ensure_ascii=False),encoding="utf-8")
def log(msg):
    STATE["message"]=msg
    with (DATA/"activity.log").open("a",encoding="utf-8") as f:
        f.write(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {msg}\n")

def create_draft(product):
    cfg=load(CFG,DEFAULT_CFG); handle=cfg["handle"]
    hook=random.choice([
        f"WAIT… why is this only {product['price']}? 👀",
        f"I found something actually useful for {product['price']}.",
        "This is the kind of thing you don't know you need… until you see it."
    ])
    text=f"""REEL: {product['name']}

0–3s HOOK
{hook}

3–8s SHOW
Show the product being used with 2–3 quick close-ups.

8–12s VALUE
"This {product['name'].lower()} {product['why']}."

12–15s CTA
"Save this for later and follow {handle} for more finds."

CAPTION
WAIT, IT'S ON SALE 👀

{product['name']}
Example price: {product['price']}

Why it caught our attention:
• {product['why']}
• Easy to understand quickly
• Good candidate for a visual product demo

Verify the current price, seller, reviews, warranty and return policy before buying.

Follow {handle} for more finds.

#waititsonsale #usefulproducts #budgetfinds #shoppingfinds #reelsindia

Disclosure: Product links may be affiliate links. Prices and availability can change.
"""
    fn=DRAFTS/f"{datetime.now():%Y%m%d_%H%M%S}_{product['name'].replace(' ','_')}.txt"
    fn.write_text(text,encoding="utf-8")
    return fn

def cycle():
    while True:
        cfg=load(CFG,DEFAULT_CFG)
        if cfg.get("enabled"):
            products=load(QUEUE,DEFAULT_PRODUCTS)
            if products:
                count=max(1,min(10,int(cfg.get("posts_per_day",3))))
                for p in random.sample(products,min(count,len(products))):
                    create_draft(p); STATE["created"]+=1
                STATE["last_run"]=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                log(f"Created {min(count,len(products))} Reel drafts.")
            # 24-hour schedule divided into posts_per_day slots
            sleep=max(60,int(86400/max(1,int(cfg.get("posts_per_day",3)))))
            for _ in range(sleep):
                time.sleep(1)
                if not load(CFG,DEFAULT_CFG).get("enabled"): break
        else:
            time.sleep(2)

app=FastAPI(title="WaitItsOnSale Cloud Autopilot")

@app.get("/",response_class=HTMLResponse)
def home():
    return HTMLResponse("""<!doctype html><meta name=viewport content="width=device-width,initial-scale=1">
<style>body{font-family:system-ui;max-width:720px;margin:auto;padding:22px;background:#f4f4f4}.c{background:#fff;padding:20px;border-radius:18px;margin:14px 0;box-shadow:0 2px 12px #0001}button{padding:14px 20px;border:0;border-radius:12px;font-weight:800}.start{background:#111;color:#fff}.stop{background:#ddd}input,select{width:100%;padding:11px;box-sizing:border-box;margin:6px 0 12px;border:1px solid #ddd;border-radius:10px}</style>
<h1>⚡ @waititsonsale</h1><div class=c><h2 id=s>Loading…</h2><p id=x></p><button class=start onclick="run(1)">▶ START</button> <button class=stop onclick="run(0)">■ STOP</button></div>
<div class=c><b>Settings</b><p>Reels per day</p><input id=p type=number min=1 max=10 value=3><p>Mode</p><select id=m><option value=draft>Draft mode</option><option value=publish>Publish mode</option></select><p>Instagram account ID</p><input id=i><p>Meta access token</p><input id=t type=password><button onclick="save()">Save</button></div>
<div class=c><b>Important</b><p>Draft mode is ready now. Publish mode is a connection point for Meta's official Instagram publishing API; it will not bypass permissions or use your Instagram password.</p></div>
<script>
async function r(){let a=await(await fetch('/api/status')).json();s.textContent=a.enabled?'🟢 RUNNING':'⚪ STOPPED';x.innerHTML='Drafts created: '+a.created+'<br>Last run: '+(a.last_run||'—')+'<br>'+a.message}
async function run(v){await fetch('/api/run',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({enabled:v})});r()}
async function save(){await fetch('/api/config',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({posts_per_day:+p.value,mode:m.value,instagram_business_account_id:i.value,meta_access_token:t.value})});alert('Saved');r()}
r();setInterval(r,2000)
</script>""")

@app.get("/api/status")
def status():
    c=load(CFG,DEFAULT_CFG)
    return JSONResponse({**STATE,"enabled":bool(c.get("enabled")),"handle":c["handle"]})

@app.post("/api/run")
async def run(req:Request):
    body=await req.json(); c=load(CFG,DEFAULT_CFG); c["enabled"]=bool(body.get("enabled")); save(CFG,c)
    log("START pressed." if c["enabled"] else "STOP pressed.")
    return {"ok":True}

@app.post("/api/config")
async def config(req:Request):
    body=await req.json(); c=load(CFG,DEFAULT_CFG)
    for k in ("posts_per_day","mode","instagram_business_account_id","meta_access_token"):
        if k in body: c[k]=body[k]
    save(CFG,c); log("Settings saved."); return {"ok":True}

@app.get("/health")
def health(): return {"ok":True}

if __name__=="__main__":
    import uvicorn
    load(CFG,DEFAULT_CFG); load(QUEUE,DEFAULT_PRODUCTS)
    threading.Thread(target=cycle,daemon=True).start()
    uvicorn.run(app,host="0.0.0.0",port=int(os.getenv("PORT","8080")))
