#to enable elevation calculation the get_green_grid_points function need to be called and calcElevation uncommented


import overpy
import numpy as np
import cv2
import math
import statistics
import imutils
from scipy.spatial import distance as dist
from scipy.spatial import Delaunay
import os

from shapely.geometry import Point, Polygon
from scipy.interpolate import splprep, splev

from earthelevation import calcElevation
from beziersvg import drawbeziersvg

#for elevation and slope direction plotting
import matplotlib.pyplot as plt
import matplotlib.tri as tri
import matplotlib.tri as mtri

# imports to use svg for feature drawing
from scipy.interpolate import splprep, splev
import svgwrite


# convert hex to bgr format for numpy

def hexToBGR(hex):
    if hex[0] == "#":
        hex = hex[1:]

    r = int(hex[0:2], 16)
    g = int(hex[2:4], 16)
    b = int(hex[4:6], 16)

    return (b, g, r)


# given a list of coordinates, calculate the min and max longitude and latitude 

def getBoundingBoxLatLon(nodes):

    minlat = 100
    maxlat = -100
    minlon = 360
    maxlon = -360

    for node in nodes:
        minlat = float(min(minlat, node.lat))
        maxlat = float(max(maxlat, node.lat))
        minlon = float(min(minlon, node.lon))
        maxlon = float(max(maxlon, node.lon))

    return minlat, minlon, maxlat, maxlon


# function to get the golf holes contained within a given bounding box

def getOSMGolfWays(bottom_lat, left_lon, top_lat, right_lon, printf=print):

    op = overpy.Overpass(url="https://overpass.osm.jp/api/interpreter")

    # create the coordinate string for our request - order is South, West, North, East
    coord_string = str(bottom_lat) + "," + str(left_lon) + \
                       "," + str(top_lat) + "," + str(right_lon)

    # use the coordinate string to pull the data through Overpass - golf holes only
    try:
        query = "(way['golf'='hole'](" + coord_string + "););out;"
        return op.query(query)

    except overpy.exception.OverPyException:
        printf("OpenStreetMap servers are too busy right now.  Try running this tool later.")
        return None

# function to get all golf data contained within a given bounding box (e.g. fairways, greens, sand traps, etc)


def getOSMGolfData(bottom_lat, left_lon, top_lat, right_lon, printf=print):

    # optional replacement url if servers are busy - url="https://overpass.kumi.systems/api/interpreter"
    op = overpy.Overpass(url="https://overpass.osm.jp/api/interpreter")

    # create the coordinate string for our request - order is South, West, North, East
    coord_string = str(bottom_lat) + "," + str(left_lon) + \
                       "," + str(top_lat) + "," + str(right_lon)

    # use the coordinate string to pull the data through Overpass
    # we want all golf ways, with some additions for woods, trees, and water hazards
    try:
        query = "(way['golf'](" + coord_string + ");way['natural'='wood'](" + coord_string + ");node['natural'='tree'](" + \
                  coord_string + \
                      ");way['landuse'='forest'](" + coord_string + \
                                                 ");way['natural'='water'](" + \
                                                                           coord_string + "););out;"

        return op.query(query)

    except overpy.exception.OverPyException:
        printf("OpenStreetMap servers are too busy right now.  Try running this tool later.")
        return None


# calculate length of a degree of latitude at a given location

def getLatDegreeDistance(bottom_lat, top_lat):

    # this is the approximate distance of a degree of latitude at the equator in yards
    lat_degree_distance_equator = 120925.62

    # this is the approximate distance of a degree of latitude at the equator in meters
    lat_degree_distance_equator_meter = 111, 111

    # a degree of latitude gets approximately 13.56 yards longer per degree you go north because earth is a geioid (shaped like an onion)
    lat_yds_per_degree = 13.56

    # find the average latitude of our course
    average_lat = statistics.mean([bottom_lat, top_lat])

    # calculate length of a degree of latitude is at this average latitude
    lat_degree_distance_yds = lat_degree_distance_equator + \
        (abs(average_lat) * lat_yds_per_degree)

    return lat_degree_distance_yds


# calculate length of a degree of longitude at a given location

# length of longitude depends on latitude because the Earth is a sphere!
def getLonDegreeDistance(bottom_lat, top_lat):

    # this is the approximate distance of a degree of longitude at the equator in yards
    lon_degree_distance_equator_yds = 69.172 * 5280 / 3

    # find the average latitude of our course
    average_lat = statistics.mean([bottom_lat, top_lat])

    # do some fancy trig to calculate how far a degree of longitude is at this average latitude
    radian_avg_lat = average_lat * (math.pi/180)

    lon_distance_multiplier = math.cos(radian_avg_lat)

    lon_degree_distance_yds = lon_degree_distance_equator_yds * lon_distance_multiplier

    return lon_degree_distance_yds


# given the points of a golf hole on OSM, define a bounding box for that hole

def getHoleBoundingBox(way, lat_degree_distance, lon_degree_distance):

    # get the bounding lat and lon of this particular hole

    hole_way_nodes = way.get_nodes(resolve_missing=True)

    lowest_lat, lowest_lon, highest_lat, highest_lon = getBoundingBoxLatLon(
        hole_way_nodes)

    # add 50 yards in each direction to the bounding box (to include all features like sand traps, water, etc)

    extra_lat_distance = 50 * (1/lat_degree_distance)

    extra_lon_distance = 50 * (1/lon_degree_distance)

    lowest_lat = lowest_lat - extra_lat_distance
    highest_lat = highest_lat + extra_lat_distance

    lowest_lon = lowest_lon - extra_lon_distance
    highest_lon = highest_lon + extra_lon_distance

    return lowest_lat, lowest_lon, highest_lat, highest_lon, hole_way_nodes


# create a blank dwg of the appropriate size to use in drawing the hole

""" def generatedwg(latmin, lonmin, latmax, lonmax, lat_degree_distance, lon_degree_distance, dwg_bg_color):

    lat_distance = (latmax - latmin) * lat_degree_distance
    lon_distance = (lonmax - lonmin) * lon_degree_distance

    # set the scale of our dwgs to be 3000 pixels for the longest distance (x or y)
    # also define yards per pixel (ypp) and pixels per yard values to use in distance calculation

    y_scale = 3000
    x_scale = 3000

    if lat_distance >= lon_distance:
        y_dim = y_scale
        x_dim = int((lon_distance / lat_distance) * x_scale)
        ypp = lat_distance / y_scale
    else:
        x_dim = x_scale
        y_dim = int((lat_distance / lon_distance) * y_scale)
        ypp = lon_distance / y_scale


    im = np.zeros((x_dim, y_dim, 3), np.uint8)

    # Fill dwg with background color

    im[:] = dwg_bg_color

    # return the dwg and some other information for use in measurement

    return im, x_dim, y_dim, ypp
 """


def rgb_to_hex(rgb_tuple):
    return '#%02x%02x%02x' % rgb_tuple
# svg document creation, instead of raster dwg

# create a blank dwg of the appropriate size to use in drawing the hole

def generateSVG(latmin, lonmin, latmax, lonmax, lat_degree_distance, lon_degree_distance, bg_color):
    lat_distance = (latmax - latmin) * lat_degree_distance
    lon_distance = (lonmax - lonmin) * lon_degree_distance

    y_scale = 3000
    x_scale = 3000

    if lat_distance >= lon_distance:
        y_dim = y_scale
        x_dim = int((lon_distance / lat_distance) * x_scale)
        ypp = lat_distance / y_scale
    else:
        x_dim = x_scale
        y_dim = int((lat_distance / lon_distance) * y_scale)
        ypp = lon_distance / y_scale

     # Convert fill color if it's a tuple
    if isinstance(bg_color, tuple):
        bg_color = rgb_to_hex(bg_color)

    # SVG dimensions in pixels (can be styled in px or user units)
    dwg = svgwrite.Drawing(size=(x_dim, y_dim), viewBox=f"0 0 {x_dim} {y_dim}")
    
    # Add background rectangle
    dwg.add(dwg.rect(insert=(0, 0), size=(x_dim, y_dim), fill="purple"))
    # Create a group for all features. This is to ensure that we can crop the paths and only show what's important
    features_group = dwg.g(id="features")
    dwg.add(features_group)

    #DEBUG - save the SVG to a file
    #filename = "newdrawing.svg"
    #dwg.saveas(filename) #saving for debugging purposes

    return dwg, x_dim, y_dim, ypp

# given a golf hole's waypoints, get all feature data from OSM for that hole (e.g. fairway, sand traps, water hazards, etc)

def getHoleOSMData(way, lat_degree_distance, lon_degree_distance):

    # get the bounding box to search for this hole

    hole_minlat, hole_minlon, hole_maxlat, hole_maxlon, hole_way_nodes = getHoleBoundingBox(way, lat_degree_distance, lon_degree_distance)

    # download all golf data in this bounding box from OSM

    hole_result = getOSMGolfData(hole_minlat, hole_minlon, hole_maxlat, hole_maxlon)

    return hole_way_nodes, hole_result, hole_minlat, hole_minlon, hole_maxlat, hole_maxlon


# given a list of coordinates that define a golf hole in OSM, find the green

def identifyGreen(hole_way_nodes, hole_result):

    green_found = False
    holeway_pointElv = []
    lenght = len(hole_way_nodes)

    #calcuate the elevation for each of the way points found in hole_way_nodes and add to holeway_pointElv array
    for i in range(lenght):
        elevationPoint = calcElevation (hole_way_nodes[i].lat, hole_way_nodes[i].lon)
        holeway_pointElv.append(elevationPoint)
        print("this is the number ", i, "holeway node elevation point :", holeway_pointElv)
  
    green_center = hole_way_nodes[-1] #-1 gets us the last node, assuning it's in the middle of the green and the hole way is drawn from T to Green
  
    """# if mapped correctly, the last coordinate should mark the center of the green in OSM
    
    #green_edge = hole_way_nodes[-1] #-1 gets us the last node, assuning it's at the front edge of the green (closest to the Tee)
    print(hole_way_nodes, "these are the hole way nodes")
    print(green_center, "these is the green center node")
    print(green_center.lat, green_center.lon)
    
    #get elevation from google elevation api
    green_pointElv = calcElevation (green_center.lat, green_center.lon)
    print(green_pointElv, "this is the elevation of the green center point") """

 
    
    #get the Green Center Elevation and caculate relative hight difference from T to Green Center
    relative_green_centerElevation = holeway_pointElv[-1] - holeway_pointElv[0]
    print("this is the height difference from T to Green Center: ", round(relative_green_centerElevation,2))
    
 
     # now search all the data we have for this hole, and filter to find golf greens only
    # check each one to see if it contains the center of the green for the hole we are on
    # (we have to do this because sometimes the green from another hole might be close enough
    # to the fairway to show up in our data pull)

    for way in hole_result.ways:
        if way.tags.get("golf", None) == "green":

            green_nodes = way.get_nodes(resolve_missing=True)

            green_min_lat, green_min_lon, green_max_lat, green_max_lon = getBoundingBoxLatLon(green_nodes) #check if last node of way is in the center of the green
            #print("this is green_min_lat: ", green_min_lat, " this is green_max_lat: ", green_max_lat, " this is green_min_lon: ", green_min_lon, " this is green_max_lon: ", green_max_lon)
            
            #checking if we found a green
            print("we found a green")
            # print("DEBUG]: we found a green:", way, green_nodes)

            # checking if the center of the green for this hole is within this green
            #if green_edge.lat > green_min_lat and green_center.lat < green_max_lat and green_center.lon > green_min_lon and green_center.lon < green_max_lon:
            #print("[DEBUG]: green center lat >: ", green_center.lat, "green min lat: ",green_min_lat, "green center max lat <: ", green_max_lat, "green center lon >: ", green_center.lon, "green min lon: ", green_min_lon, "green center lon <: ", green_center.lon, "green max lon: ", green_max_lon)
            if green_center.lat > green_min_lat and green_center.lat < green_max_lat and green_center.lon > green_min_lon and green_center.lon < green_max_lon:

                green_found = True
                #print("DEBUG]: these are the green way nodes", way, green_nodes) #prints way number of OSM -- for debugging only
                return green_nodes

    # if we couldn't find a green, return an error

    if green_found == False:
        print("Error: green could not be found")
        return None

    
 #calcuate the lat/lon between green way nodes for elevation calcuation
def get_green_grid_points(way_nodes, spacing_yards=3):
    """
    Generate a grid of lat/lon points spaced every 3 yards inside the green.
    
    Parameters:
        way_nodes: List of (lat, lon) tuples forming the green boundary.
        spacing_yards: Grid spacing in yards.
        
    Returns:
        List of (lat, lon) tuples for each grid point inside the green.
    """
    # Convert to polygon
    coords = [(node.lat, node.lon) for node in way_nodes]
    green_polygon = Polygon(coords)
    if not green_polygon.is_valid:
        raise ValueError("Invalid polygon provided for green boundary.")

    # Convert yard spacing to degrees (approximate)
    spacing_deg = spacing_yards / 1.0936 / 111000  # 1 deg ~ 111km

    # Get bounding box
    lats, lons = zip(*[(node.lat, node.lon) for node in way_nodes])
    lat_min, lat_max = min(lats), max(lats)
    lon_min, lon_max = min(lons), max(lons)
    lat_min = float(lat_min) - (40 * spacing_deg)
    lat_max = float(lat_max) + (40 * spacing_deg)
    lon_min = float(lon_min) - (40 * spacing_deg)
    lon_max = float(lon_max) + (40 * spacing_deg)

    # Create grid
    lat_grid = np.arange(lat_min, lat_max, spacing_deg)
    lon_grid = np.arange(lon_min, lon_max, spacing_deg)

    # Elevation map
    elevation_map = {}

    for lat in lat_grid:
        for lon in lon_grid:
            if green_polygon.contains(Point(lat, lon)):
                elevation = calcElevation(lat, lon)
                if elevation is not None:
                    elevation_map[(lat, lon)] = elevation

    return elevation_map

