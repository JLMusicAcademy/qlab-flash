#!/usr/bin/env python3
"""Launch QLab Flash.

    python3 main.py            # connect to a real QLab
    python3 main.py --demo     # try it with a simulated QLab
"""

import sys

from qlabflash.app import main

if __name__ == "__main__":
    sys.exit(main())
