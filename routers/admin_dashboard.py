"""
BoBA Marketplace — Admin Dashboard Router
==========================================
Drop this into the boba-api project and wire it up in main.py:

    from admin_dashboard import router as admin_router
    app.include_router(admin_router, prefix="/api/admin", tags=["admin"])

Then set ADMIN_KEY in your Render environment variables.
"""

import os, json
from datetime import datetime, timezone
from typing import Optional

from fastapi import FastAPI, HTTPException, Header, Query
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel

# ── Auth ────────────────────────────────────────────────────────────────────────
ADMIN_KEY = os.getenv("ADMIN_KEY", "changeme")

def require_admin(key: Optional[str] = Header(None, alias="x-admin-key")) -> str:
    if not key or key != ADMIN_KEY:
        raise HTTPException(status_code=401, detail="Invalid or missing x-admin-key header")
    return key

# ── Helpers ────────────────────────────────────────────────────────────────────
import urllib.request

API_BASE = os.getenv("API_BASE", "https://boba-api.onrender.com")
DEBUG_URL = os.getenv("DEBUG_DB_URL", "https://boba-api.onrender.com/debug/db")

def api_get(path: str, params: str = ""):
    url = f"{API_BASE}{path}" + (f"?{params}" if params else "")
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read())

def admin_api_get(path: str, params: str = ""):
    """Fetch from a local/internal endpoint that may not need auth."""
    url = f"{API_BASE}{path}" + (f"?{params}" if params else "")
    req = urllib.request.Request(url, headers={"x-admin-key": ADMIN_KEY})
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read())

# ── Pydantic models ─────────────────────────────────────────────────────────────
class DashboardStats(BaseModel):
    total_users: int
    total_listings: int
    active_listings: int
    total_orders: int
    completed_orders: int
    total_cards: int
    est_gmv_cents: int
    db_status: str

class UserRow(BaseModel):
    id: str
    username: str
    display_name: Optional[str]
    email: Optional[str]
    created_at: str
    total_sales: int
    rating: float
    tier: Optional[str] = None

