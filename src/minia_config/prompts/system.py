"""System-level prompts."""

SUMMARY_PROMPT = """Summarize the conversation history below using the following structured format. Preserve all important context, decisions, and references.

# Long term goal

What is the goal of our ongoing session

# Reasoning

How we are planning to achieve this goal

# Remaining steps

- list of items to be done

# Remarks and pitfalls

Important items to highlight

# Relevant data

Reference to files and resources, with relevant snippets or explanations

---

Conversation history:
"""

WORKER_SUGGESTED_TOOL = """Suggested tool: {suggested_tool}.
Use this as a starting point, but feel free to use other tools if the task requires it."""

TOOL_RESULT_SNIPPETS: dict[str, str] = {
    "yaml": """Tool results are returned in YAML format:

  status: success
  tool_name: listDir
  content: |
    actual result here

- status: success → process content, move on
- status: error → try a different tool
- truncated: true → use a more specific query""",
    "xml": """Tool results are returned as XML with `<status>` and `<content>` tags. Always check `<status>` first:

- **`<status>success</status>`**: The tool call completed. Process the `<content>` and move on to the next step. Do NOT retry the same tool.
- **`<status>error</status>`**: The tool call failed. Try a DIFFERENT tool or a different approach. Never retry the same tool with the same parameters.
- **`<truncated>` present**: The result was cut off. Use a more specific query to narrow the results. Do NOT repeat the same call.""",
    "json": """Tool results are returned as JSON with `status`, `content`, and optional `truncated` fields. Always check `status` first:

- `"status": "success"` → process `content` and move on. Do NOT retry the same tool.
- `"status": "error"` → try a DIFFERENT tool or a different approach. Never retry the same tool with the same parameters.
- `"truncated": true` → the result was cut off. Use a more specific query to narrow the results. Do NOT repeat the same call.""",
}


def get_tool_result_snippet(fmt: str = "yaml") -> str:
    return TOOL_RESULT_SNIPPETS.get(fmt, TOOL_RESULT_SNIPPETS["yaml"])
