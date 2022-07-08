[src/consumer-groups-sync.py](src/consumer-groups-sync.py) - sync consumer groups from source Kafka cluster to target Kafka cluster, part of disaster recovery solution for Kafka, POC for MirrorMaker 2. 
Configuration example [configs/aws-stage.yaml](configs/aws-stage.yaml):
```
source:
  bootstrap_servers: 10.79.140.21:9092
destination:
  bootstrap_servers: 10.79.140.22:9092

interval: 60
log_level: INFO
health_check_port: 80
```

Usage:
```
# consumer-groups-sync.py -c configs/aws-stage.yaml
```

Requirements:
1. Python 3
2. Python's module from [src/requirements.txt](src/requirements.txt)
```
pip install -r requirements.txt
```

Links:
1. [Python Kafka module][1]

TODO:
1. Handling the case when consumer already exists but number of partitions differ from primary. This is case when new topics started processing by existing consumer group on primary.
2. Handling case when consumer exists but some partitions don't exist on backup Kafka (should be very rare case).

[1]: https://kafka-python.readthedocs.io/