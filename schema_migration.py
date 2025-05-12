"""
Database Schema Migration Script for Sensor API
----------------------------------------------
Adds the new 'mode' column to the Reading table
"""

import os
from dotenv import load_dotenv
from sqlalchemy import create_engine, Column, Integer, MetaData, Table

# Load environment variables from .env file
load_dotenv()

# Database configuration
db_username = os.environ.get('DB_USERNAME')
db_password = os.environ.get('DB_PASSWORD')
db_host = os.environ.get('DB_HOST', 'localhost')
db_name = os.environ.get('DB_NAME', 'readings_db')

# Create database URL
db_url = f'mysql+pymysql://{db_username}:{db_password}@{db_host}/{db_name}'

# Create engine and connect to the database
engine = create_engine(db_url)
connection = engine.connect()

# Set up metadata for reflection
metadata = MetaData()
metadata.reflect(bind=engine)

# Check if the Reading table exists
if 'reading' in metadata.tables:
    reading_table = metadata.tables['reading']
    
    # Check if the mode column already exists
    if 'mode' not in reading_table.columns:
        print("Adding 'mode' column to Reading table...")
        
        # Begin a transaction
        trans = connection.begin()
        
        try:
            # Execute the ALTER TABLE statement
            connection.execute('ALTER TABLE reading ADD COLUMN mode INTEGER NULL')
            
            # Commit the transaction
            trans.commit()
            print("Migration successful! Added 'mode' column to Reading table.")
        except Exception as e:
            # Roll back the transaction if there was an error
            trans.rollback()
            print(f"Error during migration: {str(e)}")
    else:
        print("The 'mode' column already exists in the Reading table.")
else:
    print("The Reading table does not exist. Run the application first to create it.")

# Close the connection
connection.close()
print("Migration script completed.")
