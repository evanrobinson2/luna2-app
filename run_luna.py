#!/usr/bin/env python3

"""
run_luna.py

A simple entry-point script that imports 'luna_main' from 'core'
and runs it.
"""

import sys

# Import the main entry function from core.py
from luna.core import luna_main

def main():
    """
    Simply calls the 'luna_main()' function, which will:
     - configure logging
     - create an event loop
     - start the console thread
     - run the main logic
    """
    print("Launching Luna from run_luna.py ...")
    luna_main()

if __name__ == "__main__":
    main()
