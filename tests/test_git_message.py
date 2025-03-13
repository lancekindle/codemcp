#!/usr/bin/env python3

import unittest
from codemcp.git import append_metadata_to_message


class TestGitMessageHandling(unittest.TestCase):
    """Test cases for Git commit message metadata handling."""

    def test_append_empty_message(self):
        """Test appending metadata to an empty message."""
        message = ""
        new_message = append_metadata_to_message(message, {"codemcp-id": "abc-123"})
        self.assertEqual(new_message, "codemcp-id: abc-123")

    def test_append_new_metadata(self):
        """Test appending new metadata to a message without existing metadata."""
        message = "feat: Add feature\n\nDescription"
        new_message = append_metadata_to_message(message, {"codemcp-id": "abc-123"})
        self.assertEqual(
            new_message, "feat: Add feature\n\nDescription\n\ncodemcp-id: abc-123"
        )

    def test_append_to_existing_metadata(self):
        """Test appending metadata to a message with existing metadata."""
        message = """feat: Add feature

Description

Signed-off-by: User <user@example.com>"""
        new_message = append_metadata_to_message(message, {"codemcp-id": "abc-123"})
        self.assertEqual(
            new_message,
            """feat: Add feature

Description

Signed-off-by: User <user@example.com>
codemcp-id: abc-123""",
        )

    def test_append_to_existing_metadata_with_trailing_newline(self):
        """Test appending metadata to a message with existing metadata and trailing newline."""
        message = """feat: Add feature

Description

Signed-off-by: User <user@example.com>
"""
        new_message = append_metadata_to_message(message, {"codemcp-id": "abc-123"})
        self.assertEqual(
            new_message,
            """feat: Add feature

Description

Signed-off-by: User <user@example.com>
codemcp-id: abc-123""",
        )

    def test_append_to_message_with_trailing_newlines(self):
        """Test appending metadata to a message with trailing newlines."""
        message = """feat: Add feature

Description

"""
        new_message = append_metadata_to_message(message, {"codemcp-id": "abc-123"})
        self.assertEqual(
            new_message,
            """feat: Add feature

Description

codemcp-id: abc-123""",
        )

    def test_append_to_message_with_double_trailing_newlines(self):
        """Test appending metadata to a message with double trailing newlines."""
        message = """feat: Add feature

Description


"""
        new_message = append_metadata_to_message(message, {"codemcp-id": "abc-123"})
        self.assertEqual(
            new_message,
            """feat: Add feature

Description


codemcp-id: abc-123""",
        )

    def test_update_existing_metadata(self):
        """Test updating existing codemcp-id in a message."""
        message = """feat: Add feature

Description

codemcp-id: old-id"""
        new_message = append_metadata_to_message(message, {"codemcp-id": "new-id"})
        # With our new implementation, we just append the new ID at the end
        self.assertEqual(
            new_message,
            """feat: Add feature

Description

codemcp-id: old-id
codemcp-id: new-id""",
        )

    def test_meta_ignored_except_codemcp_id(self):
        """Test that only codemcp-id is processed from the metadata."""
        message = "feat: Add feature"
        new_message = append_metadata_to_message(message, {"other-key": "value"})
        # Without codemcp-id, the message should be unchanged
        self.assertEqual(new_message, "feat: Add feature")


if __name__ == "__main__":
    unittest.main()
