import overpy
import numpy as np
import cv2
import math
import statistics
import imutils
from scipy.spatial import distance as dist
import os


# convert hex to bgr format for numpy

def hexToBGR(hex):
	if hex[0] == "#":
		hex = hex[1:]

	r = int(hex[0:2], 16)
	g = int(hex[2:4], 16)
	b = int(hex[4:6], 16)

	return (b,g,r)



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

	op = overpy.Overpass()

	# create the coordinate string for our request - order is South, West, North, East
	coord_string = str(bottom_lat) + "," + str(left_lon) + "," + str(top_lat) + "," + str(right_lon)

	# use the coordinate string to pull the data through Overpass - golf holes only
	try:
		query = "(way['golf'='hole'](" + coord_string + "););out;"
		return op.query(query)


	except overpy.exception.OverPyException:
		printf("OpenStreetMap servers are too busy right now.  Try running this tool later.")
		return None

# function to get all golf data contained within a given bounding box (e.g. fairways, greens, sand traps, etc)

def getOSMGolfData(bottom_lat, left_lon, top_lat, right_lon, printf=print):

	op = overpy.Overpass() # optional replacement url if servers are busy - url="https://overpass.kumi.systems/api/interpreter"

	# create the coordinate string for our request - order is South, West, North, East
	coord_string = str(bottom_lat) + "," + str(left_lon) + "," + str(top_lat) + "," + str(right_lon)

	# use the coordinate string to pull the data through Overpass
	# we want all golf ways, with some additions for woods, trees, and water hazards
	try:
		query = "(way['golf'](" + coord_string + ");way['natural'='wood'](" + coord_string + ");node['natural'='tree'](" + coord_string + ");way['landuse'='forest'](" + coord_string + ");way['natural'='water'](" + coord_string + "););out;"

		return op.query(query)

	except overpy.exception.OverPyException:
		printf("OpenStreetMap servers are too busy right now.  Try running this tool later.")
		return None


# calculate length of a degree of latitude at a given location

def getLatDegreeDistance(bottom_lat, top_lat):

	# this is the approximate distance of a degree of latitude at the equator in yards
	lat_degree_distance_equator = 120925.62

	# a degree of latitude gets approximately 13.56 yards longer per degree you go north
	lat_yds_per_degree = 13.56

	# find the average latitude of our course
	average_lat = statistics.mean([bottom_lat, top_lat])

	# calculate length of a degree of latitude is at this average latitude
	lat_degree_distance_yds = lat_degree_distance_equator + (abs(average_lat) * lat_yds_per_degree)

	return lat_degree_distance_yds


# calculate length of a degree of longitude at a given location

def getLonDegreeDistance(bottom_lat, top_lat): # length of longitude depends on latitude because the Earth is a sphere!

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

	lowest_lat, lowest_lon, highest_lat, highest_lon = getBoundingBoxLatLon(hole_way_nodes)

	# add 50 yards in each direction to the bounding box (to include all features like sand traps, water, etc)

	extra_lat_distance = 50 * (1/lat_degree_distance)

	extra_lon_distance = 50 * (1/lon_degree_distance)

	lowest_lat = lowest_lat - extra_lat_distance
	highest_lat = highest_lat + extra_lat_distance

	lowest_lon = lowest_lon - extra_lon_distance
	highest_lon = highest_lon + extra_lon_distance

	return lowest_lat, lowest_lon, highest_lat, highest_lon, hole_way_nodes


# create a blank image of the appropriate size to use in drawing the hole

def generateImage(latmin, lonmin, latmax, lonmax, lat_degree_distance, lon_degree_distance, rough_color):

	lat_distance = (latmax - latmin) * lat_degree_distance
	lon_distance = (lonmax - lonmin) * lon_degree_distance


	# set the scale of our images to be 3000 pixels for the longest distance (x or y)
	# also define yards per pixel and pixels per yard values to use in distance calculation

	scale = 3000

	if lat_distance >= lon_distance:
		y_dim = scale
		x_dim = int((lon_distance / lat_distance) * scale)
		ypp = lat_distance / scale
	else:
		x_dim = scale
		y_dim = int((lat_distance / lon_distance) * scale)
		ypp = lon_distance / scale


	im = np.zeros((x_dim, y_dim, 3), np.uint8)

	# Fill image with background color

	im[:] = rough_color

	# return the image and some other information for use in measurement

	return im, x_dim, y_dim, ypp


# given a golf hole's waypoints, get all feature data from OSM for that hole (e.g. fairway, sand traps, water hazards, etc)

def getHoleOSMData(way, lat_degree_distance, lon_degree_distance):

	# get the bounding box to search for this hole

	hole_minlat, hole_minlon, hole_maxlat, hole_maxlon, hole_way_nodes = getHoleBoundingBox(way, lat_degree_distance, lon_degree_distance)

	# download all golf data in this bounding box from OSM

	hole_result = getOSMGolfData(hole_minlat, hole_minlon, hole_maxlat, hole_maxlon)

	return hole_way_nodes, hole_result, hole_minlat, hole_minlon, hole_maxlat, hole_maxlon


# given a list of coordinates that define a golf hole in OSM, find the green

