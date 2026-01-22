#!/usr/bin/env python3
"""
Setup Script: Initialize the Substrate Agent

This script is a generic entry point that configures the substrate with
neutral defaults. It delegates to the main setup routine.
"""

from dotenv import load_dotenv
from setup_nate import setup_nate_agent


def main() -> None:
    load_dotenv()
    setup_nate_agent()


if __name__ == "__main__":
    main()
