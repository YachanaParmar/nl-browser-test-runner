
import json
import os
import re
from urllib.parse import urlparse

from openai import OpenAI


ALLOWED_ACTIONS = {
    "navigate",
    "fill",
    "click",
    "select",
    "check",
    "assert_text",
    "assert_url",
    "assert_visible",
}

VALUE_ACTIONS = {
    "fill",
    "select",
    "assert_text",
    "assert_url",
}

TARGET_ACTIONS = {
    "fill",
    "click",
    "select",
    "check",
    "assert_visible",
}

SYSTEM_PROMPT = """
You are a browser test planning assistant.

Convert the user's natural-language browser test
instructions into a JSON execution plan.

Return only valid JSON in this format:

{
  "actions": [
    {
      "action": "navigate",
      "url": "https://example.com"
    },
    {
      "action": "fill",
      "target": "Username",
      "value": "demo"
    },
    {
      "action": "click",
      "target": "Login"
    },
    {
      "action": "assert_text",
      "target": "page",
      "value": "Welcome"
    }
  ]
}

Allowed actions:
- navigate: requires url
- fill: requires target and value
- click: requires target
- select: requires target and value
- check: requires target
- assert_text: requires value, target must be page
- assert_url: requires value, target must be page
- assert_visible: requires target

Rules:
1. Preserve the order of the requested operations.
2. Never invent credentials, URLs, or expected results.
3. Use visible labels and accessible names as targets.
4. Use exact values supplied by the user.
5. Do not invent CSS selectors or XPath expressions.
6. Do not add unrequested browser actions.
7. If the user requests a page-level text assertion,
   use assert_text.
8. If the user requests an element visibility check,
   use assert_visible with its visible label.
9. If an instruction cannot be represented safely,
   return an error object explaining why.
10. Never generate Python, JavaScript, or shell commands.
"""


def validate(actions):
    """Validate a structured execution plan."""
    if not isinstance(actions, list):
        raise ValueError("Plan must be a list of actions")

    if not actions:
        raise ValueError("Plan contains no actions")

    if len(actions) > 30:
        raise ValueError("Maximum 30 actions allowed")

    cleaned = []

    for index, step in enumerate(actions, 1):
        if not isinstance(step, dict):
            raise ValueError(
                f"Step {index} must be a JSON object"
            )

        action = step.get("action")

        if action not in ALLOWED_ACTIONS:
            raise ValueError(
                f"Step {index}: unsupported action {action!r}"
            )

        item = {"action": action}

        if action == "navigate":
            url = step.get("url")

            if not isinstance(url, str) or not url.strip():
                raise ValueError(
                    f"Step {index}: URL is required"
                )

            url = url.strip()
            parsed = urlparse(url)

            if parsed.scheme not in {"http", "https", "file"}:
                raise ValueError(
                    f"Step {index}: unsupported URL scheme"
                )

            if parsed.scheme in {"http", "https"} and not parsed.netloc:
                raise ValueError(
                    f"Step {index}: invalid website URL"
                )

            item["url"] = url

        if action in TARGET_ACTIONS:
            target = step.get("target")

            if not isinstance(target, str) or not target.strip():
                raise ValueError(
                    f"Step {index}: target is required"
                )

            item["target"] = target.strip()

        if action in VALUE_ACTIONS:
            value = step.get("value")

            if not isinstance(value, str) or not value.strip():
                raise ValueError(
                    f"Step {index}: value is required"
                )

            item["value"] = value.strip()

        if action in {"assert_text", "assert_url"}:
            item["target"] = "page"

        cleaned.append(item)

    return cleaned


