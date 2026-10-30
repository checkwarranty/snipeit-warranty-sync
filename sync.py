#!/usr/bin/env python3
"""Compatibility entry point; the installable CLI lives in its own package."""
import sys
import checkwarranty_snipeit_sync as implementation

if __name__ == "__main__":
    implementation.main()
else:
    sys.modules[__name__] = implementation
