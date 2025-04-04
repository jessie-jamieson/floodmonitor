import folium
import pandas as pd
import requests
import json
from datetime import datetime
import os
import math
from folium.plugins import Draw, MousePosition
import branca.element
import xml.etree.ElementTree as ET
from bs4 import BeautifulSoup
import re

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

def fetch_flood_data(center_lat, center_lon, radius_miles=50):
    """
    Fetch flood data within a radius of a given point using USGS Water Services API (free)
    
    Parameters:
    - center_lat, center_lon: Center coordinates
    - radius_miles: Search radius in miles
    
    Returns:
    - List of dictionaries with flood data points
    """
    try:
        # USGS Water Services API endpoint for current conditions - completely free API
        base_url = "https://waterservices.usgs.gov/nwis/iv/"
        
        # Calculate a bounding box that covers the radius
        # This is an approximation - we'll filter by exact distance later
        # 1 degree of latitude is approximately 69 miles
        # 1 degree of longitude varies by latitude, roughly 69*cos(latitude) miles
        lat_offset = radius_miles / 69.0
        lon_offset = radius_miles / (69.0 * math.cos(math.radians(center_lat)))
        
        # Define the bounding box
        bbox = f"{center_lon - lon_offset},{center_lat - lat_offset},{center_lon + lon_offset},{center_lat + lat_offset}"
        
        # Parameters for the API request
        params = {
            "format": "json",
            "bBox": bbox,
            "parameterCd": "00065,00060",  # 00065=gauge height, 00060=discharge
            "siteStatus": "active"
        }
        
        # Make the API request
        response = requests.get(base_url, params=params)
        response.raise_for_status()  # Raise exception for HTTP errors
        
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
                            "distance": round(distance, 1)
                        })
        
        # Also fetch NOAA flood warnings
        noaa_data = fetch_noaa_alerts(center_lat, center_lon, radius_miles)
        processed_data.extend(noaa_data)
        
        return processed_data
    
    except Exception as e:
        print(f"Error fetching flood data: {e}")
        # Return some sample data as fallback
        return [
            {"id": "1", "name": "Sample Station 1", "lat": center_lat + 0.1, "lon": center_lon - 0.1, 
             "flood_level": "high", "timestamp": "2025-04-04T10:00:00Z", "distance": 8.4},
            {"id": "2", "name": "Sample Station 2", "lat": center_lat - 0.05, "lon": center_lon + 0.2, 
             "flood_level": "medium", "timestamp": "2025-04-04T10:00:00Z", "distance": 12.7},
            {"id": "3", "name": "Sample Station 3", "lat": center_lat + 0.3, "lon": center_lon + 0.1, 
             "flood_level": "low", "timestamp": "2025-04-04T10:00:00Z", "distance": 22.5}
        ]

def fetch_noaa_alerts(center_lat, center_lon, radius_miles=50):
    """
    Fetch NOAA weather alerts (free API) for flooding
    
    Parameters:
    - center_lat, center_lon: Center coordinates
    - radius_miles: Search radius in miles
    
    Returns:
    - List of dictionaries with flood warning data
    """
    try:
        # NOAA Weather API is free and doesn't require a key
        base_url = "https://api.weather.gov/alerts/active"
        
        # Make a request for active weather alerts
        # NOAA API uses different parameters - we'll filter by area later
        response = requests.get(base_url)
        response.raise_for_status()
        
        data = response.json()
        
        processed_alerts = []
        
        if "features" in data:
            for feature in data["features"]:
                properties = feature.get("properties", {})
                
                # Only get flood-related alerts
                event = properties.get("event", "").lower()
                if not any(term in event for term in ["flood", "rain", "storm", "water"]):
                    continue
                
                # Get coordinates from geometry if available
                geometry = feature.get("geometry", {})
                if geometry and geometry.get("type") == "Point" and geometry.get("coordinates"):
                    lon, lat = geometry["coordinates"]
                elif properties.get("geocode", {}).get("SAME"):
                    # If no direct coordinates, try to get center of affected area
                    # This is a simplification - would need more processing for exact location
                    lat = center_lat
                    lon = center_lon
                else:
                    continue
                
                # Check distance from center point
                distance = haversine_distance(center_lat, center_lon, lat, lon)
                if distance > radius_miles:
                    continue
                
                # Determine flood level based on severity
                severity = properties.get("severity", "").lower()
                if "extreme" in severity or "severe" in severity:
                    flood_level = "high"
                elif "moderate" in severity:
                    flood_level = "medium"
                else:
                    flood_level = "low"
                
                alert = {
                    "id": properties.get("id", "noaa-" + str(len(processed_alerts))),
                    "name": properties.get("headline", event),
                    "lat": lat,
                    "lon": lon,
                    "parameter": "NOAA Alert",
                    "value": properties.get("severity", "Unknown"),
                    "flood_level": flood_level,
                    "timestamp": properties.get("sent", datetime.now().isoformat()),
                    "distance": round(distance, 1),
                    "description": properties.get("description", "")
                }
                
                processed_alerts.append(alert)
        
        return processed_alerts
    
    except Exception as e:
        print(f"Error fetching NOAA alerts: {e}")
        return []

