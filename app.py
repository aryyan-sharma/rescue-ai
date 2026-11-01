import io
import html
import re
import math
import difflib
from datetime import datetime, timedelta, timezone

import requests
import streamlit as st
import pandas as pd
from PIL import Image
from streamlit_mic_recorder import speech_to_text

st.set_page_config(page_title="RescueAI", layout="wide", initial_sidebar_state="expanded")

st.markdown("""
<style>
.stApp { background: #e8edf5; }
[data-testid="stHeader"] { background: transparent; }
.block-container { padding-top: 1.6rem; max-width: 1400px; }
section[data-testid="stSidebar"] { background: #f3f6fb; border-right: 1px solid #dbe3f0; }
.logo { font-size: 1.7rem; font-weight: 800; color: #12284c; letter-spacing: -0.5px; }
.logo span { color: #e63946; }
.logo-sub { color: #6b7a99; font-size: 0.8rem; margin-bottom: 1rem; }
.page-title { font-size: 2rem; font-weight: 700; color: #12284c; }
div[class*="st-key-card"] {
    background: #f4f7fc; border: none !important; border-radius: 18px;
    box-shadow: 7px 7px 16px #cdd5e4, -7px -7px 16px #ffffff;
}
.card-title { font-weight: 700; color: #12284c; font-size: 1.05rem; margin-bottom: 0.4rem; }
.kpi { background: #f4f7fc; border-radius: 18px; padding: 16px 20px;
       box-shadow: 7px 7px 16px #cdd5e4, -7px -7px 16px #ffffff; }
.kpi-label { color: #6b7a99; font-size: 0.85rem; font-weight: 600; }
.kpi-value { font-size: 2rem; font-weight: 800; line-height: 1.2; }
.kpi-sub { color: #8a97b2; font-size: 0.75rem; }
.item { background: #ffffff; border-radius: 12px; padding: 8px 12px; margin-bottom: 8px;
        box-shadow: 2px 2px 6px #dde3ef; }
.item-title { font-weight: 700; color: #12284c; font-size: 0.9rem; }
.item-sub { color: #6b7a99; font-size: 0.8rem; }
.pill { color: #fff; border-radius: 999px; padding: 1px 9px; font-size: 0.75rem; margin-left: 6px; }
.st-key-nav label[data-testid="stRadioOption"] { width: 100%; padding: 9px 14px; border-radius: 12px; }
.st-key-nav label[data-testid="stRadioOption"] > div > div:first-child { display: none; }
.st-key-nav label[data-testid="stRadioOption"][data-selected="true"] {
    background: #ffffff; box-shadow: 3px 3px 8px #d3dae8; }
.st-key-nav label[data-testid="stRadioOption"][data-selected="true"] p { font-weight: 700; color: #2f5bea; }
.st-key-open_form button { background: #e63946; border: none; color: #fff; font-weight: 700; border-radius: 12px; }
.st-key-open_form button:hover { background: #cf2f3c; color: #fff; }
</style>
""", unsafe_allow_html=True)

CITIES = {
    "Ludhiana": (30.9010, 75.8573),
    "Jalandhar": (31.3260, 75.5762),
    "Patiala": (30.3398, 76.3869),
    "Amritsar": (31.6340, 74.8723),
    "Ferozepur": (30.9331, 74.6225),
    "Mohali": (30.7046, 76.7179),
}

# Sample street-level spots near Mohali. These are placeholder positions: replace with real streets and colonies.
STREETS = {
    "Sample street 1": (30.7090, 76.7110),
    "Sample street 2": (30.6990, 76.7220),
    "Sample street 3": (30.7150, 76.7240),
    "Sample street 4": (30.6930, 76.7090),
    "Sample street 5": (30.7020, 76.7330),
}
AREAS = {"Punjab (cities)": CITIES, "Mohali (street level)": STREETS}

WATER_POINTS = {"Ankle level": 0, "Knee level": 8, "Waist level": 18, "Roof / above": 25}
SPAM_WORDS = ["free", "click", "lottery", "win", "offer", "prize", "subscribe"]


