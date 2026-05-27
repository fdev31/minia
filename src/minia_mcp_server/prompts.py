"""MCP prompt definitions."""

from .mcp_instance import mcp


@mcp.prompt()
def research_topic(topic: str) -> str:
    """Generate a research prompt for a given topic."""
    return f"""
    # Role
    You are a senior research analyst.

    # Task
    Conduct a comprehensive research report on the topic: "{topic}".

    # Steps
    1. **Search**: Use the `base:search_web` tool to find the top 5 most relevant articles.
    2. **Read**: Use the `base:read_web_page` tool to read the content of the top 3 results.
    3. **Synthesize**: Combine the information from the sources to create a detailed report.

    # Output Format
    Provide a structured report with:
    - **Executive Summary**: A 2-3 sentence overview.
    - **Key Findings**: Bullet points of the most important information.
    - **Sources**: A list of URLs used.
    - **Conclusion**: A final summary thought.

    # Constraints
    - Only use information from the provided search results.
    - If sources conflict, note the discrepancy.
    - Keep the tone objective and professional.
    """


@mcp.prompt()
def code_review(file_path: str, focus_area: str = "general") -> str:
    """Generate a code review prompt for a specific file."""
    return f"""
    # Role
    You are a senior software engineer specializing in {focus_area}.

    # Task
    Perform a code review on the file located at: "{file_path}".

    # Steps
    1. **Read**: Use the `{file_path}` resource to read the file content.
    2. **Analyze**: Review the code specifically for issues related to "{focus_area}".
    3. **Suggest**: Provide specific code snippets or recommendations for improvement.

    # Output Format
    Provide a structured review with:
    - **Overall Assessment**: A brief summary of the code quality.
    - **Critical Issues**: Any bugs or security vulnerabilities.
    - **Improvements**: Suggestions for better performance or readability.
    - **Refactored Snippets**: Code examples showing how to fix issues.

    # Constraints
    - Be constructive and specific.
    - Do not rewrite the entire file, just focus on the issues.
    """


@mcp.prompt()
def generate_doc(file_path: str) -> str:
    """Generate documentation for a code file."""
    return f"""
    # Role
    You are a senior software engineer specializing in documentation.

    # Task
    Generate documentation for the file located at: "{file_path}".

    # Steps
    1. **Read**: Use the `{file_path}` resource to read the file content.
    2. **Analyze**: Identify the main functions, classes, and their docstrings.
    3. **Generate**: Create a markdown documentation.

    # Output Format
    Provide a markdown document with:
    - **Overview**: A brief description of the file's purpose.
    - **Functions**: List of functions with their docstrings.
    - **Classes**: List of classes with their docstrings.
    - **Usage Examples**: If applicable, show how to use the main functions/classes.

    # Constraints
    - Use only the information from the file.
    - If there are no docstrings, generate a brief description based on the code structure.
    """
