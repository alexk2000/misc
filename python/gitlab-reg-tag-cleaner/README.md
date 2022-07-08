[reg_tag_cleaner.py](reg_tag_cleaner.py) - delete Gitlab registry repository tags in bulk. It requires yaml configuration file with definition projects/groups and tags to delete, example: [reg_tag_cleaner.yml](reg_tag_cleaner.yml).
Usage:
```
# reg_tag_cleaner.py -c reg_tag_cleaner.yml
```

Requirements:
1. Python 3
2. Python's module from [requirements.txt](requirements.txt)
```
pip install -r requirements.txt
```

Links:
1. [Container Registry API][1]
2. [Python Gitlab module][2]

[1]: https://docs.gitlab.com/ce/api/container_registry.html
[2]: https://python-gitlab.readthedocs.io/en/stable/