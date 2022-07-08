#!/usr/bin/env python

import config
import argparse
#import argcomplete
import plib
from time import strptime
import datetime
#PYTHON_ARGCOMPLETE_OK = True



parser = argparse.ArgumentParser()
parser.add_argument("-l", "--log", dest="accessLog", help="apache access log to parse")
parser.add_argument("-d", "--db", dest="DB", default=config.db, help="path to sqlite3 db, default is {} in current directory".format(config.db))

parser.add_argument("-s", "--start", dest="startDate", help="start date and time, format yyyy:m:d:h:m:s")
parser.add_argument("-e", "--end", dest="endDate", help="end date and time, format yyyy:m:d:h:m:s")

#argcomplete.autocomplete(parser)
args = parser.parse_args()

app = plib.DB(args.DB, config.schema)

if args.accessLog:
    app.process(log=args.accessLog, url_skip_list=config.url_skip_list)
else:
    app.group_by_code(startDate=args.startDate, endDate=args.endDate)
