import folium
import pandas as pd
import requests
import json
from datetime import datetime
import os
import math
from folium.plugins import MousePosition
import random

def haversine_distance(lat1, lon1, lat2, lon2):
    """
    Calculate the great circle distance between two points 
    on the earth (specified in decimal degrees)
    """
    # Convert decimal degrees to radians
    lat1, lon1, lat2, lon2 = map(math.radians, [lat1, lon1, lat2, lon2])
    
    # Haversine formula
    dlon = lon2 - lon1
    dlat = lat2 - lat1
    a = math.sin(dlat/2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon/2)**2
    c = 2 * math.asin(math.sqrt(a))
    r = 3956  # Radius of earth in miles
    return c * r

def fetch_usgs_water_data(center_lat, center_lon, radius_miles=50):
    """
    Fetch real USGS water data if available, otherwise use fallback data
    """
    try:
        # USGS Water Services API endpoint
        base_url = "https://waterservices.usgs.gov/nwis/iv/"
        
        # Calculate a bounding box
        lat_offset = radius_miles / 69.0
        lon_offset = radius_miles / (69.0 * math.cos(math.radians(center_lat)))
        
        # Define the bounding box (smaller area for faster response)
        bbox = f"{center_lon - lon_offset/2},{center_lat - lat_offset/2},{center_lon + lon_offset/2},{center_lat + lat_offset/2}"
        
        # Parameters for the API request
        params = {
            "format": "json",
            "bBox": bbox,
            "parameterCd": "00065,00060",  # 00065=gauge height, 00060=discharge
            "siteStatus": "active"
        }
        
        # Make the API request with a timeout
        response = requests.get(base_url, params=params, timeout=3)
        response.raise_for_status()
        
        data = response.json()
        
        # Process the response into our desired format
        processed_data = []
        
        if "value" in data and "timeSeries" in data["value"]:
            for site in data["value"]["timeSeries"]:
                # Get site information
                site_code = site["sourceInfo"]["siteCode"][0]["value"]
                site_name = site["sourceInfo"]["siteName"]
                lat = float(site["sourceInfo"]["geoLocation"]["geogLocation"]["latitude"])
                lon = float(site["sourceInfo"]["geoLocation"]["geogLocation"]["longitude"])
                
                # Check if the site is within the specified radius
                distance = haversine_distance(center_lat, center_lon, lat, lon)
                if distance > radius_miles:
                    continue
                
                # Get parameter information
                parameter = site["variable"]["variableName"]
                
                # Get the latest reading
                if "values" in site and len(site["values"]) > 0:
                    if "value" in site["values"][0] and len(site["values"][0]["value"]) > 0:
                        latest = site["values"][0]["value"][0]
                        value = float(latest["value"])
                        timestamp = latest["dateTime"]
                        
                        # Determine flood level based on gauge height or discharge
                        flood_level = "low"
                        if "gauge height" in parameter.lower():
                            if value > 15:  # Example threshold for high flooding
                                flood_level = "high"
                            elif value > 10:  # Example threshold for medium flooding
                                flood_level = "medium"
                        elif "discharge" in parameter.lower():
                            if value > 10000:  # Example threshold for high discharge
                                flood_level = "high"
                            elif value > 5000:  # Example threshold for medium discharge
                                flood_level = "medium"
                        
                        processed_data.append({
                            "id": site_code,
                            "name": site_name,
                            "lat": lat,
                            "lon": lon,
                            "parameter": parameter,
                            "value": value,
                            "flood_level": flood_level,
                            "timestamp": timestamp,
                            "distance": round(distance, 1),
                            "source": "USGS"
                        })
        
        return processed_data
    
    except Exception as e:
        print(f"Error fetching USGS water data: {e}")
        return []  # Return empty list, will use fallback data later