# convert an OSM way to a numpy array we can use for dwg processing

def translateWaytoNP(way, hole_minlat, hole_minlon, hole_maxlat, hole_maxlon, x_dim, y_dim):
    #
    # print("getting nodes for: ", way.tags.get("golf", None))


    # convert each coordinate's location within the bounding box to a pixel location
    # ex: if a coordinate is 70% of the way east and 30% of the way north in the bounding box,
    # we want that point to be 70% from the left and 30% from the bottom of our dwg

    nds = []
    for node in way.get_nodes(resolve_missing=True):
        yfactor = ((float(node.lat) - hole_minlat) / (hole_maxlat - hole_minlat)) * y_dim
        xfactor = ((float(node.lon) - hole_minlon) / (hole_maxlon - hole_minlon)) * x_dim

        # we need to round to integers for dwg processing

        column = int(xfactor)
        row = int(yfactor)

        nds.append((column, row))

    # the script uses points and not dwg pixels, so flip the x and y

    nds = np.array(nds)
    nds[:,[0, 1]] = nds[:,[1, 0]]

    return nds


# convert a list of coordinates to a numpy array we can use for dwg processing

def translateNodestoNP(nodes, hole_minlat, hole_minlon, hole_maxlat, hole_maxlon, x_dim, y_dim):

    # convert each coordinate's location within the bounding box to a pixel location
    # ex: if a coordinate is 70% of the way east and 30% of the way north in the bounding box,
    # we want that point to be 70% from the left and 30% from the bottom of our dwg

    nds = []
    for node in nodes:
        yfactor = ((float(node.lat) - hole_minlat) / (hole_maxlat - hole_minlat)) * y_dim
        xfactor = ((float(node.lon) - hole_minlon) / (hole_maxlon - hole_minlon)) * x_dim


        # we need to round to integers for dwg processing

        column = int(xfactor)
        row = int(yfactor)

        nds.append((column, row))

    # the script uses points and not dwg pixels, so flip the x and y

    nds = np.array(nds)
    nds[:,[0, 1]] = nds[:,[1, 0]]

    return nds


# take the data dump for a given hole and categorize all the data by feature type for drawing

def categorizeWays(hole_result, hole_minlat, hole_minlon, hole_maxlat, hole_maxlon, x_dim, y_dim):

    sand_traps = []
    tee_boxes = []
    fairways = []
    water_hazards = []
    woods = []
    trees = []

    print("Categorizing ways...")

    for way in hole_result.ways:

        # see how each object was tagged in OSM (and do a little extra categorizing for
        # water hazards and woods)

        golf_type = way.tags.get("golf", None)

        natural_type = way.tags.get("natural", None)

        if natural_type == "water":
            golf_type = "water_hazard"

        if natural_type == "wood" or way.tags.get("landuse", None) == "forest":
            golf_type = "woods"


        # find what kind of feature we have and add its numpy array to the appropriate list

        if golf_type == "bunker":
            # node_list = list(way.get_nodes(resolve_missing=True))
            # print(node_list)
            sand_traps.append(translateWaytoNP(way, hole_minlat, hole_minlon, hole_maxlat, hole_maxlon, x_dim, y_dim))

        elif golf_type == "tee":
            # node_list = list(way.get_nodes(resolve_missing=True))
            # print(node_list)
            tee_boxes.append(translateWaytoNP(way, hole_minlat, hole_minlon, hole_maxlat, hole_maxlon, x_dim, y_dim))

        elif golf_type == "water_hazard" or golf_type == "lateral_water_hazard":
            # node_list = list(way.get_nodes(resolve_missing=True))
            # print(node_list)
            water_hazards.append(translateWaytoNP(way, hole_minlat, hole_minlon, hole_maxlat, hole_maxlon, x_dim, y_dim))

        elif golf_type == "fairway":
            # node_list = list(way.get_nodes(resolve_missing=True))
            #print(node_list)
            fairways.append(translateWaytoNP(way, hole_minlat, hole_minlon, hole_maxlat, hole_maxlon, x_dim, y_dim))

        elif golf_type == "woods":
            woods.append(translateWaytoNP(way, hole_minlat, hole_minlon, hole_maxlat, hole_maxlon, x_dim, y_dim))

        else:
            continue


    # the only feature we care about that would show up as a node would be a tree

    for node in hole_result.nodes:

        if node.tags.get("natural", None) == "tree":

            trees.append(translateNodestoNP([node], hole_minlat, hole_minlon, hole_maxlat, hole_maxlon, x_dim, y_dim))


    # give back a list of the numpy arrays for each feature type
    print("these are the trees found:", trees)

    return sand_traps, tee_boxes, fairways, water_hazards, woods, trees


# given a numpy array and an dwg, fill in the array as a polygon on the dwg (in a given color). Negative line thickness = filled polygon
# also draw an outline if it is specified

""" def drawFeature(dwg, array, color, line):
    #upsize dwg for better quality
    dwg = np.zeros((height * 4, width * 4, 3), dtype=np.uint8)
    
    nds = np.array(array)
    #nds = np.int32([array]) # bug in fillPoly - needs explicit cast to 32bit
    print("node 0", nds[0])
    tck, u = splprep([nds[:, 0], nds[:, 1]], s=0.1, per=1)
    smooth_lat, smooth_lon = splev(np.linspace(0, 1, 100000), tck)
    
    smooth_points = np.vstack((smooth_lat, smooth_lon)).T  # Stack as Nx2 array
    smooth_points = np.round(smooth_points).astype(int)    # Round and convert to integers
    
    # Ensure the points are in a shape cv2.polylines expects (list of arrays)
    smooth_points = smooth_points.reshape((-1, 1, 2))
    print("smoothing done")
    
    if line < 0:
        cv2.fillPoly(dwg, [smooth_points], color)
        
    if line > 0:
        print("drawing the line now")
        # need to redraw a line since fillPoly has no line thickness options that I've found
        #cv2.polylines(dwg, nds, True, color, line, lineType=cv2.LINE_AA)
        cv2.polylines(dwg, [smooth_points], True, color, line, lineType=cv2.LINE_AA)

    #downsize dwg after drawing. 
    dwg = cv2.resize(dwg, (width, height), interpolation=cv2.INTER_AREA) """
     

#draw features with SVG
def drawFeatureSVG(features_group, array, color, fill, line_width=1, smoothness=1.0, samples=1000):
    # Convert the input array to numpy array
    nds = np.array(array)
    #print(f"[DEBUG]: Input array: {array}")  # Debugging line
    stroke_color = darken_hex_color(color, factor=0.8)
    
    # Check if there are enough points
    if len(nds) < 3:
        print("Not enough points to create a feature.")  # Debugging line
        return
    
    # Prepare the spline
    tck, u = splprep([nds[:, 0], nds[:, 1]], s=smoothness, per=1)
    #print(f"[DEBUG]: Spline preparation result: tck={tck}, u={u}")  # Debugging line
    
    # Evaluate the spline at samples intervals
    smooth_x, smooth_y = splev(np.linspace(0, 1, samples), tck)
    points = list(zip(smooth_x, smooth_y))
    
    # Debugging the smooth points
    #print(f[DEBUG]: Generated points: {list(zip(smooth_x, smooth_y))[:5]}")  # Log first 5 points
    
    # Create the path for the feature
    path_data = "M {} {}".format(points[0][0], points[0][1])
    for x, y in points[1:]:
        path_data += " L {},{}".format(x, y)
    path_data += " Z"
    #print(f"[DEBUG]: Path data: {path_data}")  # Debugging line

    # Create the path element
    path = svgwrite.path.Path(d=path_data, stroke=stroke_color, fill=color if fill else "none", stroke_width=line_width)
    
    # Add the path element to the SVG
    features_group.add(path)
    
    # Print out the entire SVG content for inspection
    #print("[DEBUG]: ", dwg.tostring())  # Log the full SVG content


def darken_hex_color(hex_color, factor=0.85):
    """
    Returns a darker version of a given hex color.
    Keeps it strictly hex — no RGB or named colors.
    """
    hex_color = hex_color.lstrip('#')
    if len(hex_color) != 6:
        raise ValueError(f"Invalid hex color: {hex_color}")
    r = int(hex_color[0:2], 16)
    g = int(hex_color[2:4], 16)
    b = int(hex_color[4:6], 16)

    r = max(0, int(r * factor))
    g = max(0, int(g * factor))
    b = max(0, int(b * factor))

    return "#{:02x}{:02x}{:02x}".format(r, g, b)
# for a list of arrays and an dwg, draw each array as a polygon on the dwg (in a given color)

def drawFeatures(dwg, feature_list, color, line_width=1,feature_type=None):
    print("calling drawFeaturesSVG", color)
    for feature_nodes in feature_list:
        print("calling drawFeaturesSVG", color)
  
        #check if color = sand and if yes set fill to true
        fill = feature_type in ["sand", "woods", "water"]
   
        drawFeatureSVG(dwg, feature_nodes, color, fill, line_width=1)
          


# for a list of tree nodes and an dwg, draw each tree on the dwg

def wavy_tree_path(size, wave_count=8, inner=False):
    """Generate a wavy circular path representing the tree canopy."""
    r = size * 0.35 if not inner else size * 0.25
    cx, cy = size / 2, size / 2
    path = svgwrite.path.Path(fill="none", stroke_width=2)

    angle_step = 2 * math.pi / wave_count
    wave_amplitude = size * 0.05
    rotate_offset = angle_step / 2 if inner else 0

    # Move to start
    x0 = cx + r * math.cos(rotate_offset)
    y0 = cy + r * math.sin(rotate_offset)
    path.push(f"M{x0:.2f},{y0:.2f}")

    for i in range(1, wave_count + 1):
        angle1 = rotate_offset + (i - 1) * angle_step
        angle2 = rotate_offset + i * angle_step
        mid_angle = (angle1 + angle2) / 2

        # Control point for wavy effect
        control_x = cx + (r + wave_amplitude) * math.cos(mid_angle)
        control_y = cy + (r + wave_amplitude) * math.sin(mid_angle)
        x = cx + r * math.cos(angle2)
        y = cy + r * math.sin(angle2)

        path.push(f"Q{control_x:.2f},{control_y:.2f} {x:.2f},{y:.2f}")

    path.push("Z")
    return path

