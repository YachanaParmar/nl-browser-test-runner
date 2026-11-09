
import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from playwright.sync_api import sync_playwright, expect
from planner import ai_plan, rule_plan, validate


def locate(page, target):
    """Locate interactive elements using accessible names and labels."""
    candidates = [
        page.get_by_role("button", name=target, exact=True),
        page.get_by_role("link", name=target, exact=True),
        page.get_by_label(target, exact=True),
        page.get_by_placeholder(target, exact=True),
        page.locator("input[type='submit']").filter(
            has_not=page.locator("nonexistent-element")
        ) if target.lower() == "login" else page.locator(
            "nonexistent-element"
        ),
        page.get_by_role("textbox", name=target, exact=True),
        page.get_by_role("combobox", name=target, exact=True),
    ]

    for locator in candidates:
        count = locator.count()

        visible = [
            locator.nth(i)
            for i in range(count)
            if locator.nth(i).is_visible()
        ]

        if len(visible) == 1:
            return visible[0]

        if len(visible) > 1:
            raise ValueError(
                f"Ambiguous target '{target}': "
                f"{len(visible)} matching elements"
            )

    raise ValueError(
        f"Could not locate '{target}'"
    )

def perform(page, step):
    action = step["action"]

    if action == "navigate":
        page.goto(
            step["url"],
            wait_until="domcontentloaded"
        )
        return

    if action == "assert_text":
        expect(page.locator("body")).to_contain_text(
            step["value"],
            timeout=10000
        )
        return

    if action == "assert_url":
        if step["value"] not in page.url:
            raise AssertionError(
                f"URL {page.url!r} does not contain "
                f"{step['value']!r}"
            )
        return

    locator = locate(page, step["target"])

    if action == "fill":
        locator.fill(step["value"])

        if locator.input_value() != step["value"]:
            raise AssertionError(
                "Filled value did not persist"
            )

    elif action == "click":
        locator.click()

    elif action == "select":
        try:
            locator.select_option(
                label=step["value"],
                timeout=3000
            )
        except Exception:
            locator.select_option(
                value=step["value"]
            )

    elif action == "check":
        locator.check()

    elif action == "assert_visible":
        expect(locator).to_be_visible()

    else:
        raise ValueError(
            f"Unsupported action {action}"
        )


def execute(actions, headless=True, report_dir="reports"):
    output = Path(report_dir)
    output.mkdir(
        parents=True,
        exist_ok=True
    )

    report = {
        "started_at": datetime.now(
            timezone.utc
        ).isoformat(),
        "status": "passed",
        "steps": []
    }

    with sync_playwright() as p:
        # Use installed Google Chrome.
        # No Chromium download is required.
        browser = p.chromium.launch(
            channel="chrome",
            headless=headless
        )

        page = browser.new_page()
        page.set_default_timeout(10000)

        try:
            for index, step in enumerate(
                validate(actions), 1
            ):
                result = {
                    "number": index,
                    "step": step,
                    "status": "passed"
                }

                try:
                    perform(page, step)

                except Exception as exc:
                    result["status"] = "failed"
                    result["error"] = str(exc)
                    report["status"] = "failed"

                    report["steps"].append(result)

                    try:
                        page.screenshot(
                            path=str(
                                output / "failure.png"
                            ),
                            full_page=True
                        )
                    except Exception:
                        pass

                    break

                report["steps"].append(result)

        finally:
            browser.close()

    report["finished_at"] = datetime.now(
        timezone.utc
    ).isoformat()

    (output / "report.json").write_text(
        json.dumps(report, indent=2),
        encoding="utf-8"
    )

    return report


def main():
    parser = argparse.ArgumentParser(
        description="Natural-language browser test runner"
    )

    group = parser.add_mutually_exclusive_group(
        required=True
    )

    group.add_argument(
        "--instruction",
        help="Plain-English steps separated by semicolons"
    )

    group.add_argument(
        "--file",
        help="Read instructions from a text file"
    )

    group.add_argument(
        "--plan",
        help="Read a structured JSON plan"
    )

    parser.add_argument(
        "--ai",
        action="store_true",
        help="Use AI to plan instructions"
    )

    parser.add_argument(
        "--headed",
        action="store_true",
        help="Show the Chrome browser"
    )

    parser.add_argument(
        "--report-dir",
        default="reports"
    )

    args = parser.parse_args()

    try:
        if args.plan:
            data = json.loads(
                Path(args.plan).read_text(
                    encoding="utf-8"
                )
            )

            actions = validate(
                data["actions"]
                if isinstance(data, dict)
                else data
            )

        else:
            instruction = (
                args.instruction
                or Path(args.file).read_text(
                    encoding="utf-8"
                )
            )

            actions = (
                ai_plan(instruction)
                if args.ai
                else rule_plan(instruction)
            )

        print(
            "PLAN:",
            json.dumps(actions, indent=2)
        )

        result = execute(
            actions,
            headless=not args.headed,
            report_dir=args.report_dir
        )

        for step in result["steps"]:
            print(
                f"{step['status'].upper()}: "
                f"{step['number']} "
                f"{step['step']['action']}"
            )

            if "error" in step:
                print("  ", step["error"])

        print(
            "RESULT:",
            result["status"].upper()
        )

        print(
            "Report:",
            str(
                Path(args.report_dir)
                / "report.json"
            )
        )

        return (
            0
            if result["status"] == "passed"
            else 1
        )

    except Exception as exc:
        print("ERROR:", exc)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
