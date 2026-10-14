"""Private candidate constraints shared by the episode's geometric planners."""
import math


def bearing_allowed(angle_rad, parameters):
    bearing = math.degrees(angle_rad) % 360.
    minimum = parameters.get("minimum_group_bearing_difference_deg", 60.)
    return all(abs((bearing - previous + 180.) % 360. - 180.) >= minimum - 1e-9
               for previous in parameters.get("excluded_work_area_bearings_deg", []))
