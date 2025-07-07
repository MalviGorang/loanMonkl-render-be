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
        response = requests.get(
            f"https://api.postalpincode.in/pincode/{pincode}",
            timeout=10,  # Add timeout
            headers={"User-Agent": "LoanAssistanceTool/1.0"},  # Add user agent
        )
        response.raise_for_status()
        data = response.json()

        if data and len(data) > 0 and data[0].get("Status") == "Success":
            post_offices = data[0].get("PostOffice", [])
            if post_offices and len(post_offices) > 0:
                post_office = post_offices[0]
                location = {
                    "city": post_office.get("District", ""),
                    "state": post_office.get("State", ""),
                }
                # Cache in MongoDB only if we have valid data
                if location["city"] and location["state"]:
                    try:
                        db.pincode.insert_one(
                            {
                                "pincode": pincode,
                                **location,
                                "region": post_office.get("Region", ""),
                            }
                        )
                    except Exception as db_error:
                        logger.warning(f"Failed to cache pincode data: {db_error}")
                return location

        logger.warning(f"No valid data found for pincode: {pincode}")
        return None
    except requests.exceptions.Timeout:
        logger.error(f"Timeout occurred while fetching pincode data for: {pincode}")
        return None
    except requests.exceptions.RequestException as e:
        logger.error(f"Pincode API call failed: {e}")
        return None
    except (KeyError, IndexError, ValueError) as e:
        logger.error(f"Invalid response format from pincode API: {e}")
        return None