# ── HTML Dashboard ─────────────────────────────────────────────────────────────
def get_dashboard_html(stats: dict, users: list, listings: list, orders: list) -> str:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    # Format numbers
    def fmt_cents(c): return f"${c/100:,.2f}" if c else "$0.00"
    def fmt_date(d):
        if not d: return "—"
        return d[:10] if "T" in str(d) else str(d)[:10]

    users_html = ""
    for u in users:
        age_days = None
        if u.get("created_at"):
            try:
                created = datetime.fromisoformat(u["created_at"].replace("Z","+00:00"))
                age_days = (datetime.now(timezone.utc) - created).days
            except Exception:
                pass
        badge = "🆕 NEW" if age_days is not None and age_days <= 7 else "✅ active"
        rating = f"⭐ {u['rating']:.1f}" if u.get("rating") else "—no ratings"
        email = u.get("email") or '<span style="color:#6b7280">—</span>'
        users_html += f"""
        <tr>
          <td><b>{u.get('display_name') or u['username']}</b><br><span style="color:#6b7280;font-size:12px">@{u['username']}</span></td>
          <td style="color:#6b7280;font-size:12px">{email}</td>
          <td>{fmt_date(u.get('created_at'))}</td>
          <td class="{'zero' if u.get('total_sales',0)==0 else 'val'}">{u.get('total_sales',0)}</td>
          <td>{rating}</td>
          <td><span class="badge">{badge}</span></td>
        </tr>"""

    listings_html = ""
    for l in (listings or [])[:50]:
        price = fmt_cents(l.get("price_cents"))
        badge_style = "active" if l.get("status")=="active" else "inactive"
        listings_html += f"""
        <tr>
          <td><b>{l.get('title') or l.get('card',{}).get('name','—')}</b><br><span style="color:#6b7280;font-size:12px">{l.get('card',{}).get('card_number','')}</span></td>
          <td>@{l.get('seller',{}).get('username','')}</td>
          <td class="price">{price}</td>
          <td>{l.get('condition','—')}</td>
          <td><span class="badge {badge_style}">{l.get('status','—')}</span></td>
          <td>{fmt_date(l.get('created_at'))}</td>
          <td>{l.get('views',0)}</td>
        </tr>"""

    orders_html = ""
    for o in (orders or [])[:50]:
        total = fmt_cents(o.get("total_cents") or o.get("subtotal_cents"))
        status = o.get("status","—")
        orders_html += f"""
        <tr>
          <td class="mono">{str(o.get('id',''))[:12]}</td>
          <td>@{o.get('buyer',{}).get('username', o.get('buyer_username','—'))}</td>
          <td>@{o.get('seller_username', o.get('seller_id','')[:8] if not o.get('seller_username') else '—')}</td>
          <td class="price">{total}</td>
          <td><span class="badge {status}">{status}</span></td>
          <td>{fmt_date(o.get('created_at'))}</td>
        </tr>"""

    gmv = fmt_cents(stats.get("est_gmv_cents", 0))
    return f"""
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>BoBA Marketplace — Admin</title>
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:#0d1117;color:#e6edf3;min-height:100vh}}
.navbar{{background:#161b22;border-bottom:1px solid #30363d;padding:14px 24px;display:flex;align-items:center;justify-content:space-between}}
.brand{{font-size:18px;font-weight:700;color:#f0a020}}
.meta{{font-size:12px;color:#484f58}}
.container{{max-width:1400px;margin:0 auto;padding:24px}}
.kpi-grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:14px;margin-bottom:28px}}
.kpi{{background:#161b22;border:1px solid #30363d;border-radius:10px;padding:18px 22px}}
.kpi .lbl{{font-size:11px;color:#484f58;text-transform:uppercase;letter-spacing:.6px;margin-bottom:6px}}
.kpi .val{{font-size:28px;font-weight:800;color:#f0a020}}
.kpi .sub{{font-size:11px;color:#484f58;margin-top:3px}}
.tab-nav{{display:flex;gap:4px;margin-bottom:18px}}
.tab{{padding:7px 16px;border-radius:7px;font-size:13px;cursor:pointer;color:#484f58;border:1px solid transparent;background:transparent}}
.tab:hover{{color:#e6edf3;background:#161b22}}
.tab.active{{background:#f0a020;color:#0d1117;font-weight:700}}
.tab-content{{display:none}}
.tab-content.active{{display:block}}
.section{{background:#161b22;border:1px solid #30363d;border-radius:10px;margin-bottom:22px;overflow:hidden}}
.sh{{padding:14px 18px;border-bottom:1px solid #30363d;font-size:13px;font-weight:600;display:flex;justify-content:space-between;align-items:center}}
.sh .count{{font-size:11px;color:#484f58;font-weight:400}}
table{{width:100%;border-collapse:collapse}}
th{{text-align:left;padding:9px 14px;font-size:10px;color:#484f58;text-transform:uppercase;letter-spacing:.5px;border-bottom:1px solid #21262d}}
td{{padding:10px 14px;font-size:13px;border-bottom:1px solid #21262d}}
tr:last-child td{{border-bottom:none}}
tr:hover td{{background:#1c2128}}
.badge{{display:inline-block;padding:2px 8px;border-radius:999px;font-size:10px;font-weight:700;background:#21262d;color:#7d8590}}
.badge.active,.badge.completed,.badge.PROCESSING{{background:#0f3320;color:#3fb950}}
.badge.pending,.badge.AWAITING_PAYMENT{{background:#1c2d40;color:#58a6ff}}
.badge.SHIPPED{{background:#2a1f4e;color:#a371f7}}
.badge.inactive,.badge.CANCELLED,.badge.refunded{{background:#3b1010;color:#f85149}}
.badge.fulfilled{{background:#0f3320;color:#3fb950}}
.zero{{color:#f85149}}
.mono{{font-family:'SF Mono','Fira Code',monospace;font-size:12px;color:#484f58}}
.price{{color:#3fb950;font-weight:600}}
.loading{{text-align:center;padding:60px;color:#484f58}}
.spinner{{display:inline-block;width:28px;height:28px;border:3px solid #21262d;border-top-color:#f0a020;border-radius:50%;animation:spin .7s linear infinite;margin-bottom:10px}}
@keyframes spin{{to{{transform:rotate(360deg)}}}}
.refresh{{padding:6px 14px;border-radius:6px;font-size:12px;cursor:pointer;background:#21262d;color:#7d8590;border:1px solid #30363d}}
.refresh:hover{{background:#30363d;color:#e6edf3}}
.error{{background:#3b1010;border:1px solid #f85149;border-radius:8px;padding:20px;color:#f85149}}
.mt{{margin-top:16px}}
</style>
</head>
<body>
<div class="navbar">
  <div class="brand">🥕 BoBA Admin Dashboard</div>
  <div style="display:flex;align-items:center;gap:12px">
    <span class="meta" id="ts">Updated {now}</span>
    <button class="refresh" onclick="load()">↻ Refresh</button>
  </div>
</div>
<div class="container">

<!-- KPI row -->
<div class="kpi-grid">
  <div class="kpi"><div class="lbl">Total Users</div><div class="val">{stats.get('total_users',0)}</div><div class="sub">registered</div></div>
  <div class="kpi"><div class="lbl">Active Listings</div><div class="val">{stats.get('active_listings',0)}</div><div class="sub">of {stats.get('total_listings',0)} total</div></div>
  <div class="kpi"><div class="lbl">Total Sales</div><div class="val">{stats.get('total_orders',0)}</div><div class="sub">{stats.get('completed_orders',0)} completed</div></div>
  <div class="kpi"><div class="lbl">Est. GMV</div><div class="val">{gmv}</div><div class="sub">platform volume</div></div>
  <div class="kpi"><div class="lbl">Card Catalog</div><div class="val">{stats.get('total_cards',0):,}</div><div class="sub">in database</div></div>
  <div class="kpi"><div class="lbl">DB Status</div><div class="val" style="font-size:20px">{stats.get('db_status','—')}</div></div>
</div>

<!-- Tabs -->
<div class="tab-nav">
  <button class="tab active" onclick="showTab('users')">Users ({len(users)})</button>
  <button class="tab" onclick="showTab('listings')">Listings ({len(listings)})</button>
  <button class="tab" onclick="showTab('orders')">Orders ({len(orders)})</button>
  <button class="tab" onclick="showTab('api')">API Explorer</button>
</div>

<!-- Users -->
<div class="tab-content active" id="tab-users">
  <div class="section">
    <div class="sh">All Users <span class="count">{len(users)} total</span></div>
    <table><thead><tr><th>User</th><th>Email</th><th>Joined</th><th>Sales</th><th>Rating</th><th>Status</th></tr></thead>
    <tbody>{users_html}</tbody></table>
  </div>
</div>

<!-- Listings -->
<div class="tab-content" id="tab-listings">
  <div class="section">
    <div class="sh">Listings <span class="count">{len(listings)} shown (latest 50)</span></div>
    <table><thead><tr><th>Card</th><th>Seller</th><th>Price</th><th>Cond.</th><th>Status</th><th>Listed</th><th>Views</th></tr></thead>
    <tbody>{listings_html}</tbody></table>
  </div>
</div>

<!-- Orders -->
<div class="tab-content" id="tab-orders">
  <div class="section">
    <div class="sh">Orders <span class="count">{len(orders)} shown (latest 50)</span></div>
    <table><thead><tr><th>Order ID</th><th>Buyer</th><th>Seller</th><th>Total</th><th>Status</th><th>Date</th></tr></thead>
    <tbody>{orders_html}</tbody></table>
  </div>
</div>

<!-- API Explorer -->
<div class="tab-content" id="tab-api">
  <div class="section" style="padding:20px">
    <div class="sh" style="border:none;padding:0;margin-bottom:16px">API Explorer</div>
    <p style="color:#484f58;font-size:13px;margin-bottom:14px">Test any BoBA API endpoint with your admin key. Results shown as formatted JSON.</p>
    <div style="display:flex;gap:10px;margin-bottom:14px">
      <input id="api-path" value="/api/listings?limit=5" style="flex:1;background:#0d1117;border:1px solid #30363d;border-radius:7px;color:#e6edf3;padding:8px 12px;font-family:monospace;font-size:13px" />
      <button onclick="testApi()" style="padding:8px 18px;background:#f0a020;border:none;border-radius:7px;color:#0d1117;font-weight:700;cursor:pointer">Test</button>
    </div>
    <pre id="api-result" style="background:#0d1117;border:1px solid #21262d;border-radius:8px;padding:16px;font-size:12px;max-height:400px;overflow:auto;color:#7ee787;white-space:pre-wrap">{json.dumps({"listings": [{"id":"...","title":"...","price_cents":123,"status":"active","seller":{"username":"..."},"card":{"name":"...","card_number":"..."}}]}, indent=2)}</pre>
  </div>
</div>

</div>
<script>
function showTab(n){
  document.querySelectorAll('.tab').forEach(t=>t.classList.remove('active'));
  document.querySelectorAll('.tab-content').forEach(t=>t.classList.remove('active'));
  document.querySelector('.tab[onclick="showTab(\\''+n+'\\')"]').classList.add('active');
  document.getElementById('tab-'+n).classList.add('active');
}
async function testApi(){
  const path=document.getElementById('api-path').value;
  const ADMIN_KEY=localStorage.getItem('boba_admin_key')||prompt('Enter admin key:');
  localStorage.setItem('boba_admin_key',ADMIN_KEY);
  try{
    const r=await fetch('/api/admin/proxy'+encodeURIComponent(path),{headers:{'x-admin-key':ADMIN_KEY}});
    const d=await r.json();
    document.getElementById('api-result').textContent=JSON.stringify(d,null,2);
  }catch(e){document.getElementById('api-result').textContent='Error: '+e;}
}
</script>
</body>
</html>"""

