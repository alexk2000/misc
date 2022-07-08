#!/usr/bin/env python3

import hashlib
import logging
import os
import sys
from time import sleep
import datetime
import argparse
import magic
from elasticsearch import Elasticsearch
from elasticsearch.helpers import scan

ELASTIC_HOSTS = ['127.0.0.1',]
INDEX = 'mydata'
TYPE = 'mydocs'

MAP = {
    "settings": {
    "analysis": {
      "filter": {
        "ru_stop": {
          "type": "stop",
          "stopwords": "_russian_"
        },
        "ru_stemmer": {
          "type": "stemmer",
          "language": "russian"
        },
        "en_stop": {
          "type": "stop",
          "stopwords": "_english_"
        },
        "en_stemmer": {
          "type": "stemmer",
          "language": "english"
        }
      },
      "analyzer": {
        "default": {
          "char_filter": [
            "html_strip"
          ],
          "tokenizer": "standard",
          "filter": [
            "lowercase",
            "ru_stop",
            "ru_stemmer",
            "en_stop",
            "en_stemmer"
          ]
        }
      }
    }
  },

    "mappings": {
        "mydocs": {

            "properties": {
                "path": {
                    "type": "keyword"
                },
                "md5": {
                    "type": "keyword"
                },
                "mdate": {
                    "type": "date"
                }
            }
        }
        }
}


class ElasticData(object):

    def __init__(self, elastic_hosts, index, type, map):
        self.elastic_hosts = elastic_hosts
        self.index = index
        self.type = type
        self.map = map
        self.connected = False
        self.es = Elasticsearch(self.elastic_hosts)
        self.info = {}

    def connect(self):
        self.connected = self.es.ping()
        # create index if connection is ok
        if self.connected:
            if not self.es.indices.exists(index=self.index):
                self.es.indices.create(index=self.index, body=self.map)

    def update_info(self, wait=1):
        sleep(wait)
        self.info = self.es.cat.indices(index=self.index, format='json')[0]
        return self.info

    def is_connected(self):
        return self.connected

    def search(self, q=None):
        query = q
        if q is None:
            query = ' '.join(sys.argv[1:])

        body = {
            "_source": ['path', ],
            'query':
                {'match':
                     {'content': query
                      }
                 },
            "highlight": {
                "fields": {
                    "content": {}
                }
            }
        }

        res = self.es.search(index=INDEX, body=body)

        for item in res['hits']['hits']:
            print(item['_score'], item['_source']['path'])
            for hl in item['highlight']['content']:
                print('<<<\n', hl, '\n>>>')
            print('-' * 50)

    def import_docs(self, paths=None):

        if paths is None:
            print('warning: nothing to index')
            sys.exit(1)
        if not self.connected:
            sys.exit(1)

        if type(paths) is str:
            paths = [paths]

        import_status = {
            'skipped': 0,
            'added': 0,
            'updated': 0,
            'not_found': 0
        }

        for path in paths:
            if os.path.isfile(path):
                print(path)
                ret = self.file2index(file=path)
                import_status[ret] += 1
            else:
                for root, dirs, files in os.walk(path):
                    for file in files:
                        file_path = os.path.join(root, file)
                        # print(file_path)
                        if magic.from_file(file_path, mime=True).startswith('text/'):
                            print(file_path)
                            ret = self.file2index(file=file_path)
                            import_status[ret] += 1

        print('added: ', import_status['added'], ' updated: ', import_status['updated'], 'skipped: ',
              import_status['skipped'])

    def file2index(self, file=None, skip=True):
        if not file or not os.path.isfile(file):
            return 'not_found'

        content = open(file, 'rb').read()
        file_md5 = hashlib.md5(content).hexdigest()
        if skip:
            res = self.es.search(index=INDEX, body={'query': {'term': {'md5': file_md5}}})
            if res['hits']['hits'] != []:
                # content of file already in index, skip it
                return 'skipped'

        doc = {
            'path': file,
            'content': content.decode('utf-8', errors='ignore'),
            'md5': file_md5,
            'mdate': os.path.getmtime(file)
        }

        res1 = self.es.search(index=INDEX, body={'query': {'term': {'path': doc['path']}}})
        if not res1['hits']['hits']:
            self.es.index(index=INDEX, doc_type=TYPE, body=doc)
            return 'added'
        else:
            # if md5 not changed for the file - skip indexing
            if not skip:
                query = {
                    "query": {
                        "bool": {
                            "must": {"match_all": {}},
                            "filter": [
                                {
                                    "term": {
                                        "md5": file_md5
                                    }
                                },
                                {
                                    "term": {
                                        "path": file
                                    }
                                }
                            ]
                        }
                    }
                }
                res2 = self.es.search(index=INDEX, body=query)
                if res2['hits']['hits'] != []:
                    # print(file, ' skipped')
                    return 'skipped'
                    # continue

            # update document
            self.es.index(index=INDEX, id=res1['hits']['hits'][0]['_id'], doc_type=TYPE, body=doc)
            print(file, ' updated')
            return 'updated'

    # update index for each file already in index
    def update(self):

        update_status = {
            'skipped': 0,
            'added': 0,
            'updated': 0,
            'not_found': 0
        }

        for file in self.list(fields=['path']):
            ret = self.file2index(file=file['_source']['path'], skip=False)
            # print(file['_source']['path'])
            update_status[ret] += 1

        print('added: ', update_status['added'], ' updated: ', update_status['updated'], 'skipped: ',
              update_status['skipped'], 'not found: ', update_status['not_found'])

    def list(self, fields=["path", "md5", "mdate"]):
        return scan(self.es,
                    query={"query": {"match_all": {}}, "_source": ['path'], "_source": fields},
                    index=INDEX,
                    doc_type=TYPE
                    )

    # remove files from index which already removed from fs
    def cleanup(self):
        for file in self.list(fields=['path']):
            if not os.path.isfile(file['_source']['path']):
                print('deleted from index', file['_source']['path'])
                self.es.delete(index=INDEX, doc_type=TYPE, id=file['_id'])

    def find_by_path(self, path=None):
        query = {
            "query": {
                "bool": {
                    "must": {"match_all": {}},
                    "filter": {"term": {"path": path}}
                }
            }
        }

        res = self.es.search(index=INDEX, doc_type=TYPE, body=query)
        if res['hits']['hits']:
            return res['hits']['hits'][0]
        else:
            return None

    def delete_by_path(self, path=None):
        query = {
            "query": {
                "regexp": {
                    "path": {
                        "value": "{}.*".format(path)
                    }
                }
            }
        }

        return self.es.delete_by_query(index=INDEX, doc_type=TYPE, body=query)


