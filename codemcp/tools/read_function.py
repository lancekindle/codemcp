#!/usr/bin/env python3

"""Tool for reading function definitions from Python files."""

import logging
from typing import Optional

# Import the core implementation from code_entity
from .code_entity import read_function as _read_function

logger = logging.getLogger(__name__)

__all__ = ["read_function"]


async def read_function(
    file_path: str, function_name: str, chat_id: str, class_name: Optional[str] = None
) -> str:
    """Read a function or method definition from a file.

    A thin wrapper around the code_entity implementation.

    Args:
        file_path: Path to the file
        function_name: Name of the function to read
        chat_id: The unique ID of the current chat session
        class_name: Optional class name if the function is a method

    Returns:
        Source code of the function
    """
    entity_type = "method" if class_name else "function"
    location = f" in class '{class_name}'" if class_name else ""

    logger.info(f"Reading {entity_type} '{function_name}'{location} from {file_path}")
    try:
        result = await _read_function(file_path, function_name, chat_id, class_name)
        logger.info(f"Successfully read {entity_type} '{function_name}'{location} from {file_path}")
        return result
    except Exception as e:
        logger.error(f"Error reading {entity_type} '{function_name}'{location} from {file_path}: {e}")
        raise