# ── FastAPI Router ───────────────────────────────────────────────────────────────
from fastapi import APIRouter
router = APIRouter()

# ── GET /api/admin/dashboard ───────────────────────────────────────────────────
@router.get("/dashboard", response_class=HTMLResponse)
async def admin_dashboard(x_admin_key: Optional[str] = Header(None, alias="x-admin-key")):
    """
    Serve the full admin dashboard HTML.
    Loads all data server-side and renders it (no client-side fetch needed).
    """
    require_admin(x_admin_key)

    try:
        # 1. DB stats from debug endpoint
        db_data = api_get("/debug/db")

        # 2. Listings
        listings_data = api_get("/api/listings", "limit=100&offset=0")
        listings = listings_data.get("listings", []) if isinstance(listings_data, dict) else (listings_data or [])

        # 3. Orders
        try:
            orders_data = api_get("/api/orders", "limit=100")
            orders = orders_data.get("orders", []) if isinstance(orders_data, dict) else (orders_data or [])
        except Exception:
            orders = []

        # 4. Cards count
        try:
            cards_data = api_get("/api/cards", "limit=1")
            total_cards = cards_data.get("total", 0) if isinstance(cards_data, dict) else 0
        except Exception:
            total_cards = db_data.get("card_count", 0)

        # Build stats
        users = db_data.get("users", [])
        active_listings = [l for l in listings if l.get("status") == "active"]
        completed_orders = [o for o in orders if o.get("status") in ("completed", "fulfilled", "shipped")]

        est_gmv = sum(
            (o.get("total_cents") or o.get("subtotal_cents") or 0) for o in orders
        ) or sum(
            l.get("price_cents", 0) for l in active_listings
        )

        stats = {
            "total_users": db_data.get("user_count", len(users)),
            "active_listings": len(active_listings),
            "total_listings": len(listings),
            "total_orders": len(orders),
            "completed_orders": len(completed_orders),
            "total_cards": db_data.get("card_count", total_cards),
            "est_gmv_cents": est_gmv,
            "db_status": "✅ healthy" if db_data.get("tcp") == "connected" else "❌ down",
        }

        html = get_dashboard_html(stats, users, listings, orders)
        return HTMLResponse(content=html)

    except HTTPException:
        raise
    except Exception as e:
        return HTMLResponse(
            content=f"<pre class='error'>Dashboard error: {e}</pre>",
            status_code=500
        )

