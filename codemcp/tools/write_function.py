#!/usr/bin/env python3

"""Tool for writing/updating function definitions in Python files."""

import logging
from typing import Dict, Any, Optional

# Import the core implementation from code_entity
from .code_entity import write_function as _write_function

logger = logging.getLogger(__name__)

__all__ = ["write_function"]


async def write_function(
    file_path: str,
    function_name: str,
    new_code: str,
    description: str,
    chat_id: str,
    class_name: Optional[str] = None,
) -> str:
    """Write or replace a function in a file.

    A thin wrapper around the code_entity implementation.

    Args:
        file_path: Path to the file
        function_name: Name of the function
        new_code: New function implementation
        description: Description of the change
        chat_id: The unique ID of the current chat session
        class_name: Optional class name for methods

    Returns:
        Success message
    """
    entity_type = "method" if class_name else "function"
    location = f" in class '{class_name}'" if class_name else ""
    
    logger.info(f"Writing {entity_type} '{function_name}'{location} to {file_path}")
    try:
        result = await _write_function(
            file_path, 
            function_name, 
            new_code, 
            description, 
            chat_id, 
            class_name
        )
        logger.info(f"Successfully wrote {entity_type} '{function_name}'{location} to {file_path}")
        return result
    except Exception as e:
        logger.error(f"Error writing {entity_type} '{function_name}'{location} to {file_path}: {e}")
        raise
