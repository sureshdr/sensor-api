"""
Graph Manager for Sensor Readings
---------------------------------
Generates matplotlib-based graphs for sensor readings over different time periods.
"""

import os
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from datetime import datetime, timedelta
import numpy as np
from io import BytesIO
import base64
import logging

# Set up logger
logger = logging.getLogger('sensor_api.graph_manager')

class GraphManager:
    """Manages the generation of time-series graphs for sensor readings."""
    
    def __init__(self, graph_dir="static/graph"):
        """
        Initialize the graph manager.
        
        Args:
            graph_dir (str): Directory where graph images will be stored
        """
        # Create directory if it doesn't exist
        self.graph_dir = graph_dir
        os.makedirs(self.graph_dir, exist_ok=True)
        
        # Set up graph styling
        plt.style.use('seaborn-v0_8-darkgrid')
        
        logger.info(f"Graph Manager initialized with directory: {graph_dir}")
    
    def generate_graphs(self, readings):
        """
        Generate graphs for different time periods.
        
        Args:
            readings (list): List of Reading objects with timestamp and value attributes
        
        Returns:
            list: List of dictionaries with graph information
        """
        if not readings:
            logger.warning("No readings provided to generate graphs")
            return []
            
        try:
            # Sort readings by timestamp
            readings = sorted(readings, key=lambda x: x.timestamp)
            
            graph_files = []
            
            # Define time periods for graphs
            time_periods = [
                {"name": "hourly", "title": "Last Hour", "hours": 1, "width": 10},
                {"name": "daily", "title": "Last 24 Hours", "hours": 24, "width": 12},
                {"name": "weekly", "title": "Last Week", "hours": 168, "width": 14},
                {"name": "monthly", "title": "Last Month", "hours": 720, "width": 15}
            ]
            
            current_time = datetime.utcnow()
            
            for period in time_periods:
                # Filter readings for current period
                period_start = current_time - timedelta(hours=period["hours"])
                period_readings = [r for r in readings if r.timestamp >= period_start]
                
                # Create the graph
                try:
                    fig_path = self._create_graph(
                        period_readings, 
                        period["name"], 
                        period["title"],
                        period["width"]
                    )
                    
                    graph_files.append({
                        "period": period["name"],
                        "title": period["title"],
                        "file": f"/graph/{period['name']}.png"  # URL path
                    })
                except Exception as e:
                    logger.error(f"Error creating graph for {period['name']}: {str(e)}")
            
            logger.info(f"Generated {len(graph_files)} graphs")
            return graph_files
            
        except Exception as e:
            logger.error(f"Error in generate_graphs: {str(e)}")
            return []
        
    def _create_graph(self, readings, name, title, width):
        """
        Create a single graph for the given readings and time period.
        
        Args:
            readings (list): List of Reading objects
            name (str): Name identifier for the graph
            title (str): Display title for the graph
            width (int): Width of the graph in inches
            
        Returns:
            str: Path to the saved graph file
        """
        # Extract timestamps and values, and separate readings by mode
        timestamps = [r.timestamp for r in readings]
        values = [r.value for r in readings]
        
        # Group readings by mode (0 or 1) - for separate visualization
        mode0_readings = [r for r in readings if r.mode == 0]
        mode1_readings = [r for r in readings if r.mode == 1]
        mode_none_readings = [r for r in readings if r.mode is None]
        
        mode0_timestamps = [r.timestamp for r in mode0_readings]
        mode0_values = [r.value for r in mode0_readings]
        
        mode1_timestamps = [r.timestamp for r in mode1_readings]
        mode1_values = [r.value for r in mode1_readings]
        
        # Set up the figure with better DPI for sharper images
        plt.figure(figsize=(width, 6), dpi=100)
        
        # If no readings for this period, create an empty graph
        if not timestamps:
            # Create a figure with a message
            plt.title(f"Sensor Readings - {title}")
            plt.text(0.5, 0.5, "No data available for this period", 
                    horizontalalignment='center', verticalalignment='center',
                    transform=plt.gca().transAxes, fontsize=14)
            plt.tight_layout()
            
            # Save the figure
            file_path = os.path.join(self.graph_dir, f"{name}.png")
            plt.savefig(file_path)
            plt.close()
            return file_path
        
        # Plot mode 0 readings in blue
        if mode0_readings:
            plt.plot(mode0_timestamps, mode0_values, '-o', color='#2196F3', markersize=4, 
                    linewidth=1.5, markerfacecolor='white', markeredgewidth=1, label='Mode 0')
                    
        # Plot mode 1 readings in green
        if mode1_readings:
            plt.plot(mode1_timestamps, mode1_values, '-s', color='#4CAF50', markersize=4, 
                    linewidth=1.5, markerfacecolor='white', markeredgewidth=1, label='Mode 1')
        
        # Plot readings with no mode specified in gray (for backward compatibility)
        if mode_none_readings:
            none_timestamps = [r.timestamp for r in mode_none_readings]
            none_values = [r.value for r in mode_none_readings]
            plt.plot(none_timestamps, none_values, '-^', color='#9E9E9E', markersize=4, 
                    linewidth=1.5, markerfacecolor='white', markeredgewidth=1, label='No Mode')
        
        # Add trend line (if enough data points)
        if len(values) > 2:
            try:
                # Convert timestamps to numeric format for linear regression
                numeric_dates = mdates.date2num(timestamps)
                
                # Fit a linear trend line
                z = np.polyfit(numeric_dates, values, 1)
                p = np.poly1d(z)
                
                # Plot trend line
                plt.plot(timestamps, p(numeric_dates), "r--", linewidth=1, 
                        alpha=0.7, label=f"Trend: {z[0]:.2e}x + {z[1]:.2f}")
                
            except Exception as e:
                logger.warning(f"Could not generate trend line: {str(e)}")
                
        # Add legend if we have different modes plotted
        if mode0_readings or mode1_readings or mode_none_readings:
            plt.legend(loc='upper left', fontsize=9)
        
        # Add statistics as a box
        if values:
            avg_value = sum(values) / len(values)
            min_value = min(values)
            max_value = max(values)
            current_value = values[-1] if values else 0
            
            stats_text = (
                f"Current: {current_value:.2f}\n"
                f"Average: {avg_value:.2f}\n"
                f"Min: {min_value:.2f}\n"
                f"Max: {max_value:.2f}"
            )
            
            # Add statistics text with better styling
            plt.figtext(0.02, 0.02, stats_text, 
                      bbox=dict(facecolor='white', alpha=0.8, 
                                boxstyle='round,pad=0.5', edgecolor='#cccccc'))
        
        # Format the plot
        plt.title(f"Sensor Readings - {title}", fontsize=14, pad=10)
        plt.ylabel("Reading Value", fontsize=12)
        plt.grid(True, linestyle='--', alpha=0.7)
        
        # Format the x-axis to show dates properly
        plt.gcf().autofmt_xdate()
        
        # Choose appropriate date format based on time period
        if "Hour" in title:
            date_format = mdates.DateFormatter('%H:%M')
        elif "24 Hours" in title:
            date_format = mdates.DateFormatter('%H:%M')
        else:
            date_format = mdates.DateFormatter('%Y-%m-%d %H:%M')
            
        plt.gca().xaxis.set_major_formatter(date_format)
        
        # Add margin to y-axis
        if values:
            y_min, y_max = plt.ylim()
            y_margin = (y_max - y_min) * 0.1  # 10% margin
            plt.ylim(y_min - y_margin, y_max + y_margin)
        
        plt.tight_layout()
        
        # Save the figure with improved quality
        file_path = os.path.join(self.graph_dir, f"{name}.png")
        plt.savefig(file_path, dpi=100, bbox_inches='tight')
        plt.close()
        
        return file_path
        
    def get_embedded_graph(self, readings, hours=24):
        """
        Generate a base64-encoded graph for embedding in HTML.
        
        Args:
            readings (list): List of Reading objects
            hours (int): Number of hours to include in the graph
            
        Returns:
            str: Base64-encoded PNG image
        """
        if not readings:
            logger.warning("No readings provided to generate embedded graph")
            return ""
            
        try:
            # Sort readings by timestamp
            readings = sorted(readings, key=lambda x: x.timestamp)
            
            # Filter readings for the requested time period
            period_start = datetime.utcnow() - timedelta(hours=hours)
            period_readings = [r for r in readings if r.timestamp >= period_start]
            
            # Group readings by mode
            mode0_readings = [r for r in period_readings if r.mode == 0]
            mode1_readings = [r for r in period_readings if r.mode == 1]
            mode_none_readings = [r for r in period_readings if r.mode is None]
            
            # Create the figure with improved styling
            plt.figure(figsize=(10, 5), dpi=100)
            plt.style.use('seaborn-v0_8-darkgrid')
            
            if not period_readings:
                plt.text(0.5, 0.5, "No data available for this period", 
                        horizontalalignment='center', verticalalignment='center',
                        transform=plt.gca().transAxes, fontsize=14)
            else:
                # Plot mode 0 readings in blue
                if mode0_readings:
                    mode0_timestamps = [r.timestamp for r in mode0_readings]
                    mode0_values = [r.value for r in mode0_readings]
                    plt.plot(mode0_timestamps, mode0_values, '-o', color='#2196F3', markersize=4, 
                            linewidth=1.5, markerfacecolor='white', markeredgewidth=1, label='Mode 0')
                    
                # Plot mode 1 readings in green
                if mode1_readings:
                    mode1_timestamps = [r.timestamp for r in mode1_readings]
                    mode1_values = [r.value for r in mode1_readings]
                    plt.plot(mode1_timestamps, mode1_values, '-s', color='#4CAF50', markersize=4, 
                            linewidth=1.5, markerfacecolor='white', markeredgewidth=1, label='Mode 1')
                
                # Plot readings with no mode specified in gray
                if mode_none_readings:
                    none_timestamps = [r.timestamp for r in mode_none_readings]
                    none_values = [r.value for r in mode_none_readings]
                    plt.plot(none_timestamps, none_values, '-^', color='#9E9E9E', markersize=4, 
                            linewidth=1.5, markerfacecolor='white', markeredgewidth=1, label='No Mode')
                
                plt.gcf().autofmt_xdate()
                plt.grid(True, linestyle='--', alpha=0.7)
                
                # Add legend if we have different modes
                if (mode0_readings and mode1_readings) or mode_none_readings:
                    plt.legend(loc='upper left', fontsize=9)
                
                # Add statistics
                if values:
                    avg_value = sum(values) / len(values)
                    min_value = min(values)
                    max_value = max(values)
                    current_value = values[-1] if values else 0
                    
                    stats_text = (
                        f"Current: {current_value:.2f}\n"
                        f"Average: {avg_value:.2f}\n"
                        f"Min: {min_value:.2f}\n"
                        f"Max: {max_value:.2f}"
                    )
                    
                    plt.figtext(0.02, 0.02, stats_text, 
                             bbox=dict(facecolor='white', alpha=0.8, 
                                     boxstyle='round,pad=0.5', edgecolor='#cccccc'))
            
            # Format the plot
            plt.title(f"Sensor Readings - Last {hours} Hours", fontsize=14, pad=10)
            plt.ylabel("Reading Value", fontsize=12)
            
            # Choose appropriate date format
            if hours <= 24:
                date_format = mdates.DateFormatter('%H:%M')
            else:
                date_format = mdates.DateFormatter('%Y-%m-%d')
                
            plt.gca().xaxis.set_major_formatter(date_format)
            
            plt.tight_layout()
            
            # Save to a BytesIO object
            buffer = BytesIO()
            plt.savefig(buffer, format='png', dpi=100, bbox_inches='tight')
            plt.close()
            
            # Get the buffer content and encode as base64
            buffer.seek(0)
            image_png = buffer.getvalue()
            buffer.close()
            
            return base64.b64encode(image_png).decode('utf-8')
            
        except Exception as e:
            logger.error(f"Error generating embedded graph: {str(e)}")
            return ""