def rule_plan(instruction):
    """
    Simple deterministic planner for the supported
    semicolon-separated command syntax.
    """
    if not isinstance(instruction, str) or not instruction.strip():
        raise ValueError("Instructions cannot be empty")

    actions = []

    parts = [
        part.strip()
        for part in instruction.split(";")
        if part.strip()
    ]

    for part in parts:
        match = re.fullmatch(
            r"(?:Open|Visit|Navigate to)\s+(\S+)",
            part,
            flags=re.IGNORECASE,
        )

        if match:
            actions.append({
                "action": "navigate",
                "url": match.group(1),
            })
            continue

        match = re.fullmatch(
            r"(?:Enter|Type|Fill)\s+(.+?)\s+into\s+(.+)",
            part,
            flags=re.IGNORECASE,
        )

        if match:
            actions.append({
                "action": "fill",
                "target": match.group(2).strip(),
                "value": match.group(1).strip(),
            })
            continue

        match = re.fullmatch(
            r"Select\s+(.+?)\s+from\s+(.+)",
            part,
            flags=re.IGNORECASE,
        )

        if match:
            actions.append({
                "action": "select",
                "target": match.group(2).strip(),
                "value": match.group(1).strip(),
            })
            continue

        match = re.fullmatch(
            r"Click\s+(?:on\s+)?(.+)",
            part,
            flags=re.IGNORECASE,
        )

        if match:
            actions.append({
                "action": "click",
                "target": match.group(1).strip(),
            })
            continue

        match = re.fullmatch(
            r"Check\s+(.+)",
            part,
            flags=re.IGNORECASE,
        )

        if match:
            actions.append({
                "action": "check",
                "target": match.group(1).strip(),
            })
            continue

        match = re.fullmatch(
            r"Verify\s+page\s+contains\s+(.+)",
            part,
            flags=re.IGNORECASE,
        )

        if match:
            actions.append({
                "action": "assert_text",
                "target": "page",
                "value": match.group(1).strip(),
            })
            continue

        match = re.fullmatch(
            r"Verify\s+URL\s+contains\s+(.+)",
            part,
            flags=re.IGNORECASE,
        )

        if match:
            actions.append({
                "action": "assert_url",
                "target": "page",
                "value": match.group(1).strip(),
            })
            continue

        match = re.fullmatch(
            r"Verify\s+(.+?)\s+is\s+visible",
            part,
            flags=re.IGNORECASE,
        )

        if match:
            actions.append({
                "action": "assert_visible",
                "target": match.group(1).strip(),
            })
            continue

        raise ValueError(
            f"Rule planner cannot understand: {part!r}. "
            "Use --ai for flexible instructions."
        )

    return validate(actions)


def ai_plan(instruction):
    """Generate browser actions using Groq."""
    if not isinstance(instruction, str) or not instruction.strip():
        raise ValueError("Instructions cannot be empty")

    api_key = os.environ.get("GROQ_API_KEY")

    if not api_key:
        raise ValueError(
            "GROQ_API_KEY is not configured. "
            "Set it in PowerShell before using --ai."
        )

    model = os.environ.get(
        "GROQ_MODEL",
        "llama-3.3-70b-versatile"
    )

    client = OpenAI(
        api_key=api_key,
        base_url="https://api.groq.com/openai/v1",
        timeout=45.0,
        max_retries=2,
    )

    response = client.chat.completions.create(
        model=model,
        temperature=0,
        response_format={"type": "json_object"},
        messages=[
            {
                "role": "system",
                "content": SYSTEM_PROMPT,
            },
            {
                "role": "user",
                "content": instruction,
            },
        ],
    )

    content = response.choices[0].message.content

    if not content:
        raise ValueError(
            "Groq returned an empty planning response"
        )

    try:
        data = json.loads(content)
    except json.JSONDecodeError as exc:
        raise ValueError(
            "Groq returned invalid JSON"
        ) from exc

    if not isinstance(data, dict):
        raise ValueError(
            "Groq response must be a JSON object"
        )

    if "error" in data:
        raise ValueError(
            f"Groq could not plan this test: {data['error']}"
        )

    if "actions" not in data:
        raise ValueError(
            "Groq response is missing 'actions'"
        )

    return validate(data["actions"])
