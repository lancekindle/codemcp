#!/usr/bin/env python3

import os
import ast
import logging
from typing import Tuple, Optional, List, Dict, Any

from ..common import get_edit_snippet
from ..file_utils import (
    async_open_text,
    check_file_path_and_permissions,
    check_git_tracking_for_existing_file,
    write_text_content,
)
from ..git import commit_changes
from ..line_endings import detect_line_endings

# Set up logger
logger = logging.getLogger(__name__)

__all__ = [
    "read_class",
    "read_function",
    "write_class",
    "write_function",
]


class CodeEntityVisitor(ast.NodeVisitor):
    """AST visitor to find class and function definitions."""
    
    def __init__(self, target_class=None, target_function=None):
        self.target_class = target_class
        self.target_function = target_function
        self.class_info = {}
        self.function_info = {}
        self.current_class = None
    
    def visit_ClassDef(self, node):
        """Visit a class definition."""
        class_name = node.name
        # Store class info with line numbers
        self.class_info[class_name] = {
            'lineno': node.lineno,
            'end_lineno': node.end_lineno,
            'col_offset': node.col_offset,
            'methods': {}
        }
        
        # Save current class context for method tracking
        old_class = self.current_class
        self.current_class = class_name
        
        # Visit all nodes in the class body
        for child in node.body:
            self.visit(child)
        
        # Restore previous class context
        self.current_class = old_class

    def visit_FunctionDef(self, node):
        """Visit a function definition."""
        func_name = node.name
        
        if self.current_class:
            # This is a method, store it in the class's methods dict
            self.class_info[self.current_class]['methods'][func_name] = {
                'lineno': node.lineno,
                'end_lineno': node.end_lineno,
                'col_offset': node.col_offset
            }
        else:
            # This is a standalone function
            self.function_info[func_name] = {
                'lineno': node.lineno,
                'end_lineno': node.end_lineno,
                'col_offset': node.col_offset
            }


async def parse_file(file_path: str) -> Tuple[str, ast.AST, Dict[str, Any], Dict[str, Any]]:
    """Parse a Python file and extract class and function definitions.
    
    Args:
        file_path: Path to the Python file
        
    Returns:
        Tuple containing:
        - file content
        - AST tree
        - dict of class information
        - dict of function information
    """
    # Read the file content
    content = await async_open_text(file_path, encoding='utf-8')
    
    try:
        # Parse the source into an AST
        tree = ast.parse(content)
        
        # Create a visitor to extract class and function info
        visitor = CodeEntityVisitor()
        visitor.visit(tree)
        
        return content, tree, visitor.class_info, visitor.function_info
    except SyntaxError as e:
        logger.error(f"Syntax error parsing {file_path}: {e}")
        raise ValueError(f"Failed to parse {file_path} - syntax error: {e}")


def get_entity_source(content: str, start_line: int, end_line: int) -> str:
    """Extract source code for an entity from line numbers.
    
    Args:
        content: File content
        start_line: Starting line number (1-indexed)
        end_line: Ending line number (1-indexed)
        
    Returns:
        Source code of the entity
    """
    lines = content.splitlines()
    
    # Adjusting for zero-indexing
    entity_lines = lines[start_line-1:end_line]
    
    # Join lines back together
    return '\n'.join(entity_lines)


def find_insertion_point(content: str, class_name: Optional[str] = None) -> int:
    """Find an appropriate insertion point for a new class or function.
    
    Args:
        content: File content
        class_name: Optional class name for inserting a method
        
    Returns:
        Line number for insertion (0-indexed)
    """
    lines = content.splitlines()
    
    if class_name:
        # Try to insert at the end of the specified class
        try:
            tree = ast.parse(content)
            for node in ast.walk(tree):
                if isinstance(node, ast.ClassDef) and node.name == class_name:
                    # Insert at the end of the class
                    return node.end_lineno
        except SyntaxError:
            # Fall back to simple approach on parsing error
            pass
        
        # Simple fallback: find class definition and look for the next class or EOF
        in_target_class = False
        indentation = 0
        class_start = 0
        
        for i, line in enumerate(lines):
            if f"class {class_name}" in line and not in_target_class:
                in_target_class = True
                class_start = i
                # Detect indentation
                indentation = len(line) - len(line.lstrip())
                continue
                
            if in_target_class:
                # Looking for end of class
                if i > class_start and line.strip() and len(line) - len(line.lstrip()) <= indentation:
                    # Found a line with same or less indentation - this is after the class
                    return i - 1
        
        # If we're still in the target class at EOF
        if in_target_class:
            return len(lines)
    
    # For top-level entities, try to insert after imports and before first class/function
    import_end = 0
    for i, line in enumerate(lines):
        trimmed = line.strip()
        if trimmed.startswith(("import ", "from ")) or trimmed == "":
            import_end = i + 1
        elif trimmed.startswith(("class ", "def ")):
            # Found first class or function
            return import_end
    
    # If no suitable location found, add to end of file
    return len(lines)


