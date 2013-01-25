#!/usr/bin/env python
# -*- coding:utf-8 -*-

import requests

from flask import Flask, json
from flask_sqlalchemy import SQLAlchemy

import config

import os
import re
import datetime

app = Flask(__name__, instance_relative_config=True)
path_to_db = os.path.expanduser(config.db_path)
app.config['SQLALCHEMY_DATABASE_URI'] = "sqlite:///" + path_to_db
db = SQLAlchemy(app)


class Agency(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(256))
    url = db.Column(db.String(256))
    timezone = db.Column(db.String(256))

    def __init__(self, id, name, url, timezone):
        self.id = id
        self.name = name
        self.url = url
        self.timezone = timezone

    def __repr__(self):
        rep = "<Agency> %s, [%i]" % (self.name, self.id)
        return rep.encode("utf-8")


class DB_Stop(db.Model):
    ''' The represenation of a stop in the database '''
    id = db.Column(db.Integer, primary_key=True)
    last_run = db.Column(db.DateTime)
    name = db.Column(db.String(200), index=True)
    matches = db.Column(db.Float)
    lat = db.Column(db.Float)
    lon = db.Column(db.Float)

    def __init__(self, vbb_id, name, lat, lon, matches):
        self.id = vbb_id
        self.name = name
        self.lat = lat
        self.lon = lon
        self.matches = int(matches)
        self.last_run = datetime.datetime.now().replace(microsecond=0)

    def to_vbb_syntax(self):
        ''' Return a line that looks as if it comes from the routes.txt '''
        return '%i,,"%s",,%f,%f' % (self.id, self.name, self.lat, self.lon)

    def __repr__(self):
        return '<Stop %r>' % self.name

    def to_dict(self):
        return {
                "lat": self.lat,
                "lon": self.lon,
                "name": self.name,
                "matches": self.matches
               }


class VBB_Stop():
    ''' Takes a line from the stops.txt and returns a VBB_Stop object '''
    def __init__(self, line_from_stops_txt):
        #since csvreader doesnt understand unicode we'll just use good old regex
        pattern = re.compile('(\d*),,"(.*)",,(\d*\.\d*),(\d*\.\d*)')
        fields = re.findall(pattern, line_from_stops_txt)[0]
        self.stop_id = fields[0]
        self.name = fields[1]
        self.lat = float(fields[2])
        self.lon = float(fields[3])

    def is_in_osm(self):
        ''' Call Overpass to see if there is an object with the given name
            close to the cordinates given '''
        north = self.lat - 0.002
        east = self.lon - 0.002
        south = self.lat + 0.002
        west = self.lon + 0.002
        short_name = self.name
        if "(" in short_name:  # remove the (Berlin) from the line
            short_name = short_name.split(" (")[0]

        # if we have something like StreetA/StreetB overpass is not able to find this
        # we can just look for StreetB or StreetA though since we are limiting the search on a small ara
        if "/" in short_name:
            short_name = short_name.replace("/", "|")

        # In Osm "Spandau Bhf" is just "Spandau" so we drop the "Bhf"
        if "Bhf" in short_name:
            short_name = short_name.replace(" Bhf", "")

        if "Str." in short_name:
            parts = short_name.split("Str.")
            short_name = short_name + "|" + parts[0] + u"Straße"

        if "S+U" in short_name:
            # Stops Like "S+U Wedding" are in OSM as "S Wedding" and "U Wedding"
            # So we split it up and check for both
            stop_name = short_name[3:]  # Take the part without "S+U"
            s_station = "S" + stop_name
            u_station = "U" + stop_name
            short_name = s_station + "|" + u_station
        print short_name
        payload = {"data":'[output:json];node(%f, %f, %f, %f)["name"~"%s"];out skel;' % (north, east, south, west, short_name)}
        r = requests.get("http://overpass-api.de/api/interpreter", params=payload)
        this_json = json.loads(r.text)
        stations = this_json.get("elements")
        return len(stations)


class Bvg_line():
    ''' Takes a line from routes.txt and return a Bvg_line object '''
    def __init__(self, line_from_routes_txt):
        fields = line_from_routes_txt.split(",")
        self.bvg_id = fields[0]
        self.agency = fields[1][:3]
        self.line_number = fields[2]
        #operator
        if self.agency.startswith("BV"):
            self.operator = "BVG"
        elif self.agency.startswith("DB"):
            self.operator = "DB"
        else:
            self.operator = "other"
        #transit_type (Bus/tram/etc.)
        if self.agency.endswith("T"):
            self.transit_type = "Tram"
        elif self.agency.endswith("S"):
            self.transit_type = "S-Bahn"
        elif self.agency.endswith("B"):
            self.transit_type = "Bus"
        elif self.agency.endswith("F"):
            self.transit_type = "Faehre"
        else:
            self.transit_type = self.agency

    def is_in_osm(self):
        payload = {"data":'[output:json];relation["network"="VBB"]["ref"="%s"];out;'% self.line_number}
        r = requests.get("http://overpass-api.de/api/interpreter", params=payload)
        if "tags" in r.text:
            return r.text.split('"name": "')[1].split('"')[0]
        else:
            return False


class DB_Train():
    id = db.Column(db.Integer, primary_key=True)
    agency = db.Column(db.String(200))
    operator = db.Column(db.String(200))
    transit_type = db.Column(db.String(200))
    in_osm = db.Column(db.Boolean)

    def __init__(self, vbb_id, agency, operator, transit_type, in_osm):
        self.id = id
        self.agency = agency
        self.operator = operator
        self.transit_type = transit_type
        self.in_osm = in_osm