def identifyGreen(hole_way_nodes, hole_result):

	# if mapped correctly, the last coordinate should mark the center of the green in OSM

	green_center = hole_way_nodes[-1]

	# now search all the data we have for this hole, and filter to find golf greens only
	# check each one to see if it contains the center of the green for the hole we are on
	# (we have to do this because sometimes the green from another hole might be close enough
	# to the fairway to show up in our data pull)

	green_found = False

	for way in hole_result.ways:
		if way.tags.get("golf", None) == "green":

			green_nodes = way.get_nodes(resolve_missing=True)

			green_min_lat, green_min_lon, green_max_lat, green_max_lon = getBoundingBoxLatLon(green_nodes)

			# checking if the center of the green for this hole is within this green

			if green_center.lat > green_min_lat and green_center.lat < green_max_lat and green_center.lon > green_min_lon and green_center.lon < green_max_lon:

				green_found = True
				return green_nodes

	# if we couldn't find a green, return an error

	if green_found == False:
		print("Error: green could not be found")
		return None


# convert an OSM way to a numpy array we can use for image processing

def translateWaytoNP(way, hole_minlat, hole_minlon, hole_maxlat, hole_maxlon, x_dim, y_dim):
	#
	# print("getting nodes for: ", way.tags.get("golf", None))


	# convert each coordinate's location within the bounding box to a pixel location
	# ex: if a coordinate is 70% of the way east and 30% of the way north in the bounding box,
	# we want that point to be 70% from the left and 30% from the bottom of our image

	nds = []
	for node in way.get_nodes(resolve_missing=True):
		yfactor = ((float(node.lat) - hole_minlat) / (hole_maxlat - hole_minlat)) * y_dim
		xfactor = ((float(node.lon) - hole_minlon) / (hole_maxlon - hole_minlon)) * x_dim

		# we need to round to integers for image processing

		column = int(xfactor)
		row = int(yfactor)

		nds.append((column, row))

	# the script uses points and not image pixels, so flip the x and y

	nds = np.array(nds)
	nds[:,[0, 1]] = nds[:,[1, 0]]

	return nds


# convert a list of coordinates to a numpy array we can use for image processing

def translateNodestoNP(nodes, hole_minlat, hole_minlon, hole_maxlat, hole_maxlon, x_dim, y_dim):

	# convert each coordinate's location within the bounding box to a pixel location
	# ex: if a coordinate is 70% of the way east and 30% of the way north in the bounding box,
	# we want that point to be 70% from the left and 30% from the bottom of our image

	nds = []
	for node in nodes:
		yfactor = ((float(node.lat) - hole_minlat) / (hole_maxlat - hole_minlat)) * y_dim
		xfactor = ((float(node.lon) - hole_minlon) / (hole_maxlon - hole_minlon)) * x_dim


		# we need to round to integers for image processing

		column = int(xfactor)
		row = int(yfactor)

		nds.append((column, row))

	# the script uses points and not image pixels, so flip the x and y

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
			# print(node_list)
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

	return sand_traps, tee_boxes, fairways, water_hazards, woods, trees


# given a numpy array and an image, fill in the array as a polygon on the image (in a given color)
# also draw an outline if it is specified

def drawFeature(image, array, color, line=-1):

	nds = np.int32([array]) # bug in fillPoly - needs explicit cast to 32bit

	cv2.fillPoly(image, nds, color)

	if line > 0:
		# need to redraw a line since fillPoly has no line thickness options that I've found
		cv2.polylines(image, nds, True, (0,0,0), line, lineType=cv2.LINE_AA)


# for a list of arrays and an image, draw each array as a polygon on the image (in a given color)

def drawFeatures(image, feature_list, color, line=-1):

	for feature_nodes in feature_list:

		drawFeature(image, feature_nodes, color, line=-1)


# for a list of tree nodes and an image, draw each tree on the image

def drawTrees(image, feature_list, color):

	for feature_nodes in feature_list:

		nds = np.int32([feature_nodes])

		# convert from numpy array back to a list of coordinates (not best-practice)
		tree = nds.tolist()[0][0]


		x = int(tree[0])
		y = int(tree[1])

		# draw a circle with an X inside as a tree symbol

		cv2.circle(image, (x,y), 50, color, thickness=6)

		top = (x,y - 50)
		bottom = (x,y + 50)

		cv2.line(image, top, bottom, color, thickness=6)

		left = (x - 50, y)
		right = (x + 50, y)

		cv2.line(image, left, right, color, thickness=6)

		tr = (x + int(50 * math.cos(math.pi/4)),y + int(50 * math.sin(math.pi/4)))
		bl = (x + int(50 * math.cos(5*math.pi/4)),y + int(50 * math.sin(5*math.pi/4)))

		cv2.line(image, tr, bl, color, thickness=6)

		tl = (x + int(50 * math.cos(3*math.pi/4)),y + int(50 * math.sin(3*math.pi/4)))
		br = (x + int(50 * math.cos(7*math.pi/4)),y + int(50 * math.sin(7*math.pi/4)))

		cv2.line(image, tl, br, color, thickness=6)


# when the features were rotated, their coordinates could have been outside our image boundaries
# so we have to adjust them to be within the boundaries of our new image

def adjustRotatedFeatures(feature_list, ymin, xmin):

	minx = miny = 10000
	maxx = maxy = -10000

	output_list = []

	for feature_nodes in feature_list:

		w = np.zeros(feature_nodes.shape)

		# print("pre-translation:",feature_nodes)

		for i,v in enumerate(feature_nodes):
			w[i] = v

			x = w[i,0]
			y = w[i,1]

			newx = float(x) - xmin
			newy = float(y) - ymin


			w[i,0] = newx
			w[i,1] = newy

			minx = min(x, minx)
			miny = min(y, miny)
			maxx = max(x, maxx)
			maxy = max(y, maxy)

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
	tee_box_filter = tee_box * (90/ypp + par4plus * (140/ypp))

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

		if fairway == 1:

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
	denominator = math.sqrt(((x2-x)**2)+((bigy-smally)**2))

	rads = math.acos((numerator/denominator))

	angle = math.degrees(rads)

	# adjust to get the appropriate angle for our use

	if y > y2 and x > x2:
		angle = 180 - angle
	elif y > y2 and x < x2:
		angle = 180 + angle
	elif y < y2 and x < x2:
		angle = 360 - angle
	else:
		angle=angle

	return angle


