[src/mm2-monitor.py](src/mm2-monitor.py) - monitor mirroring status from source to tagret Kafka clusters, part of disaster recovery solution for Kafka, POC for MirrorMaker 2.
It exports prometheus metrics for alerting and Grafana dashboards, the most important metrics:

**m2_monitor_number_of_period_diff_topics** - number of topics which have different number of messages on source/tagret clusters for some period in the past. This indicates problem missing/duplicate messages on target cluster. It should be 0 if it's OK.
**mm2_monitor_number_of_lag_topics** - number of topics with lag. Lag threshold configured by `lag_threshold` parameter in configuration file. It should be 0 if no lag topics.

Configuration example [configs/mm2-monitor-aws-stage.yaml](configs/mm2-monitor-aws-stage.yaml):
```
source:
  name:  aws stage
  bservers: 10.79.140.21:9092
target:
  name: mvp c2
  bservers: kafka-c2-n1.com:9092,kafka-c2-n2.com:9092,kafka-c2-n3.com:9092

topics: ALL

interval: 30
log_level: INFO
web_port: 80
lag_threshold: 1000

# Time range to calculate offset diff (seconds)
# monitor_period: 21600
monitor_period: 3600

# "monitor_period" starts "monitor_shift" seconds ago
monitor_shift: 60
```

Usage:
```
# src/mm2-monitor.py -c configs/mm2-monitor-aws-stage.yaml
```

Prometheus metrics:
```
TOPICS = Gauge("mm2_monitor_topics", "Number of topics from source under monitoring", ["mm_instance"])
ITER_DURATION = Gauge("mm2_monitor_iter_duration", "Time spent for one loop iteration (seconds)", ["mm_instance"])
ITER_START = Gauge("mm2_monitor_iter_start", "Time last loop iteration started (timestamp)", ["mm_instance"])
ITER_FAILED = Counter("mm2_monitor_iter_failed_total", "Number of failed loop iterations", ["mm_instance"])
ITER_LAST_SUCCESS = Gauge("mm2_monitor_iter_last_success", "Time of last successful loop iteration (timestamp)", ["mm_instance"])
ITER_LAST_STATUS = Gauge("mm2_monitor_iter_last_status", "Status of last loop iteration (0 - failed, 1 success)", ["mm_instance"])
NUMBER_OF_PERIOD_DIFF_TOPICS = Gauge("mm2_monitor_number_of_period_diff_topics", 
    "Number of topics with different number of messages for particular period of time in the past", ["mm_instance"])
NUMBER_OF_LAG_TOPICS = Gauge("mm2_monitor_number_of_lag_topics", 
    "Number of topics with lag more the lag_threshold parameter in config", ["mm_instance"])
```

Requirements:
1. Python 3
2. Python's module from [src/requirements.txt](src/requirements.txt)
```
pip install -r requirements.txt
```

Links:
1. [Python Kafka module][1]

[1]: https://kafka-python.readthedocs.io/