#Introduction#

DevOps is about managing production environments at large scale -- deep
stacks, hundreds of servers, highly distributed systems. Such systems
tend towards decay and chaos. It's just a fact of the job: Something is
probably going wrong at any given moment in a large enough installation.

This exercise tests your ability to distinguish the signal from the
noise. First, you will organize a random input into meaningful output.
Second, you'll report on that output using software.

#Prerequisites#

Your answer will be written in python, and must meet the
following requirements:

 * The python component should run on python v3.2.3+, unless you import
   a public module that requires v2.7.x. If you do so, you'll be expected
   to justify that decision. Python programs that rely on pre-2.7 syntax
   will not be accepted.

 * It must run on Ubuntu 12.04 (aka "precise"), and shouldn't require
   any unusual binaries or new software to run.

If you're a vagrant user, you can exactly replicate the box on which
we'll test your answer by using this [base
box](https://cloud-images.ubuntu.com/vagrant/precise/current/precise-server-cloudimg-amd64-vagrant-disk1.box)
and then running `apt-get install -y python3`.

#The Randomness Beacon#

The National Institute of Standards and Technology broadcasts a signed,
timestamped random bit sequence once a minute, every minute, and has
since Unix epoch time 1378395540 (09/05/2013 11:39 a.m.). It's called
the [_Randomness Beacon_](http://www.nist.gov/itl/csd/ct/nist_beacon.cfm), and you're
going to analyze it.

##Goal 1: Sampling Chaos##

The Randomness Beacon publishes a [RESTful
API](https://beacon.nist.gov/home), through which you can retrieve any
given minute's beacon value as 128 hexadecimal characters, as well as a
variety of other authentication data. Your first goal is to summarize
the beacon's emissions over arbitrary amounts of time.

This repository contains the basic structure of a python module. Note
that the module set-up has been accomplished for you, and `python
setup.py install`, issued inside a clone of this repository, should
work. Within the `bin/` directory, you'll find a `summarize-beacon`
stub.

*Rewrite the summarize-beacon stub to be a full-fledged python script,
relying, if you'd like, on any classes or functions you'd like to add to
the (currently empty) beacon library.*

That script should have the following characteristics:

1. Without additional arguments, it should retrieve the most recent
   event from the randomness beacon, and count the number of characters
   in the OutputValue the beacon returns. It should then print that output
   to standard out in comma-delimited format.

   For example, if the randomness beacon returned the string "01AF04F" for
   its OutputValue, your script should print:

        0,2
        1,1
        4,1
        A,1
        F,2

   The first value of any given line is a character. The second value is
   the number of times that value occurred in the OutputValue string.

2. When given optional `--from` and `--to` arguments, the script should
   output the character count over a span of beacon values using
   *relative time*. For example, if we provided the script the following
   arguments:

        $ summarize-beacon --from "3 months 1 day 1 hour ago" --to "1 month 1 hour ago"

   the script should parse the strings "3 months 1 day 1 hour ago" and "1
   month 1 hour ago" into a time format the beacon's API can understand,
   and print the summed character count of all beacon values between those
   two times. The script should understand "month(s)," "day(s)", "hour(s)",
   and "minutes(s)", and should handle any combination of those values.

   Note that output is summed. For example, if the user enters `--from` and
   `--to` values that yield two beacon values, "B423AF" and "7352BA", the
   script should output the summed character counts of both values:

        2,2
        3,2
        4,1
        5,1
        7,1
        A,2
        B,2
        F,1

3. The script should error in a friendly way if a user enters a `--from`
   or `--to` time that predates the start of the beacon, Unix epoch time
   1378395540.

*A Quick Note:* Don't feel obligated to solve this problem using just
the python standard library. Part of engineering is knowing when to
include 3rd party modules. In particular, if you know a good alternative
to `urllib` or `xml.etree`, feel free to include it.

#Submitting Answers#

Submit solutions to this problem via Github pull requests.