# given a list of the hole coordinates, figure out how much we need to
# rotate our image in order to display the hole running from bottom to top

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

	# print("Angle to be rotated is:", angle)

	return angle


# given a list of the hole coordinates, figure out how much we need to rotate our image
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


# rotate an array (such as a sand trap) by the appropriate angle to show
# the hole running from bottom to top

def rotateArray(image, array, angle):

	theta = np.radians(-angle)

	(height, width) = image.shape[:2]

	ox = width // 2
	oy = height // 2

	center = np.array([ox, oy])

	return Rotate2D(array,center,theta)


# given a list of arrays for a certain hole, rotate each of them by a given angle

def rotateArrayList(image,array_list,angle):

	new_list = []

	for array in array_list:
		rotated_array = rotateArray(image, array, angle)
		new_list.append(rotated_array)

	return new_list


# given an existing hole image and an angle to rotate it,
# create a new image with appropriate dimensions to display
# the hole running from bottom to top

def getNewImage(image, angle, rough_color):
	(h, w) = image.shape[:2]

	boundary_array = np.array([[0,0],[w,0],[0,h],[w,h]])

	result_array = rotateArray(image,boundary_array,angle)

	coord_list = result_array.tolist()

	xmin = ymin = 10000
	xmax = ymax = -10000

	for coord in coord_list:

		xmin = min(xmin,coord[0])
		ymin = min(ymin,coord[1])
		xmax = max(xmax,coord[0])
		ymax = max(ymax,coord[1])

	x_dim = int(xmax - xmin)
	y_dim = int(ymax - ymin)

	new_image = np.zeros((y_dim, x_dim, 3), np.uint8)

	# Fill image with background color

	new_image[:] = rough_color

	return new_image, ymin, xmin, ymax, xmax


# calculate the difstance between two pixels in yards (given a yards per pixel value)

def getDistance(originpoint, destinationpoint, ypp):

	distance = dist.euclidean(originpoint, destinationpoint)

	distance_in_yards = distance * ypp

	return distance_in_yards


# for a list of features, get the point of each feature that is
# closest to the top of the image

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
# furthest from the top of the image

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


# given a list of points, draw a dot on each point in our image

def drawMarkerPoints(image, marker_point_list, text_size, text_color):

	for point in marker_point_list:

		cv2.circle(image, (int(point[0]),int(point[1])), int(6.5+text_size), text_color, thickness=-1)


# given a point, draw in the carry distances to that point from the
# back of each tee box (given in tee_box_points)

def drawCarry(image, green_center, carrypoint, tee_box_points, ypp, text_size, text_color, right):

	text_weight = round(text_size*2)

	dist_list = []

	if len(tee_box_points) == 0:
		print("error: no tee box points found for carries")
		return 0

	for tee in tee_box_points:
		distance = int(getDistance(tee,carrypoint,ypp))
		dist_list.append(distance)

	maxpoint_distance = max(dist_list)

	# we only want to draw carry distances that are actually helpful to see on the tee
	# if it's too close or too far, ignore it

	if maxpoint_distance < 185 or maxpoint_distance > 325:
		# print("carry outside of our reasonable range")
		return 0

	# count the number of tees

	tee_num = len(dist_list)

	# measure how big the label will be so we can center properly

	(label_width, label_height), baseline = cv2.getTextSize(str(distance), cv2.FONT_HERSHEY_SIMPLEX,text_size, text_weight)

	# calculate the total label height

	totalheight = (32 * (tee_num-1) * text_size)

	# declare x and y coordinates to place the text

	if right:
		x = int(carrypoint[0] + (10 * (text_size + 0.1)) + 5)
	else:
		x = int(carrypoint[0] - (10 * (text_size + 0.1)) - label_width)

	y = int(carrypoint[1] - totalheight/2 + 4 + baseline)

	# declare an increment for each new tee distance (so that they stack vertically)

	yinc = int(32 * text_size)

	# now for each distance found, write it on the image next to the marker

	dist_list.sort()

	for distance in dist_list:

		cv2.putText(image, str(distance), (x , y), cv2.FONT_HERSHEY_SIMPLEX, text_size, text_color, text_weight)

		y += yinc

	# mark where these distances are measuring

	cv2.circle(image, (int(carrypoint[0]),int(carrypoint[1])), int(6.5+text_size), text_color, thickness=-1)

	drawMarkerPoints(image, tee_box_points, text_size, text_color)

	dtg = getDistance(green_center, carrypoint, ypp)

	if dtg < 40 or maxpoint_distance < 215 or maxpoint_distance > 290:

		# print("still need a carry to reasonable fairway point",dtg,maxpoint_distance)

		return 0

	else:

		# print("confirmed reasonable carry")

		return 1



def getMidpoint(ptA, ptB):
	return ((ptA[0] + ptB[0]) * 0.5, (ptA[1] + ptB[1]) * 0.5)



# get a list of three waypoints for a  hole, even if there are only two or more than three

def getThreeWaypoints(adjusted_hole_array):
	hole_points = adjusted_hole_array[0].tolist()

	hole_origin = hole_points[0]

	if len(hole_points) == 2:
		midpoint = getMidpoint(hole_origin,hole_points[-1])
	else:
		midpoint = hole_points[1]


	green_center = hole_points[-1]

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