def generate_sample_flood_data(center_lat, center_lon, radius_miles=50, num_points=10):
    """
    Generate sample flood data points around the center point
    """
    flood_data = []
    
    # Define some realistic stream/river names
    stream_names = [
        "Clear Creek", "Muddy River", "Rocky Branch", "Cedar Stream", 
        "Pine River", "Oak Creek", "Maple Run", "Willow Stream",
        "Eagle River", "Bear Creek", "Fox River", "Deer Stream"
    ]
    
    # Define parameters
    parameters = ["Gauge height, ft", "Discharge, cubic feet per second"]
    
    # Current timestamp
    now = datetime.now().isoformat()
    
    # Generate random points within the radius
    for i in range(num_points):
        # Random angle and distance
        angle = random.uniform(0, 2 * math.pi)
        # Distribute points throughout the radius (square root gives more uniform distribution)
        distance = random.uniform(0, radius_miles) * math.sqrt(random.random())
        
        # Convert to lat/lon offset
        lat_offset = (distance / 69.0) * math.sin(angle)
        lon_offset = (distance / (69.0 * math.cos(math.radians(center_lat)))) * math.cos(angle)
        
        # Create the point
        lat = center_lat + lat_offset
        lon = center_lon + lon_offset
        
        # Random flood level with weighted distribution
        flood_level = random.choices(
            ["low", "medium", "high"], 
            weights=[0.6, 0.3, 0.1],  # 60% low, 30% medium, 10% high
            k=1
        )[0]
        
        # Random value based on flood level
        parameter = random.choice(parameters)
        if "gauge height" in parameter.lower():
            if flood_level == "high":
                value = round(random.uniform(15, 25), 1)
            elif flood_level == "medium":
                value = round(random.uniform(10, 15), 1)
            else:
                value = round(random.uniform(2, 10), 1)
        else:  # discharge
            if flood_level == "high":
                value = round(random.uniform(10000, 20000), 0)
            elif flood_level == "medium":
                value = round(random.uniform(5000, 10000), 0)
            else:
                value = round(random.uniform(500, 5000), 0)
        
        flood_data.append({
            "id": f"sample-{i}",
            "name": random.choice(stream_names),
            "lat": lat,
            "lon": lon,
            "parameter": parameter,
            "value": value,
            "flood_level": flood_level,
            "timestamp": now,
            "distance": round(distance, 1),
            "source": "Sample Data"
        })
    
    return flood_data

def generate_sample_road_closures(center_lat, center_lon, radius_miles=50, num_closures=8):
    """
    Generate sample road closure data around the center point
    """
    road_closures = []
    
    # Define realistic road names
    road_names = [
        "Main St", "Oak Ave", "Pine Rd", "Maple Blvd", "River Dr",
        "Highway 1", "Route 66", "County Rd 5", "State Highway 99",
        "Park Ave", "Market St", "Bridge Rd", "Valley Way", "Mountain Pass"
    ]
    
    # Define realistic closure reasons
    reasons = [
        "flooding", "water on roadway", "storm damage", 
        "road washout", "bridge flooding", "mudslide", "debris"
    ]
    
    # Current timestamp
    now = datetime.now().isoformat()
    
    # Generate random closures within the radius
    for i in range(num_closures):
        # Random angle and distance
        angle = random.uniform(0, 2 * math.pi)
        # Distribute points throughout the radius
        distance = random.uniform(0, radius_miles) * math.sqrt(random.random())
        
        # Convert to lat/lon offset
        lat_offset = (distance / 69.0) * math.sin(angle)
        lon_offset = (distance / (69.0 * math.cos(math.radians(center_lat)))) * math.cos(angle)
        
        # Create the point
        lat = center_lat + lat_offset
        lon = center_lon + lon_offset
        
        # Random status (closed or restricted)
        status = random.choice(["closed", "restricted"])
        
        # Random reason
        reason = random.choice(reasons)
        
        # Create description
        description = f"Road {status} due to {reason}"
        
        road_closures.append({
            "id": f"road-{i}",
            "name": random.choice(road_names),
            "lat": lat,
            "lon": lon,
            "status": status,
            "reason": reason,
            "description": description,
            "distance": round(distance, 1),
            "timestamp": now,
            "source": "Sample Data"
        })
    
    return road_closures

def create_click_handler():
    """Create JavaScript function to handle clicks on the map"""
    return """
    function updateMapOnClick(e) {
        // Get the clicked coordinates
        var lat = e.latlng.lat.toFixed(6);
        var lng = e.latlng.lng.toFixed(6);
        
        // Show loading indicator
        var loadingDiv = document.createElement('div');
        loadingDiv.id = 'loading';
        loadingDiv.innerHTML = '<div style="position: fixed; top: 50%; left: 50%; transform: translate(-50%, -50%); background-color: white; padding: 20px; border-radius: 5px; box-shadow: 0 0 10px rgba(0,0,0,0.3); z-index: 10000;"><b>Loading data...</b></div>';
        document.body.appendChild(loadingDiv);
        
        // Update the form and submit it
        document.getElementById('lat_input').value = lat;
        document.getElementById('lon_input').value = lng;
        document.getElementById('coord_form').submit();
    }
    
    // Add click event listener to the map
    map.on('click', updateMapOnClick);
    """

