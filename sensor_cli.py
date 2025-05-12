#!/usr/bin/env python3
"""
Sensor Readings CLI Tool
------------------------
Command-line tool for manually adding, viewing, or importing readings to the database.
"""

import os
import sys
import argparse
from datetime import datetime, timedelta
import csv
import sqlalchemy
from sqlalchemy import create_engine, Column, Integer, Float, DateTime, String
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv
import getpass

# Load environment variables from .env file
load_dotenv()

# Set up SQLAlchemy
Base = declarative_base()

# Define Reading model (must match app.py model)
class Reading(Base):
    """Model for sensor readings."""
    __tablename__ = 'reading'
    
    id = Column(Integer, primary_key=True)
    value = Column(Float, nullable=False)
    timestamp = Column(DateTime, nullable=False, default=datetime.utcnow)
    source_ip = Column(String(45), nullable=True)
    mode = Column(Integer, nullable=True)  # 0 or 1

    def __repr__(self):
        return f"<Reading {self.value} (mode:{self.mode}) at {self.timestamp}>"
    
    def to_dict(self):
        return {
            'id': self.id,
            'value': self.value,
            'mode': self.mode,
            'timestamp': self.timestamp.isoformat(),
            'source_ip': self.source_ip
        }

def connect_to_database():
    """Connect to the database using credentials from .env."""
    # Database configuration
    db_username = os.environ.get('DB_USERNAME')
    db_password = os.environ.get('DB_PASSWORD')
    db_host = os.environ.get('DB_HOST', 'localhost')
    db_name = os.environ.get('DB_NAME', 'readings_db')
    
    # If credentials are not in .env, prompt for them
    if not db_username:
        db_username = input("Database username: ")
    
    if not db_password:
        db_password = getpass.getpass("Database password: ")
        
    # Create database URL
    db_url = f'mysql+pymysql://{db_username}:{db_password}@{db_host}/{db_name}'
    
    try:
        # Create engine and connect
        engine = create_engine(db_url)
        # Check connection
        engine.connect()
        print(f"Connected to database '{db_name}' on {db_host}")
        
        # Create session
        Session = sessionmaker(bind=engine)
        return Session()
    except Exception as e:
        print(f"Error connecting to database: {str(e)}")
        sys.exit(1)

def add_reading(args):
    """Add a single reading to the database."""
    # Connect to the database
    session = connect_to_database()
    
    try:
        # Validate reading value
        if not (0.0 <= args.value <= 50.0):
            print("Error: Reading value must be between 0.0 and 50.0")
            return
        
        # Validate mode value if provided
        if args.mode is not None and args.mode not in [0, 1]:
            print("Error: Mode value must be either 0 or 1")
            return
        
        # Parse timestamp if provided, otherwise use current time
        timestamp = None
        if args.timestamp:
            try:
                timestamp = datetime.fromisoformat(args.timestamp)
            except ValueError:
                print("Error: Invalid timestamp format. Use ISO format (YYYY-MM-DDTHH:MM:SS)")
                return
        else:
            timestamp = datetime.utcnow()
        
        # Create new reading
        new_reading = Reading(
            value=args.value,
            mode=args.mode,
            timestamp=timestamp,
            source_ip='CLI'
        )
        
        # Add to database
        session.add(new_reading)
        session.commit()
        
        print(f"Reading added successfully (ID: {new_reading.id}):")
        print(f"  Value: {new_reading.value}")
        print(f"  Mode: {new_reading.mode}")
        print(f"  Timestamp: {new_reading.timestamp}")
        
    except Exception as e:
        session.rollback()
        print(f"Error adding reading: {str(e)}")
    finally:
        session.close()

def list_readings(args):
    """List readings from the database."""
    # Connect to the database
    session = connect_to_database()
    
    try:
        # Build query
        query = session.query(Reading)
        
        # Apply filters
        if args.days:
            cutoff = datetime.utcnow() - timedelta(days=args.days)
            query = query.filter(Reading.timestamp >= cutoff)
            
        if args.mode is not None:
            query = query.filter(Reading.mode == args.mode)
            
        # Apply sorting
        if args.sort == 'newest':
            query = query.order_by(Reading.timestamp.desc())
        else:  # oldest
            query = query.order_by(Reading.timestamp.asc())
            
        # Apply limit
        if args.limit:
            query = query.limit(args.limit)
            
        # Execute query
        readings = query.all()
        
        # Display results
        if not readings:
            print("No readings found.")
            return
            
        print(f"Found {len(readings)} readings:")
        print("-" * 80)
        print(f"{'ID':>5} | {'Value':>8} | {'Mode':>4} | {'Timestamp':>25} | Source")
        print("-" * 80)
        
        for reading in readings:
            print(f"{reading.id:5d} | {reading.value:8.2f} | {reading.mode if reading.mode is not None else 'N/A':>4} | {reading.timestamp.isoformat():25} | {reading.source_ip}")
        
    except Exception as e:
        print(f"Error listing readings: {str(e)}")
    finally:
        session.close()