TEAMS = [
    {"name": "Boat Team 1", "type": "Boat", "base": "Chandigarh", "lat": 30.7333, "lon": 76.7794},
    {"name": "Boat Team 2", "type": "Boat", "base": "Ludhiana", "lat": 30.9010, "lon": 75.8573},
    {"name": "Medical Team 1", "type": "Medical", "base": "Patiala", "lat": 30.3398, "lon": 76.3869},
    {"name": "Medical Team 2", "type": "Medical", "base": "Amritsar", "lat": 31.6340, "lon": 74.8723},
    {"name": "Relief Truck 1", "type": "Relief", "base": "Jalandhar", "lat": 31.3260, "lon": 75.5762},
    {"name": "Local Boat A", "type": "Boat", "base": "Mohali depot (sample)", "lat": 30.7120, "lon": 76.7060},
    {"name": "Local Boat B", "type": "Boat", "base": "Mohali depot (sample)", "lat": 30.6960, "lon": 76.7300},
    {"name": "Local Medical Team", "type": "Medical", "base": "Mohali hospital (sample)", "lat": 30.7000, "lon": 76.7150},
    {"name": "Local Relief Truck", "type": "Relief", "base": "Mohali depot (sample)", "lat": 30.7080, "lon": 76.7200},
]


def distance_km(lat1, lon1, lat2, lon2):
    r = 6371
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lon2 - lon1)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(h))


def make_plan(requests):
    valid = [r for r in requests if r["trust"] != "Likely fake"]
    ordered = sorted(valid, key=lambda r: r["score"], reverse=True)
    free = list(TEAMS)
    plan = []
    for r in ordered:
        if not free:
            break
        if r.get("medical"):
            wanted = "Medical"
        elif r["score"] >= 40:
            wanted = "Boat"
        else:
            wanted = "Relief"
        options = [t for t in free if t["type"] == wanted] or free
        lat, lon = r["lat"], r["lon"]
        team = min(options, key=lambda t: distance_km(t["lat"], t["lon"], lat, lon))
        km = distance_km(team["lat"], team["lon"], lat, lon) * 1.3
        minutes = 5 + km / 40 * 60
        free.remove(team)
        plan.append(
            {"Order": len(plan) + 1, "Send": team["name"], "From": team["base"], "To": r["place"],
             "Why": f"score {r['score']}: {r['need']}", "Distance (km)": round(km, 1),
             "ETA (min)": round(minutes)}
        )
    return plan


# Sample assumption (0-20): how exposed each place is to flooding. A real version would use elevation and river data.
TERRAIN_RISK = {"Ludhiana": 15, "Jalandhar": 15, "Patiala": 10, "Amritsar": 10, "Ferozepur": 20, "Mohali": 10}

# Used in demo mode, and when the live forecast cannot be reached: (rain in past 24h, expected rain in next 6h) in mm
DEMO_RAIN = {
    "Ludhiana": (62, 28), "Jalandhar": (48, 22), "Patiala": (35, 14),
    "Amritsar": (20, 6), "Ferozepur": (70, 35), "Mohali": (15, 3),
}


def fetch_rain(lat, lon):
    """Free weather forecast (Open-Meteo, no key needed). Returns (past 24h mm, next 6h mm)."""
    params = {"latitude": lat, "longitude": lon, "hourly": "precipitation",
              "past_days": 1, "forecast_days": 2, "timezone": "auto"}
    data = requests.get("https://api.open-meteo.com/v1/forecast", params=params, timeout=6).json()
    times = data["hourly"]["time"]
    rain = [x or 0 for x in data["hourly"]["precipitation"]]
    local_now = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(seconds=data.get("utc_offset_seconds", 0))
    key = local_now.strftime("%Y-%m-%dT%H:00")
    idx = times.index(key) if key in times else 24 + local_now.hour
    past24 = sum(rain[max(0, idx - 24):idx])
    next6 = sum(rain[idx:idx + 6])
    return round(past24, 1), round(next6, 1)


def calc_risk(past24, next6, terrain):
    pts_next = min(next6 / 20, 1) * 50
    pts_past = min(past24 / 50, 1) * 30
    total = round(pts_next + pts_past + terrain)
    if total >= 60:
        level = "High"
    elif total >= 30:
        level = "Medium"
    else:
        level = "Low"
    why = f"coming rain +{round(pts_next)}, recent rain +{round(pts_past)}, terrain +{terrain}"
    return total, level, why