def drawCarryDistances(image, adjusted_hole_array, tee_box_list, carry_feature_list, ypp, text_size, text_color, filter_dist=40):

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
			right_carries_drawn += drawCarry(image, green_center, carry, tee_box_points, ypp, text_size, text_color, right)
			drawn_carries.append(carry)
		else:
			left_carries_drawn += drawCarry(image, green_center, carry, tee_box_points, ypp, text_size, text_color, right)
			drawn_carries.append(carry)

	return right_carries_drawn, left_carries_drawn


# we want to draw at least one carry distance on each hole, even if there are
# no bunkers or other features of note
# this way, players have a sense of how long the hole is, etc.

def drawExtraCarries(image, adjusted_hole_array, tee_boxes, right_carries, left_carries, ypp, text_size, text_color):

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

	num = drawCarry(image, green_center, carry, tee_box_points, ypp, text_size, text_color, right)



# given a point and a distance, draw the distance next to the point

def drawDistanceText(image, distance, point, text_size, text_color):

	text_weight = round(text_size*2)

	(label_width, label_height), baseline = cv2.getTextSize(str(distance), cv2.FONT_HERSHEY_SIMPLEX,text_size, text_weight)

	x = int(point[0] - (0.5*label_width))
	y = int(point[1] + 16 + (26 * text_size))

	cv2.putText(image, str(distance), (x,y), cv2.FONT_HERSHEY_SIMPLEX, text_size, text_color, text_weight)


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


# draw arcs down the fairway at 50-yard intervals from the center of the green

def drawFarGreenDistances(image, adjusted_hole_array, ypp, draw_dist, text_size, text_color):

	angle_dict = {50:30,100:15.2,150:9.8,200:7.5,250:6,300:5,350:4.6}

	hole_origin, midpoint, green_center = getThreeWaypoints(adjusted_hole_array)

	integer_green_center = (int(green_center[0]),int(green_center[1]))

	hole_length_limit = ((dist.euclidean(hole_origin,midpoint) + dist.euclidean(midpoint,green_center)) * ypp) - 200

	hole_length_limit = max(hole_length_limit, ((dist.euclidean(hole_origin,midpoint) + dist.euclidean(midpoint,green_center)) * ypp)*0.6)

	midpoint_dist = dist.euclidean(green_center,midpoint) * ypp

	hole_length_limit = max(midpoint_dist, hole_length_limit)

	hole_length_limit = min(350,hole_length_limit)

	# hole_length_limit = 301

	while draw_dist < midpoint_dist:

		drawpoint = getPointOnOtherLine(midpoint, green_center, green_center, draw_dist, ypp)


		drawDistanceText(image, draw_dist, drawpoint, text_size, text_color)


		pixel_dist = int(draw_dist/ypp)

		angle = getAngle(green_center,drawpoint)

		# print("Arc angle is:",angle)

		drawn_angle = angle + 90


		offset = angle_dict[draw_dist]

		# print("Offset is:", offset)

		cv2.ellipse(image,integer_green_center,(pixel_dist,pixel_dist),drawn_angle,-offset,offset,text_color,2)

		draw_dist += 50


	# once the distance we are drawing is farther than the distance to the hole's
	# midpoint, we have to switch to drawing on the line between the origin and the
	# midpoint

	while draw_dist < hole_length_limit:

		drawpoint = getPointOnOtherLine(hole_origin, midpoint, green_center, draw_dist, ypp)

		drawDistanceText(image, draw_dist, drawpoint, text_size, text_color)

		pixel_dist = int(draw_dist/ypp)

		angle = getAngle(green_center,drawpoint)

		drawn_angle = angle + 90


		offset = angle_dict[draw_dist]

		cv2.ellipse(image,integer_green_center,(pixel_dist,pixel_dist),drawn_angle,-offset,offset,text_color,2)


		draw_dist += 50


# special case to handle holes with four waypoints (double doglegs)

