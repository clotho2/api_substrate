#!/usr/bin/env python3
"""
Test file for Level 3 file editing demonstration.
This file will be used to test the edit_file functionality.
"""


def hello_world():
    """Simple function to test editing."""
    message = "Hello, World!"
    print(message)
    return message


def add_numbers(a, b):
    """Add two numbers."""
    result = a + b
    return result


if __name__ == "__main__":
    hello_world()
    print(add_numbers(5, 3))