def drawTrees(features_group, feature_list, stroke_color="#228B22"):  # Default color is a forest green

    #print("[DEBUG]: tree feature list", feature_list)
    trunk_color="#6D4C41"
    size=100

    for feature_nodes in feature_list:
        # Convert numpy feature array to coordinate
        tree = np.int32([feature_nodes]).tolist()[0][0]
        x, y = int(tree[0]), int(tree[1])
        
        # Create a group element for the tree
        tree_group = svgwrite.container.Group()
        
        # Outer wavy canopy
        outer_path = wavy_tree_path(size, wave_count=12)
        outer_path.stroke(color=stroke_color)
        tree_group.add(outer_path)
        
        # Inner rotated wavy layer
        inner_path = wavy_tree_path(size, wave_count=10, inner=True)
        inner_path.stroke(color=stroke_color, opacity=0.7)
        tree_group.add(inner_path)
        
        # Trunk
        trunk = svgwrite.shapes.Circle(
            center=(size * 0.5, size * 0.5),
            r=size * 0.03,
            fill=trunk_color
        )
        
        tree_group.add(trunk)
        
        #add the central trunk circle (adjust position based on size) 
        trunk = svgwrite.shapes.Circle(center=(size//2, size//2), r=size//33, fill=trunk_color)
        

         # Add to group
        tree_group.add(outer_path)
        tree_group.add(inner_path)
        tree_group.add(trunk)
        # Translate group to desired x,y (centered)
        tree_group.translate(x - size // 2, y - size // 2)
        
        # Add elements to the drawing
        features_group.add(tree_group)


# when the features were rotated, their coordinates could have been outside our dwg boundaries
# so we have to adjust them to be within the boundaries of our new dwg

def adjustRotatedFeatures(feature_list, ymin, xmin):
    minx = miny = 10000
    maxx = maxy = -10000

    output_list = []

    for feature_nodes in feature_list:
        print(f"Processing feature_nodes type: {type(feature_nodes)}")

        if isinstance(feature_nodes, np.ndarray):
            feature_nodes = feature_nodes.tolist()
            #print(f"[]DEBUG]: onverted feature_nodes to list: {feature_nodes}")

        print(f"feature_nodes length: {len(feature_nodes)}")

        feature_nodes = np.array(feature_nodes)
        w = np.zeros((len(feature_nodes), 2), dtype=np.float64)  # 2D array

        #print(f"[DEBUG]: Before translation, feature_nodes: {feature_nodes}")

        for i, v in enumerate(feature_nodes):
            w[i] = v
            x = w[i, 0]
            y = w[i, 1]

            newx = float(x) - xmin
            newy = float(y) - ymin

            w[i, 0] = newx
            w[i, 1] = newy

            minx = min(x, minx)
            miny = min(y, miny)
            maxx = max(x, maxx)
            maxy = max(y, maxy)

        #print(f"[DEBUG]:Processed feature_nodes: {w}")
        output_list.append(w)

    return output_list, minx, miny, maxx, maxy




# take a properly rotated hole from OSM and create a bounding box around it

def createHoleBoundingBox(rotated_hole_array, ypp):

    hole_node_list = rotated_hole_array.tolist()

    org_bb_xmin = org_bb_ymin = 6000
    org_bb_xmax = org_bb_ymax = -6000

    for node in hole_node_list:
        org_bb_xmin = min(org_bb_xmin,node[0])
        org_bb_ymin = min(org_bb_ymin,node[1])
        org_bb_xmax = max(org_bb_xmax,node[0])
        org_bb_ymax = max(org_bb_ymax,node[1])

    # add some padding in each direction to make sure we get all the features:

    # 50 yards to the left and to the right
    bb_xmin = org_bb_xmin - (50 / ypp)
    bb_xmax = org_bb_xmax + (50 / ypp)

    # 30 yards to the top (for bunkers or water that are past the green)
    bb_ymin = org_bb_ymin - (30 / ypp)

    # 10 yards to the bottom (we don't really care about features behind the tee box)
    bb_ymax = org_bb_ymax + (10 / ypp)


    # calculate the width of our hole bounding box, and if it's too wide, trim it down a bit
    x_spread = (bb_xmax - bb_xmin) * ypp

    if x_spread > 125:

        bb_xmin += ((x_spread - 125) / 2) / ypp
        bb_xmax -= ((x_spread - 125) / 2) / ypp

        bb_xmin = min(bb_xmin, (org_bb_xmin - 15/ypp))
        bb_xmax = max(bb_xmax, (org_bb_xmax + 15/ypp))

        x_spread = (bb_xmax - bb_xmin) * ypp

        print("Hole bounding box constrained to: ", x_spread, " yards wide")


    # print("Hole bounding box: ",bb_xmin, bb_ymin, bb_xmax, bb_ymax)

    return bb_xmin, bb_ymin, bb_xmax, bb_ymax


# take a list of features and filter out anything that is too far from the hole we are drawing right now

def filterArrayList(rotated_hole_array, feature_list, ypp, par, tee_box=0, fairway=0, filter_yards=50, small_filter=1, med_filter=1):

    # if we've decided not to filter anything, just return the original list
    if filter_yards == None:
        return feature_list

    # take a properly rotated hole from OSM and create a bounding box around it

    bb_xmin, bb_ymin, bb_xmax, bb_ymax = createHoleBoundingBox(rotated_hole_array, ypp)


    # get the origin point and center of the green for this hole

    hole_node_list = rotated_hole_array.tolist()

    green_center = hole_node_list[-1]
    hole_origin = hole_node_list[0]


    # get the hole midpoint as well

    if len(hole_node_list) == 2:
        midpoint = getMidpoint(green_center, hole_origin)
    else:
        midpoint = hole_node_list[1]


    # define an empty result list
    filtered_list = []

    box_width = bb_xmax - bb_xmin


    # since par 3s are pretty short, we want to handle filtering a little differently
    if par == 3:
        par4plus = 0
    else:
        par4plus = 1

    # filtering out any tee boxes that are too close to the green
    # this helps reduce drawing extra features and carry distances
    tee_box_filter = tee_box * (75/ypp + par4plus * (140/ypp))

    # optional parameters to control how features are filtered near the tee box
    small = filter_yards * small_filter #0.5
    med = filter_yards * med_filter #0.75
    # lg =  box_width - (box_width / 1.25)


    for array in feature_list:

        centroid = array.mean(axis=0)

        x = float(centroid[0])
        y = float(centroid[1])

        # filter to see whether the point is within 75 yards
        # of the tee box (near tee) or within 150 yards (short range)

        nearest_tee = ((bb_ymax - y)*ypp < 75)
        short_range = ((bb_ymax - y)*ypp < 150)
        # mid_range = ((bb_ymax - y)*ypp < 200)

        if par == 3:
            # for par 3s, don't filter anything more constrained than the initial box
            # so, ignore whether the object is close to the tee box

            nearest_tee = False
            short_range = False
            # mid_range = False


        # first step - if the center of our object is outside the hole bounding box,
        # let's filter it out

        if y > bb_ymax or y < (bb_ymin + tee_box_filter) or x < bb_xmin or x > bb_xmax:
            # print("Object outside bounding box filtered out")
            continue


        # we can add another easy check for whether a fairway belongs to the
        # current hole by seeing if it has any points that go behind the tee box or
        # past the green - if it does, we'll filter it out

        if fairway == 1 & par > 3: #par 3 fairways typically extend beyond the green hence we need to include them

            pointlist = array.tolist()
            maxpoint = minpoint = pointlist[0]

            for point in pointlist:
                if point[1] > maxpoint[1]:
                    maxpoint = point
                if point[1] < minpoint[1]:
                    minpoint = point

            if maxpoint[1] > bb_ymax or minpoint[1] < bb_ymin:
                # print("Fairway filtered out - points outside of bounding box")
                continue


        # now we're getting to trickier filtering
        # we want to calculate how far away the object is from the "center line" of the hole

        if y < midpoint[1]:
            dist_to_way = distToLine(centroid,midpoint,green_center,ypp)
        else:
            dist_to_way = distToLine(centroid,midpoint,hole_origin,ypp)

        # # print("Bounding box nearest tees: x from",(bb_xmin + (30/ypp)), "to",(bb_xmax - (30/ypp)),"y from", bb_ymin, "to", bb_ymax)
        # # print("Bounding box for tee boxes nearest tees: x from",
        # (bb_xmin + (30/ypp)), "to",(bb_xmax - (30/ypp)),"y from", (bb_ymin + (tee_box * 190 / ypp)), "to", bb_ymax)

        # if constrained:

        # 	if x > bb_xmin and x < bb_xmax and y > (bb_ymin + (tee_box * 190 / ypp)) and y < bb_ymax:
        # 		filtered_list.append(array)
        # 	else:
        # 		print("Array filtered out:", centroid)

        # else:


        # now we are going to filter based on hole width - if something is too far
        # to the left or right, we'll assume it's from a different hole and filter it out.
        # (again, there is an option to filter more aggressively near the tee box)

        if nearest_tee:
            if dist_to_way < small:
                filtered_list.append(array)
            # else:
                # print("Array filtered out:", centroid)

        elif short_range:
            if dist_to_way < med:
                filtered_list.append(array)
            # else:
                # print("Array filtered out:", centroid)

        else:
            if dist_to_way < filter_yards:
                filtered_list.append(array)
            # else:
                # print("Array filtered out:", centroid)

        # elif mid_range:
        # 	if x > (bb_xmin + lg/2) and x < (bb_xmax - lg/2) and y > (bb_ymin + tee_box_filter) and y < bb_ymax:
        # 		filtered_list.append(array)
        # 	else:
        # 		print("Array filtered out:", centroid)

        # else:
        # 	if x > bb_xmin and x < bb_xmax and y > (bb_ymin + tee_box_filter) and y < bb_ymax:
        # 		filtered_list.append(array)
        # 	else:
        # 		print("Array filtered out:", centroid)
  
        print("done with filtering array list")

    return filtered_list


# calculate the angle from the center of the green to an arbitrary point

def getAngle(green_center, other_point):
    x = green_center[0]
    y = green_center[1]

    x2 = other_point[0]
    y2 = other_point[1]

    bigy = max(y, y2)
    smally = min(y, y2)

    numerator = bigy - smally
    denominator = math.sqrt(((x2 - x) ** 2) + ((bigy - smally) ** 2))

    rads = math.acos((numerator / denominator))
    angle = math.degrees(rads)
    print("DEBUG: this is the original rotation angle in RAD found:", angle)

    # adjust to get the appropriate angle for our use
    if y > y2 and x > x2:
        angle = 180 - angle
    elif y > y2 and x < x2:
        angle = 180 + angle
    elif y < y2 and x < x2:
        angle = 360 - angle

    return angle


# given a list of the hole coordinates, figure out how much we need to
# rotate our dwg in order to display the hole running from bottom to top

def getRotateAngle(hole_way_nodes):

    combined_list = hole_way_nodes.tolist()

    green_center = combined_list[-1]

    midpoint = combined_list[0]

    x = green_center[0]
    y = green_center[1]

    x2 = midpoint[0]
    y2 = midpoint[1]


    bigy = max(y, y2)
    smally = min(y, y2)


    numerator = bigy - smally
    denominator = math.sqrt(((x2-x)**2)+((bigy-smally)**2))

    rads = math.acos((numerator/denominator))

    angle = math.degrees(rads)

    # adjust to get the appropriate angle for our use

    if y > y2 and x > x2:
        angle = 180 - angle
        # print("green center is lower right of midpoint")
    elif y > y2 and x < x2:
        angle = 180 + angle
        # print("green center is lower left of midpoint")
    elif y < y2 and x < x2:
        angle = 360 - angle
        # print("green center is upper left of midpoint")
    else:
        # print("green center is upper right of midpoint")
        angle=angle

    print("DEBUG: Angle to be rotated is:", angle)

    return angle


# given a list of the hole coordinates, figure out how much we need to rotate our dwg
# to show the approach to the green running from the bottom to the top

def getMidpointAngle(hole_way_nodes):

    combined_list = hole_way_nodes.tolist()

    green_center = combined_list[-1]

    midpoint = combined_list[-2]

    x = green_center[0]
    y = green_center[1]

    x2 = midpoint[0]
    y2 = midpoint[1]


    bigy = max(y, y2)
    smally = min(y, y2)


    numerator = bigy - smally
    denominator = math.sqrt(((x2-x)**2)+((bigy-smally)**2))

    rads = math.acos((numerator/denominator))

    angle = math.degrees(rads)

    # adjust to get the appropriate angle for our use

    if y > y2 and x > x2:
        angle = 180 - angle
        # print("green center is lower right of midpoint")
    elif y > y2 and x < x2:
        angle = 180 + angle
        # print("green center is lower left of midpoint")
    elif y < y2 and x < x2:
        angle = 360 - angle
        # print("green center is upper left of midpoint")
    else:
        # print("green center is upper right of midpoint")
        angle=angle

    # print("Angle to be rotated is:", angle)

    return angle


def Rotate2D(pts,cnt,ang):

    # rotates pts about center cnt by angle ang in radians
    # found online somewhere

    return np.dot(pts-cnt,np.array([[math.cos(ang),math.sin(ang)],
        [-math.sin(ang),math.cos(ang)]]))+cnt


def get_svg_dimensions(dwg):
    width = int(str(dwg['width']).replace("px", ""))
    height = int(str(dwg['height']).replace("px", ""))
    return height, width

# rotate an array (such as a sand trap) by the appropriate angle to show
# the hole running from bottom to top

""" def rotateArray(dwg, array, angle):

    theta = np.radians(-angle)

    (height, width) = dwg.shape[:2]

    ox = width // 2
    oy = height // 2

    center = np.array([ox, oy])

    return Rotate2D(array,center,theta) """
 
 
 #adapted for SVG
 
def rotateArray(dwg, array, angle):
    # Convert angle to radians (negated to match typical rotation convention)
    theta = np.radians(-angle)
    print("DEBUG: this is the rotate Array angle in RADn from function rotate array:", theta)

    # Extract width and height from SVG drawing (removing 'px' and converting to int)
    width = int(str(dwg['width']).replace("px", ""))
    height = int(str(dwg['height']).replace("px", ""))

    # Determine center point of the canvas
    ox = width // 2
    oy = height // 2
    center = np.array([ox, oy])

    # Rotate the array of points around the center
    return Rotate2D(array, center, theta)



# given a list of arrays for a certain hole, rotate each of them by a given angle

def rotateArrayList(dwg,array_list,angle):

    new_list = []

    for array in array_list:
        rotated_array = rotateArray(dwg, array, angle)
        new_list.append(rotated_array)

    return new_list


# given an existing hole dwg and an angle to rotate it,
# create a new dwg with appropriate dimensions to display
# the hole running from bottom to top


def getNewdwg(dwg, angle, dwg_bg_color):
    # Extract dimensions from svgwrite.Drawing
    w = int(float(str(dwg['width']).replace("px", "")))
    h = int(float(str(dwg['height']).replace("px", "")))

    # Define the original corners of the canvas
    boundary_array = np.array([
        [0, 0],
        [w, 0],
        [w, h],
        [0, h]
    ])

    # Rotate the boundary corners
    rotated_array = rotateArray(dwg, boundary_array, angle)
    rotated_coords = rotated_array.tolist()

    # Find new bounding box
    xs, ys = zip(*rotated_coords)
    xmin, xmax = min(xs), max(xs)
    ymin, ymax = min(ys), max(ys)
    x_dim = int(np.ceil(xmax - xmin))
    y_dim = int(np.ceil(ymax - ymin))

    # Create new drawing with expanded dimensions
    new_dwg = svgwrite.Drawing(size=(f"{y_dim}px", f"{x_dim}px")) #swap for vertical orientation

    # Simulate background color by drawing a filled rectangle
    #new_dwg.add(new_dwg.rect(insert=(0, 0), size=(y_dim, x_dim), fill="pink"))#dwg_bg_color
    #filename = "new_rotated_drawing.svg"
    #new_dwg.saveas(filename)
    #print(f"[DEBUG] New drawing saved as {filename}")	

    return new_dwg, ymin, xmin, ymax, xmax


# calculate the difstance between two pixels in yards (given a yards per pixel value)

def getDistance(originpoint, destinationpoint, ypp):
    """
    Computes the distance between two 2D points and scales to yards.
    Includes debugging output for tracing issues.
    """
    try:
        #print(f"[DEBUG] Raw input -> origin: {originpoint}, dest: {destinationpoint}, ypp: {ypp}")

        # Handle nested structures
        if isinstance(originpoint[0], (list, tuple, np.ndarray)):
            #print("[DEBUG] Unwrapping origin point")
            originpoint = originpoint[0]
        if isinstance(destinationpoint[0], (list, tuple, np.ndarray)):
            #print("[DEBUG] Unwrapping destination point")
            destinationpoint = destinationpoint[0]

        # Ensure proper format
        if not (isinstance(originpoint, (list, tuple, np.ndarray)) and 
                isinstance(destinationpoint, (list, tuple, np.ndarray))):
            #print("[ERROR] One or both points are not list/tuple/ndarray")
            return 0

        if len(originpoint) != 2 or len(destinationpoint) != 2:
            #print(f"[ERROR] Incorrect point dimensions: origin {len(originpoint)}, dest {len(destinationpoint)}")
            return 0

        # Compute distance
        distance = dist.euclidean(originpoint, destinationpoint)
        distance_in_yards = distance * ypp
        #print(f"[DEBUG] Distance (pixels): {distance}, in yards: {distance_in_yards}")

        return distance_in_yards

    except Exception as e:
        print(f"[EXCEPTION] getDistance failed with: {e}")
        return 0



# for a list of features, get the point of each feature that is
# closest to the top of the dwg

def getMaxPoints(feature_list):

    max_points = []

    for feature in feature_list:
        pointlist = feature.tolist()
        maxpoint = pointlist[0]

        for point in pointlist:
            if point[1] < maxpoint[1]:
                maxpoint = point

        max_points.append(maxpoint)

    return max_points


# for a list of features, get the point of each feature that is
# furthest from the top of the dwg

def getMinPoints(feature_list):

    min_points = []

    for feature in feature_list:
        pointlist = feature.tolist()
        minpoint = pointlist[0]

        for point in pointlist:
            if point[1] > minpoint[1]:
                minpoint = point

        min_points.append(minpoint)

    return min_points


# given a list of points, draw a dot on each point in our dwg

def drawMarkerPoints(dwg, tee_box_points, text_size, text_color):
    # Loop through the points and draw circles using SVG methods
    for point in tee_box_points:
        # Draw a circle at each point
        dwg.add(dwg.circle(
            center=(int(point[0]), int(point[1])),  # Position of the circle
            r=int(0.25*text_size),  # Radius of the circle, adjusted with text_size
            fill=text_color  # Fill color
        ))

# given a point, draw in the carry distances to that point from the
# back of each tee box (given in tee_box_points)
# carry distance is measured from back of tee box

def drawCarry(dwg, green_center, carrypoint, tee_box_points, ypp, text_size, text_color, right):
    print("drawing carry distances")
    text_weight = round(text_size * 2)
    font_weight = "normal" if text_weight < 2 else "bold"  # default behavior

    dist_list = []

    if len(tee_box_points) == 0:
        print("error: no tee box points found for carries")
        return 0

    for tee in tee_box_points:
        distance = int(getDistance(tee, carrypoint, ypp))
        dist_list.append(distance)

    maxpoint_distance = max(dist_list)

    # we only want to draw carry distances that are actually helpful to see on the tee
    # if it's too close or too far, ignore it
    if maxpoint_distance < 185 or maxpoint_distance > 325:
        # print("carry outside of our reasonable range")
        return 0

    # count the number of tees
    tee_num = len(dist_list)

    # calculate the total label height
    totalheight = (32 * (tee_num - 1) * text_size)

    # declare x and y coordinates to place the text
    if right:
        x = int(carrypoint[0] + (0.8 * text_size))
    else:
        x = int(carrypoint[0] + (0.4 * text_size + 0.1))  # Adjusted to better center text

    y = int(carrypoint[1] - totalheight / 2 + 4)

    # declare an increment for each new tee distance (so that they stack vertically)
    yinc = int(32 * text_size)

    # sort the distances for the marked T boxes in ascending order i.e. from shortest to longest
    dist_list.sort()

    # draw each distance as text on the SVG canvas
    for distance in dist_list:
        dwg.add(dwg.text(
            str(distance),
            insert=(x, y),
            font_size=text_size, #text_size,
            fill="red", #text_color,
            font_weight=font_weight,
            font_family="Arial"
        ))
        y += yinc

    # mark the carry point as a circle
    dwg.add(dwg.circle(
        center=(carrypoint[0], carrypoint[1]),
        r=int(0.25*text_size),
        fill=text_color
    ))

    drawMarkerPoints(dwg, tee_box_points, text_size, text_color)

    dtg = getDistance(green_center, carrypoint, ypp)

    if dtg < 40 or maxpoint_distance < 215 or maxpoint_distance > 290:
        # print("still need a carry to reasonable fairway point", dtg, maxpoint_distance)
        return 0
    else:
        # print("confirmed reasonable carry")
        return 1




def getMidpoint(ptA, ptB):
    return ((ptA[0] + ptB[0]) * 0.5, (ptA[1] + ptB[1]) * 0.5)



# get a list of three waypoints for a  hole, even if there are only two or more than three

def getThreeWaypoints(adjusted_hole_array):
    # Check if the adjusted_hole_array is empty or not
    if len(adjusted_hole_array) == 0:
        print("Error: adjusted_hole_array is empty.")
        return None, None, None  # Or handle the error as needed
    
    # If the array is not empty, proceed with accessing the first element
    hole_points = adjusted_hole_array[0].tolist()

    hole_origin = hole_points[0]

    if len(hole_points) == 2:
        midpoint = getMidpoint(hole_origin, hole_points[-1])
    else:
        midpoint = hole_points[1]

    green_center = hole_points[-1]
    
    print("done with getting 3 way points")

    return hole_origin, midpoint, green_center


# calculate the distance from a point to a line defined by two other points (line1 and line2)

def distToLine(point,line1,line2,ypp):

    try:
        slope = (line1[1]-line2[1])/(line1[0]-line2[0])
        vertical = False
    except:
        vertical = True


    # handle exception if line1 and line2 form a vertical line
    # the distance of our point to this line would just be the x distance

    if vertical:

        distance = abs(line1[0] - point[0])

    else:
        # otherwise, treat it like a normal line
        # y = mx + b --> solving for intercept

        intercept = line1[1] - (slope * line1[0])

        # converting to -mx + y + -b = 0

        a = -slope
        b = 1
        c = -intercept

        distance = (abs(a*point[0] + b*point[1] + c) / math.sqrt(a**2 + b**2))

    return distance * ypp


def getLine(point1,point2):

    slope = ((point1[1] - point2[1]) / (point1[0] - point2[0]))

    intercept = point1[1] - (slope * point1[0])

    return slope, intercept


# given a list of features and a list of tee boxes, draw carry distances to all of the
# features from each of the tee boxes
#using pixel points not Lat/Long

def drawCarryDistances(dwg, adjusted_hole_array, tee_box_list, carry_feature_list, ypp, text_size, text_color, filter_dist=40):

    hole_origin, midpoint, green_center = getThreeWaypoints(adjusted_hole_array)
    

    carry_points = getMaxPoints(carry_feature_list)

    tee_box_points = getMinPoints(tee_box_list)

    right_carries_drawn = left_carries_drawn = 0

    drawn_carries = []

    for carry in carry_points:

        close = False

        if len(drawn_carries) > 0:
            for pastcarry in drawn_carries:
                carry_dist = getDistance(carry, pastcarry, ypp)
                if carry_dist < 20:
                    close = True
                    break

        if close:
            continue

        right = True

        if carry[1] < midpoint[1]:
            dist_to_way = distToLine(carry,midpoint,green_center,ypp)

            slope, intercept = getLine(midpoint,green_center)


        else:
            dist_to_way = distToLine(carry,midpoint,hole_origin,ypp)

            slope, intercept = getLine(midpoint,hole_origin)

        if dist_to_way > filter_dist:
            continue


        # y = mx + b    y = carry[1]   x = (carry[1] - b) / slope

        comp_value = (carry[1] - intercept) / slope


        if carry[0] < comp_value:
            right = False

        if right:
            right_carries_drawn += drawCarry(dwg, green_center, carry, tee_box_points, ypp, text_size, text_color, right)
            drawn_carries.append(carry)
        else:
            left_carries_drawn += drawCarry(dwg, green_center, carry, tee_box_points, ypp, text_size, text_color, right)
            drawn_carries.append(carry)


    return right_carries_drawn, left_carries_drawn


# we want to draw at least one carry distance on each hole, even if there are
# no bunkers or other features of note
# this way, players have a sense of how long the hole is, etc.

def drawExtraCarries(dwg, adjusted_hole_array, tee_boxes, right_carries, left_carries, ypp, text_size, text_color):

    # if we already have enough carries, let's move on

    if (int(right_carries) + int(left_carries)) > 0:

        return None

    # otherwise, let's proceed to draw a carry

    hole_origin, midpoint, green_center = getThreeWaypoints(adjusted_hole_array)

    tee_box_points = getMinPoints(tee_boxes)

    # how long our carry should be depends on how long the hole is

    measure = getDistance(hole_origin,green_center,ypp)

    if measure < 380:
        y = green_center[1] + (95/ypp)
    elif measure < 430:
        y = green_center[1] + (145/ypp)
    elif measure < 480:
        y = green_center[1] + (195/ypp)
    else:
        y = hole_origin[1] - (230/ypp)


    if midpoint[1] > y:
        slope, intercept = getLine(midpoint,green_center)
    else:
        slope, intercept = getLine(midpoint,hole_origin)

    base_x = (y - intercept) / slope

    if midpoint[0] < green_center[0]:
        # draw on left

        x = base_x - (20/ypp)

        carry = (x,y)

        right = False

    else:
        # draw on right

        x = base_x + (20/ypp)

        carry = (x,y)

        right = True

    num = drawCarry(dwg, green_center, carry, tee_box_points, ypp, text_size, text_color, right)



# given a point and a distance, draw the distance next to the point

def drawDistanceText(dwg, distance, point, text_size, text_color):
    text_weight = "bold" if text_size >= 10 else "normal"  # You can adjust this logic

    # Estimate label position similar to cv2.putText adjustment
    x = int(point[0] + (0.8 * text_size))
    y = int(point[1]+(0.4 *text_size))  # You can fine-tune the vertical offset

    # Add text to the SVG drawing
    dwg.add(dwg.text(
        str(distance),
        insert=(x, y),
        font_size=f"{text_size}px",
        fill=text_color,
        font_weight=text_weight,
        font_family="Arial"
    ))


# complicated - we are drawing arcs at 50, 100, 150, 200 yards, etc.
# if the hole is a dogleg, we want to draw these arcs in the fairway, so we have
# to measure the longer distances to a different line

def getPointOnOtherLine(origin_point, midpoint, green_center, distance, ypp):

    distance = distance / ypp

    x0 = green_center[0]
    y0 = green_center[1]

    x1 = midpoint[0]
    y1 = midpoint[1]

    x2 = origin_point[0]
    y2 = origin_point[1]


    A = y2 - y1
    B = x1 - x2
    C = (x2 * y1) - (x1 * y2)

    a = A**2 + B**2
    b = 2*A*C + 2*A*B*y0 - 2*(B**2)*x0
    c = C**2 + 2*B*C*y0 - (B**2 * (distance**2 - x0**2 - y0 **2))

    if B < 3 and b > -3:

        return None


    x_int = (b*-1 + math.sqrt(b**2 - 4*a*c)) / (2*a)
    y_int = -1 * ((A*x_int + C) / B)

    min_x = min(x1,x2)
    max_x = max(x1,x2)
    min_y = min(y1,y2)
    max_y = max(y1,y2)

    if x_int > min_x and x_int < max_x and y_int > min_y and y_int < max_y:
        return (int(x_int), int(y_int))

    else:
        x_int = (b*-1 - math.sqrt(b**2 - 4*a*c)) / (2*a)
        y_int = -1 * ((A*x_int + C) / B)

        return (int(x_int), int(y_int))


def draw_ellipse_arc(dwg, center, radius, start_angle, end_angle, angle, color, stroke_width):
    import math

    def rotate_point(px, py, cx, cy, angle_deg):
        angle_rad = math.radians(angle_deg)
        dx, dy = px - cx, py - cy
        qx = cx + dx * math.cos(angle_rad) - dy * math.sin(angle_rad)
        qy = cy + dx * math.sin(angle_rad) + dy * math.cos(angle_rad)
        return qx, qy

    x, y = center
    rx, ry = radius, radius

    # Convert degrees to radians
    start_rad = math.radians(start_angle)
    end_rad = math.radians(end_angle)

    # Start and end points before rotation
    x_start = x + rx * math.cos(start_rad)
    y_start = y - ry * math.sin(start_rad)
    x_end = x + rx * math.cos(end_rad)
    y_end = y - ry * math.sin(end_rad)

    # Rotate points 90 degrees
    x_start, y_start = rotate_point(x_start, y_start, x, y, angle+90)
    x_end, y_end = rotate_point(x_end, y_end, x, y, angle+90)

    # Flip direction: swap angles and adjust flags
    large_arc = int(abs(end_angle - start_angle) > 180)
    sweep_flag = 0 if end_angle > start_angle else 1  # flipped sweep

    # Path data
    path_data = f"M {x_start},{y_start} A {rx},{ry} 0 {large_arc},{sweep_flag} {x_end},{y_end}"
    dwg.add(dwg.path(
        d=path_data,
        fill="none",
        stroke=color,
        stroke_width=stroke_width
    ))



# draw arcs down the fairway at 50-yard intervals from the center of the green

def drawFarGreenDistances(dwg, adjusted_hole_array, ypp, draw_dist, text_size, text_color):
    import math
    from scipy.spatial import distance as dist

    angle_dict = {50: 30, 100: 15.2, 150: 9.8, 200: 7.5, 250: 6, 300: 5, 350: 4.6}

    hole_origin, midpoint, green_center = getThreeWaypoints(adjusted_hole_array)
    integer_green_center = (int(green_center[0]), int(green_center[1]))

    # Calculate distances
    d1 = dist.euclidean(hole_origin, midpoint)
    d2 = dist.euclidean(midpoint, green_center)
    midpoint_dist = d2 * ypp
    total_dist = (d1 + d2) * ypp

    # Set hole length limits
    hole_length_limit = max(midpoint_dist, min(350, total_dist - 80, total_dist))

    print(f"[DEBUG] midpoint_dist: {midpoint_dist:.2f}, hole_length_limit: {hole_length_limit:.2f}, starting draw_dist: {draw_dist}")

    while draw_dist < hole_length_limit:
        if draw_dist < midpoint_dist:
            drawpoint = getPointOnOtherLine(midpoint, green_center, green_center, draw_dist, ypp)
        else:
            drawpoint = getPointOnOtherLine(hole_origin, midpoint, green_center, draw_dist, ypp)

        #print(f"[DEBUG] Drawing distance {draw_dist} yards at point {drawpoint}")

        drawDistanceText(dwg, draw_dist, drawpoint, text_size, text_color)

        pixel_dist = int(draw_dist / ypp)
        angle = getAngle(green_center, drawpoint)
        offset = angle_dict.get(draw_dist, 10)  # Fallback angle

        #print(f"[DEBUG] Pixel radius: {pixel_dist}, angle: {angle:.2f}, drawn_angle: {drawn_angle:.2f}, offset: {offset}")

        # SVG rotation via transform (if needed)
        stroke_width=2
        draw_ellipse_arc(dwg, integer_green_center, pixel_dist, -offset, offset, angle, text_color, stroke_width)
        """ dwg.add(dwg.ellipse(
            center=integer_green_center,
            r=(pixel_dist, pixel_dist),
            fill='none',
            stroke=text_color,
            stroke_width=2,
            transform=f"rotate({drawn_angle} {integer_green_center[0]} {integer_green_center[1]})"
        )) """

        draw_dist += 50




# special case to handle holes with four waypoints (double doglegs)
def drawGreenDistancesAnyWaypoint(dwg, adjusted_hole_array, ypp, draw_dist, text_size, text_color):
    hole_points = adjusted_hole_array[0].tolist()

    if len(hole_points) < 4:
        print("Using fallback method: fewer than 4 waypoints")
        drawFarGreenDistances(dwg, adjusted_hole_array, ypp, draw_dist, text_size, text_color)
        return True

    if len(hole_points) != 4:
        print(f"Error: Unexpected number of hole waypoints: {len(hole_points)}")
        return False

    # Define angle dictionary and fallback function
    angle_dict = {50: 30, 100: 15.2, 150: 9.8, 200: 7.5, 250: 6, 300: 5, 350: 4.6}
    def get_closest_angle(dist_value):
        keys = sorted(angle_dict.keys())
        return angle_dict[min(keys, key=lambda k: abs(k - dist_value))]

    hole_origin = hole_points[0]
    first_midpoint = hole_points[1]
    second_midpoint = hole_points[2]
    green_center = hole_points[3]
    integer_green_center = (int(green_center[0]), int(green_center[1]))

    # Calculate distances in yards
    seg_lengths = [
        dist.euclidean(hole_origin, first_midpoint),
        dist.euclidean(first_midpoint, second_midpoint),
        dist.euclidean(second_midpoint, green_center)
    ]
    total_pixel_length = sum(seg_lengths)
    total_yard_length = total_pixel_length * ypp

    # Compute hole length limit
    hole_length_limit = max(total_yard_length - 200, total_yard_length * 0.6)
    hole_length_limit = min(hole_length_limit, 350)

    second_mp_dist = dist.euclidean(green_center, second_midpoint) * ypp
    first_mp_dist = dist.euclidean(green_center, first_midpoint) * ypp
    hole_length_limit = max(first_mp_dist, hole_length_limit)

    
    print(f"Starting draw_dist: {draw_dist}, going up to {hole_length_limit:.2f} yards")

    # Draw from green to second midpoint
    while draw_dist < second_mp_dist:
        drawpoint = getPointOnOtherLine(second_midpoint, green_center, green_center, draw_dist, ypp)
        if drawpoint is None:
            print(f"Warning: drawpoint is None at {draw_dist} yards (segment: GC–2MP)")
            draw_dist += 50
            continue

        drawDistanceText(dwg, draw_dist, drawpoint, text_size, text_color)
        pixel_dist = int(draw_dist / ypp)
        angle = getAngle(green_center, drawpoint)
        offset = get_closest_angle(draw_dist)
        stroke_width=2
        draw_ellipse_arc(dwg, integer_green_center, pixel_dist, -offset, offset, angle, text_color, stroke_width)
        draw_dist += 50

    # Draw from second midpoint to first midpoint
    while draw_dist < first_mp_dist:
        drawpoint = getPointOnOtherLine(first_midpoint, second_midpoint, green_center, draw_dist, ypp)
        if drawpoint is None:
            print(f"Warning: drawpoint is None at {draw_dist} yards (segment: 2MP–1MP)")
            draw_dist += 50
            continue

        drawDistanceText(dwg, draw_dist, drawpoint, text_size, text_color)
        pixel_dist = int(draw_dist / ypp)
        angle = getAngle(green_center, drawpoint)
        offset = get_closest_angle(draw_dist)
        draw_ellipse_arc(dwg, integer_green_center, pixel_dist, -offset, offset, angle, text_color, stroke_width)
        draw_dist += 50

    # Draw from first midpoint to tee
    while draw_dist < hole_length_limit:
        drawpoint = getPointOnOtherLine(hole_origin, first_midpoint, green_center, draw_dist, ypp)
        if drawpoint is None:
            print(f"Warning: drawpoint is None at {draw_dist} yards (segment: 1MP–Tee)")
            draw_dist += 50
            continue

        drawDistanceText(dwg, draw_dist, drawpoint, text_size, text_color)
        pixel_dist = int(draw_dist / ypp)
        angle = getAngle(green_center, drawpoint)
        offset = get_closest_angle(draw_dist)
        stroke_width=2
        draw_ellipse_arc(dwg, integer_green_center, pixel_dist, -offset, offset, angle,text_color, stroke_width)
        draw_dist += 50

    return True



def draw_polygon(dwg, points, stroke_color="#000000", stroke_width=2, fill="none"):
    dwg.add(dwg.polygon(
        points=points,
        stroke=stroke_color,
        stroke_width=stroke_width,
        fill=fill
    ))
    
def fill_polygon(dwg, points, fill_color="#000000"):
    dwg.add(dwg.polygon(
        points=points,
        fill=fill_color,
        stroke="none"
    ))

# given a point, draw a triangle on it

def drawTriangle(dwg, point, base, height, text_color):
    apex = (int(point[0]), int(point[1] - (height / 2)))
    base1 = (int(point[0] - (base / 2)), int(point[1] + (height / 2)))
    base2 = (int(point[0] + (base / 2)), int(point[1] + (height / 2)))

    # Triangle vertices in (x, y) tuple format
    vertices = [apex, base1, base2]

    # Draw stroke
    draw_polygon(dwg, vertices, stroke_color="#000000", stroke_width=2)

    # Fill
    fill_polygon(dwg, vertices, fill_color=text_color)




def drawTriangleMarkers(dwg, points, base, height, text_color):

    for point in points:
        drawTriangle(dwg, point, base, height, text_color)


# given a list of features, draw the distance to the center of the green from each
# (from the farthest back point)

def drawGreenDistancesMin(dwg, adjusted_hole_array, feature_list, ypp, text_size, text_color, filter_dist=40, par_3_tees=0):

    hole_origin, midpoint, green_center = getThreeWaypoints(adjusted_hole_array)

    hole_distance = getDistance(hole_origin,green_center,ypp)

    distance_points = getMinPoints(feature_list)

    drawn_distances = []

    for point in distance_points:

        distance = int(getDistance(point,green_center,ypp))

        if distance < 40 or distance > 305:
            continue

        if par_3_tees == 0:
            if distance > (0.75*hole_distance):
                continue

        close = False

        if len(drawn_distances) > 0:
            for pastdist in drawn_distances:
                rel_dist = getDistance(point, pastdist, ypp)
                if rel_dist < 15:
                    close = True
                    break

        if close:
            continue

        if point[1] < midpoint[1]:
            dist_to_way = distToLine(point,midpoint,green_center,ypp)
        else:
            dist_to_way = distToLine(point,midpoint,hole_origin,ypp)

        if dist_to_way > filter_dist:
            continue

        # Draw marker and label
        base = 0.5 * text_size# base length of the triangle in relation to text hight
        height = base #for an iscoloces triangle 

        drawTriangleMarkers(dwg, [point], base, height, text_color)

        drawDistanceText(dwg, distance, point, text_size, text_color)

        drawn_distances.append(point)

#estimate the correct text size
def estimate_text_size(text, font_size, char_width_factor=0.6):
    width = int(len(text) * font_size * char_width_factor)
    height = int(font_size)
    return width, height

# given a list of trees, draw the distance to the center of the green form each

def drawGreenDistancesTree(dwg, adjusted_hole_array, tree_list, ypp, text_size, text_color, filter_dist=25, par_3_tees=0):
    """
    Draws the distances from trees to the green, with appropriate filtering.
    The function uses SVG for drawing instead of OpenCV.
    
    :param dwg: SVG drawing object
    :param adjusted_hole_array: List of hole waypoints
    :param tree_list: List of trees (as points)
    :param ypp: Yards per pixel scaling factor
    :param text_size: Text size for labels
    :param text_color: Color for the text and lines
    :param filter_dist: Minimum distance from line to consider for drawing
    :param par_3_tees: Tee position modifier for par 3 holes
    """
    # Calculate text weight based on text size
    text_weight = round(text_size * 2)

    # Extract hole origin, midpoint, and green center coordinates
    hole_origin, midpoint, green_center = getThreeWaypoints(adjusted_hole_array)

    # Calculate the total hole distance
    hole_distance = getDistance(hole_origin, green_center, ypp)

    # Prepare list for distance points
    distance_points = []
    for i, tree in enumerate(tree_list):
        #print(f"\n[DEBUG] Tree #{i}: type = {type(tree)}")
        #print(f"[DEBUG] Raw tree data: {tree}")
        
        if isinstance(tree, np.ndarray):
            tree_point = tree.tolist()
            #print(f"[DEBUG] Converted to list: {tree_point}")
        else:
            tree_point = tree

        # Make sure we always get a flat [x, y]#
        if isinstance(tree_point[0], (list, np.ndarray)):
            point = tree_point[0]
        else:
            point = tree_point
            
        #Dubbing
        #print(f"[DEBUG] Final point used: {point} (type: {type(point)}, length: {len(point) if hasattr(point, '__len__') else 'n/a'})")

        # Sanity check
        if not (isinstance(point, list) or isinstance(point, tuple)) or len(point) != 2:
            raise ValueError(f"Tree #{i} does not have a valid [x, y] structure: {point}")
        distance_points.append(point)

            
    
    drawn_distances = []  # To store points that have already been drawn

    for point in distance_points:
        distance = int(getDistance(point, green_center, ypp))

        # Skip if distance is too small or too large
        if distance < 40 or (par_3_tees == 0 and distance > (0.75 * hole_distance)):
            continue

        # Check if this point is close to previously drawn points
        if any(getDistance(point, past_dist, ypp) < 15 for past_dist in drawn_distances):
            continue

        # Skip distances that are too close to multiples of 50
        if distance % 50 < 5 or distance % 50 > 45:
            continue

        # Calculate the distance to the line based on position (above or below midpoint)
        if point[1] < midpoint[1]:
            dist_to_way = distToLine(point, midpoint, green_center, ypp)
            slope, intercept = getLine(midpoint, green_center)
        else:
            dist_to_way = distToLine(point, midpoint, hole_origin, ypp)
            slope, intercept = getLine(midpoint, hole_origin)

        # Filter out points that are too far from the line
        if dist_to_way > filter_dist:
            continue

        # Determine if the point is to the right or left of the line
        comp_value = (point[1] - intercept) / slope
        right = point[0] < comp_value

        # Calculate text size and position based on the side of the line
        label_width, label_height = estimate_text_size(str(distance), text_size)
        label_position = (point[0] - 100 - label_width, point[1]) if right else (point[0] + 100, point[1]) #the labels position if left or right

        # Draw the line from the tree to the label position
        dwg.add(dwg.line(start=(point[0], point[1]), end=(label_position[0], label_position[1]), stroke=text_color, stroke_width=3))

        # Draw the distance text near the label at about 1/3 of the text size from the end of the line
        dwg.add(dwg.text(
            str(distance),
            insert=(label_position[0], label_position[1]),#at the end of the line
            font_size=f"{text_size}px",
            fill=text_color,
            font_weight="normal" if text_weight < 2 else "bold",
            font_family="Arial"
        ))

        # Add this point to the list of drawn distances to avoid duplication
        drawn_distances.append(point)



# given a list of features, draw the distance to the center of the green from each
# (from the closest point)

def drawGreenDistancesMax(dwg, adjusted_hole_array, feature_list, ypp, text_size, text_color, filter_dist=40):
    """
    Draws distance markers for the farthest points (e.g., trees, hazards) near the green.
    
    :param dwg: SVG drawing object
    :param adjusted_hole_array: Waypoints for the hole
    :param feature_list: List of feature points (e.g., trees, bunkers)
    :param ypp: Yards per pixel
    :param text_size: Font size for distance text
    :param text_color: Color of the triangle and text
    :param filter_dist: Max perpendicular distance from the fairway line to consider
    """
    
    hole_origin, midpoint, green_center = getThreeWaypoints(adjusted_hole_array)
    #print("get dinstancde")
    hole_distance = getDistance(hole_origin, green_center, ypp)

    # Retrieve and sanitize max distance points
    #print("# Retrieve and sanitize max distance points")
    raw_points = getMaxPoints(feature_list)
    distance_points = []

    for i, point in enumerate(raw_points):
        # Handle nested or incorrect structures
        if isinstance(point, (list, tuple, np.ndarray)):
            if isinstance(point[0], (list, tuple, np.ndarray)):
                point = point[0]  # Unpack one level
            if len(point) == 2 and all(isinstance(coord, (int, float)) for coord in point):
                distance_points.append(point)
            else:
                print(f"[WARN] Invalid point structure at index {i}: {point}")
        else:
            print(f"[WARN] Non-iterable point at index {i}: {point}")

    for point in distance_points:
        distance = int(getDistance(point, green_center, ypp))

        # Skip too-close or too-far distances
        if distance < 40 or distance > (0.75 * hole_distance):
            continue

        # Distance from fairway line
        #print("# Distance from fairway line")
        if point[1] < midpoint[1]:
            dist_to_way = distToLine(point, midpoint, green_center, ypp)
        else:
            dist_to_way = distToLine(point, midpoint, hole_origin, ypp)

        if dist_to_way > filter_dist:
            continue

        # Draw marker and label
        base = text_size #base length of the triangle in relation to text hight
        height = base #for an iscoloces triangle 
        
        print("draw triangle markers")
        drawTriangleMarkers(dwg, [point], base, height, text_color)
        drawDistanceText(dwg, distance, point, text_size, text_color)


def generate_contours_and_arrows(elevation_map, dwg, x_center_px, y_center_px,
                                 green_center_lat, green_center_lon, ypp, angle,
                                 contour_interval=20):
    """
    Draws smoothed contour lines and slope arrows on the SVG.
    - Uses cs.allsegs instead of cs.collections for compatibility.
    - Sanitizes arrow marker IDs (no '#' in ids).
    """
    from scipy.interpolate import griddata
    import numpy as np
    import math
    import matplotlib.pyplot as plt

    try:
        # --- Helpers ---
        def latlon_to_svg(lat, lon, rotate=False):
            lat = float(lat); lon = float(lon)
            dlat = lat - float(green_center_lat)
            dlon = lon - float(green_center_lon)

            dlat_m = dlat * 111_000.0
            dlon_m = dlon * 111_000.0 * math.cos(math.radians(float(green_center_lat)))

            dlat_yd = dlat_m * 1.09361
            dlon_yd = dlon_m * 1.09361

            # yards-per-pixel scaling (your ypp = yards-per-pixel)
            dx_px = dlon_yd / ypp
            dy_px = dlat_yd / ypp

            ux = x_center_px + dx_px
            uy = y_center_px - dy_px  # SVG y grows downward

            if rotate:
                ang = np.radians(-(angle - 90))
                # Rotate2D: expects Nx2 array and a pivot; assumed available in your codebase
                rx, ry = Rotate2D(np.array([[ux, uy]]),
                                  np.array([x_center_px, y_center_px]),
                                  ang)[0]
                return rx, ry
            return ux, uy

        def get_arrow_color(slope_percent):
            # slope_percent ~ gradient * 100
            if slope_percent <= 0.5:  return '#a1a1a1'
            if slope_percent <= 1.0:  return '#5ac5fa'
            if slope_percent <= 2.0:  return '#3375f6'
            if slope_percent <= 3.0:  return '#5fcb3f'
            if slope_percent <= 4.0:  return '#3d8025'
            if slope_percent <= 5.0:  return '#dc3b2f'
            if slope_percent <= 6.0:  return '#ee7a30'
            if slope_percent <= 7.0:  return '#d8337e'
            return 'magenta'

        def chaikin_smooth(vertices, iterations=2):
            v = np.asarray(vertices)
            for _ in range(iterations):
                if len(v) < 3:
                    break
                nv = []
                for i in range(len(v)-1):
                    p0 = v[i]; p1 = v[i+1]
                    Q = 0.75*p0 + 0.25*p1
                    R = 0.25*p0 + 0.75*p1
                    nv.extend([Q, R])
                v = np.array(nv)
            return v

        # --- 1) Prepare points ---
        lats, lons = zip(*elevation_map.keys())
        elevations = np.array(list(elevation_map.values()), dtype=float)

        svg_coords = [latlon_to_svg(lat, lon, rotate=True) for lat, lon in zip(lats, lons)]
        points = np.array(svg_coords, dtype=float)

        # Optional: label elevations at sample points
        for (x, y), elev in zip(points, elevations):
            dwg.add(dwg.text(f"{round(float(elev), 1)}",
                             insert=(x, y),
                             fill='black', font_size="1.5px"))

        # --- 2) Interpolation grid ---
        x_min, y_min = points.min(axis=0)
        x_max, y_max = points.max(axis=0)

        # 500x500 is heavy; adjust if needed
        xx, yy = np.meshgrid(
            np.linspace(x_min, x_max, 500),
            np.linspace(y_min, y_max, 500)
        )
        grid_z = griddata(points, elevations, (xx, yy), method='cubic')

        # Handle NaNs from cubic interpolation by infilling with nearest as a fallback
        if np.isnan(grid_z).any():
            grid_z_near = griddata(points, elevations, (xx, yy), method='nearest')
            grid_z = np.where(np.isnan(grid_z), grid_z_near, grid_z)

        # Guard: if still all-NaN or flat, bail gracefully
        if not np.isfinite(grid_z).any() or np.nanmin(grid_z) == np.nanmax(grid_z):
            print("[WARN] Contours skipped: insufficient elevation variance or interpolation failed.")
            return

        # --- 3) Contours (iterate via allsegs, not collections) ---
        fig, ax = plt.subplots()
        ax.set_axis_off()

        # Build an appropriate set of levels
        vmin = float(np.nanmin(grid_z))
        vmax = float(np.nanmax(grid_z))
        # contour_interval here means "number of levels"
        levels = np.linspace(vmin, vmax, int(contour_interval))

        cs = ax.contour(xx, yy, grid_z, levels=levels, colors='grey', linewidths=0.8)

        # cs.allsegs is a list of lists of (N_i x 2) arrays per level
        for level_segs in cs.allsegs:
            for seg in level_segs:
                # seg is an Nx2 array of vertices
                if seg is None or len(seg) < 4:
                    continue
                smooth_vertices = chaikin_smooth(seg)
                if len(smooth_vertices) < 2:
                    continue

                # Build cubic-bezier-ish SVG path: start M, then C in groups of 3 points
                path_cmds = [f"M {smooth_vertices[0][0]},{smooth_vertices[0][1]}"]
                i = 1
                while i + 2 < len(smooth_vertices):
                    x1, y1 = smooth_vertices[i]
                    x2, y2 = smooth_vertices[i+1]
                    x3, y3 = smooth_vertices[i+2]
                    path_cmds.append(f"C {x1},{y1} {x2},{y2} {x3},{y3}")
                    i += 3
                # leftover vertices as straight segments
                for j in range(i, len(smooth_vertices)):
                    xj, yj = smooth_vertices[j]
                    path_cmds.append(f"L {xj},{yj}")

                dwg.add(dwg.path(d=" ".join(path_cmds),
                                 stroke="#e6e6e6", fill="none", stroke_width=0.3))
        plt.close(fig)

        # --- 4) Arrowhead marker defs (sanitize IDs) ---
        arrow_colors = ['#a1a1a1', '#5ac5fa', '#3375f6', '#5fcb3f', '#3d8025',
                        '#dc3b2f', '#ee7a30', '#d8337e', 'magenta']
        arrow_markers = {}
        for color in arrow_colors:
            safe_id = f"arrow-{color.replace('#','hex-')}"
            marker = dwg.marker(
                id=safe_id, insert=(0, 3), size=(1.5, 1.5),
                orient='auto', markerUnits='userSpaceOnUse'
            )
            marker.add(dwg.path(d="M0,2 L0,4 L3,3 z", fill=color))
            dwg.defs.add(marker)
            arrow_markers[color] = marker

        # --- 5) Coarse grid for slope arrows ---
        num_cells = 18
        x_grid = np.linspace(x_min, x_max, num_cells)
        y_grid = np.linspace(y_min, y_max, num_cells)
        xx_c, yy_c = np.meshgrid(x_grid, y_grid)

        grid_z_c = griddata(points, elevations, (xx_c, yy_c), method='nearest')

        # If any NaNs persist, skip arrows there
        # Gradient: note spacing is in SVG px
        dy, dx = np.gradient(grid_z_c, y_grid[1]-y_grid[0], x_grid[1]-x_grid[0])

        # --- 6) Draw slope arrows (pointing downhill) ---
        arrow_length = 5.0  # px length
        for j in range(num_cells):
            for i in range(num_cells):
                if not np.isfinite(dx[j, i]) or not np.isfinite(dy[j, i]):
                    continue
                gx, gy = dx[j, i], dy[j, i]
                mag = float(np.hypot(gx, gy))
                if mag < 1e-6:
                    continue

                # Normalize gradient; slope arrows point downhill => subtract gradient
                gx /= mag; gy /= mag
                start_x = xx_c[j, i]; start_y = yy_c[j, i]
                end_x   = start_x - arrow_length * gx
                end_y   = start_y - arrow_length * gy

                slope_percent = mag * 100.0
                color = get_arrow_color(slope_percent)

                dwg.add(dwg.line(
                    start=(start_x, start_y), end=(end_x, end_y),
                    stroke=color, stroke_width=0.4,
                    marker_end=arrow_markers[color].get_funciri()
                ))

    except Exception as e:
        print("ERROR in generate_contours_and_arrows:", str(e))



# draw a three-yard grid over the green dwg that is aligned with the center of the green

def getGreenGrid(adjusted_hole_array, ypp, dwg, features_group, green_group, holeway_nodes, angle, elevation_map=None):
    """
    Draws a green grid in SVG format with central marker and grid lines based on the hole coordinates.

    :param adjusted_hole_array: List of hole waypoints
    :param ypp: Yards per pixel scaling factor
    :param dwg: SVG drawing object (svgwrite.Drawing)
    :return: SVG drawing object with grid
    """
    green_center = holeway_nodes[-1]
    green_center_lat = green_center.lat
    green_center_lon = green_center.lon
    
    hole_origin, midpoint, green_center = getThreeWaypoints(adjusted_hole_array)
    x, y = map(int, green_center)
    #grid spacing 
    spacing = 3 / ypp # # pixel size of 3 yards
    print("[DEBUG]spacing value:", spacing)

    # Define cropping box (in pixel coordinates)
    xmin = int(x - (30 / ypp)) # 30 yards from center to
    xmax = int(x + (30 / ypp))
    ymin = int(y - (30 / ypp))
    ymax = int(y + (30 / ypp))
    
    x_lines_min = [x-k * spacing for k in range(11)]  # 0..30 yards
    y_lines_min = [y-k * spacing for k in range(11)]  # 0..30 yards
    x_lines_max = [x+k * spacing for k in range(11)]  # 0..30 yards
    y_lines_max = [y+k * spacing for k in range(11)]  # 0..30 yards
    

    # Set up grid spacing
    grid_color = "#d1d1d1"  # Grid color as a hex code, light gray
    line_thickness = 2 if (xmax - xmin) > 850 else 1  # Set line thickness based on width

    # Draw vertical grid lines from green center to the left and up, increasing by 3 yards to the left with every iteration
    for gx_lu in x_lines_min:
        gx_lu_line = svgwrite.shapes.Line(start=(gx_lu, y), end=(gx_lu, y_lines_min[-1]), stroke=grid_color, stroke_width=line_thickness)
        green_group.add(gx_lu_line)

    # Draw vertical grid lines from green center to the right and up, increasing by 3 yards to the left with every iteration
    for gx_ru in x_lines_max:
        gx_ru_line = svgwrite.shapes.Line(start=(gx_ru, y), end=(gx_ru, y_lines_min[-1]), stroke=grid_color, stroke_width=line_thickness)
        green_group.add(gx_ru_line)

    # Draw vertical grid lines from green center to the left and down, increasing by 3 yards to the left with every iteration
    for gx_ld in x_lines_min:
        gx_ld_line = svgwrite.shapes.Line(start=(gx_ld, y), end=(gx_ld, y_lines_max[-1]), stroke=grid_color, stroke_width=line_thickness)
        green_group.add(gx_ld_line)

    # Draw vertical grid lines from green center to the right and down, increasing by 3 yards to the left with every iteration
    for gx_rd in x_lines_max:
        gx_rd_line = svgwrite.shapes.Line(start=(gx_rd, y), end=(gx_rd, y_lines_max[-1]), stroke=grid_color, stroke_width=line_thickness)
        green_group.add(gx_rd_line)

    # Draw horizontal grid lines from center to left and up, increasing by 3 yards to the top with every iteration
    for gy_lu in y_lines_min:
        gy_lu_line = svgwrite.shapes.Line(start=(x, gy_lu), end=(x_lines_min[-1], gy_lu), stroke=grid_color, stroke_width=line_thickness)
        green_group.add(gy_lu_line)

    # Draw horizontal grid lines from center to right and up, increasing by 3 yards to the top with every iteration
    for gy_ru in y_lines_min:
        gy_ru_line = svgwrite.shapes.Line(start=(x, gy_ru), end=(x_lines_max[-1], gy_ru), stroke=grid_color, stroke_width=line_thickness)
        green_group.add(gy_ru_line)

    # Draw horizontal grid lines from center to left and down, increasing by 3 yards to the top with every iteration
    for gy_ld in y_lines_max:
        gy_ld_line = svgwrite.shapes.Line(start=(x, gy_ld), end=(x_lines_max[-1], gy_ld), stroke=grid_color, stroke_width=line_thickness)
        green_group.add(gy_ld_line)

    # Draw horizontal grid lines from center to right and down, increasing by 3 yards to the top with every iteration
    for gy_rd in y_lines_max:
        gy_rd_line = svgwrite.shapes.Line(start=(x, gy_rd), end=(x_lines_min[-1], gy_rd), stroke=grid_color, stroke_width=line_thickness)
        green_group.add(gy_rd_line)

    
    # Draw central grid marker in SVG (center marker)
    circle_radius = int(0.5/ ypp)
    circle = svgwrite.shapes.Circle(center=(x, y), r=circle_radius, fill="#0ccb1f")
    green_group.add(circle)
    
    # Draw the border around the cropped grid area (using a rectangle)
    box = svgwrite.shapes.Rect(insert=(x_lines_min[-1], y_lines_min[-1]), size=(x_lines_max[-1] - x_lines_min[-1], y_lines_max[-1] - y_lines_min[-1]), stroke=grid_color, stroke_width=line_thickness, fill="none")
    green_group.add(box)
    
    
    # Define clipping path ID
    clip_id = "grid-clip"

    # Define the clipping rectangle
    padd = line_thickness / 2  # Optional padding to ensure full visibility of border
    clip_path = dwg.defs.add(dwg.clipPath(id=clip_id))
    clip_path.add(dwg.rect(insert=(x_lines_min[-1]-padd, y_lines_min[-1]-padd), size=(x_lines_max[-1]+padd - x_lines_min[-1]+padd, y_lines_max[-1]+padd - y_lines_min[-1]+padd)))

    # Create a group to hold everything you want to clip
    clipped_group = dwg.g(clip_path=f"url(#{clip_id})")

    # Add the green group to the clipped group
    clipped_group.add(green_group)

    # Finally, add the clipped group to the main drawing
    dwg.add(clipped_group)

    # Move features_group under new clipped group
    dwg.elements.remove(features_group)

    # Add features_group to clipped_group
    clipped_group.add(features_group)

    # Define Contours and arrows group
    #contours_group = dwg.g(id="contours-and-arrows")
    
     # If elevation data is available, add contour lines and arrow
    if elevation_map:
        print("elevation data is found!")
    try:
        generate_contours_and_arrows(elevation_map, dwg, x, y,  green_center_lat, green_center_lon, ypp, angle)
        #dwg.saveas("green_with_contours.svg")
    except Exception as e:
        print(f"Error while generating contours and arrows: {e}")

    # Set the viewBox so (x_object, y_object) becomes the top-left of the viewport. The size is as big as the green bounding box
    dwg.viewbox(minx=float(x_lines_min[-1]), miny=float(y_lines_min[-1]), width=(x_lines_max[-1]+padd - x_lines_min[-1]-padd), height=(y_lines_max[-1]+padd - y_lines_min[-1]-padd))
    dwg['width'], dwg['height'] = (x_lines_max[-1]+padd - x_lines_min[-1]+padd), (y_lines_max[-1]+padd - y_lines_min[-1]+padd)
   

    return dwg


""" 
def getFixedSizedwg(rotated_dwg, final_green_array, adjusted_hole_array, ypp, target_width=1275, target_height=2100):
    # Create a blank white canvas with fixed dimensions
    fixed_dwg = np.ones((target_height, target_width, 3), dtype=np.uint8) * 255
    
    # Get the bounding box of the green (coordinates of the green)
    g_minx = min(point[0] for array in final_green_array for point in array)
    g_miny = min(point[1] for array in final_green_array for point in array)
    g_maxx = max(point[0] for array in final_green_array for point in array)
    g_maxy = max(point[1] for array in final_green_array for point in array)
    
    # Calculate green dimensions (width and height)
    green_width = g_maxx - g_minx
    green_height = g_maxy - g_miny
    
    # Determine scale factor to fit the green to about 60% of the target width
    target_green_width = target_width * 0.6
    scale = target_green_width / max(green_width, 1)  # Avoid division by zero
    
    # Calculate the offset to center the green on the canvas
    offset_x = int((target_width - green_width * scale) / 2 - g_minx * scale)
    offset_y = int((target_height - green_height * scale) / 2 - g_miny * scale)
    
    # Transform all features (green, hole) to the new coordinate system
    def transform_array_list(array_list):
        transformed = []
        for feature in array_list:
            transformed_feature = []
            for point in feature:
                new_x = int(point[0] * scale + offset_x)
                new_y = int(point[1] * scale + offset_y)
                transformed_feature.append([new_x, new_y])
            transformed.append(transformed_feature)
        return transformed
    
    # Transform the green and hole arrays
    fixed_green_array = transform_array_list(final_green_array)
    fixed_hole_array = transform_array_list([adjusted_hole_array[0]])[0]
    
    # Calculate the new yards per pixel (ypp) based on the scale
    fixed_ypp = ypp / scale
    
    # Now create the SVG output
    dwg = svgwrite.Drawing(size=(target_width, target_height), viewBox=f"0 0 {target_width} {target_height}")
    
    # Remove the white background rectangle since it’s redundant
    # Instead, we'll fill the entire background with the green area first
    # Add transformed green polygons (assumes the green is a polygon with multiple points)
    for feature in fixed_green_array:
        points = [(point[0], point[1]) for point in feature]
        dwg.add(dwg.polygon(points=points, fill="green", stroke="black", stroke_width=2))
    
    # Add transformed hole locations (represented as circles with a small radius)
    hole_radius = 5
    for hole in fixed_hole_array:
        dwg.add(dwg.circle(center=(hole[0], hole[1]), r=hole_radius, fill="black"))
    
    return dwg, fixed_green_array, fixed_hole_array, fixed_ypp """



def parse_svg_length(length):
    if isinstance(length, (int, float)):
        return float(length)
    elif isinstance(length, str):
        return float(length.replace("mm", "").replace("px", "").strip())
    raise ValueError(f"Unsupported SVG length format: {length}")

def to_float(val):
    if isinstance(val, (int, float)):
        return float(val)
    elif isinstance(val, str):
        return float(val.strip())
    raise ValueError(f"Unexpected type for padding value: {type(val)}")


#SVG add padding and save image, adds a white color to the background
def add_svg_padding_and_save(
    dwg,
    file_name,
    top_y_pad,
    bottom_y_pad,
    left_x_pad,
    right_x_pad,
    background_color="#FFFFFF",
    output_folder="output",
    
    rectangle_stroke="#000000",
    rectangle_stroke_width=0.5,
):
    from svgwrite import Drawing
    import copy, os

    def parse_svg_length(length):
        if isinstance(length, str):
            if length.endswith("mm"):
                return float(length[:-2])
            elif length.endswith("px"):
                px = float(length[:-2])
                return px * 25.4 / 300.0  # px -> mm @ 300 DPI
            else:
                raise ValueError(f"Unsupported SVG length unit in: {length}")
        elif isinstance(length, (float, int)):
            return float(length)
        else:
            raise ValueError(f"Invalid SVG length format: {length}")

    def to_float(v):
        try:
            return float(v)
        except Exception as e:
            print(f"[ERROR] Could not convert {v} to float: {e}")
            raise

    # Source size (assumes dwg['width']/['height'])
    old_w_mm = parse_svg_length(dwg['width'])
    old_h_mm = parse_svg_length(dwg['height'])

    # Padding px -> mm
    px_to_mm = 25.4 / 300.0
    left_pad_mm   = to_float(left_x_pad)   * px_to_mm
    right_pad_mm  = to_float(right_x_pad)  * px_to_mm
    top_pad_mm    = to_float(top_y_pad)    * px_to_mm
    bottom_pad_mm = to_float(bottom_y_pad) * px_to_mm

    new_w_mm = old_w_mm + left_pad_mm + right_pad_mm
    new_h_mm = old_h_mm + top_pad_mm + bottom_pad_mm

    os.makedirs(output_folder, exist_ok=True)
    out_path = f"{output_folder}/{file_name}"

    # New drawing
    padded = Drawing(filename=out_path, size=(f"{new_w_mm}mm", f"{new_h_mm}mm"), profile="full")
    padded.viewbox(0, 0, new_w_mm, new_h_mm)

    # --- Bring over source <defs> so styles/markers/gradients still work ---
    # Find the source defs block (if any) and copy its children
    for el in list(dwg.elements):
        if getattr(el, "elementname", "") == "defs":
            for child in el.elements:
                padded.defs.add(copy.deepcopy(child))

    # --- Final-box clipPath ---
    clip = padded.clipPath(id="final-drawing-box-clip", clipPathUnits="userSpaceOnUse")
    clip.add(padded.rect(insert=(0, 0), size=(new_w_mm, new_h_mm)))
    padded.defs.add(clip)
    
     # Content group translated by padding
    translated = padded.g(
        id="content-translated",
        transform=f"translate({left_pad_mm},{top_pad_mm})"
    )

    # --- Clip group that contains EVERYTHING ---
    final_group = padded.g(
        id="final-drawing-box-clip-group",
        clip_path=clip.get_funciri()
    )
    
    # Copy all non-defs top-level elements
    for el in list(dwg.elements):
        if getattr(el, "elementname", "") == "defs":
            continue
        translated.add(copy.deepcopy(el))

    # --- content-translated (applies padding offset) ---
    content_translated = padded.g(
        id="content-translated",
        transform=f"translate({left_pad_mm},{top_pad_mm})"
    )

    # --- final-drawing-box (clip group) ---
    final_box_group = padded.g(
        id="final-drawing-box",
        clip_path=clip.get_funciri()
    )

    # --- features: copy all non-defs top-level elements from source ---
    features_group = padded.g(id="features")
    for el in list(dwg.elements):
        if getattr(el, "elementname", "") == "defs":
            continue
        features_group.add(copy.deepcopy(el))

    # add features first (per your specified order)
    final_box_group.add(features_group)

    # --- rectangle outline of the final box (no fill, on top in DOM order you asked) ---
    final_box_group.add(
        padded.rect(
            insert=(0, 0),
            size=(new_w_mm, new_h_mm),
            fill="none",
            stroke=rectangle_stroke,
            stroke_width=rectangle_stroke_width	
        )
    )

    # assemble tree
    content_translated.add(final_box_group)
    padded.add(content_translated)

    # save once
    padded.save()
    print(f"[INFO] Saved padded SVG to {padded.filename}")




def generateYardageBook(latmin,lonmin,latmax,lonmax,replace_existing,colors,chosen_tbox,filter_width=50,short_factor=1,med_factor=1):

    # calculate distance in yards of one degree of latitude and one degree of longitude
    lat_degree_distance = getLatDegreeDistance(latmin,latmax)
    lon_degree_distance = getLonDegreeDistance(latmin,latmax)


    # download golf hole info from OSM
    result = getOSMGolfWays(latmin,lonmin,latmax,lonmax)
    ways = result.ways


    # find or create output directory
    # and get a list of existing files so we don't overwrite unintentionally

    try:
        file_list = os.listdir("output")
    except:
        os.mkdir("output")
        file_list = []

    # track the holes we are doing today

    new_file_list = []



    # for each hole in our data:

    for way in ways:


        # make sure each hole nas a number and value for par
        # (if not, you will need to add these in OSM)

        hole_num = way.tags.get("ref", None)
        hole_par = way.tags.get("par", None)

        print("Hole",hole_num,"Par",hole_par)

        if hole_num == None:
            print("Error: Hole number missing: skipping hole")
            continue

        try:
            hole_par = int(hole_par)
        except:
            print("Error: Hole par missing: skipping hole")
            continue


        # check if we are going to overwrite an existing dwg

        file_name = "hole_" + str(hole_num) + ".svg"

        if not replace_existing and file_name in file_list:
            print("Output file exists: skipping hole")
            continue


        if file_name in new_file_list:
            print("Output conflict found")
            counter = 2

            while file_name in new_file_list:
                file_name = "hole_" + str(hole_num) + "_" + str(counter)
                print(file_name)
                counter += 1
        # else:
            # print("no conflict found")


        new_file_list.append(file_name)


        # download all the golf data for this hole

        hole_way_nodes, hole_result, hole_minlat, hole_minlon, hole_maxlat, hole_maxlon = getHoleOSMData(way, lat_degree_distance, lon_degree_distance)

        # create a base dwg to use for this hole (and calculate yards per pixel)
        dwg, x_dim, y_dim, ypp = generateSVG(hole_minlat, hole_minlon, hole_maxlat, hole_maxlon, lat_degree_distance, lon_degree_distance,colors["background"])

        # find this hole's green
        green_nodes = identifyGreen(hole_way_nodes, hole_result)
  
        #calculate the 3 yard lat/lon coordinates for elevation calculation and contourline
        elevation_map = get_green_grid_points(green_nodes, spacing_yards=3)
        
        green_array = translateNodestoNP(green_nodes, hole_minlat, hole_minlon, hole_maxlat, hole_maxlon, x_dim, y_dim)

        # categorize all of the feature types (we do different things with each of them)
        sand_traps, tee_boxes, fairways, water_hazards, woods, trees = categorizeWays(hole_result, hole_minlat, hole_minlon, hole_maxlat, hole_maxlon, x_dim, y_dim)

        # by default, everything will be drawn as it is oriented in real life
        # but, for a yardage book, we want the hole drawn from the bottom to the top of the dwg
        # so, we need to figure out how much to rotate everythiung for this hole
        angle = getRotateAngle(translateNodestoNP(hole_way_nodes,hole_minlat, hole_minlon, hole_maxlat, hole_maxlon, x_dim, y_dim))

        # convert the hole waypoints to an array for rotation
        way_node_array = translateNodestoNP(hole_way_nodes, hole_minlat, hole_minlon, hole_maxlat, hole_maxlon, x_dim, y_dim)


        # rotate all of our features, including the green and the hole waypoints
        rotated_fairways = rotateArrayList(dwg,fairways,angle)
        rotated_tee_boxes = rotateArrayList(dwg,tee_boxes,angle)
        rotated_water_hazards = rotateArrayList(dwg,water_hazards,angle)
        rotated_sand_traps = rotateArrayList(dwg,sand_traps,angle)
        rotated_woods = rotateArrayList(dwg,woods,angle)
        rotated_trees = rotateArrayList(dwg,trees,angle)

        rotated_green = rotateArray(dwg,green_array,angle)
        rotated_green_array = [rotated_green]

        rotated_waypoints = rotateArray(dwg,way_node_array,angle)


        # we need to filter out any features that don't belong to this hole
        # (example - another hole's fairway that might be close by)
        filtered_fairways = filterArrayList(rotated_waypoints, rotated_fairways, ypp, hole_par, fairway=1, filter_yards=filter_width, small_filter=short_factor, med_filter=med_factor)
        filtered_tee_boxes = filterArrayList(rotated_waypoints, rotated_tee_boxes, ypp, hole_par, tee_box=1, filter_yards=filter_width, small_filter=short_factor, med_filter=med_factor)
        filtered_water_hazards = filterArrayList(rotated_waypoints, rotated_water_hazards, ypp, hole_par, filter_yards=None)
        filtered_sand_traps = filterArrayList(rotated_waypoints, rotated_sand_traps, ypp, hole_par, filter_yards=filter_width, small_filter=short_factor, med_filter=med_factor)
        filtered_woods = filterArrayList(rotated_waypoints, rotated_woods, ypp, hole_par, filter_yards=None)
        filtered_trees = filterArrayList(rotated_waypoints, rotated_trees, ypp, hole_par, filter_yards=25)


        # create a new, rotated base dwg to work with
        rotated_dwg, ymin, xmin, ymax, xmax = getNewdwg(dwg,angle,colors["background"])
        #create new features group
        features_group = rotated_dwg.g(id="features")


        # we need to adjust all our rotated features
        #print(f"filtered_fairways type: {type(filtered_fairways)}")
        print("filtering final fairways")
        final_fairways, fw_minx, fw_miny, fw_maxx, fw_maxy = adjustRotatedFeatures(filtered_fairways, ymin, xmin)
        print("filtering final t boxes")
        final_tee_boxes, tb_minx, tb_miny, tb_maxx, tb_maxy = adjustRotatedFeatures(filtered_tee_boxes, ymin, xmin)
        print("filtering final water hazards")
        final_water_hazards, n1, n2, n3, n4 = adjustRotatedFeatures(filtered_water_hazards, ymin, xmin)
        print("filtering final woods")
        final_woods, n1, n2, n3, n4 = adjustRotatedFeatures(filtered_woods, ymin, xmin)
        final_trees, n1, n2, n3, n4 = adjustRotatedFeatures(filtered_trees, ymin, xmin)


        final_green_array, g_minx, g_miny, g_maxx, g_maxy = adjustRotatedFeatures(rotated_green_array, ymin, xmin)

        final_sand_traps, st_minx, st_miny, st_maxx, st_maxy = adjustRotatedFeatures(filtered_sand_traps, ymin, xmin)

        adjusted_hole_array, n1, n2, n3, n4 = adjustRotatedFeatures([rotated_waypoints], ymin, xmin)

        # finally, we can draw all of the features on our dwg (with specific colors for each)
        drawFeatures(features_group, final_fairways, colors["fairways"], line_width=1)
        drawFeatures(features_group, final_tee_boxes, colors["tee boxes"], line_width=-1)
        drawFeatures(features_group, final_water_hazards, colors["water"], line_width=-1, feature_type="water")
        drawFeatures(features_group, final_woods, colors["woods"], line_width=-1, feature_type="woods")
        drawFeatures(features_group, final_green_array, colors["greens"], line_width=1)

        # drawing the sand traps and trees last so they aren't overlapped by fairways, etc.
        print("drawing sand features")
        drawFeatures(features_group, final_sand_traps, colors["sand"], line_width=-1, feature_type="sand")
        drawTrees(features_group, final_trees, colors["trees"])
        # Add the features group to the SVG

        rotated_dwg.add(features_group)

        # now we need to pad or crop the dwg to get a consistent aspect ratio
        # future TODO: clean this all up into functions, see about making aspect ratio adjustable
        print("now we need to pad or crop the dwg to get a consistent aspect ratio")
        lower_bound_x = min(fw_minx, tb_minx, g_minx, st_minx) - (20/ypp) - xmin
        lower_bound_y = min(fw_miny, tb_miny, g_miny, st_miny) - (5/ypp) - ymin - 100
        upper_bound_x = max(fw_maxx, tb_maxx, g_maxx, st_maxx) + (20/ypp) - xmin + 100
        upper_bound_y = tb_maxy + (10/ypp) - ymin + 100

        lower_bound_x = int(max(lower_bound_x, 0))
        upper_bound_x = int(min(upper_bound_x, xmax - xmin))
        lower_bound_y = int(max(lower_bound_y, 0))
        upper_bound_y = int(min(upper_bound_y, ymax - ymin))

        # start = (int(lower_bound_x - xmin),int(lower_bound_y - ymin))
        # end = (int(upper_bound_x - xmin),int(upper_bound_y - ymin))

        # cv2.rectangle(rotated_dwg, start, end, (0,0,255), 2)


        height = upper_bound_y - lower_bound_y
        width = upper_bound_x - lower_bound_x

        # check whether we need to pad the height or width to make the aspect ratio work
        if height/width > 2.83:
            eventual_height = height
            new_width = math.ceil(1/2.83 * height)

            right_x_pad = int(min(130,(new_width - width),xmax - xmin - upper_bound_x))
            left_x_pad = int(min((new_width - width - right_x_pad),lower_bound_x))

            top_y_pad = 0
            bottom_y_pad = 0

        else:
            eventual_height = new_height = math.ceil(2.83 * width)

            top_y_pad = int(min((new_height - height) / 2, lower_bound_y))
            bottom_y_pad = int(min((new_height - height) / 2, ymax - ymin - upper_bound_y))

            left_x_pad = 0
            right_x_pad = 0


        lower_bound_x = lower_bound_x - left_x_pad
        upper_bound_x = upper_bound_x + right_x_pad
        lower_bound_y = lower_bound_y - top_y_pad
        upper_bound_y = upper_bound_y + bottom_y_pad



        # using eventual height to get the text size and draw everything accordingly

        bb_xmin, bb_ymin, bb_xmax, bb_ymax = createHoleBoundingBox(rotated_waypoints, ypp)


        # adjusting the font size to vary based on how tall the dwg is in pixels
        # this way, the lettering will look consistent across holes, even if one is
        # 500 yards and one is 100 yards (this used to be a problem)
        print("adjusting the font size to vary based on how tall the dwg is in pixels")
        text_size = 48/3000*eventual_height
        text_size = round(text_size,2)


        # for a par 3, all we need to do is give distances to the center of the green from the tee box
        if hole_par == 3:
            print("drawing carry distance to green")
            drawGreenDistancesMin(rotated_dwg, adjusted_hole_array, final_tee_boxes, ypp, text_size, colors["text"], par_3_tees=1)

        # for longer holes, there's more to do:
        else:
            print("draw the carry distance to all the sand traps and water hazards")
            # draw the carry distance to all the sand traps and water hazards
            right_carries, left_carries = drawCarryDistances(rotated_dwg, adjusted_hole_array, final_tee_boxes, final_sand_traps, ypp, text_size, colors["text"])
            add_r, add_l = drawCarryDistances(rotated_dwg, adjusted_hole_array, final_tee_boxes, final_water_hazards, ypp, text_size, colors["text"])

            right_carries += add_r
            left_carries += add_l

            # if there aren't any sand traps or water hazards, draw something anyway to give the hole some scale
            drawExtraCarries(rotated_dwg, adjusted_hole_array, final_tee_boxes, right_carries, left_carries, ypp, text_size, colors["text"])

            # now, draw distances to the center of the green from any notable features (like traps or hazards)
            print("# now, draw distances to the center of the green from any notable features (like traps or hazards)")
            drawGreenDistancesMin(rotated_dwg, adjusted_hole_array, final_sand_traps, ypp, text_size, colors["text"])
            drawGreenDistancesMin(rotated_dwg, adjusted_hole_array, final_water_hazards, ypp, text_size, colors["text"])
            print("# now, draw distances to FAIRWAYS from any notable features (like traps or hazards)")
            drawGreenDistancesMax(rotated_dwg, adjusted_hole_array, final_fairways, ypp, text_size, colors["text"])
            print("# now, draw distances to TREES from any notable features (like traps or hazards)")
            drawGreenDistancesTree(rotated_dwg, adjusted_hole_array, final_trees, ypp, text_size, colors["text"])

            # finally, draw arcs on the fairway every 50 yards from the center of the green
            print("# finally, draw arcs on the fairway every 50 yards from the center of the green")
            drawGreenDistancesAnyWaypoint(rotated_dwg, adjusted_hole_array, ypp, 50, text_size, colors["text"])



        # now, we need to do a second round of padding to make the aspect ratio work
        # in case we ran out of room with our earlier efforts
        print("# now, we need to do a second round of padding to make the aspect ratio work")

        cropped_width = upper_bound_x - lower_bound_x
        cropped_height = upper_bound_y - lower_bound_y

        cropped_dwg = svgwrite.Drawing(size=(f"{cropped_width}px", f"{cropped_height}px"))

        if height/width > 2.83:
            new_width = math.ceil(1/2.83 * height)

            right_x_pad = int(min((new_width - width), 130))
            left_x_pad = int(max(0,(new_width - width - right_x_pad)))

            top_y_pad = 0
            bottom_y_pad = 0

        else:
            new_height = math.ceil(2.83 * width)

            right_x_pad = 0
            left_x_pad = 0

            top_y_pad = int((new_height - height) / 2)
            bottom_y_pad = int((new_height - height) / 2)

        #adds green to the backgroud of the image!!!!
        #padded_dwg = cv2.copyMakeBorder(cropped_dwg,top_y_pad,bottom_y_pad,left_x_pad,right_x_pad, cv2.BORDER_CONSTANT, value=(94, 166, 44))
        # save the dwg file to the output folder
          #cv2.imwrite(("output/" + file_name), padded_dwg)
         #add SVG padding and save image
        print("#add SVG padding and save image")
        add_svg_padding_and_save(rotated_dwg, file_name, top_y_pad, bottom_y_pad,left_x_pad, right_x_pad) 
        #rotated_dwg.saveas(f"output/{file_name.replace('.png', '.svg')}")
          

        # now, we need to make the green dwg for this hole
        print('creating green grid')

        try:
            green_list = os.listdir("greens")
        except:
            os.mkdir("greens")
            green_list = []


        # this time, we want to rotate the green (and everythign else) to be aligned front to back
        angle = getMidpointAngle(translateNodestoNP(hole_way_nodes,hole_minlat, hole_minlon, hole_maxlat, hole_maxlon, x_dim, y_dim))
        print("DEBUG: this is the green rotation angle", angle)
                                  
        # again, we need to rotate everything, including the green and hole waypoints
        rotated_fairways = rotateArrayList(dwg,fairways,angle)
        rotated_tee_boxes = rotateArrayList(dwg,tee_boxes,angle)
        rotated_water_hazards = rotateArrayList(dwg,water_hazards,angle)
        rotated_sand_traps = rotateArrayList(dwg,sand_traps,angle)
        rotated_woods = rotateArrayList(dwg,woods,angle)

        rotated_green = rotateArray(dwg,green_array,angle)
        rotated_green_array = [rotated_green]

        way_node_array = translateNodestoNP(hole_way_nodes, hole_minlat, hole_minlon, hole_maxlat, hole_maxlon, x_dim, y_dim)
        rotated_waypoints = rotateArray(dwg,way_node_array,angle)

        # and again, we want to filter out anything that isn't close by and relevant
        filtered_fairways = filterArrayList(rotated_waypoints, rotated_fairways, ypp, hole_par, fairway=1, filter_yards=filter_width, small_filter=short_factor, med_filter=med_factor)
        filtered_tee_boxes = filterArrayList(rotated_waypoints, rotated_tee_boxes, ypp, hole_par, tee_box=1, filter_yards=filter_width, small_filter=short_factor, med_filter=med_factor)
        filtered_water_hazards = filterArrayList(rotated_waypoints, rotated_water_hazards, ypp, hole_par, filter_yards=None)
        filtered_sand_traps = filterArrayList(rotated_waypoints, rotated_sand_traps, ypp, hole_par, filter_yards=None)
        filtered_woods = filterArrayList(rotated_waypoints, rotated_woods, ypp, hole_par, filter_yards=None)


        # time to make a new dwg
        rotated_dwg, ymin, xmin, ymax, xmax = getNewdwg(dwg,angle,colors["background"])
        features_group = rotated_dwg.g(id="features")       

        final_fairways, fw_minx, fw_miny, fw_maxx, fw_maxy = adjustRotatedFeatures(filtered_fairways, ymin, xmin)
        final_tee_boxes, tb_minx, tb_miny, tb_maxx, tb_maxy = adjustRotatedFeatures(filtered_tee_boxes, ymin, xmin)
        final_water_hazards, n1, n2, n3, n4 = adjustRotatedFeatures(filtered_water_hazards, ymin, xmin)
        final_woods, n1, n2, n3, n4 = adjustRotatedFeatures(filtered_woods, ymin, xmin)


        final_green_array, g_minx, g_miny, g_maxx, g_maxy = adjustRotatedFeatures(rotated_green_array, ymin, xmin)
        # green_nds = np.int32([rotated_green_array]) # bug in fillPoly - needs explicit cast to 32bit
        # cv2.fillPoly(dwg, green_nds, (155,242,161))

        final_sand_traps, st_minx, st_miny, st_maxx, st_maxy = adjustRotatedFeatures(filtered_sand_traps, ymin, xmin)

        adjusted_hole_array, n1, n2, n3, n4 = adjustRotatedFeatures([rotated_waypoints], ymin, xmin)

        # we're going to draw everything in black and white this time for a different style
        #bw_green_dwg = rotated_dwg
        #bw_green_dwg[:] = (255,255,255)
        
        drawFeatures(features_group, final_fairways, "#ebebeb", line_width=-1)
        drawFeatures(features_group, final_tee_boxes, "#c3c3c3", line_width=-1)
        drawFeatures(features_group, final_water_hazards, "#b4b4b4", line_width=-1)
        drawFeatures(features_group, final_woods, "#b4b4b4", line_width=-1)
        drawFeatures(features_group, final_green_array, "#0ccb1f", line_width=3)
        drawFeatures(features_group, final_sand_traps, "#ebebeb", line_width=-1)
        print(type(elevation_map), elevation_map)

        # Add the drawn features to the features group to the SVG
        rotated_dwg.add(features_group)
        #DEBUG: saving file for testing
        #print("[DEBUG]: for testing only, saving unpadded green dwg as test.svg")
        #rotated_dwg.saveas("test.svg")
        
        # we also want to overlay a 3-yard grid to show how large the green is
        # and to make it easier to figure out carry distances to greenside bunkers
        print("# we also want to overlay a 3-yard grid to show how large the green is.This is the rotation angle:", angle)
        
            
        # Create a group for all features. This is to ensure that we can crop the paths and only show what's important
        green_grid_group = rotated_dwg.g(id="green-grid")
        #rotated_dwg.add(green_grid_group)

        green_grid_svg = getGreenGrid(adjusted_hole_array, ypp, rotated_dwg, features_group, green_grid_group, hole_way_nodes, angle, elevation_map)
        
        # save the green dwg to the greens folder
        green_grid_svg.saveas(f"greens/{file_name.replace('.png', '.svg')}")

    return True
