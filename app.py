"""
Sensor Reading API v1.0
-----------------------
A Flask REST API that saves sensor readings to a MariaDB database
and generates time-series graphs using Python's Matplotlib.
"""

from flask import Flask, request, jsonify, render_template, send_from_directory, abort
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, timedelta
import os
from dotenv import load_dotenv
from functools import wraps
import base64
import secrets
import logging
from logging.handlers import RotatingFileHandler
import time
import re
import ipaddress

# Import the graph manager after it's been created
from graph_manager import GraphManager

# Load environment variables
load_dotenv()

# Configure logging
log_dir = os.environ.get('LOG_DIR', 'logs')
os.makedirs(log_dir, exist_ok=True)
log_file = os.path.join(log_dir, 'app.log')

# Configure the logger
logger = logging.getLogger('sensor_api')
logger.setLevel(logging.INFO)
handler = RotatingFileHandler(log_file, maxBytes=10485760, backupCount=5)
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)
logger.addHandler(handler)

# Authentication configuration
API_USERNAME = os.environ.get('API_USERNAME')
API_PASSWORD = os.environ.get('API_PASSWORD')

# Validate that authentication credentials are set
if not API_USERNAME or not API_PASSWORD or API_PASSWORD == 'change_this_password':
    logger.warning("Warning: Using default or empty API credentials. This is insecure!")

# Rate limiting configuration
RATE_LIMIT_WINDOW = int(os.environ.get('RATE_LIMIT_WINDOW', 60))  # seconds
MAX_REQUESTS = int(os.environ.get('MAX_REQUESTS', 10))  # max requests per window
request_history = {}  # IP address -> list of timestamps

# Allowed IP ranges (optional)
allowed_ips_str = os.environ.get('ALLOWED_IPS', '')
allowed_ip_ranges = []
if allowed_ips_str:
    for ip_range in allowed_ips_str.split(','):
        try:
            allowed_ip_ranges.append(ipaddress.ip_network(ip_range.strip(), strict=False))
        except ValueError as e:
            logger.error(f"Invalid IP range: {ip_range} - {str(e)}")

app = Flask(__name__)

# Database configuration with timeout and connection pooling
db_username = os.environ.get('DB_USERNAME')
db_password = os.environ.get('DB_PASSWORD') 
db_host = os.environ.get('DB_HOST', 'localhost')
db_name = os.environ.get('DB_NAME', 'readings_db')

if not all([db_username, db_password]):
    logger.error("Database credentials not configured properly")
    raise ValueError("Database credentials must be configured in .env file")

# SQLAlchemy configuration with safety options
app.config['SQLALCHEMY_DATABASE_URI'] = f'mysql+pymysql://{db_username}:{db_password}@{db_host}/{db_name}'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
    'pool_recycle': 280,  # recycle connections before MySQL default timeout
    'pool_pre_ping': True,  # verify connection is active before using
    'connect_args': {'connect_timeout': 10}  # connection timeout in seconds
}

# Initialize the database
db = SQLAlchemy(app)

# Initialize Graph manager
graph_dir = os.environ.get('GRAPH_DIR', 'static/graph')
graph_manager = GraphManager(graph_dir=graph_dir)

# IP address restriction
def check_ip_allowed(ip_addr):
    """Check if an IP address is allowed based on configured ranges."""
    if not allowed_ip_ranges:
        return True  # No restrictions if no ranges defined
    
    try:
        ip = ipaddress.ip_address(ip_addr)
        for allowed_range in allowed_ip_ranges:
            if ip in allowed_range:
                return True
        return False
    except ValueError:
        return False  # Invalid IP address format

# Rate limiting function
def is_rate_limited(ip_addr):
    """Check if an IP is being rate limited due to too many requests."""
    now = time.time()
    
    # Initialize or clean up old requests for this IP
    if ip_addr not in request_history:
        request_history[ip_addr] = []
    else:
        # Remove timestamps older than the window
        request_history[ip_addr] = [t for t in request_history[ip_addr] 
                                   if now - t < RATE_LIMIT_WINDOW]
    
    # Check if too many requests
    if len(request_history[ip_addr]) >= MAX_REQUESTS:
        return True
    
    # Record this request
    request_history[ip_addr].append(now)
    return False

