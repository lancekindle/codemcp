#!/usr/bin/env python3


import asyncio
import functools
import logging
import os
import sys
from asyncio import Future, Queue, Task
from typing import Any, Dict, List, Optional, Protocol, Tuple, Union, cast

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.server.fastmcp import FastMCP
from mcp.types import TextContent


# Define the ClientSession.call_tool result type
class CallToolResult(Protocol):
    """Protocol for objects returned by call_tool."""

    isError: bool
    content: Union[str, List[TextContent], Any]


# Add type information for ClientSession
if not hasattr(ClientSession, "__call_tool_typed__"):
    # Store original call_tool method
    setattr(ClientSession, "__call_tool_typed__", True)
    # Add type hints (this won't change runtime behavior, just helps type checking)

# Import the original codemcp function from main to clone its signature
from codemcp.main import (
    codemcp as original_codemcp,
)
from codemcp.main import (
    configure_logging as main_configure_logging,
)

# Initialize FastMCP server with the same name
mcp = FastMCP("codemcp")


class HotReloadManager:
    """
    Manages the lifecycle of the hot reload context in a dedicated background task.
    This ensures proper cleanup of async resources by having a single task own the
    context manager.
    """

    def __init__(self):
        logging.info("Initializing HotReloadManager")
        self._task: Optional[Task[None]] = None
        self._request_queue: Optional[Queue[Tuple[str, Any, asyncio.Future[Any]]]] = (
            None
        )
        self._hot_reload_file = os.path.join(
            os.path.dirname(os.path.dirname(__file__)), ".hot_reload"
        )
        self._last_hot_reload_mtime: Optional[float] = None
        self._check_hot_reload_file()

    def _check_hot_reload_file(self) -> bool:
        """
        Check if the .hot_reload file exists and if its mtime has changed.
        Returns True if a reload should be triggered, False otherwise.
        """
        if not os.path.exists(self._hot_reload_file):
            # If the file doesn't exist now but did before, we should reload
            if self._last_hot_reload_mtime is not None:
                logging.info("Hot reload file removed, triggering reload")
                self._last_hot_reload_mtime = None
                return True
            return False

        current_mtime = os.path.getmtime(self._hot_reload_file)

        # If we haven't recorded an mtime yet, store it and don't reload
        if self._last_hot_reload_mtime is None:
            self._last_hot_reload_mtime = current_mtime
            return False

        # If the mtime has changed, trigger a reload
        if current_mtime > self._last_hot_reload_mtime:
            logging.info(
                f"Hot reload file modified, triggering reload (mtime: {current_mtime})"
            )
            self._last_hot_reload_mtime = current_mtime
            return True

        return False

    async def start(self) -> None:
        """Start the background task if not already running."""
        # NB: done() checks for if the old event loop was cleaned up
        if self._task is None or self._task.done():
            logging.info("Starting new HotReloadManager task")
            # Create fresh queue for this run
            self._request_queue = Queue()

            # Create the task with explicit parameters
            self._task = asyncio.create_task(
                self._run_manager_task(self._request_queue)
            )
            logging.info(f"Started task with ID: {id(self._task)}")

    async def stop(self) -> None:
        """Stop the background task and clean up resources."""
        logging.info("HotReloadManager.stop() called")
        
        if self._task and not self._task.done() and self._request_queue:
            logging.info(f"Attempting to stop task {id(self._task)}")
            
            # Create a future for the stop command
            stop_future: Future[bool] = asyncio.Future()

            # Get a local reference to the queue and task before clearing
            request_queue = self._request_queue
            task = self._task

            # Clear request_queue BEFORE any awaits to prevent race conditions
            self._request_queue = None
            logging.info("Request queue cleared")

            try:
                # Now it's safe to do awaits since new messages can't be added to self._request_queue
                logging.info("Putting stop command on queue")
                await request_queue.put(("stop", None, stop_future))
                
                # Add a timeout to avoid hanging indefinitely
                logging.info("Waiting for stop_future with timeout")
                await asyncio.wait_for(stop_future, timeout=5.0)
                logging.info("Stop future completed")
                
                logging.info("Waiting for task to complete")
                await asyncio.wait_for(task, timeout=5.0)
                logging.info("Task completed successfully")
            except asyncio.TimeoutError:
                logging.error("Timeout waiting for task to stop - force cancelling")
                # Force cancel the task if it times out
                task.cancel()
                try:
                    await asyncio.wait_for(task, timeout=1.0)
                except (asyncio.TimeoutError, asyncio.CancelledError):
                    logging.warning("Task cancellation complete")
            except Exception as e:
                logging.error(f"Error stopping task: {e}", exc_info=True)
                # Try to force cancel even on other errors
                if not task.done():
                    task.cancel()

    async def call_tool(self, **kwargs: Any) -> str:
        """Call the codemcp tool in the subprocess."""
        tool_info = f"subtool={kwargs.get('subtool', 'unknown')}"
        logging.info(f"call_tool called with {tool_info}")
        
        # Check if we need to reload based on .hot_reload file
        if (
            self._check_hot_reload_file()
            and self._task is not None
            and not self._task.done()
        ):
            logging.info("Stopping hot reload manager due to .hot_reload file change")
            await self.stop()

        # Start if needed
        if self._task is None or self._task.done() or self._request_queue is None:
            logging.info(f"Task needs starting for {tool_info}")
            await self.start()

        # Create a future for this specific request
        response_future: Future[str] = asyncio.Future()
        logging.info(f"Created future {id(response_future)} for {tool_info}")

        # Send the request and its associated future to the manager task
        if self._request_queue is not None:
            logging.info(f"Putting {tool_info} request on queue")
            await self._request_queue.put(("call", kwargs, response_future))
            logging.info(f"Request for {tool_info} queued successfully")
        else:
            logging.error(f"Request queue is None for {tool_info}, this shouldn't happen")
            raise RuntimeError("Request queue is None after starting the task")

        # Wait for the response with a timeout
        try:
            logging.info(f"Waiting for response for {tool_info} with timeout")
            result = await asyncio.wait_for(response_future, timeout=30.0)  # 30-second timeout
            logging.info(f"Received response for {tool_info}")
            return result
        except asyncio.TimeoutError:
            logging.error(f"Timeout waiting for response for {tool_info}")
            raise RuntimeError(f"Timeout waiting for response for {tool_info}")

    async def _run_manager_task(
        self, request_queue: Queue[Tuple[str, Any, asyncio.Future[Any]]]
    ) -> None:
        """
        Background task that owns and manages the async context managers lifecycle.

        Parameters:
            request_queue: Queue to receive commands from
        """
        logging.info("_run_manager_task started")
        
        # Setup stdio connection to main.py
        server_params = StdioServerParameters(
            command=sys.executable,  # Use the same Python interpreter
            args=[
                os.path.join(os.path.dirname(__file__), "__main__.py")
            ],  # Use __main__
            env=os.environ.copy(),  # Pass current environment variables
        )

        logging.info(f"Connecting to subprocess: {server_params.command} {' '.join(server_params.args)}")
        
        try:
            # Use nested async with statements to properly manage context
            logging.info("Creating stdio client")
            async with stdio_client(server_params) as (read, write):
                logging.info("stdio client created, creating ClientSession")
                async with ClientSession(read, write) as session:
                    # Initialize the session
                    logging.info("Initializing session")
                    await session.initialize()
                    logging.info("Session initialized successfully")

                    # Process commands until told to stop
                    while True:
                        logging.info("Waiting for next command from queue")
                        try:
                            # Add timeout to queue.get to avoid hanging indefinitely
                            command, args, future = await asyncio.wait_for(
                                request_queue.get(), timeout=60.0
                            )
                            logging.info(f"Received command: {command}")
                            
                            try:
                                if command == "stop":
                                    logging.info("Processing stop command")
                                    if not future.done():
                                        future.set_result(True)
                                    logging.info("Stop command processed, breaking loop")
                                    break

                                if command == "call":
                                    # Log the call details
                                    tool_args = cast(Dict[str, Any], args)
                                    subtool = tool_args.get("subtool", "unknown")
                                    logging.info(f"Processing call command for subtool={subtool}")
                                    
                                    try:
                                        # Get the raw result from call_tool with timeout
                                        logging.info(f"Calling tool {subtool} via session.call_tool")
                                        call_result = await asyncio.wait_for(
                                            session.call_tool(  # type: ignore
                                                name="codemcp", arguments=tool_args
                                            ),
                                            timeout=25.0  # Shorter than the outer timeout
                                        )
                                        logging.info(f"Received response for {subtool}")

                                        # Apply our protocol to the result
                                        result = cast(CallToolResult, call_result)
                                        
                                        # Handle error cases
                                        if result.isError:
                                            logging.error(f"Error result for {subtool}: {result.content}")
                                            match result.content:
                                                case [TextContent(text=err)]:
                                                    logging.error(f"Error message: {err}")
                                                    if not future.done():
                                                        future.set_exception(RuntimeError(err))
                                                case _:
                                                    logging.error("Unknown error format")
                                                    if not future.done():
                                                        future.set_exception(
                                                            RuntimeError("Unknown error")
                                                        )
                                        else:
                                            logging.info(f"Setting successful result for {subtool}")
                                            if not future.done():
                                                future.set_result(result.content)
                                    except asyncio.TimeoutError:
                                        logging.error(f"Timeout calling tool {subtool}")
                                        if not future.done():
                                            future.set_exception(
                                                RuntimeError(f"Timeout calling {subtool}")
                                            )
                                    except Exception as e:
                                        logging.error(f"Error calling tool {subtool}: {e}", exc_info=True)
                                        if not future.done():
                                            future.set_exception(e)

                            except Exception as e:
                                logging.error(f"Error processing command {command}: {e}", exc_info=True)
                                if not future.done():
                                    future.set_exception(e)
                                    
                        except asyncio.TimeoutError:
                            logging.warning("Timeout waiting for command from queue, continuing...")
                            continue
                        except Exception as e:
                            logging.error(f"Unexpected error in command loop: {e}", exc_info=True)
                            # Continue the loop to avoid crashing the manager task
                            continue
                            
            logging.info("Exited context managers successfully")
            
        except Exception as e:
            logging.error(f"Critical error in _run_manager_task: {e}", exc_info=True)


