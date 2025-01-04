# hacker yardage
# see readme.md for instructions on how to map a course in OpenStreetMap


# import all the formulas we need

from hyformulas import *

import os
from datetime import datetime


# Enter bounding box coordinates from OSM here:

latmin = 30.2286     # minimum latitude (south)
lonmin = -97.7114    # minimum longitude (west)
latmax = 30.2448     # maximum latitude (north)
lonmax = -97.7018    # maximum longitude (east)


# do you want to replace existing output files? default is False
# change this to True if you want to overwrite existing files in the output folder

replace_existing = False


# colors for each feature can be customized here

fairway_color = '#85d87e'
tee_box_color = '#85d87e'
green_color = '#a1f29b'
rough_color = '#2ca65e' # this is the overall background color
tree_color = '#1c6b3d'
water_color = '#bafbeb'
sand_color = '#ffeea1'
text_color = '#000000'



# how wide are the holes?
# (objects that are more than this number of yards
# from the center line will be filtered out)

hole_width = 100 # in yards


# do you want to filter more aggressively near the tees?
# (this can help ignore random bunkers, etc.)
# enter a fraction

short_filter = 1.5



# passing colors to a dict for the yardage book script

colors = {"fairways":hexToBGR(fairway_color),"tee boxes":hexToBGR(tee_box_color),
"greens":hexToBGR(green_color),"rough":hexToBGR(rough_color),"trees":hexToBGR(tree_color),
"water":hexToBGR(water_color),"sand":hexToBGR(sand_color),"text":hexToBGR(text_color),
"woods":hexToBGR(tree_color)}


# calculate a medium range filter from the short range filter
# (you could also customize this if you want)

med_filter = (short_filter + 1) / 2


# toggle for whether or not to include individual trees in the yardage book

include_trees = True


# toggle for showing distances in meters instead of yards

in_meters = False


# generate the yardage book

if __name__ == "__main__":
    print('start: ', datetime.now().time())
    book = generateYardageBook(latmin,lonmin,latmax,lonmax,replace_existing,colors,filter_width=hole_width,short_factor=short_filter,med_factor=med_filter,include_trees=include_trees,in_meters=in_meters)
