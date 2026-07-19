#!/usr/bin/env python3
"""Compatibility entrypoint for the guarded production database upgrade."""

from safe_upgrade import run_upgrade


if __name__ == "__main__":
    raise SystemExit(run_upgrade())
