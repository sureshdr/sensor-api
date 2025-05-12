"""
Authentication and authorization module for Sensor API
-----------------------------------------------------
Handles user authentication and permission checks
"""

import os
import logging
from functools import wraps
from flask import request, jsonify
from dotenv import load_dotenv
import time
import ipaddress

# Load environment variables
load_dotenv()

# Set up logger
logger = logging.getLogger('sensor_api.auth')

# User roles and permissions
ROLE_ADMIN = 'admin'  # Can read and write
ROLE_VIEWER = 'viewer'  # Can only read

# Load users from environment variables
def load_users():
    """Load user credentials and roles from environment variables."""
    users = {}
    
    # Admin user (read/write access)
    admin_username = os.environ.get('API_USERNAME')
    admin_password = os.environ.get('API_PASSWORD')
    
    if admin_username and admin_password:
        users[admin_username] = {
            'password': admin_password,
            'role': ROLE_ADMIN
        }
    
    # Viewer user (read-only access)
    viewer_username = os.environ.get('VIEWER_USERNAME')
    viewer_password = os.environ.get('VIEWER_PASSWORD')
    
    if viewer_username and viewer_password:
        users[viewer_username] = {
            'password': viewer_password,
            'role': ROLE_VIEWER
        }
    
    return users

# Global user dictionary
USERS = load_users()

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

def authenticate_user(auth):
    """
    Authenticate a user based on HTTP Basic Auth credentials.
    Returns (authenticated, user_data) tuple.
    """
    if not auth:
        return False, None
    
    username = auth.username
    password = auth.password
    
    if username in USERS and USERS[username]['password'] == password:
        return True, {
            'username': username,
            'role': USERS[username]['role']
        }
    
    return False, None

def requires_auth(f):
    """Decorator to require authentication for an endpoint."""
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
        authenticated, user_data = authenticate_user(auth)
        
        if not authenticated:
            # Log failed authentication attempt
            logger.warning(f"Failed authentication attempt from {ip_addr}")
            
            # Return 401 Unauthorized with WWW-Authenticate header
            return jsonify({'error': 'Authentication required'}), 401, {
                'WWW-Authenticate': 'Basic realm="Sensor API"'
            }
        
        # Authentication successful
        request.user_data = user_data  # Attach user data to the request
        return f(*args, **kwargs)
    return decorated

def requires_admin(f):
    """Decorator to require admin role (in addition to authentication)."""
    @wraps(f)
    def decorated(*args, **kwargs):
        # First require authentication
        auth_result = requires_auth(lambda *a, **kw: None)(*args, **kwargs)
        if isinstance(auth_result, tuple):  # This means auth failed
            return auth_result
        
        # Check if user has admin role
        if not hasattr(request, 'user_data') or request.user_data.get('role') != ROLE_ADMIN:
            logger.warning(f"Access denied: User {request.user_data.get('username')} attempted to access admin-only resource")
            return jsonify({'error': 'Access denied. Admin privileges required.'}), 403
        
        return f(*args, **kwargs)
    return decorated
