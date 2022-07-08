import re
from time import strptime
import datetime
import sqlite3
import urllib
import hashlib
import config
import argparse
import os
import sys

class DB(object):

    def __init__(self, path, schema):

        self.path = path
        self.schema = schema

        if not os.path.isfile(self.path):
            self.create()
        elif not os.access(path, os.W_OK):
            print("no write access to {}".format(self.path))
            sys.exit(1)
 

    def create(self):

        conn = sqlite3.connect(self.path)
        c = conn.cursor()
        with open(self.schema) as f:
            for q in f:
                c.execute(q) 
                conn.commit()
            conn.close() 

    def process(self, log, url_skip_list):

        regex = '([(\d\.)]+) (.*?) (.*?) \[(.*?)\] "(.*?)" (\d+) (.*?) (.*?) (.*?) (\d+)'
        added = 0
        skipped = 0

        conn = sqlite3.connect(self.path)
        c = conn.cursor()

        with open(log) as f:
            for line_str in f:

                try:
                    line_tuple = re.match(regex, line_str).groups()
                except Exception as e:
                    print e
                    print line_str
                    break

                ip = line_tuple[0]
                dt = line_tuple[3]
                url = urllib.quote(line_tuple[4], safe=' /?=&')

                if url in url_skip_list:
                    continue

                code = int(line_tuple[5])
                try:
                    res_bytes = int(line_tuple[6])
                except:
                    res_bytes = 0

                response = int(line_tuple[9])

                date_time = strptime(dt[:-6], "%d/%b/%Y:%H:%M:%S")
                time_info = list(date_time[:6]) + [ 0, None ]
                timestamp = datetime.datetime(*time_info).strftime("%s")
                res_hash = hashlib.md5(line_str).hexdigest()


                try:
                    q = "INSERT INTO log (ip,date,url,code,bytes,response,hash) VALUES ('{ip}',{date},'{url}',{code},{res_bytes},{response},'{res_hash}')".format(ip=ip,date=timestamp,url=url,code=code,res_bytes=res_bytes,response=response, res_hash=res_hash)
                    c.execute(q)
                    conn.commit()
                except sqlite3.IntegrityError:
                    skipped += 1
                else:
                    added += 1


            print("added {}, skipped {}".format(added, skipped))
            conn.close()

    def get_ts(self, time_str):

        dtime = strptime(time_str, "%Y:%m:%d:%H:%M:%S")
        tinfo = list(dtime[:6]) + [ 0, None ]
        return datetime.datetime(*tinfo).strftime("%s")

    def group_by_code(self, startDate=None, endDate=None):

        q_template = "select code, count(*) from log {where} group by code order by code"
        where = ""
        if startDate is not None and endDate is not None:
            s_ts = self.get_ts(startDate)
            e_ts = self.get_ts(endDate)
            if s_ts > e_ts:
                print("error: start date is after end date")
                sys.exit(2)
            where = "where date >= {} and date <= {}".format(s_ts, e_ts)
        elif startDate is not None:
            s_ts = self.get_ts(startDate)
            where = "where date >= {}".format(s_ts)
        elif endDate is not None:
            e_ts = int(datetime.datetime.now().strftime("%s"))
            where = "where date <= {}".format(e_ts)

        q = q_template.format(where=where)
    
        conn = sqlite3.connect(self.path)
        c = conn.cursor()
        sum = 0
        print "code request(s)"
        for row in c.execute(q):     
            print row[0], row[1]
            sum += row[1]
        print "\ntotal requests: ", sum