# ── GET /api/admin/dashboard/data (JSON) ──────────────────────────────────────
@router.get("/dashboard/data")
async def dashboard_data(x_admin_key: Optional[str] = Header(None, alias="x-admin-key")):
    """Machine-readable JSON of all dashboard data."""
    require_admin(x_admin_key)

    db_data = api_get("/debug/db")
    listings_data = api_get("/api/listings", "limit=100&offset=0")
    try:
        orders_data = api_get("/api/orders", "limit=100")
        orders = orders_data.get("orders", []) if isinstance(orders_data, dict) else (orders_data or [])
    except Exception:
        orders = []

    users = db_data.get("users", [])
    listings = listings_data.get("listings", []) if isinstance(listings_data, dict) else (listings_data or [])
    active = [l for l in listings if l.get("status") == "active"]

    return JSONResponse(content={
        "stats": {
            "total_users": db_data.get("user_count", len(users)),
            "active_listings": len(active),
            "total_listings": len(listings),
            "total_orders": len(orders),
            "total_cards": db_data.get("card_count", 0),
            "db_connected": db_data.get("tcp") == "connected",
        },
        "users": [
            {
                "id": u.get("id"),
                "username": u.get("username"),
                "display_name": u.get("display_name"),
                "email": u.get("email"),
                "created_at": u.get("created_at"),
                "total_sales": u.get("total_sales", 0),
                "rating": u.get("rating") or 0.0,
            }
            for u in users
        ],
        "listings": listings[:100],
        "orders": orders[:100],
    })

# ── GET /api/admin/users ────────────────────────────────────────────────────────
@router.get("/users")
async def admin_list_users(
    x_admin_key: Optional[str] = Header(None, alias="x-admin-key"),
    limit: int = Query(50, le=200),
    offset: int = Query(0, ge=0),
):
    """Paginated user list."""
    require_admin(x_admin_key)
    db_data = api_get("/debug/db")
    users = db_data.get("users", [])[offset : offset + limit]
    return JSONResponse(content={
        "users": users,
        "total": db_data.get("user_count", 0),
        "limit": limit,
        "offset": offset,
    })