def import_csv(args):
    """Import readings from a CSV file."""
    # Connect to the database
    session = connect_to_database()
    
    try:
        # Check if file exists
        if not os.path.isfile(args.file):
            print(f"Error: File '{args.file}' not found.")
            return
            
        # Read CSV file
        readings_added = 0
        readings_skipped = 0
        
        with open(args.file, 'r') as f:
            reader = csv.DictReader(f)
            
            # Validate CSV structure
            required_fields = ['value']
            for field in required_fields:
                if field not in reader.fieldnames:
                    print(f"Error: CSV file must contain '{field}' column.")
                    return
            
            # Process rows
            for row in reader:
                try:
                    # Extract and validate value
                    value = float(row['value'])
                    if not (0.0 <= value <= 50.0):
                        print(f"Skipping row: value {value} not in range 0.0-50.0")
                        readings_skipped += 1
                        continue
                    
                    # Extract mode if present
                    mode = None
                    if 'mode' in row and row['mode']:
                        mode = int(row['mode'])
                        if mode not in [0, 1]:
                            print(f"Skipping row: mode {mode} not 0 or 1")
                            readings_skipped += 1
                            continue
                    
                    # Extract timestamp if present
                    timestamp = datetime.utcnow()
                    if 'timestamp' in row and row['timestamp']:
                        try:
                            timestamp = datetime.fromisoformat(row['timestamp'])
                        except ValueError:
                            print(f"Warning: Invalid timestamp format in row. Using current time.")
                    
                    # Create reading
                    new_reading = Reading(
                        value=value,
                        mode=mode,
                        timestamp=timestamp,
                        source_ip=f'CSV Import ({args.file})'
                    )
                    
                    # Add to database
                    session.add(new_reading)
                    readings_added += 1
                    
                except Exception as e:
                    print(f"Error processing row: {str(e)}")
                    readings_skipped += 1
            
            # Commit all readings at once
            session.commit()
            
        print(f"Import complete: {readings_added} readings added, {readings_skipped} skipped.")
        
    except Exception as e:
        session.rollback()
        print(f"Error importing CSV: {str(e)}")
    finally:
        session.close()

def delete_readings(args):
    """Delete readings from the database."""
    # Connect to the database
    session = connect_to_database()
    
    try:
        # Confirm deletion
        if not args.force:
            confirm = input("Are you sure you want to delete readings? This cannot be undone. (y/n): ")
            if confirm.lower() != 'y':
                print("Operation cancelled.")
                return
                
        # Build query
        query = session.query(Reading)
        
        # Apply filters
        if args.id:
            query = query.filter(Reading.id == args.id)
        
        if args.days:
            cutoff = datetime.utcnow() - timedelta(days=args.days)
            query = query.filter(Reading.timestamp >= cutoff)
            
        if args.before:
            try:
                before_date = datetime.fromisoformat(args.before)
                query = query.filter(Reading.timestamp <= before_date)
            except ValueError:
                print("Error: Invalid before date format. Use ISO format (YYYY-MM-DDTHH:MM:SS)")
                return
                
        if args.mode is not None:
            query = query.filter(Reading.mode == args.mode)
            
        # Get count for confirmation
        count = query.count()
        if count == 0:
            print("No readings match the criteria. Nothing to delete.")
            return
            
        # Confirm again for large deletions
        if count > 10 and not args.force:
            confirm = input(f"This will delete {count} readings. Are you absolutely sure? (y/n): ")
            if confirm.lower() != 'y':
                print("Operation cancelled.")
                return
                
        # Execute deletion
        deleted = query.delete()
        session.commit()
        
        print(f"Successfully deleted {deleted} readings.")
        
    except Exception as e:
        session.rollback()
        print(f"Error deleting readings: {str(e)}")
    finally:
        session.close()

def main():
    """Main function to parse arguments and execute commands."""
    # Create argument parser
    parser = argparse.ArgumentParser(description='Sensor Readings CLI Tool')
    subparsers = parser.add_subparsers(dest='command', help='Command to execute')
    
    # Add command
    add_parser = subparsers.add_parser('add', help='Add a single reading')
    add_parser.add_argument('value', type=float, help='Reading value (0.0-50.0)')
    add_parser.add_argument('--mode', '-m', type=int, choices=[0, 1], help='Mode value (0 or 1)')
    add_parser.add_argument('--timestamp', '-t', help='Timestamp in ISO format (YYYY-MM-DDTHH:MM:SS). Default: now')
    
    # List command
    list_parser = subparsers.add_parser('list', help='List readings')
    list_parser.add_argument('--days', '-d', type=int, help='Only show readings from the last N days')
    list_parser.add_argument('--mode', '-m', type=int, choices=[0, 1], help='Filter by mode')
    list_parser.add_argument('--limit', '-l', type=int, default=20, help='Maximum number of readings to display (default: 20)')
    list_parser.add_argument('--sort', '-s', choices=['newest', 'oldest'], default='newest', help='Sort order (default: newest)')
    
    # Import command
    import_parser = subparsers.add_parser('import', help='Import readings from a CSV file')
    import_parser.add_argument('file', help='Path to CSV file')
    
    # Delete command
    delete_parser = subparsers.add_parser('delete', help='Delete readings')
    delete_parser.add_argument('--id', type=int, help='Delete a specific reading by ID')
    delete_parser.add_argument('--days', '-d', type=int, help='Delete readings from the last N days')
    delete_parser.add_argument('--before', '-b', help='Delete readings before this date (ISO format)')
    delete_parser.add_argument('--mode', '-m', type=int, choices=[0, 1], help='Delete readings with this mode')
    delete_parser.add_argument('--force', '-f', action='store_true', help='Skip confirmation prompt')
    
    # Parse arguments
    args = parser.parse_args()
    
    # Execute command
    if args.command == 'add':
        add_reading(args)
    elif args.command == 'list':
        list_readings(args)
    elif args.command == 'import':
        import_csv(args)
    elif args.command == 'delete':
        delete_readings(args)
    else:
        parser.print_help()

if __name__ == '__main__':
    main()
