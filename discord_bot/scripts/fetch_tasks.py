#!/usr/bin/env python3
import requests
import json
import sys
import os

# Get token from .env
token = None
try:
    with open('.env', 'r') as f:
        for line in f:
            if line.startswith('DISCORD_TOKEN='):
                token = line.split('=', 1)[1].strip()
                break
except:
    print("Error reading .env file")
    sys.exit(1)

if not token:
    print("DISCORD_TOKEN not found in .env")
    sys.exit(1)

# Fetch messages from tasks channel
channel_id = os.getenv("TASKS_CHANNEL_ID", "")
url = f"https://discord.com/api/v10/channels/{channel_id}/messages?limit=30"
headers = {"Authorization": f"Bot {token}"}

response = requests.get(url, headers=headers)
if response.status_code != 200:
    print(f"Error fetching messages: {response.status_code}")
    sys.exit(1)

messages = response.json()

# Find and print self tasks
for msg in messages:
    content = msg.get('content', '')
    if 'task_name' in content and 'self' in content.lower():
        # Extract JSON from code block
        if '```json' in content:
            try:
                json_str = content.split('```json')[1].split('```')[0].strip()
                task = json.loads(json_str)
                print("\n=== SELF TASK ===")
                print(json.dumps(task, indent=2))
                print()
            except Exception as e:
                print(f"Error parsing task: {e}")


