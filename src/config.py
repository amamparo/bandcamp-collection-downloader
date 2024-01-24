from configparser import ConfigParser

config = ConfigParser()
config.read('config.ini')

tracks_location = config.get('default', 'tracks_location')