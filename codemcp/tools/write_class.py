#!/usr/bin/env python3

"""Tool for writing/updating class definitions in Python files."""

import logging
from typing import Dict, Any

# Import the core implementation from code_entity
from .code_entity import write_class as _write_class

logger = logging.getLogger(__name__)

__all__ = ["write_class"]


async def write_class(
    file_path: str, class_name: str, new_code: str, description: str, chat_id: str
) -> str:
    """Write or replace a class in a file.

    A thin wrapper around the code_entity implementation.

    Args:
        file_path: Path to the file
        class_name: Name of the class
        new_code: New class implementation
        description: Description of the change
        chat_id: The unique ID of the current chat session

    Returns:
        Success message
    """
    logger.info(f"Writing class '{class_name}' to {file_path}")
    try:
        result = await _write_class(file_path, class_name, new_code, description, chat_id)
        logger.info(f"Successfully wrote class '{class_name}' to {file_path}")
        return result
    except Exception as e:
        logger.error(f"Error writing class '{class_name}' to {file_path}: {e}")
        raise