def build_forecast(demo):
    rows = []
    live_ok = True
    for place, (lat, lon) in CITIES.items():
        if demo:
            past24, next6 = DEMO_RAIN[place]
        else:
            try:
                past24, next6 = fetch_rain(lat, lon)
            except Exception:
                live_ok = False
                past24, next6 = DEMO_RAIN[place]
        total, level, why = calc_risk(past24, next6, TERRAIN_RISK[place])
        color = {"High": "#e63946", "Medium": "#f4a261", "Low": "#2a9d8f"}[level]
        rows.append({"Place": place, "Past 24h rain (mm)": past24, "Next 6h rain (mm)": next6,
                     "Risk score": total, "Risk level": level, "Why": why,
                     "lat": lat, "lon": lon, "color": color})
    if demo:
        source = "DEMO MODE: simulated heavy rain (not real weather)."
    elif live_ok:
        source = "Live rain forecast from Open-Meteo (free weather service)."
    else:
        source = "Live forecast could not be reached, so sample data is shown."
    return {"rows": rows, "source": source}


LANGS = {"Hindi / Hinglish": "hi-IN", "English": "en-IN", "Punjabi": "pa-IN"}

ELDERLY_WORDS = ["bujurg", "buzurg", "budhe", "boodhe", "dadi", "dada", "nani", "nana", "bapu", "beeji",
                 "elderly", "old man", "old woman", "senior",
                 "बुजुर्ग", "बूढ़े", "बूढ़ी", "बुजुर्गों", "दादी", "दादा", "ਬਜ਼ੁਰਗ", "ਬੁੱਢੇ"]
CHILD_WORDS = ["bache", "bacche", "bachche", "baccha", "bachha", "child", "kids", "baby",
               "बच्चे", "बच्चा", "बच्चों", "बच्ची", "ਬੱਚੇ", "ਬੱਚਾ"]
MEDICAL_WORDS = ["doctor", "bimar", "bimaar", "dawai", "dawa", "hospital", "chot", "injured", "pregnant",
                 "garbhwati", "medical", "sick", "medicine",
                 "डॉक्टर", "बीमार", "दवाई", "अस्पताल", "चोट", "गर्भवती", "प्रेग्नेंट",
                 "ਡਾਕਟਰ", "ਬਿਮਾਰ", "ਦਵਾਈ", "ਹਸਪਤਾਲ"]
WATER_WORDS = [
    ("Roof / above", ["chhat", "roof", "छत", "ਛੱਤ"]),
    ("Waist level", ["kamar", "waist", "कमर", "ਕਮਰ"]),
    ("Knee level", ["ghutne", "knee", "घुटने", "ਗੋਡੇ"]),
    ("Ankle level", ["ankle", "takhne", "टखने"]),
]


def extract_details(text):
    """Turn a spoken sentence into form fields using simple keyword rules."""
    t = text.lower()
    details = {
        "people": None,
        "elderly": any(w in t for w in ELDERLY_WORDS),
        "children": any(w in t for w in CHILD_WORDS),
        "medical": any(w in t for w in MEDICAL_WORDS),
        "water": None,
    }
    numbers = [int(n) for n in re.findall(r"\d+", t) if 1 <= int(n) <= 50]
    if numbers:
        details["people"] = numbers[0]
    for level, words in WATER_WORDS:
        if any(w in t for w in words):
            details["water"] = level
            break
    return details


def calc_score(people, elderly, children, medical, water, hours):
    points = 0
    why = []
    p = min(people, 10) * 3
    points += p
    why.append(f"{people} people (+{p})")
    if elderly:
        points += 10
        why.append("elderly (+10)")
    if children:
        points += 10
        why.append("children (+10)")
    if medical:
        points += 15
        why.append("medical emergency (+15)")
    w = WATER_POINTS[water]
    points += w
    why.append(f"water {water.lower()} (+{w})")
    h = min(hours, 10)
    points += h
    why.append(f"waiting {hours}h (+{h})")
    return min(points, 100), ", ".join(why)


def analyze_photo(uploaded):
    """Read the real photo: make a fingerprint and look for the date it was taken."""
    if uploaded is None:
        return None
    try:
        img = Image.open(io.BytesIO(uploaded.getvalue()))
        small = img.convert("L").resize((8, 8))
        pixels = list(small.getdata())
        avg = sum(pixels) / len(pixels)
        bits = "".join("1" if px > avg else "0" for px in pixels)
    except Exception:
        return {"bits": None, "taken": None}
    taken = None
    try:
        exif = img.getexif()
        raw_date = exif.get_ifd(0x8769).get(36867) or exif.get(306)
        if raw_date:
            taken = datetime.strptime(str(raw_date).strip(), "%Y:%m:%d %H:%M:%S")
    except Exception:
        taken = None
    return {"bits": bits, "taken": taken}


