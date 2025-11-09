#!/usr/bin/env python3
"""
INDIAN MARKET PRICE ADVISOR — AI EDITION (v2.3)
- Contextual error messages for item / state / city / quantity
- Strict commodity matching and safe cache usage
- Prediction + weather + alerts included
"""

import requests
import json
import os
from datetime import datetime
from statistics import mean, stdev
from difflib import get_close_matches

# ---------------- CONFIG (use your own keys) ----------------
DATA_GOV_KEY = "579b464db66ec23bdd0000018c35b26b76c7400d7a782573a2f7dc44"
OPENWEATHER_KEY = "f4d045df8b173df3c23b55661f3e3856"
# ------------------------------------------------------------

DATA_GOV_URL = "https://api.data.gov.in/resource/9ef84268-d588-465a-a308-a864a43d0070"
CACHE_FILE = "mandi_cache.json"

VALID_STATES = {
    "Andhra Pradesh","Arunachal Pradesh","Assam","Bihar","Chhattisgarh","Delhi","Goa",
    "Gujarat","Haryana","Himachal Pradesh","Jammu And Kashmir","Jharkhand","Karnataka",
    "Kerala","Madhya Pradesh","Maharashtra","Manipur","Meghalaya","Mizoram","Nagaland",
    "Odisha","Punjab","Rajasthan","Sikkim","Tamil Nadu","Telangana","Tripura",
    "Uttar Pradesh","Uttarakhand","West Bengal"
}

# ------------------ Helpers ------------------

def save_cache(records):
    try:
        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump({"timestamp": datetime.now().isoformat(), "records": records}, f)
    except Exception:
        pass

def load_cache():
    try:
        if os.path.exists(CACHE_FILE):
            with open(CACHE_FILE, "r", encoding="utf-8") as f:
                return json.load(f).get("records", [])
    except Exception:
        return []
    return []

def fetch_mandi_records_from_api(commodity, limit=800):
    """Call data.gov.in API (returns raw records or [] on failure)."""
    params = {
        "api-key": DATA_GOV_KEY,
        "format": "json",
        "limit": limit,
        "filters[commodity]": commodity
    }
    try:
        r = requests.get(DATA_GOV_URL, params=params, timeout=12)
        r.raise_for_status()
        j = r.json()
        records = j.get("records", []) or []
        if records:
            save_cache(records)
        return records
    except Exception:
        return []

def safe_load_cached_for_commodity(item):
    """Return cached records that mention the requested commodity (case-insensitive)."""
    cached = load_cache()
    if not cached:
        return []
    item_l = item.lower()
    filtered = []
    for r in cached:
        commodity_field = (r.get("commodity") or r.get("commodity_name") or "").strip().lower()
        if not commodity_field:
            continue
        # strict token or exact match
        if item_l == commodity_field or item_l in commodity_field.split() or commodity_field.startswith(item_l):
            filtered.append(r)
    return filtered

def smart_fetch_records(item):
    """Fetch records for 'item' with validation and safe cache fallback."""
    item_clean = item.strip().lower()
    api_records = fetch_mandi_records_from_api(item_clean)
    # validate api_records contain commodity fields that match item
    valid = []
    for r in api_records:
        com = (r.get("commodity") or r.get("commodity_name") or "").strip().lower()
        if not com:
            continue
        if item_clean == com or item_clean in com.split() or com.startswith(item_clean):
            valid.append(r)
    if valid:
        return valid
    # if API returned but none matched strictly -> prepare suggestions (do not auto-use)
    if api_records:
        return []
    # API empty; try cache but strict
    cached_match = safe_load_cached_for_commodity(item_clean)
    return cached_match

def parse_price_records(records):
    """Return parsed list with keys: commodity, state, market, price (float), date(if any)"""
    parsed = []
    for rec in records:
        try:
            commodity = (rec.get("commodity") or rec.get("commodity_name") or "").strip()
            modal = rec.get("modal_price") or rec.get("modalprice") or ""
            if modal in (None, ""):
                continue
            price = float(modal)
            parsed.append({
                "commodity": commodity,
                "state": (rec.get("state_name") or rec.get("state") or "").strip(),
                "market": (rec.get("market") or rec.get("market_name") or "").strip(),
                "price": price,
                "date": (rec.get("arrival_date") or rec.get("date") or rec.get("date_of_arrival") or "").strip()
            })
        except Exception:
            continue
    return parsed

def compute_state_aggregates(parsed):
    state_map = {}
    for p in parsed:
        st = p["state"] or "Unknown"
        state_map.setdefault(st, []).append(p["price"])
    state_avg = {s: mean(vals) for s, vals in state_map.items() if vals}
    all_prices = [p["price"] for p in parsed]
    stats = {}
    if all_prices:
        stats["min"] = min(all_prices)
        stats["max"] = max(all_prices)
        stats["avg"] = mean(all_prices)
        stats["count"] = len(all_prices)
        stats["stddev"] = stdev(all_prices) if len(all_prices) > 1 else 0.0
    return state_avg, stats

