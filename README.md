# RescueAI: Flood Rescue Coordination

**GRAVITON 2026 | CGC University, Mohali**
Problem statement #5: *RescueAI: Disaster Risk and Resource Coordination*

**Team:** Tensor Titan
**Members:** Aryan Sharma, Sahil, Rishab Ahajuria, Kritika Sharma

## The problem

During floods, control rooms get many calls and messages at once. Some are urgent, some are duplicates, and some are old or fake. Deciding who to help first is slow and stressful, and boats and medical teams are limited.

## Our solution

RescueAI is a web dashboard that helps a control room decide who to help first. **A human officer always makes the final decision.**

| Feature | What it does |
|---|---|
| **Request help** | Anyone can send a request by typing, speaking, or attaching a photo |
| **Priority Score** | An explainable formula (people in danger, elderly, children, medical emergency, water level, waiting time) gives a score from 0 to 100, shown as red, orange or green |
| **Fake Report Filter** | Flags duplicate text, photos already used in another report, old photos, and photos with no date. It flags reports for human review and never deletes them |
| **Voice SOS** | Speak in Hindi/Hinglish, English or Punjabi and the form fills itself in |
| **One-Click Rescue Plan** | Suggests which team to send first (boat, medical team or relief truck), with estimated travel time |
| **Predict Next Risk Zone** | Uses the rain forecast to show which places may be at risk in the next 6 hours (with a clearly labeled Demo mode) |
| **Street-level view** | Switches the map to a close-up of a local area (Mohali) |

## How it works

Help request (text, voice or photo) -> Fake report check -> Priority score -> Rescue plan -> Human officer approves

## Screenshots

[Add screenshots of the dashboard, request form, rescue plan and risk zones here]

## Tech stack

- **Python** and **Streamlit** (the app and the dashboard)
- **pandas** (tables and map data)
- **Pillow** (photo fingerprint and photo date)
- **streamlit-mic-recorder** and **SpeechRecognition** (Voice SOS, using a free Google speech service)
- **Open-Meteo** (free rain forecast, no key needed)
- **GitHub** and **GitHub Codespaces**

## Run it

```bash
pip install -r requirements.txt
streamlit run app.py
```

Voice SOS needs a browser with microphone permission and an internet connection.

## Honest limitations

- The demo uses **sample data**. The street-level spots are placeholders.
- Requests are kept **in memory** and reset when the app restarts. There is no database yet.
- Travel times are **estimates** (straight-line distance), not real road routes.
- The risk score uses the rain forecast plus **sample terrain assumptions**. It is not a full flood model.
- The scoring is **rule-based and explainable on purpose**. Speech recognition is a free service and may be less accurate for Punjabi.
- **Demo mode** simulates heavy rain and is labeled on screen.

## Future work

Real data from IMD, NDMA and satellite flood maps, a database, real SMS and WhatsApp requests, real road routing, search for any place in Punjab, more Indian languages, and a volunteer mobile app.

## Sustainable Development Goals

SDG 13 (Climate Action), SDG 11 (Sustainable Cities and Communities), SDG 3 (Good Health and Well-Being)

## Built with open-source tools and AI assistance

Built during GRAVITON 2026 using open-source tools, as the rules allow. Claude (by Anthropic) was used as a coding assistant. The team chose the problem, designed the features, tested the app and prepared the pitch.