async def read_class(file_path: str, class_name: str, chat_id: str) -> str:
    """Read a class definition from a file.
    
    Args:
        file_path: Path to the file
        class_name: Name of the class to read
        chat_id: The unique ID of the current chat session
        
    Returns:
        Source code of the class
    """
    # Import normalize_file_path for tilde expansion
    from ..common import normalize_file_path
    
    # Normalize the path with tilde expansion
    full_file_path = normalize_file_path(file_path)
    
    # Check if file exists
    if not os.path.exists(full_file_path):
        raise FileNotFoundError(f"File not found: {full_file_path}")
    
    # Check file permissions
    is_valid, error_message = await check_file_path_and_permissions(full_file_path)
    if not is_valid:
        raise ValueError(error_message)
    
    # Parse the file
    content, _, class_info, _ = await parse_file(full_file_path)
    
    # Check if the class exists
    if class_name not in class_info:
        raise ValueError(f"Class '{class_name}' not found in {full_file_path}")
    
    # Get the class definition lines
    class_data = class_info[class_name]
    class_source = get_entity_source(content, class_data['lineno'], class_data['end_lineno'])
    
    return class_source


async def read_function(
    file_path: str, 
    function_name: str, 
    chat_id: str, 
    class_name: Optional[str] = None
) -> str:
    """Read a function or method definition from a file.
    
    Args:
        file_path: Path to the file
        function_name: Name of the function to read
        chat_id: The unique ID of the current chat session
        class_name: Optional class name if the function is a method
        
    Returns:
        Source code of the function
    """
    # Import normalize_file_path for tilde expansion
    from ..common import normalize_file_path
    
    # Normalize the path with tilde expansion
    full_file_path = normalize_file_path(file_path)
    
    # Check if file exists
    if not os.path.exists(full_file_path):
        raise FileNotFoundError(f"File not found: {full_file_path}")
    
    # Check file permissions
    is_valid, error_message = await check_file_path_and_permissions(full_file_path)
    if not is_valid:
        raise ValueError(error_message)
    
    # Parse the file
    content, _, class_info, function_info = await parse_file(full_file_path)
    
    # Check if we're looking for a method in a class
    if class_name:
        # Check if the class exists
        if class_name not in class_info:
            raise ValueError(f"Class '{class_name}' not found in {full_file_path}")
        
        # Check if the method exists in the class
        if function_name not in class_info[class_name]['methods']:
            raise ValueError(f"Method '{function_name}' not found in class '{class_name}' in {full_file_path}")
        
        # Get the method definition lines
        method_data = class_info[class_name]['methods'][function_name]
        function_source = get_entity_source(content, method_data['lineno'], method_data['end_lineno'])
    else:
        # Check if the function exists
        if function_name not in function_info:
            raise ValueError(f"Function '{function_name}' not found in {full_file_path}")
        
        # Get the function definition lines
        function_data = function_info[function_name]
        function_source = get_entity_source(content, function_data['lineno'], function_data['end_lineno'])
    
    return function_source