def same_photo(bits_a, bits_b):
    if not bits_a or not bits_b:
        return False
    different = sum(1 for a, b in zip(bits_a, bits_b) if a != b)
    return different <= 5


def calc_trust(place, need, photo, existing):
    flags = []
    for r in existing:
        if r["place"] == place:
            similarity = difflib.SequenceMatcher(None, need.lower(), r["need"].lower()).ratio()
            if similarity > 0.8:
                flags.append("duplicate text for the same place")
                break
    if photo is not None:
        for r in existing:
            if same_photo(photo["bits"], r.get("bits")):
                flags.append("same photo already used in another report")
                break
        if photo["taken"] is None:
            flags.append("photo has no date information")
        else:
            age_days = (datetime.now() - photo["taken"]).days
            if age_days > 2:
                flags.append(f"photo is {age_days} days old")
    if len(need.strip()) < 8:
        flags.append("message too short")
    if any(word in re.findall(r"[a-z]+", need.lower()) for word in SPAM_WORDS):
        flags.append("spam-like words")
    if len(flags) == 0:
        return "Likely genuine", "no warning signs"
    if len(flags) == 1:
        return "Needs review", ", ".join(flags)
    return "Likely fake", ", ".join(flags)


def pick_color(score, trust):
    if trust == "Likely fake":
        return "#888888"
    if score >= 70:
        return "#e63946"
    if score >= 40:
        return "#f4a261"
    return "#2a9d8f"


def make_seed(area, locs, items):
    out = []
    for place, need, score, medical in items:
        lat, lon = locs[place]
        out.append({"area": area, "place": place, "need": need, "lat": lat, "lon": lon, "score": score,
                    "why": "sample", "trust": "Likely genuine", "flags": "sample", "bits": None, "medical": medical})
    return out


if "requests" not in st.session_state:
    st.session_state.requests = make_seed("Punjab (cities)", CITIES, [
        ("Ludhiana", "Family trapped, water rising", 92, False),
        ("Patiala", "Pregnant woman needs medical help", 88, True),
        ("Jalandhar", "Village cut off, needs food", 64, False),
        ("Amritsar", "Family safe on roof", 45, False),
        ("Ferozepur", "Cattle and crops at risk", 22, False),
        ("Mohali", "Road blocked, no danger", 15, False),
    ]) + make_seed("Mohali (street level)", STREETS, [
        ("Sample street 1", "Family trapped, water rising", 92, False),
        ("Sample street 2", "Pregnant woman needs medical help", 88, True),
        ("Sample street 3", "Lane cut off, needs food", 64, False),
        ("Sample street 4", "Family safe on roof", 45, False),
        ("Sample street 5", "Road blocked, no danger", 15, False),
    ])

st.session_state.setdefault("need", "")
st.session_state.setdefault("people", 3)
st.session_state.setdefault("elderly", False)
st.session_state.setdefault("children", False)
st.session_state.setdefault("medical", False)
st.session_state.setdefault("water", "Ankle level")
st.session_state.setdefault("hours", 1)
st.session_state.setdefault("heard", "")
st.session_state.setdefault("show_form", False)
st.session_state.setdefault("photo_n", 0)
st.session_state.setdefault("msg", "")


def open_form():
    st.session_state.show_form = True


def close_form():
    st.session_state.show_form = False


def submit_request():
    s = st.session_state
    area_now = s["area"]
    place_now = s[f"place_{area_now}"]
    lat0, lon0 = AREAS[area_now][place_now]
    photo = analyze_photo(s.get(f"photo_{s.photo_n}"))
    score, why = calc_score(s["people"], s["elderly"], s["children"], s["medical"], s["water"], s["hours"])
    trust, flags = calc_trust(place_now, s["need"], photo, s.requests)
    s.requests.append(
        {"area": area_now, "lat": lat0, "lon": lon0, "place": place_now, "need": s["need"], "score": score,
         "why": why, "trust": trust, "flags": flags, "bits": photo["bits"] if photo else None,
         "medical": s["medical"]}
    )
    s.msg = f"Request added for {place_now}. Priority score: {score} | Trust: {trust}"
    s["need"] = ""
    s["people"] = 3
    s["elderly"] = False
    s["children"] = False
    s["medical"] = False
    s["water"] = "Ankle level"
    s["hours"] = 1
    s["heard"] = ""
    s.photo_n += 1
    s.show_form = False


