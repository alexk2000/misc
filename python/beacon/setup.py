#!/usr/bin/env python

from setuptools import setup, find_packages

setup(name='beacon',
      version='1.0.2',
      scripts=['bin/summarize-beacon'],
      packages=find_packages()
      )