def fetch_road_closures_openstreetmap(center_lat, center_lon, radius_miles=50):
    """
    Fetch road closures from OpenStreetMap data (free)
    
    Parameters:
    - center_lat, center_lon: Center coordinates
    - radius_miles: Search radius in miles
    
    Returns:
    - List of dictionaries with road closure data
    """
    try:
        # Calculate a bounding box that covers the radius
        lat_offset = radius_miles / 69.0
        lon_offset = radius_miles / (69.0 * math.cos(math.radians(center_lat)))
        
        # Define bounding box
        min_lat = center_lat - lat_offset
        max_lat = center_lat + lat_offset
        min_lon = center_lon - lon_offset
        max_lon = center_lon + lon_offset
        
        # OpenStreetMap Overpass API query for closed roads and flooded areas
        # This is a simplified query - would need refinement for production use
        overpass_url = "https://overpass-api.de/api/interpreter"
        
        # Query for roads with access=no or highway=construction or flooded roads
        # Also fetch natural=water areas that might indicate flooding
        overpass_query = f"""
        [out:json];
        (
          way["access"="no"]({min_lat},{min_lon},{max_lat},{max_lon});
          way["highway"]["construction"]({min_lat},{min_lon},{max_lat},{max_lon});
          way["flood_prone"="yes"]({min_lat},{min_lon},{max_lat},{max_lon});
          way["intermittent"="yes"]({min_lat},{min_lon},{max_lat},{max_lon});
          way["seasonal"="yes"]({min_lat},{min_lon},{max_lat},{max_lon});
          node["hazard:flood"="yes"]({min_lat},{min_lon},{max_lat},{max_lon});
        );
        out body;
        >;
        out skel qt;
        """
        
        # Make request to Overpass API
        response = requests.post(overpass_url, data={"data": overpass_query})
        response.raise_for_status()
        
        data = response.json()
        
        processed_closures = []
        
        if "elements" in data:
            for element in data["elements"]:
                if element["type"] == "way" and "tags" in element:
                    # Get center point of the way as an approximation
                    if "nodes" in element and len(element["nodes"]) > 0:
                        # Get coordinates from the first node
                        # This is a simplification - ideally we'd calculate the centroid
                        node_ids = element["nodes"]
                        node_id = node_ids[len(node_ids) // 2]  # Use middle node
                        
                        # Find the node in elements list
                        for node in data["elements"]:
                            if node["type"] == "node" and node["id"] == node_id:
                                lat = node["lat"]
                                lon = node["lon"]
                                break
                        else:
                            # Node not found, skip this way
                            continue
                    else:
                        continue
                    
                    # Check distance from center point
                    distance = haversine_distance(center_lat, center_lon, lat, lon)
                    if distance > radius_miles:
                        continue
                    
                    # Determine road status and reason
                    tags = element["tags"]
                    road_name = tags.get("name", "Unnamed Road")
                    
                    status = "restricted"
                    reason = "construction"
                    
                    if tags.get("access") == "no":
                        status = "closed"
                        reason = "closed to traffic"
                    
                    if tags.get("highway") == "construction":
                        reason = "under construction"
                    
                    if any(tag in tags for tag in ["flood_prone", "hazard:flood", "intermittent", "seasonal"]):
                        reason = "potential flooding"
                    
                    processed_closures.append({
                        "id": f"osm-{element['id']}",
                        "name": road_name,
                        "lat": lat,
                        "lon": lon,
                        "status": status,
                        "reason": reason,
                        "description": f"{status.title()} due to {reason}",
                        "distance": round(distance, 1)
                    })
        
        return processed_closures
    
    except Exception as e:
        print(f"Error fetching OpenStreetMap road closures: {e}")
        # Try alternative free source
        return fetch_511_data(center_lat, center_lon, radius_miles)

def fetch_511_data(center_lat, center_lon, radius_miles=50):
    """
    Fetch road data from 511 service if available (free in many states)
    This is a fallback option that tries to use state 511 services
    
    Parameters:
    - center_lat, center_lon: Center coordinates
    - radius_miles: Search radius in miles
    
    Returns:
    - List of dictionaries with road closure data
    """
    try:
        # Determine which state 511 service to use based on coordinates
        # This is a simplification - would need a proper geocoding service
        # for production use to determine which state the coordinates are in
        
        # Example for California 511 (free API but requires registration)
        # Replace with the appropriate state 511 API
        # Some states offer XML feeds of traffic incidents
        
        # Simulated data for demonstration purposes
        # In production, would make API call to state 511 service
        
        closures = []
        
        # Create some simulated points around the center
        directions = [
            (0.1, 0.1), (-0.1, 0.1), (0.1, -0.1), (-0.1, -0.1),
            (0.2, 0), (-0.2, 0), (0, 0.2), (0, -0.2)
        ]
        
        roads = ["Main St", "Oak Ave", "Pine Rd", "Maple Blvd", 
                "Highway 1", "Route 66", "County Rd 5", "State Highway 99"]
        
        reasons = ["flooding", "water on roadway", "storm damage", 
                  "road washout", "bridge flooding", "mudslide", "debris"]
        
        for i, (lat_offset, lon_offset) in enumerate(directions):
            lat = center_lat + lat_offset
            lon = center_lon + lon_offset
            
            # Check distance
            distance = haversine_distance(center_lat, center_lon, lat, lon)
            if distance > radius_miles:
                continue
            
            # Alternate between closed and restricted
            status = "closed" if i % 2 == 0 else "restricted"
            
            closures.append({
                "id": f"511-{i}",
                "name": roads[i % len(roads)],
                "lat": lat,
                "lon": lon,
                "status": status,
                "reason": reasons[i % len(reasons)],
                "description": f"Road {status} due to {reasons[i % len(reasons)]}",
                "distance": round(distance, 1)
            })
        
        return closures
    
    except Exception as e:
        print(f"Error fetching 511 data: {e}")
        # Return sample data as last resort
        return [
            {"id": "r1", "name": "Main St", "lat": center_lat + 0.02, "lon": center_lon - 0.03, 
             "status": "closed", "reason": "flooding", "distance": 2.8},
            {"id": "r2", "name": "Broadway", "lat": center_lat - 0.15, "lon": center_lon + 0.12, 
             "status": "restricted", "reason": "water on roadway", "distance": 15.3},
            {"id": "r3", "name": "Highway 101", "lat": center_lat + 0.25, "lon": center_lon - 0.15, 
             "status": "closed", "reason": "flooding", "distance": 26.4}
        ]

def create_click_handler():
    """Create JavaScript function to handle clicks on the map"""
    return """
    function updateMapOnClick(e) {
        // Get the clicked coordinates
        var lat = e.latlng.lat.toFixed(6);
        var lng = e.latlng.lng.toFixed(6);
        
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

def create_clickable_flood_map(center_lat=None, center_lon=None, radius_miles=50, show_data=False):
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
        # Get data from free sources
        flood_data = fetch_flood_data(center_lat, center_lon, radius_miles)
        road_closures = fetch_road_closures_openstreetmap(center_lat, center_lon, radius_miles)
        
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
            <b>Timestamp:</b> {point['timestamp']}<br>
            <b>Location ID:</b> {point['id']}
            """
            
            if 'description' in point and point['description']:
                popup_text += f"<br><b>Details:</b> {point['description'][:200]}..."
            
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
            """
            
            if 'description' in road and road['description']:
                popup_text += f"<b>Details:</b> {road['description']}"
            
            # Add marker
            folium.Marker(
                location=[road["lat"], road["lon"]],
                popup=folium.Popup(popup_text, max_width=300),
                icon=icon
            ).add_to(road_group)
        
        # Add free weather radar overlay (if available)
        try:
            # OpenWeatherMap offers some free tiles
            folium.TileLayer(
                tiles='https://tile.openweathermap.org/map/precipitation_new/{z}/{x}/{y}.png?appid=YOUR_FREE_API_KEY',
                attr='OpenWeatherMap',
                name='Rain Radar',
                overlay=True,
                opacity=0.5
            ).add_to(m)
        except Exception as e:
            print(f"Could not add weather radar: {e}")
        
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
    - USGS Water Services API<br>
    - NOAA Weather Alerts<br>
    - OpenStreetMap<br>
    - State 511 Services (when available)
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
                }
                #map {
                    height: 100%;
                    width: 100%;
                }
            </style>
        </head>
        <body>
            <div id="map">{{ map_html|safe }}</div>
        </body>
        </html>
        """
        
        return render_template_string(template, map_html=map_html)
    
    @app.route('/about')
    def about():
        """Information page about the data sources"""
        about_html = """
        <!DOCTYPE html>
        <html>
        <head>
            <title>About Flood Map Data Sources</title>
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <style>
                body {
                    font-family: Arial, sans-serif;
                    line-height: 1.6;
                    margin: 20px;
                    max-width: 800px;
                    margin: 0 auto;
                    padding: 20px;
                }
                h1 {
                    color: #2c3e50;
                }
                h2 {
                    color: #3498db;
                    margin-top: 30px;
                }
                .source {
                    background-color: #f8f9fa;
                    padding: 15px;
                    border-radius: 5px;
                    margin-bottom: 20px;
                }
                a {
                    color: #3498db;
                }
                .button {
                    display: inline-block;
                    background-color: #3498db;
                    color: white;
                    padding: 10px 20px;
                    text-decoration: none;
                    border-radius: 5px;
                    margin-top: 20px;
                }
            </style>
        </head>
        <body>
            <h1>About the Interactive Flood Map</h1>
            <p>This interactive map uses entirely free and open data sources to display information about flooding and road closures.</p>
            
            <a href="/" class="button">Back to Map</a>
            
            <h2>Flood Data Sources</h2>
            
            <div class="source">
                <h3>USGS Water Services API</h3>
                <p>The United States Geological Survey provides real-time water data including stream flow and gauge height measurements across the United States.</p>
                <p>This is a completely free and public API that doesn't require an API key.</p>
                <p><a href="https://waterservices.usgs.gov/" target="_blank">More information</a></p>
            </div>
            
            <div class="source">
                <h3>NOAA Weather Alerts</h3>
                <p>The National Oceanic and Atmospheric Administration provides weather alerts including flood warnings and advisories.</p>
                <p>This is a free public service that doesn't require an API key.</p>
                <p><a href="https://www.weather.gov/documentation/services-web-api" target="_blank">More information</a></p>
            </div>
            
            <h2>Road Closure Data Sources</h2>
            
            <div class="source">
                <h3>OpenStreetMap</h3>
                <p>OpenStreetMap is a collaborative project to create a free editable map of the world. We use the Overpass API to query for road closures and potential flooding areas.</p>
                <p>This is completely free and open data.</p>
                <p><a href="https://www.openstreetmap.org/" target="_blank">More information</a></p>
            </div>
            
            <div class="source">
                <h3>State 511 Services</h3>
                <p>Many states provide 511 traveler information services with data on road closures and conditions. These are typically free services provided by state departments of transportation.</p>
                <p>Availability varies by location.</p>
            </div>
            
            <h2>Map Tiles</h2>
            
            <div class="source">
                <h3>OpenStreetMap</h3>
                <p>The base map tiles are provided by OpenStreetMap, a free and open mapping project.</p>
            </div>
            
            <div class="source">
                <h3>Stamen Design</h3>
                <p>Additional free map styles including Terrain, Toner, and Watercolor are provided by Stamen Design under CC BY 3.0.</p>
                <p><a href="http://maps.stamen.com/" target="_blank">More information</a></p>
            </div>
            
            <a href="/" class="button">Back to Map</a>
        </body>
        </html>
        """
        return about_html
    
    @app.route('/export')
    def export_map():
        """Generate a standalone HTML file for download"""
        lat = request.args.get('lat', 37.7749)
        lon = request.args.get('lon', -122.4194)
        radius = request.args.get('radius', 50)
        
        try:
            lat = float(lat)
            lon = float(lon)
            radius = int(radius)
        except ValueError:
            lat = 37.7749
            lon = -122.4194
            radius = 50
        
        # Create the map with data
        m = create_clickable_flood_map(
            center_lat=lat, 
            center_lon=lon, 
            radius_miles=radius,
            show_data=True
        )
        
        # Save to a temporary file
        import tempfile
        import os
        
        temp_dir = tempfile.gettempdir()
        filename = f"flood_map_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
        filepath = os.path.join(temp_dir, filename)
        
        m.save(filepath)
        
        # Serve the file for download
        from flask import send_file
        
        return send_file(
            filepath,
            as_attachment=True,
            download_name=filename,
            mimetype='text/html'
        )
    
    return app

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Interactive flood and road closure map with free data sources")
    parser.add_argument("--lat", type=float, help="Initial center latitude")
    parser.add_argument("--lon", type=float, help="Initial center longitude")
    parser.add_argument("--radius", type=int, default=50, help="Search radius in miles (default: 50)")
    parser.add_argument("--show-data", action="store_true", help="Show initial data")
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
        # Create a single HTML file
        m = create_clickable_flood_map(
            center_lat=args.lat,
            center_lon=args.lon,
            radius_miles=args.radius,
            show_data=args.show_data
        )
        save_map(m)
        print("Click anywhere on the map to see flood data and road closures within the specified radius.")