async def write_class(
    file_path: str,
    class_name: str,
    new_code: str,
    description: str,
    chat_id: str
) -> str:
    """Write or replace a class in a file.
    
    Args:
        file_path: Path to the file
        class_name: Name of the class
        new_code: New class implementation
        description: Description of the change
        chat_id: The unique ID of the current chat session
        
    Returns:
        Success message
    """
    # Import normalize_file_path for tilde expansion
    from ..common import normalize_file_path
    
    # Normalize the path with tilde expansion
    full_file_path = normalize_file_path(file_path)
    
    # Prevent editing codemcp.toml for security reasons
    if os.path.basename(full_file_path) == "codemcp.toml":
        raise ValueError("Editing codemcp.toml is not allowed for security reasons.")
    
    # Check file path and permissions
    is_valid, error_message = await check_file_path_and_permissions(full_file_path)
    if not is_valid:
        raise ValueError(error_message)
    
    # Check if file exists and create it if it doesn't
    creating_new_file = not os.path.exists(full_file_path)
    
    if creating_new_file:
        # Create directory if needed
        directory = os.path.dirname(full_file_path)
        os.makedirs(directory, exist_ok=True)
        content = ""
        line_endings = "\n"  # Default to Unix line endings for new files
    else:
        # Check git tracking for existing files
        is_tracked, track_error = await check_git_tracking_for_existing_file(
            full_file_path,
            chat_id=chat_id,
        )
        if not is_tracked:
            raise ValueError(track_error)
        
        # Read existing content and detect line endings
        content = await async_open_text(full_file_path, encoding='utf-8')
        line_endings = await detect_line_endings(full_file_path, return_format="format")
    
    # For existing files, check if it's valid Python
    if not creating_new_file:
        try:
            # Parse the file to find the class (if it exists)
            content, _, class_info, _ = await parse_file(full_file_path)
            
            # If class exists, replace it
            if class_name in class_info:
                lines = content.splitlines()
                class_data = class_info[class_name]
                
                # Replace class definition with new code
                start_line = class_data['lineno'] - 1  # Convert to 0-indexed
                end_line = class_data['end_lineno']    # end_lineno is already the next line
                
                # Prepare the replacement
                before_lines = lines[:start_line]
                after_lines = lines[end_line:]
                
                # Create the new content
                new_lines = before_lines + new_code.splitlines() + after_lines
                updated_content = '\n'.join(new_lines)
            else:
                # Class doesn't exist, append it to an appropriate location
                insertion_point = find_insertion_point(content)
                lines = content.splitlines()
                
                # Ensure there's a blank line before the new class
                if insertion_point > 0 and lines[insertion_point-1].strip() != "":
                    lines.insert(insertion_point, "")
                    insertion_point += 1
                
                # Insert the new class
                new_lines = lines[:insertion_point] + new_code.splitlines() + lines[insertion_point:]
                updated_content = '\n'.join(new_lines)
        except SyntaxError:
            # If the file is not valid Python, just append the class
            updated_content = content + "\n\n" + new_code
    else:
        # For new files, just use the new code
        updated_content = new_code
    
    # Write the modified content back to the file
    await write_text_content(full_file_path, updated_content, 'utf-8', line_endings)
    
    # Commit the changes
    success, message = await commit_changes(full_file_path, description, chat_id)
    git_message = ""
    if success:
        git_message = f"\n\nChanges committed to git: {description}"
        # Include any extra details like previous commit hash if present in the message
        if "previous commit was" in message:
            git_message = f"\n\n{message}"
    else:
        git_message = f"\n\nFailed to commit changes to git: {message}"
    
    action = "created" if creating_new_file else "updated"
    return f"Successfully {action} class '{class_name}' in {full_file_path}{git_message}"