def drawGreenDistancesAnyWaypoint(image, adjusted_hole_array, ypp, draw_dist, text_size, text_color):

	hole_points = adjusted_hole_array[0].tolist()

	if len(hole_points) < 4:

		# if there are 3 or fewer waypoints, we can use the old method

		drawFarGreenDistances(image, adjusted_hole_array, ypp, draw_dist, text_size, text_color)

		return True

	elif len(hole_points) == 4:

		# print("found four hole waypoints - using new method")

		angle_dict = {50:30,100:15.2,150:9.8,200:7.5,250:6,300:5,350:4.6}

		hole_origin = hole_points[0]

		green_center = hole_points[-1]

		integer_green_center = (int(green_center[0]),int(green_center[1]))

		first_midpoint = hole_points[1]

		second_midpoint = hole_points[2]

		hole_length_limit = ((dist.euclidean(hole_origin,first_midpoint) +
			dist.euclidean(first_midpoint, second_midpoint) +
			dist.euclidean(second_midpoint,green_center)) * ypp) - 200

		hole_length_limit = max(hole_length_limit,
			((dist.euclidean(hole_origin,first_midpoint) +
				dist.euclidean(first_midpoint, second_midpoint) +
				dist.euclidean(second_midpoint,green_center)) * ypp)*0.6)

		second_midpoint_dist = dist.euclidean(green_center,second_midpoint) * ypp

		first_midpoint_dist = dist.euclidean(green_center,first_midpoint) * ypp

		hole_length_limit = max(first_midpoint_dist, hole_length_limit)

		hole_length_limit = min(350,hole_length_limit)

		while draw_dist < second_midpoint_dist:

			drawpoint = getPointOnOtherLine(second_midpoint, green_center, green_center, draw_dist, ypp)


			drawDistanceText(image, draw_dist, drawpoint, text_size, text_color)


			pixel_dist = int(draw_dist/ypp)

			angle = getAngle(green_center,drawpoint)

			# print("Arc angle is:",angle)

			drawn_angle = angle + 90


			offset = angle_dict[draw_dist]

			# print("Offset is:", offset)

			cv2.ellipse(image,integer_green_center,(pixel_dist,pixel_dist),drawn_angle,-offset,offset,text_color,2)

			draw_dist += 50


		while draw_dist < first_midpoint_dist:

			drawpoint = getPointOnOtherLine(first_midpoint, second_midpoint, green_center, draw_dist, ypp)


			drawDistanceText(image, draw_dist, drawpoint, text_size, text_color)


			pixel_dist = int(draw_dist/ypp)

			angle = getAngle(green_center,drawpoint)

			# print("Arc angle is:",angle)

			drawn_angle = angle + 90


			offset = angle_dict[draw_dist]

			# print("Offset is:", offset)

			cv2.ellipse(image,integer_green_center,(pixel_dist,pixel_dist),drawn_angle,-offset,offset,text_color,2)

			draw_dist += 50


		while draw_dist < hole_length_limit:

			drawpoint = getPointOnOtherLine(hole_origin, first_midpoint, green_center, draw_dist, ypp)

			drawDistanceText(image, draw_dist, drawpoint, text_size, text_color)

			pixel_dist = int(draw_dist/ypp)

			angle = getAngle(green_center,drawpoint)

			# print("Arc angle is:",angle)

			drawn_angle = angle + 90


			offset = angle_dict[draw_dist]

			# print("Offset is:", offset)

			cv2.ellipse(image,integer_green_center,(pixel_dist,pixel_dist),drawn_angle,-offset,offset,text_color,2)


			draw_dist += 50

	else:
		print("error: more than 4 hole waypoints found")
		return None


# given a point, draw a triangle on it

def drawTriangle(image, point, base, height, text_color):

	apex = (int(point[0]),int(point[1]-(height/2)))
	base1 = (int(point[0]-(base/2)),int(point[1]+(height/2)))
	base2 = (int(point[0]+(base/2)),int(point[1]+(height/2)))

	# draw a triangle
	vertices = np.array([apex, base1, base2], np.int32)
	pts = vertices.reshape((-1, 1, 2))
	cv2.polylines(image, [pts], isClosed=True, color=(0, 0, 0), thickness=2)

	# fill it
	cv2.fillPoly(image, [pts], color=text_color)


def drawTriangleMarkers(image, points, base, height, text_color):

	for point in points:
		drawTriangle(image, point, base, height, text_color)


# given a list of features, draw the distance to the center of the green from each
# (from the farthest back point)

def drawGreenDistancesMin(image, adjusted_hole_array, feature_list, ypp, text_size, text_color, filter_dist=40, par_3_tees=0):

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

		base = int(8 + 8*text_size)

		height = int((3/5)*base)

		drawTriangleMarkers(image, [point], base, height, text_color)

		drawDistanceText(image, distance, point, text_size, text_color)

		drawn_distances.append(point)


# given a list of trees, draw the distance to the center of the green form each

def drawGreenDistancesTree(image, adjusted_hole_array, tree_list, ypp, text_size, text_color, filter_dist=25, par_3_tees=0):

	text_weight = round(text_size*2)

	hole_origin, midpoint, green_center = getThreeWaypoints(adjusted_hole_array)

	hole_distance = getDistance(hole_origin,green_center,ypp)

	distance_points = []

	for tree in tree_list:
		point = tree.tolist()[0]
		distance_points.append(point)

	drawn_distances = []

	for point in distance_points:

		distance = int(getDistance(point,green_center,ypp))

		if distance < 40:
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

		if distance % 50 < 5 or distance % 50 > 45:
			close = True

		if close:
			continue

		if point[1] < midpoint[1]:
			dist_to_way = distToLine(point,midpoint,green_center,ypp)
			slope, intercept = getLine(midpoint,green_center)
		else:
			dist_to_way = distToLine(point,midpoint,hole_origin,ypp)
			slope, intercept = getLine(midpoint,hole_origin)

		if dist_to_way > filter_dist:
			continue


		right = True

		# y = mx + b    y = carry[1]   x = (carry[1] - b) / slope

		comp_value = (point[1] - intercept) / slope


		if point[0] < comp_value:
			right = False


		if right:

			(label_width, label_height), baseline = cv2.getTextSize(str(distance), cv2.FONT_HERSHEY_SIMPLEX, text_size, text_weight)

			drawpoint = (point[0] - 75 - label_width,point[1])

		else:

			drawpoint = (point[0] + 75,point[1])

		cv2.line(image,(int(point[0]),int(point[1])),(int(drawpoint[0]),int(drawpoint[1])),text_color, 3)

		text_weight = round(text_size*2)

		(label_width, label_height), baseline = cv2.getTextSize(str(distance), cv2.FONT_HERSHEY_SIMPLEX,text_size, text_weight)

		x = int(drawpoint[0] + 2*text_weight)
		y = int(drawpoint[1] + 0.5*label_height)

		cv2.putText(image, str(distance), (x,y), cv2.FONT_HERSHEY_SIMPLEX, text_size, text_color, text_weight)

		drawn_distances.append(point)