def simple_trend_predict(parsed, days_back=7):
    """Simple trend prediction (quintal units preferred)."""
    from datetime import datetime as dt
    pairs = []
    for p in parsed:
        d = p.get("date")
        if not d:
            continue
        text = d[:10]
        for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%Y/%m/%d"):
            try:
                dtobj = dt.strptime(text, fmt)
                pairs.append((dtobj.date(), p["price"]))
                break
            except Exception:
                pass
    if pairs:
        day_map = {}
        for date_obj, price in pairs:
            day_map.setdefault(date_obj, []).append(price)
        items = sorted([(d, mean(vals)) for d, vals in day_map.items()], key=lambda x: x[0])
        recent = items[-days_back:]
        if len(recent) >= 2:
            xs = list(range(len(recent)))
            ys = [p for _, p in recent]
            n = len(xs)
            x_mean = sum(xs)/n
            y_mean = sum(ys)/n
            num = sum((xs[i]-x_mean)*(ys[i]-y_mean) for i in range(n))
            den = sum((xs[i]-x_mean)**2 for i in range(n))
            slope = num/den if den != 0 else 0.0
            intercept = y_mean - slope*x_mean
            pred = intercept + slope * n
            return max(pred, 0.0)
    raw = [p["price"] for p in parsed]
    if len(raw) >= 2:
        raw_last = raw[-min(len(raw), days_back):]
        diffs = [raw_last[i+1]-raw_last[i] for i in range(len(raw_last)-1)]
        avg_diff = mean(diffs) if diffs else 0.0
        return max(raw_last[-1] + avg_diff, 0.0)
    return None

def fetch_weather(city):
    if not OPENWEATHER_KEY:
        return None
    try:
        params = {"q": f"{city},IN", "appid": OPENWEATHER_KEY, "units": "metric"}
        r = requests.get("https://api.openweathermap.org/data/2.5/weather", params=params, timeout=10)
        if r.status_code != 200:
            return None
        j = r.json()
        return {
            "city": city,
            "temp": j["main"]["temp"],
            "desc": j["weather"][0]["description"].title(),
            "humidity": j["main"].get("humidity"),
            "code": j.get("weather", [{}])[0].get("id", 0)
        }
    except Exception:
        return None

def check_weather_alerts(weather):
    if not weather:
        return []
    alerts = []
    desc = weather.get("desc", "").lower()
    code = weather.get("code", 0)
    temp = weather.get("temp")
    if "rain" in desc or "shower" in desc:
        alerts.append("Rain expected — pack/cover produce and check transport plans.")
    if "thunder" in desc or code in (202,212,221):
        alerts.append("Thunderstorm risk — avoid long-distance shipment today.")
    if temp is not None and temp >= 40:
        alerts.append("High temperature — risk of spoilage; use cool storage.")
    if temp is not None and temp <= 2:
        alerts.append("Very low temperature — check cold-storage requirements.")
    return alerts

# ------------------ Main ------------------