def create_radius_circle(lat, lon, radius_miles=50):
    """Create a circle showing the search radius"""
    # Convert miles to meters (1 mile = 1609.34 meters)
    radius_meters = radius_miles * 1609.34
    
    circle = folium.Circle(
        location=[lat, lon],
        radius=radius_meters,
        color='blue',
        fill=True,
        fill_color='blue',
        fill_opacity=0.1,
        popup=f"{radius_miles} mile radius"
    )
    
    return circle

def create_clickable_flood_map(center_lat=None, center_lon=None, radius_miles=50, show_data=True):
    """
    Create an interactive map that allows clicking to get flood data using free data sources
    
    Parameters:
    - center_lat, center_lon: Center coordinates (optional)
    - radius_miles: Search radius in miles
    - show_data: Whether to show flood data for the initial location
    
    Returns:
    - Folium map object
    """
    # Set default center if not provided (San Francisco)
    if center_lat is None:
        center_lat = 37.7749
    if center_lon is None:
        center_lon = -122.4194
    
    # Create base map with OpenStreetMap (free)
    m = folium.Map(location=[center_lat, center_lon], 
                   zoom_start=9,
                   tiles="OpenStreetMap")
    
    # Add Stamen Terrain tiles (free)
    folium.TileLayer(
        tiles='https://stamen-tiles-{s}.a.ssl.fastly.net/terrain/{z}/{x}/{y}.png',
        attr='Map tiles by <a href="http://stamen.com">Stamen Design</a>, under <a href="http://creativecommons.org/licenses/by/3.0">CC BY 3.0</a>. Data by <a href="http://openstreetmap.org">OpenStreetMap</a>, under <a href="http://www.openstreetmap.org/copyright">ODbL</a>.',
        name='Terrain',
        overlay=False
    ).add_to(m)
    
    # Add Stamen Toner tiles (free)
    folium.TileLayer(
        tiles='https://stamen-tiles-{s}.a.ssl.fastly.net/toner/{z}/{x}/{y}.png',
        attr='Map tiles by <a href="http://stamen.com">Stamen Design</a>, under <a href="http://creativecommons.org/licenses/by/3.0">CC BY 3.0</a>. Data by <a href="http://openstreetmap.org">OpenStreetMap</a>, under <a href="http://www.openstreetmap.org/copyright">ODbL</a>.',
        name='Toner',
        overlay=False
    ).add_to(m)
    
    # Add Stamen Watercolor tiles (free, artistic style)
    folium.TileLayer(
        tiles='https://stamen-tiles-{s}.a.ssl.fastly.net/watercolor/{z}/{x}/{y}.jpg',
        attr='Map tiles by <a href="http://stamen.com">Stamen Design</a>, under <a href="http://creativecommons.org/licenses/by/3.0">CC BY 3.0</a>. Data by <a href="http://openstreetmap.org">OpenStreetMap</a>, under <a href="http://www.openstreetmap.org/copyright">ODbL</a>.',
        name='Watercolor',
        overlay=False
    ).add_to(m)
    
    # Add title and instructions
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    title_html = f'''
         <div style="position: fixed; top: 10px; left: 50px; width: 300px; z-index:9999; background-color:white; padding: 10px; border-radius: 5px; border:2px solid grey;">
         <h3 style="font-size:16px"><b>Interactive Flood and Road Closure Map</b></h3>
         <p style="font-size:12px">Last updated: {current_time}</p>
         <p style="font-size:12px"><b>Click anywhere on the map</b> to see flood data and road closures within a {radius_miles}-mile radius.</p>
         <p style="font-size:12px">Using 100% free data sources.</p>
         </div>
         '''
    m.get_root().html.add_child(folium.Element(title_html))
    
    # Add form for handling coordinates (will be hidden by CSS)
    form_html = f'''
    <form id="coord_form" method="GET" style="display:none;">
        <input type="hidden" id="lat_input" name="lat" value="{center_lat}">
        <input type="hidden" id="lon_input" name="lon" value="{center_lon}">
        <input type="hidden" name="radius" value="{radius_miles}">
        <input type="hidden" name="show_data" value="true">
        <input type="submit" value="Update">
    </form>
    '''
    m.get_root().html.add_child(folium.Element(form_html))
    
    # Add JavaScript to handle clicks
    click_script = create_click_handler()
    m.get_root().script.add_child(folium.Element(f"<script>{click_script}</script>"))
    
    # Add a marker for the center point
    folium.Marker(
        location=[center_lat, center_lon],
        popup=f"Selected Point: {center_lat}, {center_lon}",
        icon=folium.Icon(color="green", icon="crosshairs", prefix="fa")
    ).add_to(m)
    
    # Add the search radius circle
    create_radius_circle(center_lat, center_lon, radius_miles).add_to(m)
    
    # If show_data is True, fetch and display flood data
    if show_data:
        # Try to get real USGS data first
        flood_data = fetch_usgs_water_data(center_lat, center_lon, radius_miles)
        
        # If no real data is available, use sample data
        if not flood_data:
            print("No USGS data available. Using sample flood data.")
            flood_data = generate_sample_flood_data(center_lat, center_lon, radius_miles)
        
        # Always use sample road closure data (no reliable free API for this)
        road_closures = generate_sample_road_closures(center_lat, center_lon, radius_miles)
        
        # Add flood data points
        flood_group = folium.FeatureGroup(name="Flood Levels")
        
        for point in flood_data:
            # Set color based on flood level
            if point["flood_level"] == "high":
                color = "red"
                radius = 15
            elif point["flood_level"] == "medium":
                color = "orange"
                radius = 10
            else:
                color = "blue" 
                radius = 8
                
            # Create popup with information
            popup_text = f"""
            <b>{point.get('name', 'Location')}</b><br>
            <b>Flood Level:</b> {point['flood_level'].upper()}<br>
            <b>Measurement:</b> {point.get('value', 'N/A')} {point.get('parameter', '')}<br>
            <b>Distance:</b> {point.get('distance', 'N/A')} miles<br>
            <b>Source:</b> {point.get('source', 'Unknown')}<br>
            <b>Timestamp:</b> {point['timestamp']}<br>
            """
            
            # Add marker
            folium.CircleMarker(
                location=[point["lat"], point["lon"]],
                radius=radius,
                color=color,
                fill=True,
                fill_opacity=0.7,
                popup=folium.Popup(popup_text, max_width=300)
            ).add_to(flood_group)
        
        # Add road closures
        road_group = folium.FeatureGroup(name="Road Closures")
        
        for road in road_closures:
            # Set icon based on status
            if road["status"] == "closed":
                icon = folium.Icon(color="red", icon="ban", prefix="fa")
            else:
                icon = folium.Icon(color="orange", icon="exclamation-triangle", prefix="fa")
                
            # Create popup with information
            popup_text = f"""
            <b>{road['name']}</b><br>
            <b>Status:</b> {road['status'].upper()}<br>
            <b>Reason:</b> {road['reason']}<br>
            <b>Distance:</b> {road.get('distance', 'N/A')} miles<br>
            <b>Source:</b> {road.get('source', 'Unknown')}<br>
            """
            
            if 'description' in road and road['description']:
                popup_text += f"<b>Details:</b> {road['description']}"
            
            # Add marker
            folium.Marker(
                location=[road["lat"], road["lon"]],
                popup=folium.Popup(popup_text, max_width=300),
                icon=icon
            ).add_to(road_group)
        
        # Add feature groups to map
        flood_group.add_to(m)
        road_group.add_to(m)
        
        # Add data summary
        if flood_data or road_closures:
            summary_html = f'''
            <div style="position: fixed; bottom: 20px; left: 50px; width: 250px; z-index:9999; background-color:white; padding: 10px; border-radius: 5px; border:2px solid grey;">
                <h4 style="font-size:14px"><b>Data Summary</b></h4>
                <p style="font-size:12px"><b>Flood Monitoring Points:</b> {len(flood_data)}</p>
                <p style="font-size:12px"><b>Road Closures/Issues:</b> {len(road_closures)}</p>
                <p style="font-size:12px"><b>High Flood Level Areas:</b> {sum(1 for p in flood_data if p['flood_level'] == 'high')}</p>
                <p style="font-size:12px"><b>Closed Roads:</b> {sum(1 for r in road_closures if r['status'] == 'closed')}</p>
                <p style="font-size:10px"><i>Data includes a mix of real USGS data (when available) and sample data for demonstration.</i></p>
            </div>
            '''
            m.get_root().html.add_child(folium.Element(summary_html))
    
    # Add layer control
    folium.LayerControl().add_to(m)
    
    # Add custom legend
    legend_html = '''
    <div style="position: fixed; 
                bottom: 20px; right: 20px; width: 180px; height: 120px; 
                border:2px solid grey; z-index:9999; font-size:12px;
                background-color:white; padding: 10px;
                border-radius: 5px;">
                
    <b>Flood Levels</b><br>
    <i class="fa fa-circle" style="color:red"></i> High<br>
    <i class="fa fa-circle" style="color:orange"></i> Medium<br>
    <i class="fa fa-circle" style="color:blue"></i> Low<br>
    <br>
    <b>Road Status</b><br>
    <i class="fa fa-ban" style="color:red"></i> Closed<br>
    <i class="fa fa-exclamation-triangle" style="color:orange"></i> Restricted<br>
    </div>
    '''
    m.get_root().html.add_child(folium.Element(legend_html))
    
    # Add mouse position display
    MousePosition().add_to(m)
    
    # Add data sources attribution
    sources_html = '''
    <div style="position: fixed; 
                top: 130px; left: 50px; width: 250px; 
                border:1px solid grey; z-index:9998; font-size:10px;
                background-color:white; padding: 5px;
                border-radius: 5px;">
    <b>Data Sources:</b><br>
    - USGS Water Services API (when available)<br>
    - Sample data for demonstration purposes
    </div>
    '''
    m.get_root().html.add_child(folium.Element(sources_html))
    
    return m

