#!/bin/sh

case "$1/$2" in
  pre/*)
        /usr/bin/pkill -SIGUSR1 -f subwoofer3.py
    ;;
  post/*)
        /usr/bin/pkill -SIGUSR2 -f subwoofer3.py
    ;;
esac
