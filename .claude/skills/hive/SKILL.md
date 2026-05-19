```markdown
# hive Development Patterns

> Auto-generated skill from repository analysis

## Overview
This skill teaches the core development patterns and conventions used in the `hive` Python codebase. It covers file naming, import/export styles, commit message conventions, and testing patterns. By following these guidelines, contributors can write code that is consistent, maintainable, and easy to review.

## Coding Conventions

### File Naming
- Use **camelCase** for all file names.
  - Example: `dataProcessor.py`, `userManager.py`

### Import Style
- Use **relative imports** within the package.
  - Example:
    ```python
    from .utils import parseData
    from ..models import User
    ```

### Export Style
- Use **named exports** (i.e., explicitly define what is exported).
  - Example:
    ```python
    def processData(data):
        # function code

    __all__ = ['processData']
    ```

### Commit Messages
- Use **conventional commit** format.
- Prefix with `fix` for bug fixes.
- Keep messages concise (average ~75 characters).
  - Example:
    ```
    fix: handle edge case in dataProcessor when input is empty
    ```

## Workflows

### Bug Fix Workflow
**Trigger:** When you need to fix a bug in the codebase  
**Command:** `/fix-bug`

1. Create a new branch for your fix.
2. Make code changes following coding conventions.
3. Write or update tests in corresponding `*.test.*` files.
4. Commit with a message starting with `fix:`.
5. Push your branch and open a pull request.

### Add Feature Workflow
**Trigger:** When implementing a new feature  
**Command:** `/add-feature`

1. Create a new branch for your feature.
2. Add new files using camelCase naming.
3. Use relative imports and named exports.
4. Write or update tests in `*.test.*` files.
5. Commit changes with a clear, conventional message.
6. Push and open a pull request.

## Testing Patterns

- Test files follow the pattern `*.test.*` (e.g., `dataProcessor.test.py`).
- The specific test framework is not specified; use standard Python testing practices.
- Place tests alongside or near the code they test.
- Example test file structure:
  ```python
  # dataProcessor.test.py
  from .dataProcessor import processData

  def test_processData_empty_input():
      assert processData([]) == []
  ```

## Commands
| Command      | Purpose                                 |
|--------------|-----------------------------------------|
| /fix-bug     | Start the bug fix workflow              |
| /add-feature | Start the add feature workflow          |
```
