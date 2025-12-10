#!/usr/bin/env python3
"""
Setup API Routes for Substrate AI

Handles first-time setup and configuration:
- Check if API key is configured
- Save API key to .env file
- Validate API key with OpenRouter

This enables a smooth onboarding experience for new users!
"""

import os
import re
from flask import Blueprint, jsonify, request
from pathlib import Path
import requests

setup_bp = Blueprint('setup', __name__, url_prefix='/api/setup')


def get_env_file_path() -> Path:
    """Get the path to the .env file"""
    # Backend directory is parent of api/
    backend_dir = Path(__file__).parent.parent
    return backend_dir / ".env"


def read_env_file() -> dict:
    """Read the .env file and return as dict"""
    env_path = get_env_file_path()
    env_vars = {}
    
    if env_path.exists():
        with open(env_path, 'r') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, _, value = line.partition('=')
                    env_vars[key.strip()] = value.strip()
    
    return env_vars


def write_env_file(env_vars: dict):
    """Write env vars back to .env file, preserving comments"""
    env_path = get_env_file_path()
    
    # Read existing file to preserve comments and structure
    existing_lines = []
    if env_path.exists():
        with open(env_path, 'r') as f:
            existing_lines = f.readlines()
    
    # Update or add values
    updated_keys = set()
    new_lines = []
    
    for line in existing_lines:
        stripped = line.strip()
        
        # Keep comments and empty lines
        if not stripped or stripped.startswith('#'):
            new_lines.append(line)
            continue
        
        # Check if this line has a key we want to update
        if '=' in stripped:
            key = stripped.split('=')[0].strip()
            if key in env_vars:
                new_lines.append(f"{key}={env_vars[key]}\n")
                updated_keys.add(key)
            else:
                new_lines.append(line)
        else:
            new_lines.append(line)
    
    # Add any new keys that weren't in the file
    for key, value in env_vars.items():
        if key not in updated_keys:
            new_lines.append(f"{key}={value}\n")
    
    # Write back
    with open(env_path, 'w') as f:
        f.writelines(new_lines)


def is_valid_openrouter_key(key: str) -> bool:
    """Check if the key looks like a valid OpenRouter key"""
    if not key:
        return False
    
    # OpenRouter keys start with sk-or-v1-
    if not key.startswith('sk-or-v1-'):
        return False
    
    # Should be reasonably long
    if len(key) < 20:
        return False
    
    return True


def verify_api_key_with_openrouter(key: str) -> tuple[bool, str]:
    """Actually verify the API key works with OpenRouter"""
    try:
        response = requests.get(
            "https://openrouter.ai/api/v1/auth/key",
            headers={"Authorization": f"Bearer {key}"},
            timeout=10
        )
        
        if response.status_code == 200:
            data = response.json()
            # Return success with usage info if available
            usage = data.get('data', {})
            return True, f"Key valid! Credits: ${usage.get('limit_remaining', 'unknown')}"
        elif response.status_code == 401:
            return False, "Invalid API key"
        else:
            return False, f"OpenRouter returned status {response.status_code}"
            
    except requests.exceptions.Timeout:
        # If timeout, assume key format is valid (OpenRouter might be slow)
        return True, "Could not verify with OpenRouter (timeout), but key format looks valid"
    except Exception as e:
        # If we can't reach OpenRouter, just validate format
        if is_valid_openrouter_key(key):
            return True, "Could not verify with OpenRouter, but key format looks valid"
        return False, str(e)


@setup_bp.route('/status', methods=['GET'])
def get_setup_status():
    """
    Check if the application is properly configured.
    
    Returns:
        - needs_setup: True if API key is missing/invalid
        - has_api_key: True if any API key is set
        - api_key_valid: True if the key format looks correct
        - message: Human-readable status message
    """
    env_vars = read_env_file()
    
    api_key = env_vars.get('OPENROUTER_API_KEY', '')
    
    # Check if it's a placeholder
    is_placeholder = (
        not api_key or 
        api_key == 'your_openrouter_api_key_here' or
        api_key == 'your_api_key_here' or
        api_key.startswith('your_')
    )
    
    if is_placeholder:
        return jsonify({
            'needs_setup': True,
            'has_api_key': False,
            'api_key_valid': False,
            'message': 'No API key configured. Please add your OpenRouter API key to get started!'
        })
    
    # Check if key format is valid
    if not is_valid_openrouter_key(api_key):
        return jsonify({
            'needs_setup': True,
            'has_api_key': True,
            'api_key_valid': False,
            'message': 'API key format is invalid. OpenRouter keys should start with sk-or-v1-'
        })
    
    # Key looks good!
    return jsonify({
        'needs_setup': False,
        'has_api_key': True,
        'api_key_valid': True,
        'message': 'API key configured and ready!'
    })


@setup_bp.route('/api-key', methods=['POST'])
def save_api_key():
    """
    Save the OpenRouter API key to the .env file.
    
    Request body:
        - api_key: The OpenRouter API key to save
        - verify: (optional) If true, verify the key with OpenRouter first
    
    Returns:
        - success: True if saved successfully
        - message: Human-readable result message
    """
    data = request.get_json()
    
    if not data:
        return jsonify({
            'success': False,
            'message': 'No data provided'
        }), 400
    
    api_key = data.get('api_key', '').strip()
    verify = data.get('verify', True)
    
    if not api_key:
        return jsonify({
            'success': False,
            'message': 'API key is required'
        }), 400
    
    # Basic format validation
    if not is_valid_openrouter_key(api_key):
        return jsonify({
            'success': False,
            'message': 'Invalid API key format. OpenRouter keys should start with sk-or-v1-'
        }), 400
    
    # Optionally verify with OpenRouter
    if verify:
        is_valid, verify_message = verify_api_key_with_openrouter(api_key)
        if not is_valid:
            return jsonify({
                'success': False,
                'message': f'API key verification failed: {verify_message}'
            }), 400
    
    # Read current env vars
    env_vars = read_env_file()
    
    # Update API key
    env_vars['OPENROUTER_API_KEY'] = api_key
    
    # Write back to file
    try:
        write_env_file(env_vars)
        
        # Also update the current environment so the app uses the new key
        os.environ['OPENROUTER_API_KEY'] = api_key
        
        return jsonify({
            'success': True,
            'message': '✅ API key saved successfully! You can now start chatting.'
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'Failed to save API key: {str(e)}'
        }), 500


@setup_bp.route('/api-key/verify', methods=['POST'])
def verify_api_key():
    """
    Verify an API key without saving it.
    
    Request body:
        - api_key: The OpenRouter API key to verify
    
    Returns:
        - valid: True if the key is valid
        - message: Verification result message
    """
    data = request.get_json()
    
    if not data:
        return jsonify({
            'valid': False,
            'message': 'No data provided'
        }), 400
    
    api_key = data.get('api_key', '').strip()
    
    if not api_key:
        return jsonify({
            'valid': False,
            'message': 'API key is required'
        }), 400
    
    # Format check
    if not is_valid_openrouter_key(api_key):
        return jsonify({
            'valid': False,
            'message': 'Invalid format. OpenRouter keys start with sk-or-v1-'
        })
    
    # Verify with OpenRouter
    is_valid, message = verify_api_key_with_openrouter(api_key)
    
    return jsonify({
        'valid': is_valid,
        'message': message
    })