# Authentication decorator
def requires_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        # Get client IP address
        ip_addr = request.remote_addr
        
        # Check if IP is allowed (if restriction is enabled)
        if not check_ip_allowed(ip_addr):
            logger.warning(f"Blocked request from unauthorized IP: {ip_addr}")
            return jsonify({'error': 'Access denied'}), 403
        
        # Check rate limiting
        if is_rate_limited(ip_addr):
            logger.warning(f"Rate limited request from IP: {ip_addr}")
            return jsonify({'error': 'Too many requests'}), 429
            
        # Check authentication
        auth = request.authorization
        
        if not auth or auth.username != API_USERNAME or auth.password != API_PASSWORD:
            # Log failed authentication attempt
            logger.warning(f"Failed authentication attempt from {ip_addr}")
            
            # Return 401 Unauthorized with WWW-Authenticate header
            return jsonify({'error': 'Authentication required'}), 401, {
                'WWW-Authenticate': 'Basic realm="Sensor API"'
            }
        
        # Authentication successful
        return f(*args, **kwargs)
    return decorated

# Define Reading model
class Reading(db.Model):
    """Model for sensor readings."""
    id = db.Column(db.Integer, primary_key=True)
    value = db.Column(db.Float, nullable=False)
    timestamp = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    source_ip = db.Column(db.String(45), nullable=True)  # Store source IP for audit
    mode = db.Column(db.Integer, nullable=True)  # New field for the 'm' parameter (0 or 1)

    def __repr__(self):
        return f'<Reading {self.value} (mode:{self.mode}) at {self.timestamp}>'

    def to_dict(self):
        return {
            'id': self.id,
            'value': self.value,
            'mode': self.mode,
            'timestamp': self.timestamp.isoformat()
        }


# API routes
@app.route('/measure', methods=['GET'])
@requires_auth
def add_reading():
    """Add a new sensor reading."""
    try:
        # Get the reading value from query parameter
        reading_value = request.args.get('reading', type=float)
        
        # Get the mode parameter (0 or 1)
        mode_value = request.args.get('m', type=int)
        
        # Validate the reading value
        if reading_value is None:
            return jsonify({'error': 'Missing or invalid reading parameter. Must be a float value.'}), 400
        
        # Validate reading range (0.0 to 50.0)
        if not (0.0 <= reading_value <= 50.0):
            return jsonify({
                'error': 'Reading value must be between 0.0 and 50.0'
            }), 400
        
        # Validate the mode value
        if mode_value is not None and mode_value not in [0, 1]:
            return jsonify({'error': 'Mode parameter (m) must be either 0 or 1'}), 400
        
        # Create new reading record with source IP and mode
        new_reading = Reading(
            value=reading_value,
            mode=mode_value,
            source_ip=request.remote_addr
        )
        
        # Save to database
        db.session.add(new_reading)
        db.session.commit()
        
        # Log the new reading
        logger.info(f"New reading added: {reading_value} (mode:{mode_value}) from {request.remote_addr}")
        
        # Generate updated graphs
        all_readings = Reading.query.all()
        graph_manager.generate_graphs(all_readings)
        
        return jsonify({
            'message': 'Reading saved successfully',
            'reading': new_reading.to_dict()
        }), 201
        
    except Exception as e:
        # Log the error but don't expose details to the client
        logger.error(f"Error adding reading: {str(e)}")
        db.session.rollback()
        return jsonify({'error': 'An error occurred while processing your request'}), 500

# Route to get all readings
@app.route('/readings', methods=['GET'])
@requires_auth
def get_readings():
    """Get all stored readings."""
    try:
        # Optional pagination
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 100, type=int)
        
        # Limit maximum per_page to prevent resource exhaustion
        per_page = min(per_page, 1000)
        
        # Query with pagination
        readings_query = Reading.query.order_by(Reading.timestamp.desc())
        paginated_readings = readings_query.paginate(page=page, per_page=per_page)
        
        return jsonify({
            'page': page,
            'per_page': per_page,
            'total': paginated_readings.total,
            'pages': paginated_readings.pages,
            'readings': [reading.to_dict() for reading in paginated_readings.items]
        })
    except Exception as e:
        logger.error(f"Error retrieving readings: {str(e)}")
        return jsonify({'error': 'An error occurred while retrieving readings'}), 500