if __name__ == '__main__':
    # to avoid elastic connection errors printed
    el_logger = logging.getLogger('elasticsearch')
    el_logger.setLevel(logging.ERROR)

    docs = ElasticData(elastic_hosts=ELASTIC_HOSTS, index=INDEX, type=TYPE, map=MAP)
    docs.connect()
    if not docs.is_connected():
        print('error: can\'t establish connection to Elastic')
        sys.exit(1)

    parser = argparse.ArgumentParser(description='search in ElasticSearch')

    group1 = parser.add_mutually_exclusive_group()
    group1.add_argument("-a", "--add", dest="add", nargs='+', help="add files to index")
    group1.add_argument("-d", "--delete", dest="delete", type=str, help="delete files from index")
    group1.add_argument("-l", "--list", dest="list", action="store_true", help="show all files in index")
    group1.add_argument("-s", "--search", dest="search", type=str, help="search in index")
    group1.add_argument("-g", "--get", dest="get", type=str, help="get document by path")
    group1.add_argument("-u", "--update", dest="update", action="store_true",
                        help="update index for each file already in index")
    group1.add_argument("-c", "--cleanup", dest="cleanup", action="store_true",
                        help="remove files from index which already removed from fs")
    args = parser.parse_args()

    if len(sys.argv) == 1:
        info = docs.update_info()
        print('docs count: {}, store size: {}'.format(info['docs.count'], info['store.size']))

    if args.list:
        all_docs = docs.list(fields=['path', 'mdate'])
        for doc in all_docs:
            date = datetime.datetime.fromtimestamp(int(doc['_source']['mdate'])).strftime('%Y-%m-%d %H:%M:%S')
            print('{} ({})'.format(doc['_source']['path'], date))
        sys.exit(0)

    if args.search:
        docs.search(args.search)
        sys.exit(0)

    if args.update:
        docs.update()
        sys.exit(0)

    if args.cleanup:
        docs.cleanup()
        sys.exit(0)

    if args.add:
        docs.import_docs(paths=args.add)
        sys.exit(0)

    if args.delete:
        print('deleted: ', docs.delete_by_path(path=args.delete)['deleted'])
        sys.exit(0)

    if args.get:
        doc = docs.find_by_path(path=args.get)
        if doc:
            print(doc['_source']['content'])
        else:
            print('not found')
        sys.exit(0)

    sys.exit(0)
