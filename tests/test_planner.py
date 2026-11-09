import pytest
from planner import rule_plan, validate

def test_rule_plan():
    result = rule_plan("Open https://example.com; Enter Alex into First Name; Click Submit; Verify page contains Welcome Alex")
    assert [x["action"] for x in result] == ["navigate", "fill", "click", "assert_text"]

def test_unknown_instruction_fails():
    with pytest.raises(ValueError): rule_plan("Do something magical")

def test_invalid_action_fails():
    with pytest.raises(ValueError): validate([{"action": "execute_js", "target": "page"}])
