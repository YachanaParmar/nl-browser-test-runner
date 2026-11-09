# Natural Language Browser Test Runner

A Python and Playwright browser automation framework that converts natural-language test instructions into executable browser actions.

## Features
- Rule-based natural-language instruction parsing
- Browser automation using Playwright and Google Chrome
- Form filling, clicking, selecting, and assertions
- JSON execution reports
- Failure screenshots
- Optional Groq-based AI planner (not verified due to API authentication issues)

## Installation
pip install -r requirements.txt

Google Chrome must be installed.

## Run

py runner.py --instruction "Open https://www.saucedemo.com/; Enter standard_user into Username; Enter secret_sauce into Password; Click Login; Verify page contains Products" --headed

## Negative Test

py runner.py --instruction "Open https://www.saucedemo.com/; Verify page contains ThisTextShouldNeverExist12345" --headed

## Results
- Local HTML form: PASSED
- SauceDemo login: PASSED
- Negative assertion: Correctly FAILED
- JSON reporting: Verified
- Failure screenshot: Verified

## Approach
Natural-language instructions are converted into structured actions. Playwright resolves elements using accessible labels, roles, and placeholders, executes the actions, and records results.

## Limitations
- Rule-based mode requires supported instruction patterns.
- AI planning requires a valid Groq API key and was not successfully tested.
- Ambiguous element names can cause locator failures.
- The browser runner requires Google Chrome.
