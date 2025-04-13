Look at codemcp.toml for a system prompt, as well as how to run various commands.

CodeMCP: Detailed Overview
CodeMCP is a tool that integrates Claude AI with your local development environment, allowing Claude to directly modify code in your Git repositories. It acts as a bridge between the Claude Desktop application and your local filesystem, enabling Claude to read, write, and edit files, run commands, and make commits to Git repositories.
Architecture and Core Components
CodeMCP follows a client-server architecture:

MCP Server: The main server component that runs in the background and processes requests from Claude Desktop.
Tools: A collection of specialized functions that Claude can use to interact with your filesystem and repositories:

ReadFile: Reads content from files
WriteFile: Creates or overwrites files
EditFile: Makes targeted changes to specific parts of files
LS: Lists files and directories
Glob: Finds files matching patterns
Grep: Searches for text patterns in files
RunCommand: Executes predefined commands (like format, test, lint)
RM: Removes files
InitProject: Initializes a project for use with CodeMCP
Think: Allows Claude to "think" about a problem and log that thinking
UserPrompt: Records user prompts in the Git commit history
Chmod: Changes file permissions


Git Integration: CodeMCP makes extensive use of Git:

Every change is committed to Git for tracking and safety
Special Git references are used to track changes by chat session
Changes are committed with detailed messages that include the chat ID


Project Configuration: Each project has a codemcp.toml file that contains:

Project-specific instructions for Claude
Custom commands that Claude can run (like formatting, testing, linting)
Other configuration options



Key Workflows
Project Initialization

When you tell Claude "Initialize codemcp with /path/to/project", the init_project tool is invoked.
CodeMCP verifies the path exists and is a Git repository with a codemcp.toml file.
It generates a unique chat ID for this session (e.g., "1-feat-new-feature").
It creates a special Git commit reference (stored in refs/codemcp/[chat_id]) that contains the user's initial prompt.
It reads the project configuration from codemcp.toml and constructs a system prompt for Claude that includes:

General instructions for using the tools
Project-specific instructions from the codemcp.toml file
Available commands from the commands section of codemcp.toml



File Editing

When Claude uses the EditFile tool:

It first checks if the file exists and is tracked by Git
It verifies the old_string is unique within the file
It replaces the old_string with the new_string
It commits the change to Git, using the chat ID to amend the existing commit


CodeMCP has sophisticated algorithms to handle various edge cases:

Normalizing line endings
Dealing with whitespace differences
Finding similar files if a file doesn't exist
Applying edits when exact matches fail using fuzzy matching



Git Commit Behavior

For the first edit in a chat session:

CodeMCP looks for the reference commit created during initialization
It creates a new commit with the same message but the current tree state
This becomes the "working commit" for this chat session


For subsequent edits:

CodeMCP amends the existing commit rather than creating new ones
It updates the commit message to include the new edit description
It preserves the chat ID in the commit message


This approach means one chat = one Git commit, making it easy to review changes.

Safety Features

Git Integration: All changes are tracked in Git, so you can always roll back unwanted changes.
Limited Actions: Claude can only perform specifically defined actions through the provided tools.
File Tracking: Files must be in a Git repository and tracked by Git before they can be modified.
Edit Verification: When editing files, CodeMCP ensures changes are applied properly:

Old text must be uniquely identifiable
Changes are verified before being committed
Robust error handling for failed edits



Configuration Details
The codemcp.toml file can include:

project_prompt: Custom instructions for Claude specific to your project.
commands section: Defines commands that Claude can run, like:
toml[commands]
format = ["./run_format.sh"]
test = ["./run_test.sh"]
lint = ["./run_lint.sh"]

Custom documentation for commands:
toml[commands.test]
command = ["./run_test.sh"]
doc = "Accepts a pytest-style test selector as an argument to run a specific test."


Key Implementation Details

Error Handling: The codebase has robust error handling to prevent issues like:

Attempts to edit non-existent files
Ambiguous edits that might match multiple locations
Files that have been modified since they were last read


Line Ending Management: CodeMCP detects and preserves the line ending style of each file.
Chat ID Persistence: The chat ID is stored in Git commits, allowing CodeMCP to identify which commits belong to which chat sessions.
Dynamic Tool Registry: Tools are registered dynamically, making it easy to add new tools.
GitOps Approach: All operations are Git-centric, ensuring every change is tracked and reversible.

Usage Flow

You create a codemcp.toml file in your Git repository.
You tell Claude "Initialize codemcp with /path/to/repository".
Claude initializes the project and gains access to the tools.
You describe what changes you want Claude to make.
Claude:

Explores the codebase using tools like ReadFile, LS, Glob, Grep
Makes changes using WriteFile or EditFile
Runs commands like format, test, or lint to verify changes
Commits all changes to Git


You can review the changes and continue the conversation with Claude.

This architecture allows Claude to directly modify your codebase while maintaining safety through Git integration and providing a seamless experience for code modification.
