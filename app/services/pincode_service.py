# backend/app/services/pincode_service.py
# Pincode lookup service for city and state

import requests
import logging
from typing import Optional, Dict
from pymongo import MongoClient
import os

logger = logging.getLogger(__name__)

# MongoDB client
client = MongoClient(os.getenv("MONGO_URI"))
db = client["FA_bots"]


def get_location_from_pincode(pincode: str) -> Optional[Dict]:
    """Fetch city and state from pincode using MongoDB or external API."""
    # Check MongoDB first
    pincode_doc = db.pincode.find_one({"pincode": pincode})
    if pincode_doc:
        return {"city": pincode_doc["city"], "state": pincode_doc["state"]}

    # Fallback to external API (e.g., postalpincode.in)
    try:
        response = requests.get(f"https://api.postalpincode.in/pincode/{pincode}")
        response.raise_for_status()
        data = response.json()
        if data[0]["Status"] == "Success":
            post_office = data[0]["PostOffice"][0]
            location = {"city": post_office["District"], "state": post_office["State"]}
            # Cache in MongoDB
            db.pincode.insert_one(
                {
                    "pincode": pincode,
                    **location,
                    "region": post_office.get("Region", ""),
                }
            )
            return location
        return None
    except requests.exceptions.RequestException as e:
        logger.error(f"Pincode API call failed: {e}")
        return None
