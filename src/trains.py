import requests
import uuid
import json
import re
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
    
    Checks added: Proper status code handling, request timeout, and general exceptions.
    """
    # 🚅 Input validation for station_id
    if not isinstance(station_id, str) or not station_id.isdigit():
        print(f"Validation Error: Invalid station ID provided: {station_id}")
        return None

    url = f"https://app.uz.gov.ua/api/station-boards/{station_id}"
    
    # 💡 Generate a new UUID for each session attempt
    session_id = str(uuid.uuid4())
    
    headers = {
        'authority': 'app.uz.gov.ua',
        'accept': 'application/json',
        'user-agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'x-client-locale': 'en',
        'x-session-id': session_id,
        'x-user-agent': 'UZ/2 Web/1 User/guest'
    }

    try:
        # Use a short, strict timeout (10 seconds)
        response = requests.get(url, headers=headers, timeout=10)
        
        # 200: Success
        if response.status_code == 200:
            # 🔍 Check if the content is truly JSON
            try:
                return response.json()
            except json.JSONDecodeError:
                print("UZ API Error: Received 200 but response is not valid JSON.")
                return None
        
        # 400s/500s: Server or client error
        print(f"UZ API Error: Received status code {response.status_code}")
        return None
            
    except requests.exceptions.Timeout:
        print("Connection Error: Request timed out after 10 seconds.")
        return None
    except requests.exceptions.RequestException as e:
        print(f"Connection Error: A network error occurred: {e}")
        return None
    except Exception as e:
        print(f"Connection Error: An unexpected error occurred: {e}")
        return None

# --- DATA TRANSFORMATION ---

def process_uz_data(json_data, journeyConfig):
    """
    Converts UZ JSON format into the specific dictionary format 
    expected by the UK Train Display 'main.py'.
    
    Checks added: Robust dictionary key access and destination name fallback.
    """
    if not json_data:
        # 🛑 Handle cases where API connection failed or returned empty data
        return [], "Connection Failed"

    # 1. Get Station Name - Use .get() with a safe default
    station_name = json_data.get('station', {}).get('name', 'UZ Station (Unknown)')
    
    # 2. Get Departures List - Ensure it's a list
    raw_departures = json_data.get('departures', [])
    if not isinstance(raw_departures, list):
        print("Data Error: 'departures' field is not a list.")
        return [], station_name
        
    processed_services = []

    for item in raw_departures:
        departure = {}

        # --- A. TIME ---
        timestamp = item.get('time')
        if timestamp and isinstance(timestamp, (int, float)):
            try:
                dt = datetime.fromtimestamp(timestamp)
                departure["aimed_departure_time"] = dt.strftime("%H:%M")
            except ValueError:
                departure["aimed_departure_time"] = "Bad Time" # Handle invalid timestamp value
        else:
            departure["aimed_departure_time"] = "--:--"

        # --- B. STATUS ---
        delay = item.get('delay_minutes')
        if isinstance(delay, (int, float)) and delay > 0:
            # Use int() to ensure clean minutes display
            departure["expected_departure_time"] = f"Late {int(delay)}m"
        else:
            departure["expected_departure_time"] = "On time"

        # --- C. DESTINATION ---
        # 🎯 Improved: Prioritize the destination name from the 'destination' object if available
        destination_name = item.get('destination', {}).get('name')
        route = item.get('route', '')
        
        # 🌟 MINIMAL CHANGE: CLEAN THE ROUTE STRING HERE
        route = route.replace('\xa0', ' ').replace(u'\u2192', '->').strip()
        
        if destination_name:
             departure["destination_name"] = destination_name
        elif route:
            # Fallback to parsing the route string if 'destination' object is missing
            if ' - ' in route:
                departure["destination_name"] = route.split(' - ')[-1].strip()
            # The 'u\u2192' handling below is now redundant since we replaced it with '->' above,
            # but leaving the original parsing logic for '->' for robustness.
            elif '->' in route:
                departure["destination_name"] = route.split('->')[-1].strip()
            else:
                departure["destination_name"] = route.strip() # Use the whole route as fallback
        else:
            departure["destination_name"] = "Destination Unknown"

        # --- D. PLATFORM ---
        plat = item.get('platform')
        # Ensure platform is not None before converting to string
        departure["platform"] = str(plat) if plat is not None else "" 

        # --- E. CARRIAGES / OPERATOR (Standard values) ---
        departure["carriages"] = 0
        departure["operator"] = "UZ"

        # --- F. TRAIN NUMBER CLEANUP ---
        raw_train_num = str(item.get('train', ''))
        # Regex: \D means "anything that is NOT a digit". 
        train_num = re.sub(r'\D', '', raw_train_num)
        
        # Fallback to raw number if cleanup results in an empty string
        if not train_num:
            train_num = raw_train_num if raw_train_num else "N/A"

        # --- G. CALLING POINTS ---
        departure["calling_at_list"] = joinWithSpaces(
            f"Train {train_num} to {departure['destination_name']}.",
            f"Route: {route}." if route else None, # Include route only if it exists
            "Ukrainian Railways."
        )

        processed_services.append(departure)

    # Sort by time
    try:
        processed_services.sort(key=lambda x: x["aimed_departure_time"])
    except TypeError:
        # 🛡️ Handle case where time is "Bad Time" or "--:--" and cannot be sorted
        print("Sorting Error: Could not sort services by time.")
        pass

    return processed_services, station_name
# --- MAIN ENTRY POINT ---

def loadDeparturesForStation(journeyConfig, apiKey, rows):
    """
    Main function with enhanced configuration checking.
    """
    # ⚙️ Check for journeyConfig validity
    if not isinstance(journeyConfig, dict):
        print("Config Error: 'journeyConfig' must be a dictionary.")
        return [], "Config Error"

    station_id = journeyConfig.get("departureStation")
    
    if not station_id:
        print("Config Error: 'departureStation' key is missing or empty in config.")
        return [], "Config Error"

    json_data = get_uz_board(station_id)
    departures, station_name = process_uz_data(json_data, journeyConfig)

    # ✂️ Slice the list to return only the requested number of rows
    # Ensure 'rows' is treated as an integer and defaults to a reasonable number
    try:
        limit = int(rows)
    except (TypeError, ValueError):
        limit = 10 # Default to 10 rows if 'rows' argument is bad

    # Only return up to the specified number of rows
    return departures[:limit], station_name
