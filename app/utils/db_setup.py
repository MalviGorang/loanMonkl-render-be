# Database setup utilities

import logging
import os
import pymongo
from fastapi import HTTPException

# Configure logging
logger = logging.getLogger(__name__)

def setup_db_indexes():
    """
    Set up necessary database indexes for the application.
    This should be called during application startup.
    """
    try:
        client = pymongo.MongoClient(os.getenv("MONGO_URI"))
        db = client["FA_bots"]
        
        # Check and drop all existing indexes that might be causing issues
        try:
            existing_indexes = db.students.index_information()
            for index_name, index_info in existing_indexes.items():
                # Skip the default _id index
                if index_name == '_id_':
                    continue
                
                # Drop any unique indexes on email or email+mobile
                if 'unique' in index_info and index_info.get('unique', False):
                    logger.info(f"Dropping unique index: {index_name}")
                    db.students.drop_index(index_name)
                    logger.info(f"Unique index {index_name} dropped successfully")
                
                # Also drop any index with 'email_mobile' in the name
                if 'email_mobile' in index_name:
                    logger.info(f"Dropping email_mobile index: {index_name}")
                    db.students.drop_index(index_name)
                    logger.info(f"email_mobile index {index_name} dropped successfully")
        except Exception as e:
            logger.warning(f"Error checking/dropping indexes: {e}")
        
        # Create a non-unique index on email field for performance
        db.students.create_index([("email", pymongo.ASCENDING)], 
                                 name="email_1",
                                 background=True)
        logger.info("Created non-unique email index")
        
        # Create a compound index on email and mobile for better query performance
        # This is NON-UNIQUE to allow the same email with different mobiles
        db.students.create_index([("email", pymongo.ASCENDING), ("mobile", pymongo.ASCENDING)], 
                                 name="email_mobile_1",
                                 background=True)
        logger.info("Created compound email_mobile index")
        
        logger.info("Database indexes set up successfully")
    except Exception as e:
        logger.error(f"Failed to set up database indexes: {e}")
        raise HTTPException(status_code=500, detail="Database setup failed")
