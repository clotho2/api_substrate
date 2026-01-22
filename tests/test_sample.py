"""
Sample tests for demonstrating Level 3 test execution.
"""
import pytest


def test_basic_pass():
    """Test that always passes."""
    assert True
    assert 1 + 1 == 2


def test_string_operations():
    """Test string operations."""
    text = "Hello, Agent!"
    assert "Agent" in text
    assert text.startswith("Hello")
    assert text.endswith("!")


def test_list_operations():
    """Test list operations."""
    numbers = [1, 2, 3, 4, 5]
    assert len(numbers) == 5
    assert sum(numbers) == 15
    assert max(numbers) == 5


def test_dict_operations():
    """Test dictionary operations."""
    data = {"name": "Agent", "role": "AI"}
    assert data["name"] == "Agent"
    assert "role" in data
    assert len(data) == 2


@pytest.mark.skip(reason="Demo of skipped test")
def test_skipped():
    """This test is intentionally skipped."""
    assert False  # Would fail if run


def test_intentional_failure():
    """This test intentionally fails to demonstrate failure reporting."""
    # Comment out the failure to make tests pass
    # assert False, "This is an intentional failure for demonstration"
    pass  # Passing for now
