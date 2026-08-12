---
name: docstring-style
description: How to write docstrings for a new function or module - use when asked to document code.
---
When writing a docstring:

- One line summarizing what the function does, in the imperative
  ("Return the sum of a and b", not "Returns the sum" or "This function
  returns...").
- Only add more than one line if there's something non-obvious to say: a
  hidden constraint, a unit, a raised exception, an edge case. A
  well-named function with plain arguments needs nothing more than the
  one-line summary.
- Don't restate the function signature in prose ("Takes a and b and
  returns their sum") - the signature already says that.
- Document raised exceptions explicitly if the caller needs to handle
  them, e.g. "Raises ValueError if b is zero."
