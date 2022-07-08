# compare-packages
Python script to compare package versions on 2 linux servers.
Minimum python 3.5 version required.

-h - to get help with acceptable variables.

File /etc/lsb-release is used to determine .deb based OS.
If the file exists, the corresponding .deb commands will be used. If the file does not exist, the corresponding .rpm commands will be used.