async def write_function(
    file_path: str,
    function_name: str,
    new_code: str,
    description: str,
    chat_id: str,
    class_name: Optional[str] = None
) -> str:
    """Write or replace a function in a file.
    
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
    # Import normalize_file_path for tilde expansion
    from ..common import normalize_file_path
    
    # Normalize the path with tilde expansion
    full_file_path = normalize_file_path(file_path)
    
    # Prevent editing codemcp.toml for security reasons
    if os.path.basename(full_file_path) == "codemcp.toml":
        raise ValueError("Editing codemcp.toml is not allowed for security reasons.")
    
    # Check file path and permissions
    is_valid, error_message = await check_file_path_and_permissions(full_file_path)
    if not is_valid:
        raise ValueError(error_message)
    
    # Check if file exists and create it if it doesn't
    creating_new_file = not os.path.exists(full_file_path)
    
    if creating_new_file:
        # Create directory if needed
        directory = os.path.dirname(full_file_path)
        os.makedirs(directory, exist_ok=True)
        content = ""
        line_endings = "\n"  # Default to Unix line endings for new files
    else:
        # Check git tracking for existing files
        is_tracked, track_error = await check_git_tracking_for_existing_file(
            full_file_path,
            chat_id=chat_id,
        )
        if not is_tracked:
            raise ValueError(track_error)
        
        # Read existing content and detect line endings
        content = await async_open_text(full_file_path, encoding='utf-8')
        line_endings = await detect_line_endings(full_file_path, return_format="format")
    
    # For existing files, check if it's valid Python
    if not creating_new_file:
        try:
            # Parse the file to find functions and classes
            content, _, class_info, function_info = await parse_file(full_file_path)
            
            # Different handling for methods and standalone functions
            if class_name:
                # Handling method in a class
                if class_name in class_info:
                    class_data = class_info[class_name]
                    
                    if function_name in class_data['methods']:
                        # Method exists, replace it
                        method_data = class_data['methods'][function_name]
                        lines = content.splitlines()
                        
                        # Replace method definition with new code
                        start_line = method_data['lineno'] - 1  # Convert to 0-indexed
                        end_line = method_data['end_lineno']    # end_lineno is already the next line
                        
                        # Prepare the replacement
                        before_lines = lines[:start_line]
                        after_lines = lines[end_line:]
                        
                        # Create the new content
                        new_lines = before_lines + new_code.splitlines() + after_lines
                        updated_content = '\n'.join(new_lines)
                    else:
                        # Method doesn't exist, add it to the class
                        lines = content.splitlines()
                        insertion_point = find_insertion_point(content, class_name)
                        
                        # Ensure proper indentation for the new method
                        # Find class indentation
                        class_line = lines[class_data['lineno'] - 1]
                        class_indent = len(class_line) - len(class_line.lstrip())
                        method_indent = class_indent + 4  # Standard 4-space indentation
                        
                        # Indent the new method
                        indented_code = '\n'.join(
                            ' ' * method_indent + line for line in new_code.splitlines()
                        )
                        
                        # Ensure there's a blank line before the new method if the class isn't empty
                        if lines[insertion_point-1].strip() != "":
                            lines.insert(insertion_point, "")
                            insertion_point += 1
                        
                        # Insert the new method
                        new_lines = lines[:insertion_point] + [indented_code] + lines[insertion_point:]
                        updated_content = '\n'.join(new_lines)
                else:
                    # Class doesn't exist, create it and add the method
                    insertion_point = find_insertion_point(content)
                    lines = content.splitlines()
                    
                    # Create a new class with the method
                    class_code = f"class {class_name}:\n    {new_code.replace(new_code.splitlines()[0], new_code.splitlines()[0].lstrip())}"
                    
                    # Ensure there's a blank line before the new class
                    if insertion_point > 0 and lines[insertion_point-1].strip() != "":
                        lines.insert(insertion_point, "")
                        insertion_point += 1
                    
                    # Insert the new class with method
                    new_lines = lines[:insertion_point] + class_code.splitlines() + lines[insertion_point:]
                    updated_content = '\n'.join(new_lines)
            else:
                # Handling standalone function
                if function_name in function_info:
                    # Function exists, replace it
                    function_data = function_info[function_name]
                    lines = content.splitlines()
                    
                    # Replace function definition with new code
                    start_line = function_data['lineno'] - 1  # Convert to 0-indexed
                    end_line = function_data['end_lineno']    # end_lineno is already the next line
                    
                    # Prepare the replacement
                    before_lines = lines[:start_line]
                    after_lines = lines[end_line:]
                    
                    # Create the new content
                    new_lines = before_lines + new_code.splitlines() + after_lines
                    updated_content = '\n'.join(new_lines)
                else:
                    # Function doesn't exist, append it to an appropriate location
                    insertion_point = find_insertion_point(content)
                    lines = content.splitlines()
                    
                    # Ensure there's a blank line before the new function
                    if insertion_point > 0 and lines[insertion_point-1].strip() != "":
                        lines.insert(insertion_point, "")
                        insertion_point += 1
                    
                    # Insert the new function
                    new_lines = lines[:insertion_point] + new_code.splitlines() + lines[insertion_point:]
                    updated_content = '\n'.join(new_lines)
        except SyntaxError:
            # If the file is not valid Python, just append the function
            updated_content = content + "\n\n" + new_code
    else:
        # For new files, just use the new code
        updated_content = new_code
    
    # Write the modified content back to the file
    await write_text_content(full_file_path, updated_content, 'utf-8', line_endings)
    
    # Commit the changes
    success, message = await commit_changes(full_file_path, description, chat_id)
    git_message = ""
    if success:
        git_message = f"\n\nChanges committed to git: {description}"
        # Include any extra details like previous commit hash if present in the message
        if "previous commit was" in message:
            git_message = f"\n\n{message}"
    else:
        git_message = f"\n\nFailed to commit changes to git: {message}"
    
    entity_type = "method" if class_name else "function"
    location = f"in class '{class_name}'" if class_name else ""
    action = "created" if creating_new_file else "updated"
    
    return f"Successfully {action} {entity_type} '{function_name}' {location} in {full_file_path}{git_message}"