def save_map(map_obj, filename="interactive_flood_map.html"):
    """Save the map to an HTML file"""
    map_obj.save(filename)
    print(f"Map saved as {filename}. Open this file in a web browser to view.")

# Flask app to serve the interactive map
def create_flask_app():
    """Create a Flask app to serve the interactive map"""
    from flask import Flask, request, render_template_string
    
    app = Flask(__name__)
    
    @app.route('/')
    def index():
        # Get parameters from the request
        lat = request.args.get('lat', None)
        lon = request.args.get('lon', None)
        radius = request.args.get('radius', 50)
        show_data = request.args.get('show_data', False)
        
        # Convert to appropriate types
        try:
            if lat is not None:
                lat = float(lat)
            if lon is not None:
                lon = float(lon)
            radius = int(radius)
            if type(show_data) == str:
                show_data = show_data.lower() == 'true'
        except ValueError:
            lat = None
            lon = None
            radius = 50
            show_data = False
        
        # Create the map
        m = create_clickable_flood_map(
            center_lat=lat, 
            center_lon=lon, 
            radius_miles=radius,
            show_data=show_data
        )
        
        # Get the HTML representation of the map
        map_html = m.get_root()._repr_html_()
        
        # Create a simple HTML template
        template = """
        <!DOCTYPE html>
        <html>
        <head>
            <title>Interactive Flood Map</title>
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <style>
                body, html {
                    height: 100%;
                    margin: 0;
                    padding: 0;
                    font-family: Arial, sans-serif;
                }
                #map {
                    height: 100%;
                    width: 100%;
                }
                #loading {
                    display: none;
                }
                .credit {
                    position: fixed;
                    bottom: 5px;
                    left: 50%;
                    transform: translateX(-50%);
                    background-color: rgba(255,255,255,0.7);
                    padding: 3px 8px;
                    border-radius: 3px;
                    font-size: 10px;
                    z-index: 1000;
                }
            </style>
        </head>
        <body>
            <div id="map">{{ map_html|safe }}</div>
            <div class="credit">Created with Python & Folium using free data sources</div>
        </body>
        </html>
        """
        
        return render_template_string(template, map_html=map_html)
    
    return app

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Interactive flood and road closure map with free data sources")
    parser.add_argument("--lat", type=float, help="Initial center latitude")
    parser.add_argument("--lon", type=float, help="Initial center longitude")
    parser.add_argument("--radius", type=int, default=50, help="Search radius in miles (default: 50)")
    parser.add_argument("--flask", action="store_true", help="Run as Flask web app")
    parser.add_argument("--port", type=int, default=5000, help="Port for Flask app (default: 5000)")
    
    args = parser.parse_args()
    
    if args.flask:
        # Run as a Flask web app
        app = create_flask_app()
        print(f"Starting Flask server on port {args.port}...")
        print(f"Open http://127.0.0.1:{args.port}/ in your web browser")
        app.run(debug=True, port=args.port)
    else:
        # Create a single HTML file with data always shown
        m = create_clickable_flood_map(
            center_lat=args.lat,
            center_lon=args.lon,
            radius_miles=args.radius,
            show_data=True  # Always show data
        )
        save_map(m)
        print("Map created with sample data. Open the HTML file in your browser to view and interact with it.")
        print("Click anywhere on the map to see flood data and road closures within the specified radius.")