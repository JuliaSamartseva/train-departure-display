import requests
import uuid
import json
import re  # Added for removing letters from train numbers
from datetime import datetime

# --- HELPER FUNCTIONS ---

def joinWithSpaces(*args):
    """
    Helper to join strings with spaces, filtering out empty ones.
    Used to construct the 'calling at' text for the scrolling display.
    """
    return " ".join(filter(None, args))

# --- API CONNECTION ---

def get_uz_board(station_id):
    """
    Connects to the UZ API to get the raw departure board.
    """
    url = f"https://app.uz.gov.ua/api/station-boards/{station_id}"
    
    session_id = str(uuid.uuid4())
    
    headers = {
        'authority': 'app.uz.gov.ua',
        'accept': 'application/json',
        'user-agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'x-client-locale': 'en',  # Forces English for Cities
        'x-session-id': session_id,
        'x-user-agent': 'UZ/2 Web/1 User/guest'
    }

    try:
        response = requests.get(url, headers=headers, timeout=10)
        
        if response.status_code == 200:
            return response.json()
        else:
            print(f"UZ API Error: Received status code {response.status_code}")
            return None
            
    except Exception as e:
        print(f"Connection Error: {e}")
        return None

# --- DATA TRANSFORMATION ---

def process_uz_data(json_data, journeyConfig):
    """
    Converts UZ JSON format into the specific dictionary format 
    expected by the UK Train Display 'main.py'.
    """
    if not json_data:
        return [], "Connection Failed"

    # 1. Get Station Name
    station_name = json_data.get('station', {}).get('name', 'UZ Station')
    
    # 2. Get Departures List
    raw_departures = json_data.get('departures', [])
    processed_services = []

    for item in raw_departures:
        departure = {}

        # --- A. TIME ---
        timestamp = item.get('time')
        if timestamp:
            dt = datetime.fromtimestamp(timestamp)
            departure["aimed_departure_time"] = dt.strftime("%H:%M")
        else:
            departure["aimed_departure_time"] = "--:--"

        # --- B. STATUS ---
        delay = item.get('delay_minutes')
        if delay and delay > 0:
            departure["expected_departure_time"] = f"Late {delay}m"
        else:
            departure["expected_departure_time"] = "On time"

        # --- D. PLATFORM ---
        plat = item.get('platform')
        if plat:
            departure["platform"] = str(plat)
        else:
            departure["platform"] = "" 

        # --- E. CARRIAGES ---
        departure["carriages"] = 0
        departure["operator"] = "UZ"

        # --- F. TRAIN NUMBER CLEANUP ---
        # Get the raw number (e.g. "97К")
        raw_train_num = str(item.get('train', ''))
        
        # Regex: \D means "anything that is NOT a digit". We replace it with empty string.
        # "97К" -> "97"
        train_num = re.sub(r'\D', '', raw_train_num)

        # --- G. CALLING POINTS ---
        departure["calling_at_list"] = joinWithSpaces(
            f"Train {train_num} to {departure['destination_name']}. ",
            "Ukrainian Railways."
        )

        processed_services.append(departure)

    # Sort by time
    processed_services.sort(key=lambda x: x["aimed_departure_time"])

    return processed_services, station_name

# --- MAIN ENTRY POINT ---

def loadDeparturesForStation(journeyConfig, apiKey, rows):
    station_id = journeyConfig.get("departureStation")
    
    if not station_id:
        print("Error: 'departureStation' is missing in config.")
        return [], "Config Error"

    json_data = get_uz_board(station_id)
    departures, station_name = process_uz_data(json_data, journeyConfig)

    return departures, station_name
