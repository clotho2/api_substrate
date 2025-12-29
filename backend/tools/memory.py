"""
Memory Tool - Alternative API for memory block management

This tool provides file-like operations on memory blocks:
- create: Create new memory block
- str_replace: Replace text in memory block
- insert: Insert text at line
- delete: Delete memory block
- rename: Rename memory block OR update description
"""

import sys
import os

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.state_manager import StateManager, BlockType

# Global state manager instance (will be set by MemoryTools)
_state_manager: StateManager = None


def set_state_manager(state_manager: StateManager):
    """Set the global state manager instance"""
    global _state_manager
    _state_manager = state_manager


def memory(
    command: str,
    path: str = None,
    file_text: str = None,
    description: str = None,
    old_str: str = None,
    new_str: str = None,
    insert_line: int = None,
    insert_text: str = None,
    old_path: str = None,
    new_path: str = None
) -> dict:
    """
    Memory management tool with file-like sub-commands.

    Commands:
    - create: Create new memory block
    - str_replace: Replace text in memory block
    - insert: Insert text at line
    - delete: Delete memory block
    - rename: Rename memory block

    Args:
        command: Sub-command to execute
        path: Memory block label/path
        file_text: Content for create command
        description: Description for create command
        old_str: Old text for str_replace
        new_str: New text for str_replace
        insert_line: Line number for insert (0-based)
        insert_text: Text to insert
        old_path: Old path for rename
        new_path: New path for rename

    Returns:
        dict: Operation result with status and message
    """
    if not _state_manager:
        return {
            "status": "error",
            "message": "State manager not initialized. This is a bug - please report it."
        }

    try:
        if command == "create":
            # Create new memory block
            if not path:
                return {
                    "status": "error",
                    "message": "Parameter 'path' (block label) is required for create command"
                }

            if file_text is None:
                file_text = ""

            # Check if block already exists
            existing = _state_manager.get_block(path)
            if existing:
                return {
                    "status": "error",
                    "message": f"Memory block '{path}' already exists. Use str_replace to modify it."
                }

            # Create the block
            block = _state_manager.create_block(
                label=path,
                content=file_text,
                block_type=BlockType.CUSTOM,
                description=description or f"Memory block: {path}",
                limit=5000,  # Increased from 2000 to give more room for detailed memories
                read_only=False
            )

            return {
                "status": "OK",
                "message": f"Created memory block '{path}' with {len(file_text)} characters",
                "block": {
                    "label": block.label,
                    "size": len(block.content),
                    "description": block.description
                }
            }

        elif command == "str_replace":
            # Replace text in memory block
            if not path:
                return {
                    "status": "error",
                    "message": "Parameter 'path' (block label) is required for str_replace command"
                }

            if old_str is None or new_str is None:
                return {
                    "status": "error",
                    "message": "Parameters 'old_str' and 'new_str' are required for str_replace command"
                }

            # Get existing block
            block = _state_manager.get_block(path)
            if not block:
                return {
                    "status": "error",
                    "message": f"Memory block '{path}' not found. Use create command first."
                }

            # Check if old_str exists
            if old_str not in block.content:
                return {
                    "status": "error",
                    "message": f"Text not found in block '{path}': {old_str[:50]}..."
                }

            # Replace text
            new_content = block.content.replace(old_str, new_str)

            # Check limit
            if len(new_content) > block.limit:
                return {
                    "status": "error",
                    "message": f"Content exceeds block limit ({len(new_content)} > {block.limit} chars)"
                }

            # Update block
            _state_manager.update_block(path, new_content)

            return {
                "status": "OK",
                "message": f"Replaced text in '{path}': '{old_str[:30]}...' → '{new_str[:30]}...'",
                "new_size": len(new_content)
            }

        elif command == "insert":
            # Insert text at line
            if not path:
                return {
                    "status": "error",
                    "message": "Parameter 'path' (block label) is required for insert command"
                }

            if insert_line is None or insert_text is None:
                return {
                    "status": "error",
                    "message": "Parameters 'insert_line' and 'insert_text' are required for insert command"
                }

            # Get existing block
            block = _state_manager.get_block(path)
            if not block:
                return {
                    "status": "error",
                    "message": f"Memory block '{path}' not found. Use create command first."
                }

            # Split content into lines
            lines = block.content.split('\n')

            # Insert at line
            if insert_line < 0 or insert_line > len(lines):
                return {
                    "status": "error",
                    "message": f"Invalid line number {insert_line}. Block has {len(lines)} lines."
                }

            lines.insert(insert_line, insert_text)
            new_content = '\n'.join(lines)

            # Check limit
            if len(new_content) > block.limit:
                return {
                    "status": "error",
                    "message": f"Content exceeds block limit ({len(new_content)} > {block.limit} chars)"
                }

            # Update block
            _state_manager.update_block(path, new_content)

            return {
                "status": "OK",
                "message": f"Inserted text at line {insert_line} in '{path}'",
                "new_size": len(new_content)
            }

        elif command == "delete":
            # Delete memory block
            if not path:
                return {
                    "status": "error",
                    "message": "Parameter 'path' (block label) is required for delete command"
                }

            # Check if block exists
            block = _state_manager.get_block(path)
            if not block:
                return {
                    "status": "error",
                    "message": f"Memory block '{path}' not found"
                }

            # Check if read-only
            if block.read_only:
                return {
                    "status": "error",
                    "message": f"Cannot delete read-only block '{path}'"
                }

            # Delete block
            _state_manager.delete_block(path)

            return {
                "status": "OK",
                "message": f"Deleted memory block '{path}'"
            }

        elif command == "rename":
            # Rename memory block OR update description
            if new_path:
                # Rename: old_path -> new_path
                if not old_path:
                    return {
                        "status": "error",
                        "message": "Parameter 'old_path' is required when using 'new_path' for rename"
                    }

                # Get existing block
                block = _state_manager.get_block(old_path)
                if not block:
                    return {
                        "status": "error",
                        "message": f"Memory block '{old_path}' not found"
                    }

                # Check if new path already exists
                existing_new = _state_manager.get_block(new_path)
                if existing_new:
                    return {
                        "status": "error",
                        "message": f"Memory block '{new_path}' already exists. Delete it first or choose a different name."
                    }

                # Check if read-only
                if block.read_only:
                    return {
                        "status": "error",
                        "message": f"Cannot rename read-only block '{old_path}'"
                    }

                # Create new block with same content
                new_block = _state_manager.create_block(
                    label=new_path,
                    content=block.content,
                    block_type=block.block_type,
                    description=description or block.description,
                    limit=block.limit,
                    read_only=block.read_only,
                    metadata=block.metadata
                )

                # Delete old block
                _state_manager.delete_block(old_path)

                return {
                    "status": "OK",
                    "message": f"Renamed memory block '{old_path}' → '{new_path}'",
                    "block": {
                        "label": new_block.label,
                        "size": len(new_block.content),
                        "description": new_block.description
                    }
                }

            elif path and description:
                # Update description only
                block = _state_manager.get_block(path)
                if not block:
                    return {
                        "status": "error",
                        "message": f"Memory block '{path}' not found"
                    }

                # Update the block's description via metadata update
                _state_manager.update_block_metadata(path, description=description)

                return {
                    "status": "OK",
                    "message": f"Updated description for '{path}'",
                    "new_description": description
                }

            else:
                return {
                    "status": "error",
                    "message": "rename requires either (old_path + new_path) to rename, or (path + description) to update description"
                }

        else:
            return {
                "status": "error",
                "message": f"Unknown command '{command}'. Available: create, str_replace, insert, delete, rename"
            }

    except Exception as e:
        return {
            "status": "error",
            "message": f"Memory tool error: {str(e)}"
        }