# ── GET /api/admin/listings ────────────────────────────────────────────────────
@router.get("/listings")
async def admin_list_listings(
    x_admin_key: Optional[str] = Header(None, alias="x-admin-key"),
    limit: int = Query(50, le=200),
    offset: int = Query(0, ge=0),
    status: Optional[str] = Query(None),
):
    """Paginated listings with optional status filter."""
    require_admin(x_admin_key)
    params = f"limit={limit}&offset={offset}"
    data = api_get("/api/listings", params)
    listings = data.get("listings", []) if isinstance(data, dict) else (data or [])
    if status:
        listings = [l for l in listings if l.get("status") == status]
    return JSONResponse(content={
        "listings": listings,
        "total": data.get("total", len(listings)) if isinstance(data, dict) else len(listings),
        "limit": limit,
        "offset": offset,
    })

# ── GET /api/admin/orders ───────────────────────────────────────────────────────
@router.get("/orders")
async def admin_list_orders(
    x_admin_key: Optional[str] = Header(None, alias="x-admin-key"),
    limit: int = Query(50, le=200),
    offset: int = Query(0, ge=0),
    status: Optional[str] = Query(None),
):
    """Paginated orders with optional status filter."""
    require_admin(x_admin_key)
    try:
        data = api_get("/api/orders", f"limit={limit}&offset={offset}")
        orders = data.get("orders", []) if isinstance(data, dict) else (data or [])
    except Exception:
        orders = []
    if status:
        orders = [o for o in orders if o.get("status") == status]
    return JSONResponse(content={
        "orders": orders,
        "total": len(orders),
        "limit": limit,
        "offset": offset,
    })

# ── GET /api/admin/cards ────────────────────────────────────────────────────────
@router.get("/cards")
async def admin_list_cards(
    x_admin_key: Optional[str] = Header(None, alias="x-admin-key"),
    limit: int = Query(50, le=200),
    offset: int = Query(0, ge=0),
    set_name: Optional[str] = Query(None),
):
    """Paginated card catalog."""
    require_admin(x_admin_key)
    data = api_get("/api/cards", f"limit={limit}&offset={offset}&set_name={set_name or ''}")
    cards = data.get("cards", []) if isinstance(data, dict) else (data or [])
    return JSONResponse(content={
        "cards": cards,
        "total": data.get("total", len(cards)) if isinstance(data, dict) else len(cards),
        "limit": limit,
        "offset": offset,
    })

# ── GET /api/admin/proxy/{path:path} ────────────────────────────────────────────
@router.get("/proxy/{path:path}")
async def admin_proxy(
    path: str,
    x_admin_key: Optional[str] = Header(None, alias="x-admin-key"),
):
    """
    Proxy any internal API call (for the dashboard API explorer).
    Resolves path relative to /api/.
    """
    require_admin(x_admin_key)
    try:
        data = api_get(f"/{path}")
        return JSONResponse(content=data)
    except urllib.error.HTTPError as e:
        return JSONResponse(status_code=e.code, content={"error": str(e)})
    except Exception as e:
        return JSONResponse(status_code=502, content={"error": str(e)})

# ── GET /api/admin/stats ────────────────────────────────────────────────────────
@router.get("/stats")
async def admin_stats(x_admin_key: Optional[str] = Header(None, alias="x-admin-key")):
    """Lightweight KPI summary."""
    require_admin(x_admin_key)

    db_data = api_get("/debug/db")
    listings_data = api_get("/api/listings", "limit=100&offset=0")
    try:
        orders_data = api_get("/api/orders", "limit=100")
        orders = orders_data.get("orders", []) if isinstance(orders_data, dict) else (orders_data or [])
    except Exception:
        orders = []

    listings = listings_data.get("listings", []) if isinstance(listings_data, dict) else (listings_data or [])
    active = [l for l in listings if l.get("status") == "active"]
    users = db_data.get("users", [])

    return JSONResponse(content={
        "total_users": db_data.get("user_count", len(users)),
        "active_listings": len(active),
        "total_listings": len(listings),
        "total_orders": len(orders),
        "completed_orders": len([o for o in orders if o.get("status") in ("completed","fulfilled","shipped")]),
        "total_cards": db_data.get("card_count", 0),
        "db_connected": db_data.get("tcp") == "connected",
        "new_users_last_7d": sum(
            1 for u in users
            if u.get("created_at") and (
                datetime.now(timezone.utc) - datetime.fromisoformat(u["created_at"].replace("Z","+00:00"))
            ).days <= 7
        ),
    })
