#!/usr/bin/env python
import sys
from any_to_any import main

if __name__ == "__main__":
    # -w flag starts executables directly into web view
    sys.argv.append("-w")
    main()
