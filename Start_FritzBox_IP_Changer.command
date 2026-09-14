#!/bin/bash
# 1-Klick Starter für Fritz!Box IP-Changer
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"
cd "$DIR"

# Python 3 starten
python3 app.py
