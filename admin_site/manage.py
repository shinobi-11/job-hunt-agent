#!/usr/bin/env python
"""Django admin management entrypoint."""
import os
import sys
from pathlib import Path

if __name__ == "__main__":
    ROOT = Path(__file__).resolve().parent.parent
    sys.path.insert(0, str(ROOT))
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "admin_site.settings")

    from django.core.management import execute_from_command_line
    execute_from_command_line(sys.argv)