def main():
    print(" 🇮🇳 XFARMER INDIAN MARKET PRICE ADVISOR — AI EDITION ")
    print("Instructions:")
    print(" • Enter valid item name")
    print(" • Enter your state name")
    print(" • Enter your city name")
    print(" • Enter quantity in kg")
    print("----------------------------------------------------")

    # ---- Item validation ----
    item = input("Enter item name: ").strip()
    if not item:
        print("❌ Item required — please enter a crop name like 'tomato' or 'onion'.")
        return
    if len(item) < 3:
        print("❌ Item name too short — please enter full crop name (e.g., 'tomato').")
        return
    item_clean = item.lower()

    # ---- State validation ----
    state = input("Enter your state name: ").strip()
    if not state:
        print("❌ State required — please enter your Indian state (e.g., 'Rajasthan').")
        return
    state_norm = state.title()
    if state_norm not in VALID_STATES:
        # try small fixes (allow common lowercase matches)
        close = get_close_matches(state_norm, list(VALID_STATES), n=2, cutoff=0.75)
        if close:
            print(f"❌ State name '{state}' not recognized. Did you mean: {', '.join(close)} ? Please re-run with correct state.")
        else:
            print(f"❌ State name '{state}' not recognized. Please enter a valid Indian state (e.g., 'Maharashtra').")
        return

    # ---- City validation ----
    city = input("Enter your city name (for weather): ").strip()
    if not city:
        print("❌ City required — please enter your city (e.g., 'Jaipur').")
        return
    city_norm = city.title()

    # ---- Quantity validation ----
    qty_in = input("Enter quantity (in kg): ").strip()
    if not qty_in:
        print("❌ Quantity required — enter a positive number (e.g., 50).")
        return
    try:
        qty = float(qty_in)
        if qty <= 0:
            print("❌ Invalid quantity — number must be greater than zero (e.g., 50).")
            return
    except Exception:
        print("❌ Invalid quantity format — enter numeric value like 50 or 100.5.")
        return

    print("\nFetching real mandi + weather data... Please wait...\n")

    # ---- Fetch mandi records strictly ----
    raw_records = smart_fetch_records(item_clean)
    if not raw_records:
        print(f"❌ No real-time mandi records found for '{item}'.")
        print("   → Check spelling or try a common name (e.g., 'tomato', 'onion', 'potato').")
        return

    parsed = parse_price_records(raw_records)
    if not parsed:
        print(f"❌ No numeric price records found for '{item}'.")
        return

    # ensure parsed records actually mention the requested commodity
    parsed_good = [p for p in parsed if p.get("commodity", "").strip().lower().find(item_clean) != -1]
    if not parsed_good:
        # prepare suggestions (do not auto-run)
        commodities_present = sorted({(p.get("commodity") or "").strip() for p in parsed if p.get("commodity")})
        suggestions = get_close_matches(item_clean, [c.lower() for c in commodities_present], n=3, cutoff=0.7)
        if suggestions:
            print(f"❌ No exact match for '{item}'. Did you mean: {', '.join(suggestions)} ?")
        else:
            print(f"❌ No match for '{item}' in the fetched records. Try different spelling or item.")
        return

    # ---- Compute aggregates ----
    state_avg, stats = compute_state_aggregates(parsed_good)
    if not stats:
        print("⚠️ Not enough data to compute statistics for this commodity.")
        return

    overall_min = stats["min"]
    overall_max = stats["max"]
    overall_avg = stats["avg"]
    count = stats["count"]

    # best state choose ignoring Unknown if possible
    best_state = None
    best_price = None
    if state_avg:
        filtered_state_avg = {s: v for s, v in state_avg.items() if s and s.lower() != "unknown"}
        if filtered_state_avg:
            best_state = max(filtered_state_avg, key=lambda s: filtered_state_avg[s])
            best_price = filtered_state_avg[best_state]
        else:
            best_state = max(state_avg, key=lambda s: state_avg[s])
            best_price = state_avg[best_state]

    predicted_quintal = simple_trend_predict(parsed_good, days_back=7)
    predicted_kg = (predicted_quintal / 100.0) if predicted_quintal else None

    avg_per_kg = overall_avg / 100.0
    min_per_kg = overall_min / 100.0
    max_per_kg = overall_max / 100.0
    total_estimate = avg_per_kg * qty

    # weather and alerts
    weather = fetch_weather(city_norm)
    weather_alerts = check_weather_alerts(weather)

    # price alert based on prediction
    price_alerts = []
    if predicted_quintal and overall_avg:
        change_pct = ((predicted_quintal - overall_avg) / overall_avg) * 100
        if abs(change_pct) >= 8:
            if change_pct > 0:
                price_alerts.append(f"Prediction: price may RISE by {change_pct:.1f}% (next-day). Consider selling soon.")
            else:
                price_alerts.append(f"Prediction: price may DROP by {abs(change_pct):.1f}% (next-day). Consider holding off.")

    # ---- Output ----
    print("-----------------------------------------------------")
    print(f"📅 Date & Time: {datetime.now().strftime('%d-%m-%Y %H:%M:%S')}")
    print(f"🌾 Commodity: {item.title()}")
    print(f"📍 Your State (input): {state_norm}")
    print(f"🧾 Records analyzed: {count}")
    print()
    print(f"💰 Highest Market Price: ₹{max_per_kg:.2f}/kg")
    print(f"💰 Lowest Market Price:  ₹{min_per_kg:.2f}/kg")
    print(f"📊 Average Market Price: ₹{avg_per_kg:.2f}/kg")
    print()
    if best_state and best_price:
        print(f"🌟 Best State (avg): {best_state} → ₹{(best_price/100):.2f}/kg")
    print(f"📦 Estimated value for {qty} kg (at avg): ₹{total_estimate:.2f}")
    if predicted_kg:
        print()
        print(f"🔮 Next-day prediction (simple trend): ₹{predicted_kg:.2f}/kg")
    print("------------------------------------------------------")

    if weather_alerts or price_alerts:
        print("⚠️ ALERTS:")
        for a in weather_alerts:
            print(" -", a)
        for p in price_alerts:
            print(" -", p)
        print("--------------------------------------------------")

    if weather:
        print("🌦 Weather (for " + weather["city"] + "):")
        print(f"   Temp: {weather['temp']}°C  |  {weather['desc']}  |  Humidity: {weather.get('humidity')}")
    else:
        print("🌦 Weather: Not available (check OpenWeather API key or internet).")

    print("------------------------------------------------------")
    print("✅ Thank you for using XFARMER INDIAN MARKET PRICE ADVISOR — AI EDITION! 🇮🇳")
    
    print("[Program finished]\n")

if __name__ == "__main__":
    main()