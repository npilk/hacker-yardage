# hacker yardage
# see readme.md for instructions on how to map a course in OpenStreetMap


# import all the formulas we need

from hyformulas import *

import os
from datetime import datetime


# Enter bounding box coordinates from OSM here:

latmin = 30.2286     # minimum latitude (south)
lonmin = -97.7114   # minimum longitude (west)
latmax = 30.2448     # maximum latitude (north)
lonmax = -97.7018   # maximum longitude (east)


# do you want to replace existing output files? default is False
# change this to True if you want to overwrite existing files in the output folder

replace_existing = False


# colors for each feature can be customized here

fairway_color = '#34E884'
tee_box_color = '#34E884'
green_color = '#5AFCA3'
rough_color = '#18BB3E' # this is the overall background color
tree_color = '#178200'
water_color = '#15BCF1'
sand_color = '#FFD435'
text_color = '#000000'
topo_color = '#8B5E3C' 
green_arrow_color = '#000000'  # black arrows on green close-ups



# how wide are the holes?
# (objects that are more than this number of yards
# from the center line will be filtered out)

hole_width = 50 # in yards


# do you want to filter more aggressively near the tees?
# (this can help ignore random bunkers, etc.)
# enter a fraction

short_filter = 0.8



# passing colors to a dict for the yardage book script

colors = {"fairways":hexToBGR(fairway_color),"tee boxes":hexToBGR(tee_box_color),
"greens":hexToBGR(green_color),"rough":hexToBGR(rough_color),"trees":hexToBGR(tree_color),
"water":hexToBGR(water_color),"sand":hexToBGR(sand_color),"text":hexToBGR(text_color),
"woods":hexToBGR(tree_color),"topo":hexToBGR(topo_color),"green_arrow":hexToBGR(green_arrow_color)}


# calculate a medium range filter from the short range filter
# (you could also customize this if you want)

med_filter = (short_filter + 1) / 2


# toggle for whether or not to include individual trees in the yardage book

include_trees = True


# toggle for showing distances in meters instead of yards

in_meters = False


# toggle for topography/elevation contour lines
# requires py3dep (pip install py3dep) - data is from free USGS 3DEP, no API key needed
# note: 3DEP data covers the US only; contours will be silently skipped for international courses

include_topo = True

# contour interval in meters (2.0m ≈ 6.5 ft is a good default for golf courses)

topo_interval = 1.0

# toggle for index contour labels (every Nth contour drawn thicker with elevation label)

include_topo_labels = True

# how often to draw an index contour (e.g. 5 = every 5th contour level gets a label)

topo_index_every = 5


# contour interval for green close-up images (finer than the hole image to show subtle breaks)
# 0.3m ≈ 1ft is a good default for reading green contours

green_topo_interval = 0.1

# visualization style for green close-up topography
# options:
#   'gradient' — colour heatmap (blue=low, red=high) blended at 40% opacity
#   'arrows'   — grid of arrows pointing downhill, longer = steeper slope
#   'both'     — gradient heatmap + arrows overlaid
#   'contours' — thin contour lines at green_topo_interval (same style as hole image)

green_topo_style = 'both'

# total elevation range (metres) that maps to the full colour / arrow scale.
# a green with less relief than this will only use part of the scale, so flat and
# steep greens are visually comparable rather than always stretching to full range.
# 5m is generous for golf greens; reduce to 2-3m if your course is generally flat.

green_topo_scale_m = 5.0


# generate the yardage book

if __name__ == "__main__":
    print('start: ', datetime.now().time())
    book = generateYardageBook(latmin,lonmin,latmax,lonmax,replace_existing,colors,filter_width=hole_width,short_factor=short_filter,med_factor=med_filter,include_trees=include_trees,in_meters=in_meters,include_topo=include_topo,topo_interval=topo_interval,include_topo_labels=include_topo_labels,topo_index_every=topo_index_every,green_topo_interval=green_topo_interval,green_topo_style=green_topo_style,green_topo_scale_m=green_topo_scale_m)