# Global singleton manager
_MANAGER = HotReloadManager()


async def aexit():
    """Stop the hot reload manager and clean up resources."""
    logging.info("aexit called - stopping manager")
    try:
        await _MANAGER.stop()
        logging.info("Manager stopped successfully in aexit")
    except Exception as e:
        logging.error(f"Error stopping manager in aexit: {e}", exc_info=True)
        # Force cancel any running task as a last resort
        if _MANAGER._task and not _MANAGER._task.done():
            logging.warning("Force cancelling task in aexit")
            _MANAGER._task.cancel()


@mcp.tool()
@functools.wraps(original_codemcp)  # This copies the signature and docstring
async def codemcp(**kwargs: Any) -> str:
    """This is a wrapper that forwards all tool calls to the codemcp/main.py process.
    This allows for hot-reloading as main.py will be reloaded on each call.

    Arguments are the same as in main.py's codemcp tool.
    """
    subtool = kwargs.get("subtool", "unknown")
    logging.info(f"hot_reload_entry.codemcp called with subtool={subtool}")
    configure_logging()
    try:
        # Use the HotReloadManager to handle the context and session lifecycle
        logging.info(f"Delegating {subtool} to HotReloadManager.call_tool")
        result = await _MANAGER.call_tool(**kwargs)
        logging.info(f"Successfully completed {subtool}")
        return result
    except Exception as e:
        logging.error(f"Exception in hot_reload_entry.py for {subtool}: {e}", exc_info=True)
        raise


def configure_logging():
    """Import and use the same logging configuration from main module"""
    main_configure_logging("codemcp_hot_reload.log")


def run():
    """Run the MCP server with hot reload capability."""
    configure_logging()
    logging.info("Starting codemcp with hot reload capability")
    mcp.run()


if __name__ == "__main__":
    run()