# Route to get readings for a specific time period
@app.route('/readings/<period>', methods=['GET'])
@requires_auth
def get_period_readings(period):
    """Get readings for a specific time period."""
    try:
        # Define time periods
        periods = {
            'hour': 1,
            'day': 24,
            'week': 168,
            'month': 720
        }
        
        # Get hours for the requested period (default to day if invalid)
        if period not in periods:
            return jsonify({'error': f'Invalid period. Must be one of: {", ".join(periods.keys())}'}), 400
            
        hours = periods.get(period)
        
        # Calculate the start date
        start_date = datetime.utcnow() - timedelta(hours=hours)
        
        # Query readings after the start date
        readings = Reading.query.filter(Reading.timestamp >= start_date).all()
        
        return jsonify({
            'period': period,
            'hours': hours,
            'count': len(readings),
            'readings': [reading.to_dict() for reading in readings]
        })
    except Exception as e:
        logger.error(f"Error retrieving period readings: {str(e)}")
        return jsonify({'error': 'An error occurred while retrieving readings'}), 500

# Route to view graphs
@app.route('/graph', methods=['GET'])
def view_graphs():
    """View graphs of readings."""
    try:
        # Get all readings and generate graphs
        readings = Reading.query.all()
        graphs = graph_manager.generate_graphs(readings)
        
        # Get a recent reading for quick display
        latest_reading = Reading.query.order_by(Reading.timestamp.desc()).first()
        latest_value = latest_reading.value if latest_reading else None
        latest_time = latest_reading.timestamp if latest_reading else None
        
        return render_template(
            'graphs.html', 
            graphs=graphs, 
            latest_value=latest_value,
            latest_time=latest_time,
            now=datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
        )
    except Exception as e:
        logger.error(f"Error generating graphs: {str(e)}")
        return render_template('error.html', error="Could not generate graphs"), 500

# Route to access static files
@app.route('/graph/<path:filename>')
@requires_auth
def serve_graph(filename):
    """Serve graph image files."""
    # Validate filename to prevent directory traversal
    if not re.match(r'^[a-zA-Z0-9_\-]+\.(png|jpg|jpeg|gif)$', filename):
        logger.warning(f"Invalid graph filename requested: {filename}")
        abort(404)
        
    return send_from_directory(graph_dir, filename)

# Route for the homepage
@app.route('/', methods=['GET'])
@requires_auth
def home():
    """Display the homepage."""
    try:
        # Get latest reading
        latest_reading = Reading.query.order_by(Reading.timestamp.desc()).first()
        
        # Get readings for the last 24 hours for an embedded graph
        cutoff = datetime.utcnow() - timedelta(hours=24)
        recent_readings = Reading.query.filter(Reading.timestamp >= cutoff).all()
        
        # Generate an embedded graph
        embedded_graph = graph_manager.get_embedded_graph(recent_readings, hours=24)
        
        return render_template(
            'index.html',
            latest_reading=latest_reading,
            embedded_graph=embedded_graph
        )
    except Exception as e:
        logger.error(f"Error rendering homepage: {str(e)}")
        return render_template('error.html', error="Could not render homepage"), 500

# Error handlers
@app.errorhandler(404)
def not_found(error):
    return render_template('error.html', error="Page not found"), 404

@app.errorhandler(500)
def server_error(error):
    return render_template('error.html', error="Internal server error"), 500

if __name__ == '__main__':
    # Create static directory for graphs if it doesn't exist
    os.makedirs(graph_dir, exist_ok=True)
    
    # Create templates directory if it doesn't exist
    os.makedirs('templates', exist_ok=True)
    
    # Create tables if they don't exist
    with app.app_context():
        db.create_all()
    
    # Run the app
    debug_mode = os.environ.get('DEBUG', 'False').lower() == 'true'
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)), debug=debug_mode)
