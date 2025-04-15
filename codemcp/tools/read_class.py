#!/usr/bin/env python3

"""Tool for reading class definitions from Python files."""

import logging

# Import the core implementation from code_entity
from .code_entity import read_class as _read_class

logger = logging.getLogger(__name__)

__all__ = ["read_class"]


async def read_class(file_path: str, class_name: str, chat_id: str) -> str:
    """Read a class definition from a file.

    A thin wrapper around the code_entity implementation.

    Args:
        file_path: Path to the file
        class_name: Name of the class to read
        chat_id: The unique ID of the current chat session

    Returns:
        Source code of the class
    """
    logger.info(f"Reading class '{class_name}' from {file_path}")
    try:
        result = await _read_class(file_path, class_name, chat_id)
        logger.info(f"Successfully read class '{class_name}' from {file_path}")
        return result
    except Exception as e:
        logger.error(f"Error reading class '{class_name}' from {file_path}: {e}")
        raise
