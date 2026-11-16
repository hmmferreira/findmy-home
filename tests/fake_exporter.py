#!/usr/bin/env python3
"""Synthetic prompt fixture: no Apple network or real secrets."""
import sys, os
assert "SUPERVISOR_TOKEN" not in os.environ
def prompt(label):
    print(label, end="", flush=True)
    return input()
email=prompt("Apple ID: ")
password=prompt("Password: ")
code=prompt("2FA code: ")
print("Found 2 escrow bottle(s):")
print("  [0] REDACTED_SERIAL (Test iPhone)")
print("  [1] REDACTED_SERIAL (Test Mac)")
device=prompt("Choose bottle [0]: ")
passcode=prompt("Enter the passcode of that device: ")
print("SENSITIVE_RAW_OUTPUT_MUST_NOT_ESCAPE")
sys.exit(0)
