import requests
import uuid
import json
import re
from datetime import datetime

# --- CONFIGURATION ---
# This forces specific station names to map to UZ IDs if needed in future
MANUAL_STATION_OVERRIDES = {
    "Kyiv": "2200001",
    "Lviv": "2218000"
}

def joinWithSpaces(*args):
    return " ".join(filter(None, args))

def get_headers():
    return {
        'authority': 'app.uz.gov.ua',
        'accept': 'application/json',
        'user-agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'x-client-locale': 'en',  # Force English to avoid Cyrillic font issues
        'x-session-id': str(uuid.uuid4()),
        'x-user-agent': 'UZ/2 Web/1 User/guest'
    }

def get_uz_board(station_id):
    url = f"https://app.uz.gov.ua/api/station-boards/{station_id}"
    try:
        response = requests.get(url, headers=get_headers(), timeout=10)
        return response.json() if response.status_code == 200 else None
    except Exception as e:
        print(f"Connection Error: {e}")
        return None

def process_uz_data(json_data, journeyConfig):
    if not json_data: return [], "Connection Failed"

    station_name = json_data.get('station', {}).get('name', 'UZ Station')
    raw_departures = json_data.get('departures', [])
    processed_services = []

    for index, item in enumerate(raw_departures):
        departure = {}

        # 1. Time
        timestamp = item.get('time')
        departure["aimed_departure_time"] = datetime.fromtimestamp(timestamp).strftime("%H:%M") if timestamp else "--:--"

        # 2. Status
        delay = item.get('delay_minutes')
        departure["expected_departure_time"] = f"Late {delay}m" if delay else "On time"

        # 3. Destination & Route Parsing
        route = item.get('route', '')
        destination = route 
        
        # Clean up the route string to get just the destination city
        if ' - ' in route: destination = route.split(' - ')[-1]
        elif u'\u2192' in route: destination = route.split(u'\u2192')[-1].strip()
        elif '->' in route: destination = route.split('->')[-1].strip()
        
        departure["destination_name"] = destination

        # 4. Platform
        departure["platform"] = str(item.get('platform', '')) if item.get('platform') else ""

        # 5. Train Number
        raw_train_num = str(item.get('train', ''))
        train_num = re.sub(r'\D', '', raw_train_num) # Keep only digits

        # 6. SIMPLIFIED CALLING POINTS (The Fix)
        # Instead of fetching stops, we simply format the Start -> End string.
        # This removes weird symbols and complex API calls.
        
        # Parse the start station from the route string
        # e.g. "Kyiv - Lviv" -> start="Kyiv", end="Lviv"
        start_station = route.split(' - ')[0] if ' - ' in route else station_name
        if u'\u2192' in route: start_station = route.split(u'\u2192')[0].strip()
        
        # The Final String: "Kyiv -> Lviv (Train 749)"
        departure["calling_at_list"] = f"{start_station} -> {destination} (Train {train_num})"

        departure["carriages"] = 0
        departure["operator"] = "UZ"

        processed_services.append(departure)

    processed_services.sort(key=lambda x: x["aimed_departure_time"])
    return processed_services, station_name

def loadDeparturesForStation(journeyConfig, apiKey, rows):
    station_id = journeyConfig.get("departureStation")
    if not station_id: return [], "Config Error"
    json_data = get_uz_board(station_id)
    return process_uz_data(json_data, journeyConfig)
