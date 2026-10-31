import io
import re
import math
import difflib
from datetime import datetime

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

WATER_POINTS = {"Ankle level": 0, "Knee level": 8, "Waist level": 18, "Roof / above": 25}
SPAM_WORDS = ["free", "click", "lottery", "win", "offer", "prize", "subscribe"]


TEAMS = [
    {"name": "Boat Team 1", "type": "Boat", "base": "Chandigarh", "lat": 30.7333, "lon": 76.7794},
    {"name": "Boat Team 2", "type": "Boat", "base": "Ludhiana", "lat": 30.9010, "lon": 75.8573},
    {"name": "Medical Team 1", "type": "Medical", "base": "Patiala", "lat": 30.3398, "lon": 76.3869},
    {"name": "Medical Team 2", "type": "Medical", "base": "Amritsar", "lat": 31.6340, "lon": 74.8723},
    {"name": "Relief Truck 1", "type": "Relief", "base": "Jalandhar", "lat": 31.3260, "lon": 75.5762},
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
        lat, lon = CITIES[r["place"]]
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


if "requests" not in st.session_state:
    st.session_state.requests = [
        {"place": "Ludhiana", "need": "Family trapped, water rising", "score": 92, "why": "sample", "trust": "Likely genuine", "flags": "sample", "bits": None},
        {"place": "Patiala", "need": "Pregnant woman needs medical help", "score": 88, "why": "sample", "trust": "Likely genuine", "flags": "sample", "bits": None, "medical": True},
        {"place": "Jalandhar", "need": "Village cut off, needs food", "score": 64, "why": "sample", "trust": "Likely genuine", "flags": "sample", "bits": None},
        {"place": "Amritsar", "need": "Family safe on roof", "score": 45, "why": "sample", "trust": "Likely genuine", "flags": "sample", "bits": None},
        {"place": "Ferozepur", "need": "Cattle and crops at risk", "score": 22, "why": "sample", "trust": "Likely genuine", "flags": "sample", "bits": None},
        {"place": "Mohali", "need": "Road blocked, no danger", "score": 15, "why": "sample", "trust": "Likely genuine", "flags": "sample", "bits": None},
    ]

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
    place = st.selectbox("Location", list(CITIES.keys()))
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
        st.session_state.requests.append(
            {"place": place, "need": need, "score": score, "why": why, "trust": trust,
             "flags": flags, "bits": photo["bits"] if photo else None, "medical": medical}
        )
        st.success(f"Request added. Priority score: {score} | Trust: {trust}")

rows = []
for r in st.session_state.requests:
    lat, lon = CITIES[r["place"]]
    rows.append({**r, "lat": lat, "lon": lon, "color": pick_color(r["score"], r["trust"])})
df = pd.DataFrame(rows)

st.subheader("Live request map")
st.map(df, latitude="lat", longitude="lon", color="color", size=4000)
st.caption("Red = urgent, Orange = medium, Green = low, Grey = likely fake (needs human review)")

st.subheader("Control room")
if "plan" not in st.session_state:
    st.session_state.plan = None
if st.button("Make rescue plan", key="plan_btn"):
    st.session_state.plan = make_plan(st.session_state.requests)
if st.session_state.plan:
    first = st.session_state.plan[0]
    st.success(
        f"First action: send {first['Send']} from {first['From']} to {first['To']} "
        f"(about {first['ETA (min)']} min). Full plan below."
    )
    st.dataframe(pd.DataFrame(st.session_state.plan), width="stretch", hide_index=True)
    st.caption("Estimates only: straight-line distance x 1.3 at 40 km/h. Real flood routes can be slower. A human officer approves the final plan.")

st.subheader("Requests, most urgent first")
st.dataframe(
    df.sort_values("score", ascending=False)[["place", "need", "score", "trust", "flags", "why"]],
    width="stretch",
)