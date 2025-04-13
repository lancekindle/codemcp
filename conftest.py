#!/usr/bin/env python3

# Pytest configuration file
import pytest

# Register asyncio marker to support async tests
# This allows tests decorated with @pytest.mark.asyncio to be properly run
pytest.register_assert_rewrite("asyncio")
