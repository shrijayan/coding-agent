---
name: pytest-conventions
description: How to write pytest tests for this task - use when creating or reviewing a test file.
---
When writing pytest tests:

- One test function per behavior, not one giant test per module. A function
  with 3 responsibilities (e.g. add, subtract, and the divide-by-zero case)
  should be 3 separate `test_*` functions, so a single failure tells you
  exactly which behavior broke.
- Structure each test as arrange - act - assert: set up inputs, call the
  function once, then assert on the result. Don't interleave calls and
  assertions.
- Name tests after the behavior, not the function: `test_add_returns_sum`,
  not `test_add`.
- For an expected error (e.g. division by zero raising `ValueError`), use
  `pytest.raises(ExceptionType)` as a context manager around the one call
  that should raise - never a bare `try/except` with a manual `assert False`
  in the `else` branch.
- Keep each test independent - no shared mutable state between tests, no
  relying on test execution order.
