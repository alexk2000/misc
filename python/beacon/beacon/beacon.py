#!/usr/bin/python3


import urllib.request
import xml.etree.ElementTree as ET
import re
import argparse
import time
import sys

BEACON_START_TIME = 1378395540
BEACON_URL = "https://beacon.nist.gov/rest/record/"
BEACON_URL_LAST = "https://beacon.nist.gov/rest/record/last"

class Beacon():
	
	output_value = ""	
	output_value_set = set()
	cur_timestamp = None	

	def __init__(self):
		
		self.cur_timestamp = int(time.time())

	def addValue(self, value):

		self.output_value += value
		for symbol in list(value):
			self.output_value_set.add(symbol)

	def printSum(self):
		
		for symbol in self.output_value_set:
			print('{0},{1}'.format(symbol,self.output_value.count(symbol)))

	def calcSeconds(self, d_string):

		date_dict={'month':0, 'day':0, 'hour':0, 'minute':0}

		result = re.search(r'(?P<month>\d+)\s+month', d_string)
		if result:
		        date_dict['month']=int(result.group('month'))

		result = re.search(r'(?P<day>\d+)\s+day', d_string)
		if result:
		        date_dict['day']=int(result.group('day'))

		result = re.search(r'(?P<hour>\d+)\s+hour', d_string)
		if result:
		        date_dict['hour']=int(result.group('hour'))

		result = re.search(r'(?P<minute>\d+)\s+minute', d_string)
		if result:
		        date_dict['minute']=int(result.group('minute'))

		return date_dict['month']*2592000+date_dict['day']*86400+date_dict['hour']*3600+date_dict['minute']*60

	def saveRemoteValue(self, timestamp=None):

		full_url = BEACON_URL + str(timestamp)

		if timestamp == None:
			full_url = BEACON_URL_LAST

		xml = urllib.request.urlopen(full_url).read()
		root = ET.fromstring(xml)
		value = root.find('{http://beacon.nist.gov/record/0.1/}outputValue').text
		self.addValue(value)

	def logger(self, message):
		print(message)

	def main(self, from_date=None, to_date=None):
		
		if from_date == None and to_date == None:
			self.saveRemoteValue()
		else:
			from_timestamp = self.calcSeconds(from_date)
			to_timestamp = self.calcSeconds(to_date)
			
			if from_timestamp < to_timestamp:
				self.logger("Error: --from is earlier than --to")
				sys.exit(1)

			if (self.cur_timestamp - from_timestamp) < BEACON_START_TIME:
				self.logger("Error: --from is earlier than the start of the beacon")
				sys.exit(1)

			if from_timestamp == 0 or to_timestamp == 0:
				self.logger("Error: --from or --to not valid")
				sys.exit(1)
				

			i = self.cur_timestamp - from_timestamp
			i_stop = self.cur_timestamp - to_timestamp
			while i <= i_stop:
				self.saveRemoteValue(i)
				i+=60

		self.printSum()



if __name__ == "__main__":

	parser = argparse.ArgumentParser()
	parser.add_argument("--from", dest="from_date")
	parser.add_argument("--to", dest="to_date")
	args = parser.parse_args()

	app = Beacon()

	if args.from_date and args.to_date:

		app.main(args.from_date,args.to_date)

	elif args.from_date == None and args.to_date == None:

		app.main()

	else:
		print("none or both --from and --to should be specified")
 