# given a list of features, draw the distance to the center of the green from each
# (from the closest point)

def drawGreenDistancesMax(image, adjusted_hole_array, feature_list, ypp, text_size, text_color, filter_dist=40):

	hole_origin, midpoint, green_center = getThreeWaypoints(adjusted_hole_array)

	hole_distance = getDistance(hole_origin,green_center,ypp)

	distance_points = getMaxPoints(feature_list)

	for point in distance_points:

		distance = int(getDistance(point,green_center,ypp))

		if distance < 40 or distance > (0.75*hole_distance):
			continue

		if point[1] < midpoint[1]:
			dist_to_way = distToLine(point,midpoint,green_center,ypp)
		else:
			dist_to_way = distToLine(point,midpoint,hole_origin,ypp)

		if dist_to_way > filter_dist:
			continue

		# print("distance from tee box to green:",distance)

		base = int(17 + 2*text_size)

		height = int((3/5)*base)

		drawTriangleMarkers(image, [point], base, height, text_color)

		drawDistanceText(image, distance, point, text_size, text_color)


# draw a three-yard grid over the green image that is aligned with the center of the green

def getGreenGrid(b_w_image, adjusted_hole_array, ypp):

	hole_origin, midpoint, green_center = getThreeWaypoints(adjusted_hole_array)

	x = int(green_center[0])
	y = int(green_center[1])

	xmin = int(x - (30/ypp))
	xmax = int(x + (30/ypp))
	ymin = int(y - (30/ypp))
	ymax = int(y + (39/ypp))


	start = (x - int(0.5/ypp),y + int(0.5/ypp))
	end = (x + int(0.5/ypp),y - int(0.5/ypp))

	cv2.rectangle(b_w_image, start, end, (0,0,0), -1)


	cropped_image = b_w_image[ymin:ymax, xmin:xmax]

	(h, w) = cropped_image.shape[:2]

	if w > 850:
		line_thickness = 2
	else:
		line_thickness = 1

	grid_x = x - xmin

	while grid_x < w:
		x1, y1 = int(grid_x), 0
		x2, y2 = int(grid_x), h

		cv2.line(cropped_image, (x1, y1), (x2, y2), (140, 140, 140), thickness=line_thickness)

		grid_x += 3/ypp

	grid_x = int(x - xmin - 3/ypp)

	while grid_x > 0:
		x1, y1 = int(grid_x), 0
		x2, y2 = int(grid_x), h

		cv2.line(cropped_image, (x1, y1), (x2, y2), (140, 140, 140), thickness=line_thickness)

		grid_x -= 3/ypp

	grid_y = y - ymin

	while grid_y < h:
		x1, y1 = 0, int(grid_y)
		x2, y2 = w, int(grid_y)

		cv2.line(cropped_image, (x1, y1), (x2, y2), (140, 140, 140), thickness=line_thickness)

		grid_y += 3/ypp

	grid_y = int(y - ymin - 3/ypp)

	while grid_y > 0:
		x1, y1 = 0, int(grid_y)
		x2, y2 = w, int(grid_y)

		cv2.line(cropped_image, (x1, y1), (x2, y2), (140, 140, 140), thickness=line_thickness)

		grid_y -= 3/ypp

	padded_image = cv2.copyMakeBorder(cropped_image,line_thickness,line_thickness,line_thickness,line_thickness, cv2.BORDER_CONSTANT, value=(140, 140, 140))

	return padded_image


