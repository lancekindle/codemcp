#!/usr/bin/env python3

"""End-to-end tests for the hot_reload_entry module."""

import os
import unittest
import logging
import asyncio

import codemcp.main
from codemcp.testing import MCPEndToEndTestCase


class TestHotReloadEntry(MCPEndToEndTestCase):
    """End-to-end tests for the hot_reload_entry module.

    These tests verify that the hot_reload_entry module correctly forwards tool calls
    to the main module and properly handles the results.
    """
    
    async def asyncSetUp(self):
        """Set up the test environment with enhanced logging."""
        # Configure logging for this test
        logging.basicConfig(
            level=logging.DEBUG,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            handlers=[
                logging.StreamHandler(),  # Log to console
                logging.FileHandler('hot_reload_test.log')  # Log to file
            ]
        )
        logging.info("================ TEST STARTING ================")
        
        # Call the parent setup
        await super().asyncSetUp()
        
    async def asyncTearDown(self):
        """Clean up after the test with proper resource handling."""
        logging.info("================ TEST TEARDOWN ================")
        
        # Attempt to cancel any pending tasks
        from codemcp.hot_reload_entry import _MANAGER, aexit
        try:
            # Make sure we clean up the manager
            await asyncio.wait_for(aexit(), timeout=10.0)
            logging.info("Manager cleaned up in tearDown")
        except Exception as e:
            logging.error(f"Error cleaning up manager: {e}")
            
        # Call the parent teardown
        await super().asyncTearDown()

    async def test_hot_reload_mechanism(self):
        """Test that the hot reload mechanism properly forwards tool calls to the main module."""
        logging.info("Starting test_hot_reload_mechanism")
        
        # Create a test file
        test_file_path = os.path.join(self.temp_dir.name, "test_file.txt")
        test_content = "Test content\nLine 2\nLine 3"
        with open(test_file_path, "w") as f:
            f.write(test_content)

        # Add the file to git to avoid permission issues
        await self.git_run(["add", test_file_path])

        # First call through the normal method for comparison
        logging.info("Getting chat_id")
        chat_id = await self.get_chat_id(None)  # We don't need a session for this

        # Make the call directly to main.codemcp
        logging.info("Making direct call to main.codemcp")
        direct_result = await codemcp.main.codemcp(
            "ReadFile", path=test_file_path, chat_id=chat_id
        )
        logging.info("Direct call completed successfully")

        # Now call through hot_reload_entry (simulating by directly importing it)
        logging.info("Importing hot_reload_entry.codemcp")
        from codemcp.hot_reload_entry import codemcp as hot_reload_codemcp

        logging.info("Making call via hot_reload_codemcp")
        hot_reload_result_raw = await hot_reload_codemcp(
            subtool="ReadFile", path=test_file_path, chat_id=chat_id
        )
        logging.info("Hot reload call completed successfully")

        # Extract text content from result
        if isinstance(hot_reload_result_raw, list) and hasattr(
            hot_reload_result_raw[0], "text"
        ):
            hot_reload_result = hot_reload_result_raw[0].text
        else:
            hot_reload_result = str(hot_reload_result_raw)

        # Verify both results contain our file content
        for line in test_content.splitlines():
            self.assertIn(line, direct_result)
            self.assertIn(line, hot_reload_result)
            
        logging.info("test_hot_reload_mechanism completed successfully")

    async def test_hot_reload_with_parameters(self):
        """Test that the hot reload mechanism properly passes parameters to the main module."""
        logging.info("Starting test_hot_reload_with_parameters")
        
        # Create a test file for our write/edit operations
        test_file_path = os.path.join(self.temp_dir.name, "params_test.txt")
        initial_content = "Initial content\nto be edited"
        with open(test_file_path, "w") as f:
            f.write(initial_content)

        # Add the file to git so we can write to it
        await self.git_run(["add", test_file_path])
        await self.git_run(["commit", "-m", "Add params test file"])

        # Get a valid chat_id
        logging.info("Getting chat_id")
        chat_id = await self.get_chat_id(None)

        # Import the hot_reload_entry codemcp function
        logging.info("Importing hot_reload_entry.codemcp")
        from codemcp.hot_reload_entry import codemcp as hot_reload_codemcp

        # Test WriteFile with specific parameters
        logging.info("Testing WriteFile via hot_reload_codemcp")
        new_content = "New content\nadded through hot reload"
        await hot_reload_codemcp(
            subtool="WriteFile",
            path=test_file_path,
            content=new_content,
            description="Write test through hot reload",
            chat_id=chat_id,
        )
        logging.info("WriteFile call completed")

        # Read the file to verify contents were written correctly
        with open(test_file_path, "r") as f:
            file_content = f.read()
        self.assertEqual(file_content, new_content + "\n")
        
        logging.info("test_hot_reload_with_parameters completed successfully")

    async def test_error_handling(self):
        """Test that errors from the main module are properly propagated through hot_reload_entry."""
        logging.info("Starting test_error_handling")
        
        # Get a valid chat_id
        logging.info("Getting chat_id")
        chat_id = await self.get_chat_id(None)

        # Import the hot_reload_entry codemcp function
        logging.info("Importing hot_reload_entry.codemcp")
        from codemcp.hot_reload_entry import codemcp as hot_reload_codemcp

        # Call ReadFile with a non-existent file to trigger an error
        non_existent_file = os.path.join(self.temp_dir.name, "does_not_exist.txt")

        # Make the call and capture the error message
        logging.info("Testing error handling with non-existent file")
        with self.assertRaisesRegex(RuntimeError, "does_not_exist.txt"):
            await hot_reload_codemcp(
                subtool="ReadFile", path=non_existent_file, chat_id=chat_id
            )
        
        logging.info("test_error_handling completed successfully")

    async def test_subprocess_reuse(self):
        """Test that multiple tool calls work through the hot reload mechanism."""
        logging.info("Starting test_subprocess_reuse")
        
        # Create a test file
        test_file_path = os.path.join(self.temp_dir.name, "multi_call_test.txt")
        test_content = "Test content\nLine 2\nLine 3"
        with open(test_file_path, "w") as f:
            f.write(test_content)

        # Add the file to git
        await self.git_run(["add", test_file_path])

        # Get a valid chat_id
        logging.info("Getting chat_id")
        chat_id = await self.get_chat_id(None)

        # Import the hot_reload_entry codemcp function
        logging.info("Importing hot_reload_entry.codemcp")
        from codemcp.hot_reload_entry import codemcp as hot_reload_codemcp

        # Make multiple calls to verify the mechanism works consistently
        for i in range(3):
            logging.info(f"Making call {i+1} of 3")
            result_raw = await hot_reload_codemcp(
                subtool="ReadFile", path=test_file_path, chat_id=chat_id
            )
            logging.info(f"Call {i+1} completed")

            # Extract text content from result
            if isinstance(result_raw, list) and hasattr(result_raw[0], "text"):
                result = result_raw[0].text
            else:
                result = str(result_raw)

            # Verify the result includes our file content
            for line in test_content.splitlines():
                self.assertIn(line, result)
                
            # Small delay between calls for clearer logging
            await asyncio.sleep(0.1)
            
        logging.info("test_subprocess_reuse completed successfully")


if __name__ == "__main__":
    unittest.main()