PAGES = ["Dashboard", "Control room", "Risk zones", "All requests"]

with st.sidebar:
    st.markdown('<div class="logo">Rescue<span>AI</span></div>'
                '<div class="logo-sub">Flood rescue coordination</div>', unsafe_allow_html=True)
    page = st.radio("Menu", PAGES, key="nav", label_visibility="collapsed")
    st.divider()
    area = st.radio("Map area", list(AREAS.keys()), key="area")
    st.caption("Sample demo data")

head_left, head_right = st.columns([5, 1])
head_left.markdown(f'<div class="page-title">{page}</div>', unsafe_allow_html=True)
if not st.session_state.show_form:
    head_right.button("Request help", key="open_form", on_click=open_form, width="stretch")

if st.session_state.msg:
    st.success(st.session_state.msg)
    st.session_state.msg = ""

if st.session_state.show_form:
    with st.container(border=True, key="card_form"):
        form_left, form_right = st.columns([6, 1])
        form_left.markdown('<div class="card-title">Request help</div>', unsafe_allow_html=True)
        form_right.button("Close", key="close_form", on_click=close_form)

        st.markdown("**Speak your request (optional)**")
        lang_name = st.selectbox("Speak in", list(LANGS.keys()), key="lang_name")
        spoken = speech_to_text(
            start_prompt="Start speaking", stop_prompt="Stop", just_once=True,
            language=LANGS[lang_name], key="stt",
        )
        if spoken:
            d = extract_details(spoken)
            st.session_state["need"] = spoken
            st.session_state["heard"] = spoken
            if d["people"]:
                st.session_state["people"] = d["people"]
            if d["elderly"]:
                st.session_state["elderly"] = True
            if d["children"]:
                st.session_state["children"] = True
            if d["medical"]:
                st.session_state["medical"] = True
            if d["water"]:
                st.session_state["water"] = d["water"]
        if st.session_state["heard"]:
            st.caption(f"Heard: {st.session_state['heard']}")

        st.markdown("**Or fill the form**")
        col1, col2 = st.columns(2)
        with col1:
            st.selectbox("Location", list(AREAS[area].keys()), key=f"place_{area}")
            st.text_area("What is happening?", key="need", placeholder="Describe what is happening")
            uploaded = st.file_uploader("Attach a photo (optional)", type=["jpg", "jpeg", "png"],
                                        key=f"photo_{st.session_state.photo_n}")
            if uploaded is not None:
                st.image(uploaded, caption="Attached photo", width=200)
        with col2:
            st.number_input("People in danger", 1, 50, key="people")
            st.checkbox("Elderly present", key="elderly")
            st.checkbox("Children present", key="children")
            st.checkbox("Medical emergency", key="medical")
            st.selectbox("Water level", list(WATER_POINTS.keys()), key="water")
            st.slider("Waiting for help (hours)", 0, 24, key="hours")
        st.button("Submit request", key="submit", type="primary", on_click=submit_request)

area_requests = [r for r in st.session_state.requests if r["area"] == area]
rows = [{**r, "color": pick_color(r["score"], r["trust"])} for r in area_requests]
df = pd.DataFrame(rows)
street_mode = area == "Mohali (street level)"


def kpi_card(label, value, sub, color):
    return (f'<div class="kpi"><div class="kpi-label">{label}</div>'
            f'<div class="kpi-value" style="color:{color}">{value}</div>'
            f'<div class="kpi-sub">{sub}</div></div>')


def request_item(r):
    color = pick_color(r["score"], r["trust"])
    return (f'<div class="item" style="border-left:5px solid {color}">'
            f'<div class="item-title">{html.escape(r["place"])}'
            f'<span class="pill" style="background:{color}">{r["score"]}</span></div>'
            f'<div class="item-sub">{html.escape(r["need"] or "No description")}</div></div>')


def show_map(height):
    st.markdown('<div class="card-title">Live request map'
                + (" (street level)" if street_mode else "") + "</div>", unsafe_allow_html=True)
    if street_mode:
        st.map(df, latitude="lat", longitude="lon", color="color", size=80, zoom=14, height=height)
    else:
        st.map(df, latitude="lat", longitude="lon", color="color", size=4000, height=height)
    st.caption("Red = urgent, orange = medium, green = low, grey = likely fake (needs human review)")