def generateYardageBook(latmin,lonmin,latmax,lonmax,replace_existing,colors,filter_width=50,short_factor=1,med_factor=1):

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


		# check if we are going to overwrite an existing image

		file_name = "hole_" + str(hole_num) + ".png"

		if not replace_existing and file_name in file_list:
			print("Output file exists: skipping hole")
			continue


		if file_name in new_file_list:
			print("Output conflict found")
			counter = 2

			while file_name in new_file_list:
				file_name = "hole_" + str(hole_num) + "_" + str(counter) + ".png"
				print(file_name)
				counter += 1
		# else:
			# print("no conflict found")


		new_file_list.append(file_name)


		# download all the golf data for this hole

		hole_way_nodes, hole_result, hole_minlat, hole_minlon, hole_maxlat, hole_maxlon = getHoleOSMData(way, lat_degree_distance, lon_degree_distance)

		# create a base image to use for this hole (and calculate yards per pixel)
		image, x_dim, y_dim, ypp = generateImage(hole_minlat, hole_minlon, hole_maxlat, hole_maxlon, lat_degree_distance, lon_degree_distance,colors["rough"])

		# find this hole's green
		green_nodes = identifyGreen(hole_way_nodes, hole_result)

		green_array = translateNodestoNP(green_nodes, hole_minlat, hole_minlon, hole_maxlat, hole_maxlon, x_dim, y_dim)

		# categorize all of the feature types (we do different things with each of them)
		sand_traps, tee_boxes, fairways, water_hazards, woods, trees = categorizeWays(hole_result, hole_minlat, hole_minlon, hole_maxlat, hole_maxlon, x_dim, y_dim)

		# by default, everything will be drawn as it is oriented in real life
		# but, for a yardage book, we want the hole drawn from the bottom to the top of the image
		# so, we need to figure out how much to rotate everythiung for this hole
		angle = getRotateAngle(translateNodestoNP(hole_way_nodes,hole_minlat, hole_minlon, hole_maxlat, hole_maxlon, x_dim, y_dim))

		# convert the hole waypoints to an array for rotation
		way_node_array = translateNodestoNP(hole_way_nodes, hole_minlat, hole_minlon, hole_maxlat, hole_maxlon, x_dim, y_dim)


		# rotate all of our features, including the green and the hole waypoints
		rotated_fairways = rotateArrayList(image,fairways,angle)
		rotated_tee_boxes = rotateArrayList(image,tee_boxes,angle)
		rotated_water_hazards = rotateArrayList(image,water_hazards,angle)
		rotated_sand_traps = rotateArrayList(image,sand_traps,angle)
		rotated_woods = rotateArrayList(image,woods,angle)
		rotated_trees = rotateArrayList(image,trees,angle)

		rotated_green = rotateArray(image,green_array,angle)
		rotated_green_array = [rotated_green]

		rotated_waypoints = rotateArray(image,way_node_array,angle)


		# we need to filter out any features that don't belong to this hole
		# (example - another hole's fairway that might be close by)
		filtered_fairways = filterArrayList(rotated_waypoints, rotated_fairways, ypp, hole_par, fairway=1, filter_yards=filter_width, small_filter=short_factor, med_filter=med_factor)
		filtered_tee_boxes = filterArrayList(rotated_waypoints, rotated_tee_boxes, ypp, hole_par, tee_box=1, filter_yards=filter_width, small_filter=short_factor, med_filter=med_factor)
		filtered_water_hazards = filterArrayList(rotated_waypoints, rotated_water_hazards, ypp, hole_par, filter_yards=None)
		filtered_sand_traps = filterArrayList(rotated_waypoints, rotated_sand_traps, ypp, hole_par, filter_yards=filter_width, small_filter=short_factor, med_filter=med_factor)
		filtered_woods = filterArrayList(rotated_waypoints, rotated_woods, ypp, hole_par, filter_yards=None)
		filtered_trees = filterArrayList(rotated_waypoints, rotated_trees, ypp, hole_par, filter_yards=25)


		# create a new, rotated base image to work with
		rotated_image, ymin, xmin, ymax, xmax = getNewImage(image,angle,colors["rough"])


		# we need to adjust all our rotated features
		final_fairways, fw_minx, fw_miny, fw_maxx, fw_maxy = adjustRotatedFeatures(filtered_fairways, ymin, xmin)
		final_tee_boxes, tb_minx, tb_miny, tb_maxx, tb_maxy = adjustRotatedFeatures(filtered_tee_boxes, ymin, xmin)
		final_water_hazards, n1, n2, n3, n4 = adjustRotatedFeatures(filtered_water_hazards, ymin, xmin)
		final_woods, n1, n2, n3, n4 = adjustRotatedFeatures(filtered_woods, ymin, xmin)
		final_trees, n1, n2, n3, n4 = adjustRotatedFeatures(filtered_trees, ymin, xmin)


		final_green_array, g_minx, g_miny, g_maxx, g_maxy = adjustRotatedFeatures(rotated_green_array, ymin, xmin)

		final_sand_traps, st_minx, st_miny, st_maxx, st_maxy = adjustRotatedFeatures(filtered_sand_traps, ymin, xmin)

		adjusted_hole_array, n1, n2, n3, n4 = adjustRotatedFeatures([rotated_waypoints], ymin, xmin)

		# finally, we can draw all of the features on our image (with specific colors for each)

		drawFeatures(rotated_image, final_fairways, colors["fairways"])
		drawFeatures(rotated_image, final_tee_boxes, colors["tee boxes"])
		drawFeatures(rotated_image, final_water_hazards, colors["water"])
		drawFeatures(rotated_image, final_woods, colors["woods"])
		drawFeatures(rotated_image, final_green_array, colors["greens"])

		# drawing the sand traps and trees last so they aren't overlapped by fairways, etc.
		drawFeatures(rotated_image, final_sand_traps, colors["sand"])
		drawTrees(rotated_image, final_trees, colors["trees"])


		# now we need to pad or crop the image to get a consistent aspect ratio
		# future TODO: clean this all up into functions, see about making aspect ratio adjustable
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

		# cv2.rectangle(rotated_image, start, end, (0,0,255), 2)


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


		# bb_xmin, bb_ymin, bb_xmax, bb_ymax = createHoleBoundingBox(rotated_waypoints, ypp)


		# adjusting the font size to vary based on how tall the image is in pixels
		# this way, the lettering will look consistent across holes, even if one is
		# 500 yards and one is 100 yards (this used to be a problem)

		text_size = 1.5/3000*eventual_height
		text_size = round(text_size,2)


		# for a par 3, all we need to do is give distances to the center of the green from the tee box
		if hole_par == 3:

			drawGreenDistancesMin(rotated_image, adjusted_hole_array, final_tee_boxes, ypp, text_size, colors["text"], par_3_tees=1)

		# for longer holes, there's more to do:
		else:

			# draw the carry distance to all the sand traps and water hazards
			right_carries, left_carries = drawCarryDistances(rotated_image, adjusted_hole_array, final_tee_boxes, final_sand_traps, ypp, text_size, colors["text"])
			add_r, add_l = drawCarryDistances(rotated_image, adjusted_hole_array, final_tee_boxes, final_water_hazards, ypp, text_size, colors["text"])

			right_carries += add_r
			left_carries += add_l

			# if there aren't any sand traps or water hazards, draw something anyway to give the hole some scale
			drawExtraCarries(rotated_image, adjusted_hole_array, final_tee_boxes, right_carries, left_carries, ypp, text_size, colors["text"])

			# now, draw distances to the center of the green from any notable features (like traps or hazards)
			drawGreenDistancesMin(rotated_image, adjusted_hole_array, final_sand_traps, ypp, text_size, colors["text"])
			drawGreenDistancesMin(rotated_image, adjusted_hole_array, final_water_hazards, ypp, text_size, colors["text"])
			drawGreenDistancesMax(rotated_image, adjusted_hole_array, final_fairways, ypp, text_size, colors["text"])
			drawGreenDistancesTree(rotated_image, adjusted_hole_array, final_trees, ypp, text_size, colors["text"])

			# finally, draw arcs on the fairway every 50 yards from the center of the green
			drawGreenDistancesAnyWaypoint(rotated_image, adjusted_hole_array, ypp, 50, text_size, colors["text"])




		# now, we need to do a second round of padding to make the aspect ratio work
		# in case we ran out of room with our earlier efforts

		cropped_image = rotated_image[lower_bound_y:upper_bound_y, lower_bound_x:upper_bound_x]

		height = upper_bound_y - lower_bound_y
		width = upper_bound_x - lower_bound_x

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

		padded_image = cv2.copyMakeBorder(cropped_image,top_y_pad,bottom_y_pad,left_x_pad,right_x_pad, cv2.BORDER_CONSTANT, value=(94, 166, 44))


		# save the image file to the output folder
		cv2.imwrite(("output/" + file_name), padded_image)




		# now, we need to make the green image for this hole
		print('creating green grid')

		try:
			green_list = os.listdir("greens")
		except:
			os.mkdir("greens")
			green_list = []


		# this time, we want to rotate the green (and everythign else) to be aligned front to back
		angle = getMidpointAngle(translateNodestoNP(hole_way_nodes,hole_minlat, hole_minlon, hole_maxlat, hole_maxlon, x_dim, y_dim))


		# again, we need to rotate everything, including the green and hole waypoints
		rotated_fairways = rotateArrayList(image,fairways,angle)
		rotated_tee_boxes = rotateArrayList(image,tee_boxes,angle)
		rotated_water_hazards = rotateArrayList(image,water_hazards,angle)
		rotated_sand_traps = rotateArrayList(image,sand_traps,angle)
		rotated_woods = rotateArrayList(image,woods,angle)

		rotated_green = rotateArray(image,green_array,angle)
		rotated_green_array = [rotated_green]

		way_node_array = translateNodestoNP(hole_way_nodes, hole_minlat, hole_minlon, hole_maxlat, hole_maxlon, x_dim, y_dim)
		rotated_waypoints = rotateArray(image,way_node_array,angle)


		# and again, we want to filter out anything that isn't close by and relevant
		filtered_fairways = filterArrayList(rotated_waypoints, rotated_fairways, ypp, hole_par, fairway=1, filter_yards=filter_width, small_filter=short_factor, med_filter=med_factor)
		filtered_tee_boxes = filterArrayList(rotated_waypoints, rotated_tee_boxes, ypp, hole_par, tee_box=1, filter_yards=filter_width, small_filter=short_factor, med_filter=med_factor)
		filtered_water_hazards = filterArrayList(rotated_waypoints, rotated_water_hazards, ypp, hole_par, filter_yards=None)
		filtered_sand_traps = filterArrayList(rotated_waypoints, rotated_sand_traps, ypp, hole_par, filter_yards=None)
		filtered_woods = filterArrayList(rotated_waypoints, rotated_woods, ypp, hole_par, filter_yards=None)


		# time to make a new image
		rotated_image, ymin, xmin, ymax, xmax = getNewImage(image,angle,colors["rough"])

		final_fairways, fw_minx, fw_miny, fw_maxx, fw_maxy = adjustRotatedFeatures(filtered_fairways, ymin, xmin)
		final_tee_boxes, tb_minx, tb_miny, tb_maxx, tb_maxy = adjustRotatedFeatures(filtered_tee_boxes, ymin, xmin)
		final_water_hazards, n1, n2, n3, n4 = adjustRotatedFeatures(filtered_water_hazards, ymin, xmin)
		final_woods, n1, n2, n3, n4 = adjustRotatedFeatures(filtered_woods, ymin, xmin)


		final_green_array, g_minx, g_miny, g_maxx, g_maxy = adjustRotatedFeatures(rotated_green_array, ymin, xmin)
		# green_nds = np.int32([rotated_green_array]) # bug in fillPoly - needs explicit cast to 32bit
		# cv2.fillPoly(image, green_nds, (155,242,161))

		final_sand_traps, st_minx, st_miny, st_maxx, st_maxy = adjustRotatedFeatures(filtered_sand_traps, ymin, xmin)

		adjusted_hole_array, n1, n2, n3, n4 = adjustRotatedFeatures([rotated_waypoints], ymin, xmin)


		# we're going to draw everything in black and white this time for a different style
		bw_green_image = rotated_image
		bw_green_image[:] = (255,255,255)

		drawFeatures(bw_green_image, final_fairways, (235, 235, 235))
		drawFeatures(bw_green_image, final_tee_boxes, (195, 195, 195))
		drawFeatures(bw_green_image, final_water_hazards, (180,180,180))
		drawFeatures(bw_green_image, final_woods, (180,180,180))
		drawFeatures(bw_green_image, final_green_array, (255, 255, 255),line=2)
		drawFeatures(bw_green_image, final_sand_traps, (210,210,210))

		# we also want to overlay a 3-yard grid to show how large the green is
		# and to make it easier to figure out carry distances to greenside bunkers
		green_grid = getGreenGrid(bw_green_image, adjusted_hole_array,ypp)

		cv2.imwrite(("greens/" + file_name), green_grid)

	return True
