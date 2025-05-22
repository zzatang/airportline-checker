"""
airport_line_test.py
Quick check for delays on Sydney Trains T8 (Airport & South Line)

To run this script on a schedule, use:
- Windows Task Scheduler
- Linux/macOS: cron (e.g. `*/10 * * * * python3 /path/to/airport_line_test.py`)

The script only sends a Telegram alert if delays are detected (≥5 min).
Logs are written to 'airport_line_alert.log'.
"""

import os
import sys
import logging
from datetime import datetime
import requests
from dotenv import load_dotenv

# ---- settings ----
load_dotenv()  # Load environment variables from .env
API_KEY = os.getenv("TFNSW_API_KEY")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHATID = os.getenv("TELEGRAM_CHATID")
FEED_URL = "https://api.transport.nsw.gov.au/v2/gtfs/realtime/sydneytrains"
ROUTE_ID_PREFIX = "2-T8"  # Airport & South Line routes start with this
DELAY_CUTOFF_SEC = 5 * 60  # 5-minute threshold

def fetch_feed():
    """Download the GTFS-Realtime Trip Updates feed and return a parsed FeedMessage."""
    from google.transit import gtfs_realtime_pb2  # comes from gtfs-realtime-bindings
    headers = {
        "Authorization": f"apikey {API_KEY}",
        "Accept": "application/x-google-protobuf"
    }
    resp = requests.get(FEED_URL, headers=headers, timeout=10)
    resp.raise_for_status()  # crash loudly if the call failed
    feed = gtfs_realtime_pb2.FeedMessage()
    feed.ParseFromString(resp.content)
    return feed

def send_telegram_message(text):
    """Send a message to the configured Telegram chat."""
    if not TELEGRAM_TOKEN or not TELEGRAM_CHATID:
        logging.error("Telegram credentials not set in .env!")
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    try:
        resp = requests.get(url, params={"chat_id": TELEGRAM_CHATID, "text": text}, timeout=10)
        if resp.status_code != 200:
            logging.error(f"Failed to send Telegram message: {resp.text}")
        else:
            logging.info("Telegram alert sent successfully.")
    except Exception as e:
        logging.error(f"Exception sending Telegram message: {e}")

def find_t8_delays(feed):
    """Return a list of (trip_id, stop_name, delay_minutes) for T8 trips running late."""
    t8_delays = []
    for ent in feed.entity:
        if not ent.HasField("trip_update"):
            continue
        tu = ent.trip_update
        if not tu.trip.route_id.startswith(ROUTE_ID_PREFIX):
            continue  # skip other lines

        # Look through each stop-time update for this trip
        for stu in tu.stop_time_update:
            if stu.HasField("arrival") and stu.arrival.HasField("delay"):
                delay_sec = stu.arrival.delay
                if delay_sec >= DELAY_CUTOFF_SEC:
                    stop_id = stu.stop_id
                    delay_min = delay_sec // 60
                    t8_delays.append(
                        (tu.trip.trip_id, stop_id, delay_min)
                    )
                    break  # one late stop is enough – go to next trip
    return t8_delays

def format_delay_message(delays):
    if not delays:
        return "No significant T8 delays detected."
    msg = "T8 Airport Line Delays:\n"
    for trip_id, stop_id, delay_min in delays:
        msg += f"Trip {trip_id} delayed {delay_min} min at stop {stop_id}\n"
    return msg.strip()

def main():
    print("🔄 Contacting TfNSW real-time feed …")
    try:
        feed = fetch_feed()
        print(feed)
    except Exception as e:
        print(f"❌ Could not fetch feed: {e}")
        return

    delays = find_t8_delays(feed)
    if not delays:
        print("✅ No T8 delays above 5 min right now.")
    else:
        print(f"⚠️  {len(delays)} T8 service(s) running late ≥5 min:")
        for trip_id, stop_id, mins in delays:
            print(f"  • trip {trip_id} is +{mins} min at stop {stop_id}")

if __name__ == "__main__":
    # Set up logging
    logging.basicConfig(
        filename="airport_line_alert.log",
        level=logging.INFO,
        format="%(asctime)s %(levelname)s: %(message)s"
    )
    if len(sys.argv) > 1 and sys.argv[1] == "--test-alert":
        send_telegram_message("There is delay on T8 line")
        print("Test alert sent to Telegram.")
    else:
        try:
            logging.info("Checking T8 delays...")
            feed = fetch_feed()
            delays = find_t8_delays(feed)
            if delays:
                message = format_delay_message(delays)
                send_telegram_message(message)
                print("Alert sent:", message)
                logging.info(f"Alert sent: {message}")
            else:
                print("✅ No T8 delays above 5 min right now.")
                logging.info("No significant T8 delays detected.")
        except Exception as e:
            print(f"Error: {e}")
            logging.error(f"Exception occurred: {e}")
