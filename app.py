import io
import re
import math
import difflib
from datetime import datetime, timedelta, timezone

import requests
import streamlit as st
import pandas as pd
from PIL import Image
from streamlit_mic_recorder import speech_to_text

st.set_page_config(page_title="RescueAI", layout="wide")
st.title("RescueAI")
st.caption("Flood rescue coordination | sample demo data")

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

st.session_state.setdefault("need", "Water entering house")
st.session_state.setdefault("people", 3)
st.session_state.setdefault("elderly", False)
st.session_state.setdefault("children", False)
st.session_state.setdefault("medical", False)
st.session_state.setdefault("water", "Ankle level")
st.session_state.setdefault("heard", "")

with st.sidebar:
    st.header("Voice SOS")
    lang_name = st.selectbox("Speak in", list(LANGS.keys()))
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
    st.divider()
    st.header("New help request")
    area = st.radio("Map area", list(AREAS.keys()), key="area")
    LOCATIONS = AREAS[area]
    place = st.selectbox("Location", list(LOCATIONS.keys()))
    need = st.text_area("What is happening?", key="need")
    uploaded = st.file_uploader("Attach a photo (optional)", type=["jpg", "jpeg", "png"])
    if uploaded is not None:
        st.image(uploaded, caption="Attached photo", width=200)
    people = st.number_input("People in danger", 1, 50, key="people")
    elderly = st.checkbox("Elderly present", key="elderly")
    children = st.checkbox("Children present", key="children")
    medical = st.checkbox("Medical emergency", key="medical")
    water = st.selectbox("Water level", list(WATER_POINTS.keys()), key="water")
    hours = st.slider("Waiting for help (hours)", 0, 24, 1)
    if st.button("Submit request", key="submit"):
        score, why = calc_score(people, elderly, children, medical, water, hours)
        photo = analyze_photo(uploaded)
        trust, flags = calc_trust(place, need, photo, st.session_state.requests)
        lat0, lon0 = LOCATIONS[place]
        st.session_state.requests.append(
            {"area": area, "lat": lat0, "lon": lon0, "place": place, "need": need, "score": score, "why": why, "trust": trust,
             "flags": flags, "bits": photo["bits"] if photo else None, "medical": medical}
        )
        st.success(f"Request added. Priority score: {score} | Trust: {trust}")

area_requests = [r for r in st.session_state.requests if r["area"] == area]
rows = [{**r, "color": pick_color(r["score"], r["trust"])} for r in area_requests]
df = pd.DataFrame(rows)

st.subheader("Live request map" + (" (street level)" if area == "Mohali (street level)" else ""))
if area == "Mohali (street level)":
    st.map(df, latitude="lat", longitude="lon", color="color", size=80, zoom=14)
else:
    st.map(df, latitude="lat", longitude="lon", color="color", size=4000)
st.caption("Red = urgent, Orange = medium, Green = low, Grey = likely fake (needs human review)")

st.subheader("Control room")
if "plan" not in st.session_state:
    st.session_state.plan = None
if st.button("Make rescue plan", key="plan_btn"):
    st.session_state.plan = make_plan(area_requests)
if st.session_state.plan:
    first = st.session_state.plan[0]
    st.success(
        f"First action: send {first['Send']} from {first['From']} to {first['To']} "
        f"(about {first['ETA (min)']} min). Full plan below."
    )
    st.dataframe(pd.DataFrame(st.session_state.plan), width="stretch", hide_index=True)
    st.caption("Estimates only: straight-line distance x 1.3 at 40 km/h. Real flood routes can be slower. A human officer approves the final plan.")

st.subheader("Predict next risk zones (next 6 hours)")
demo_rain = st.checkbox("Demo mode: simulate heavy rain (for the presentation)", key="demo_rain")
if st.button("Check rain forecast", key="forecast_btn"):
    st.session_state.forecast = build_forecast(demo_rain)
fc = st.session_state.get("forecast")
if fc:
    fdf = pd.DataFrame(fc["rows"])
    st.caption(fc["source"])
    st.map(fdf, latitude="lat", longitude="lon", color="color", size=6000)
    st.dataframe(
        fdf.sort_values("Risk score", ascending=False)[
            ["Place", "Past 24h rain (mm)", "Next 6h rain (mm)", "Risk score", "Risk level", "Why"]],
        width="stretch", hide_index=True,
    )
    top_row = fdf.sort_values("Risk score", ascending=False).iloc[0]
    st.warning(
        f"Highest risk in the next 6 hours: {top_row['Place']} ({top_row['Risk level']}, score {top_row['Risk score']}). "
        "Consider moving boats and relief supplies there now."
    )
    st.caption("Estimate from the rain forecast plus sample terrain assumptions. It is not a full flood model.")

st.subheader("Requests, most urgent first")
st.dataframe(
    df.sort_values("score", ascending=False)[["place", "need", "score", "trust", "flags", "why"]],
    width="stretch",
)