DOMAIN = "findmy_home"
PLATFORMS = ["device_tracker", "sensor"]

def normalize_channel(channel):
    """Legacy unmarked/Beta installations are development installations."""
    return "stable" if channel=="stable" else "edge"

def entry_title(channel):
    return "Find My Home" if normalize_channel(channel)=="stable" else "Find My Home Edge"