def show_plan():
    with st.container(border=True, key="card_plan"):
        st.markdown('<div class="card-title">Rescue plan</div>', unsafe_allow_html=True)
        if st.button("Make rescue plan", key="plan_btn", type="primary"):
            st.session_state.plan = make_plan(area_requests)
            st.session_state.plan_area = area
        plan = st.session_state.get("plan")
        if plan and st.session_state.get("plan_area") == area:
            first = plan[0]
            st.success(
                f"First action: send {first['Send']} from {first['From']} to {first['To']} "
                f"(about {first['ETA (min)']} min). Full plan below."
            )
            st.dataframe(pd.DataFrame(plan), width="stretch", hide_index=True)
            st.caption("Estimates only: straight-line distance x 1.3 at 40 km/h. Real flood routes can be slower. "
                       "A human officer approves the final plan.")
        else:
            st.caption("Click the button to get an ordered list of which team to send first.")


def show_requests_table():
    with st.container(border=True, key="card_table"):
        st.markdown('<div class="card-title">Requests, most urgent first</div>', unsafe_allow_html=True)
        st.dataframe(
            df.sort_values("score", ascending=False)[["place", "need", "score", "trust", "flags", "why"]],
            width="stretch", hide_index=True,
        )


def show_risk():
    with st.container(border=True, key="card_risk"):
        st.markdown('<div class="card-title">Predict next risk zones (next 6 hours)</div>', unsafe_allow_html=True)
        demo_rain = st.checkbox("Demo mode: simulate heavy rain (for the presentation)", key="demo_rain")
        if st.button("Check rain forecast", key="forecast_btn", type="primary"):
            st.session_state.forecast = build_forecast(demo_rain)
        fc = st.session_state.get("forecast")
        if fc:
            fdf = pd.DataFrame(fc["rows"])
            st.caption(fc["source"])
            st.map(fdf, latitude="lat", longitude="lon", color="color", size=6000, height=380)
            st.dataframe(
                fdf.sort_values("Risk score", ascending=False)[
                    ["Place", "Past 24h rain (mm)", "Next 6h rain (mm)", "Risk score", "Risk level", "Why"]],
                width="stretch", hide_index=True,
            )
            top_row = fdf.sort_values("Risk score", ascending=False).iloc[0]
            st.warning(
                f"Highest risk in the next 6 hours: {top_row['Place']} ({top_row['Risk level']}, "
                f"score {top_row['Risk score']}). Consider moving boats and relief supplies there now."
            )
            st.caption("Estimate from the rain forecast plus sample terrain assumptions. It is not a full flood model.")
        else:
            st.caption("Click the button to see which places may be in danger in the next 6 hours.")


if page == "Dashboard":
    total = len(area_requests)
    urgent = len([r for r in area_requests if r["score"] >= 70 and r["trust"] != "Likely fake"])
    flagged = len([r for r in area_requests if r["trust"] not in ("Likely genuine",)])
    k1, k2, k3, k4 = st.columns(4)
    k1.markdown(kpi_card("Total requests", total, "in this area", "#12284c"), unsafe_allow_html=True)
    k2.markdown(kpi_card("Urgent now", urgent, "priority score 70 or more", "#e63946"), unsafe_allow_html=True)
    k3.markdown(kpi_card("Flagged reports", flagged, "need human review", "#f4a261"), unsafe_allow_html=True)
    k4.markdown(kpi_card("Teams ready", len(TEAMS), "boats, medical, relief", "#2a9d8f"), unsafe_allow_html=True)
    st.write("")
    map_col, list_col = st.columns([2, 1])
    with map_col:
        with st.container(border=True, key="card_map"):
            show_map(360)
    with list_col:
        with st.container(border=True, key="card_urgent"):
            st.markdown('<div class="card-title">Most urgent now</div>', unsafe_allow_html=True)
            top = sorted([r for r in area_requests if r["trust"] != "Likely fake"],
                         key=lambda r: r["score"], reverse=True)[:5]
            st.markdown("".join(request_item(r) for r in top) or "No requests yet.", unsafe_allow_html=True)
    show_plan()
    show_requests_table()
elif page == "Control room":
    show_plan()
elif page == "Risk zones":
    show_risk()
else:
    show_requests_table()
    