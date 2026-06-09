"""Ensure the repository root is importable so ``import qlabflash`` works
when pytest is invoked from anywhere in the tree."""

import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
