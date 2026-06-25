#!/usr/bin/env python3
"""
error_explainer.py — Translate error messages into plain explanations and fix suggestions.

Takes any error message, traceback text, or log snippet and produces:
  - Problem:   clear explanation of what went wrong
  - Probable cause:  what triggered it
  - Fix:       numbered actionable steps
  - Related:   similar known errors

Recognized error patterns:
  - Python exceptions (ModuleNotFoundError, ImportError, SyntaxError, TypeError, etc.)
  - Filesystem errors (ENOENT, EACCES, EEXIST, ENOTDIR, etc.)
  - npm / Node.js errors
  - Git errors
  - TypeScript / tsc errors (2307, 2322, 2554, 7016, etc.)
  - Rust panics / compiler errors
  - JSON / YAML parse errors
  - Network errors (ECONNREFUSED, ETIMEDOUT, ENOTFOUND, etc.)
  - Docker / container errors
  - Common toolchain errors (pip, cargo, go, etc.)

Usage:
    python error_explainer.py <message>
    python error_explainer.py <message> --json
    echo "error text" | python error_explainer.py
    python error_explainer.py --help
"""

__maker__ = "SmokerGreenOG"

import _protect
import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

EXIT_OK = 0
EXIT_ISSUES = 1  # recognised error — explanation returned
EXIT_ERROR = 2  # script error or unrecognised input

MAX_INPUT_LENGTH = 10_000


# ---------------------------------------------------------------------------
# Pattern definitions
# ---------------------------------------------------------------------------

# Each pattern is a (compiled_regex, label, explain_fn) tuple.
# explain_fn(text, match) -> dict with keys: problem, cause, fix (list), related (list)


def _make_fix(*steps: str) -> list[str]:
    """Numbered fix steps."""
    return [f"{i}. {s}" for i, s in enumerate(steps, 1)]


# ── Python module/import errors ──────────────────────────────────────────


def _explain_modulenotfound(text: str, m: re.Match) -> dict[str, Any]:
    """explain modulenotfound.

    Args:
        text: Description.
        m: Description.

    Returns:
        Description.
    """
    mod = m.group(1)
    return {
        "problem": (
            f"Python cannot find the module '{mod}' —"
            f" it is not installed or not on the import path."
        ),
        "cause": (
            f"The import statement tried to load '{mod}',"
            f" but Python's search paths don't contain it."
        ),
        "fix": _make_fix(
            f"Install the missing package: `pip install {mod}` or `uv pip install {mod}`",
            f"If it's a local module, make sure `__init__.py` exists in the package directory and the parent is on sys.path.",
            f"Check for typos: did you mean a different name? (e.g. 'pil' should be 'Pillow')",
            f"Verify the module is installed: `pip list | grep -i {mod}`",
        ),
        "related": [
            "ImportError",
            "ModuleNotFoundError (no module named ...)",
            "pip install failures",
        ],
    }


def _explain_importerror(text: str, m: re.Match) -> dict[str, Any]:
    """explain importerror.

    Args:
        text: Description.
        m: Description.

    Returns:
        Description.
    """
    details = m.group(1) or "could not be imported"
    return {
        "problem": f"An import failed: {details}",
        "cause": (
            "The module was found but something went wrong while loading it — circular import, missing"
            "dependency inside the module, or an AttributeError at import time."
        ),
        "fix": _make_fix(
            "Check for circular imports: module A imports B which imports A.",
            "Ensure all sub-dependencies of the module are installed.",
            "Run the import in a Python REPL to see the full traceback: `python -c 'import <module>'`",
            "Look for syntax errors or missing attributes inside the imported module.",
        ),
        "related": ["ModuleNotFoundError", "CircularImportError", "AttributeError during import"],
    }


# ── Python syntax / runtime errors ───────────────────────────────────────


def _explain_syntaxerror(text: str, m: re.Match) -> dict[str, Any]:
    """explain syntaxerror.

    Args:
        text: Description.
        m: Description.

    Returns:
        Description.
    """
    # Two patterns: one with line number, one without
    line_raw = None
    detail = "invalid syntax"
    try:
        line_raw = m.group(2)  # pattern 1: (msg)(line)
        detail = (m.group(1) or "").strip()
    except IndexError:
        detail = (m.group(1) or "invalid syntax").strip()
    if not detail:
        detail = "invalid syntax"
    lineno = ""
    if line_raw:
        lineno = f" (around line {line_raw.strip()})"
    return {
        "problem": f"Python found invalid syntax{lineno}: {detail}",
        "cause": (
            "The code does not follow Python grammar — missing colon, unmatched bracket, string not"
            "closed, etc."
        ),
        "fix": _make_fix(
            f"Check line {line_raw.strip() if line_raw else 'indicated'} for the exact position ^.",
            (
                "Common causes: missing `:` after `if`/`for`/`def`/`class`,"
                "unmatched `(`/`[`/`{`, unclosed string literal."
            ),
            "Look for mixed tabs and spaces — Python 3 disallows mixing them.",
            "Use a linter: `python -m py_compile yourfile.py` or `ruff check yourfile.py`",
        ),
        "related": ["IndentationError", "TabError", "SyntaxError: unexpected EOF while parsing"],
    }


def _explain_typeerror(text: str, m: re.Match) -> dict[str, Any]:
    """explain typeerror.

    Args:
        text: Description.
        m: Description.

    Returns:
        Description.
    """
    detail = m.group(1) or "type mismatch"
    return {
        "problem": f"TypeError: {detail.strip()}",
        "cause": (
            "An operation was applied to a value of the wrong type — e.g. calling a non-function,"
            "indexing a number, concatenating string + int."
        ),
        "fix": _make_fix(
            "Print `type(variable)` on each operand to see what you're actually working with.",
            "Add type hints and use `mypy` or `pyright` to catch mismatches statically.",
            "Check for `None` being returned from a function that you expected to return a value.",
            "Use `isinstance()` guards before operations if the type can vary.",
        ),
        "related": ["ValueError", "AttributeError", "TypeError: unsupported operand type(s)"],
    }


def _explain_valueerror(text: str, m: re.Match) -> dict[str, Any]:
    """explain valueerror.

    Args:
        text: Description.
        m: Description.

    Returns:
        Description.
    """
    detail = m.group(1) or "invalid value"
    return {
        "problem": f"ValueError: {detail.strip()}",
        "cause": (
            "A function received a value with the right type but an inappropriate value — e.g."
            "negative sqrt, empty list where data expected."
        ),
        "fix": _make_fix(
            "Validate inputs before passing them to functions that have constraints.",
            "Add try/except around the call to catch and handle the ValueError gracefully.",
            "Check that data sources (files, APIs, user input) aren't empty or malformed.",
        ),
        "related": ["TypeError", "AssertionError", "IndexError"],
    }


def _explain_attributeerror(text: str, m: re.Match) -> dict[str, Any]:
    """explain attributeerror.

    Args:
        text: Description.
        m: Description.

    Returns:
        Description.
    """
    detail = m.group(1) or "object has no attribute"
    return {
        "problem": f"AttributeError: {detail.strip()}",
        "cause": (
            "Tried to access a method or property that doesn't exist"
            "on the object — typo, wrong type, or missing import."
        ),
        "fix": _make_fix(
            "Check the spelling of the attribute/method name.",
            "Verify the object's type with `type(obj)` and `dir(obj)` to see what's available.",
            "If it's a library object, check the documentation for the correct API.",
            "A variable might be `None` when you expected a real object — trace where it got assigned.",
        ),
        "related": ["TypeError: 'NoneType' object has no attribute", "NameError"],
    }


def _explain_nameerror(text: str, m: re.Match) -> dict[str, Any]:
    """explain nameerror.

    Args:
        text: Description.
        m: Description.

    Returns:
        Description.
    """
    name = m.group(1) or "variable"
    return {
        "problem": f"NameError: name '{name}' is not defined",
        "cause": f"The name '{name}' was used but never assigned or imported in the current scope.",
        "fix": _make_fix(
            f"Check for typos in '{name}' — is it spelled correctly?",
            f"Make sure '{name}' is imported (if from another module) or assigned before use.",
            f"Check variable scope — it might be defined inside a function/block that hasn't run yet.",
            f"If it's from an external package, verify the import statement is correct.",
        ),
        "related": ["AttributeError", "UnboundLocalError", "ImportError"],
    }


def _explain_indexerror(text: str, m: re.Match) -> dict[str, Any]:
    """explain indexerror.

    Args:
        text: Description.
        m: Description.

    Returns:
        Description.
    """
    return {
        "problem": "IndexError: list index out of range",
        "cause": "Tried to access an element at an index that doesn't exist in the list/tuple.",
        "fix": _make_fix(
            "Check the list length with `len()` before indexing.",
            "Remember Python uses 0-based indexing — index `len(list)` is always out of range.",
            "Negative indices go from the end: `-1` is the last element.",
            "Use `list.get(index, default)` for dictionaries, or try/except for lists.",
        ),
        "related": [
            "KeyError",
            "IndexError: string index out of range",
            "TypeError: list indices must be integers",
        ],
    }


def _explain_keyerror(text: str, m: re.Match) -> dict[str, Any]:
    """explain keyerror.

    Args:
        text: Description.
        m: Description.

    Returns:
        Description.
    """
    key = m.group(1) or "key"
    return {
        "problem": f"KeyError: '{key}'",
        "cause": f"The key '{key}' was not found in the dictionary.",
        "fix": _make_fix(
            f"Check if '{key}' exists with `'{{key}}' in my_dict` before accessing.",
            f"Use `my_dict.get('{key}', default_value)` to provide a fallback.",
            f"Verify the dictionary contents: `print(list(my_dict.keys()))`",
            f"If parsing JSON, the key might be nested or optional — use `.get()` chaining.",
        ),
        "related": ["IndexError", "KeyError in JSON parsing", "AttributeError with dict"],
    }


def _explain_filenotfound(text: str, m: re.Match) -> dict[str, Any]:
    """explain filenotfound.

    Args:
        text: Description.
        m: Description.

    Returns:
        Description.
    """
    fname = m.group(1) or m.group(0)
    return {
        "problem": f"FileNotFoundError: {fname}",
        "cause": "Python tried to open or access a file that doesn't exist at the given path.",
        "fix": _make_fix(
            "Check the file path for typos — is the name and extension correct?",
            "Use an absolute path or verify the current working directory: `os.getcwd()`",
            f'Check if the file exists: `test -f "{fname}"` or `os.path.exists()`',
            (
                "The file might be in a different directory — use"
                "`Path(__file__).parent / 'filename'` for relative paths."
            ),
        ),
        "related": [
            "FileNotFoundError: [Errno 2] No such file or directory",
            "OSError",
            "PermissionError",
        ],
    }


# ── OS / filesystem errors ───────────────────────────────────────────────

_ERRNO_KNOWN = {
    "ENOENT": {
        "problem": "File or directory not found (errno ENOENT).",
        "cause": "The system tried to access a path that does not exist.",
        "fix": _make_fix(
            "Double-check the path spelling and case (Linux paths are case-sensitive).",
            "Verify the parent directory exists before the file.",
            "Use `ls` or `dir` to confirm the file is where you think it is.",
            "Check if a symlink is broken: `readlink -f <path>`",
        ),
        "related": [
            "FileNotFoundError",
            "ENOENT: no such file or directory",
            "docker: no such file",
        ],
    },
    "EACCES": {
        "problem": "Permission denied (errno EACCES).",
        "cause": "The process lacks read/write/execute permission for the file or directory.",
        "fix": _make_fix(
            "Check file permissions: `ls -la <path>`",
            "On Linux/macOS: `chmod +r <file>` or `chmod +x <dir>`",
            "On Windows: check file properties > Security tab, or run terminal as Administrator.",
            "The file might be open in another process (especially on Windows).",
        ),
        "related": ["PermissionError", "EACCES: permission denied", "EACCESS"],
    },
    "EEXIST": {
        "problem": "File already exists (errno EEXIST).",
        "cause": (
            "Tried to create a file or directory that already exists (often `os.mkdir()` or"
            "`os.open()` with exclusive flag)."
        ),
        "fix": _make_fix(
            "Use `os.makedirs(exist_ok=True)` to avoid the error.",
            "Check if the path exists before creating: `os.path.exists()`",
            "Remove the existing item first if you intended to replace it.",
        ),
        "related": ["FileExistsError", "EEXIST"],
    },
    "ENOTDIR": {
        "problem": "A component of the path is not a directory (errno ENOTDIR).",
        "cause": "A path like /a/b/c/file was given, but 'b' is a file, not a directory.",
        "fix": _make_fix(
            "Verify that every component of the path is a directory (except the final one).",
            "Check if you accidentally used a file as an intermediate path segment.",
            "Use `os.path.isdir()` to test each component.",
        ),
        "related": ["ENOENT", "ENOTDIR: not a directory"],
    },
}


# ── npm / Node.js errors ─────────────────────────────────────────────────


def _explain_npm_install(text: str, m: re.Match) -> dict[str, Any]:
    """explain npm install.

    Args:
        text: Description.
        m: Description.

    Returns:
        Description.
    """
    return {
        "problem": "npm install failed — could not resolve or fetch dependencies.",
        "cause": (
            "Missing package, network issue, registry problem, or version conflict in package.json /"
            "package-lock.json."
        ),
        "fix": _make_fix(
            "Delete node_modules and lockfile: `rm -rf node_modules package-lock.json && npm install`",
            "Check network connectivity and npm registry: `npm ping`",
            "Look for version conflicts in package.json — try `npm ls` to see the tree.",
            "Clear npm cache: `npm cache clean --force`",
            "Try with `--legacy-peer-deps` if this is a React 17 / npm 7+ peer dependency issue.",
        ),
        "related": [
            "npm ERR! code ERESOLVE",
            "npm ERR! 404",
            "npm ERR! network",
            "yarn install failures",
        ],
    }


def _explain_npm_errcode(text: str, m: re.Match) -> dict[str, Any]:
    """explain npm errcode.

    Args:
        text: Description.
        m: Description.

    Returns:
        Description.
    """
    code = m.group(1) or "unknown"
    return {
        "problem": f"npm error code: {code}",
        "cause": (
            f"npm encountered error code '{code}' — this is usually a"
            f"network, permission, or dependency resolution issue."
        ),
        "fix": _make_fix(
            f"Search the error code: `npm help {code}`",
            "Check your npm version: `npm -v` and update if old: `npm i -g npm`",
            "Verify you have a stable internet connection.",
            (
                "If it's a permission error, avoid `sudo npm install`"
                "— use a version manager like nvm or fix npm prefix."
            ),
        ),
        "related": ["npm ERR! code EACCES", "npm ERR! code EINTEGRITY", "npm ERR! code ENOENT"],
    }


# ── Git errors ───────────────────────────────────────────────────────────


def _explain_git_notrepo(text: str, m: re.Match) -> dict[str, Any]:
    """explain git notrepo.

    Args:
        text: Description.
        m: Description.

    Returns:
        Description.
    """
    return {
        "problem": "Not a git repository (or any parent up to mount point /).",
        "cause": "You ran a git command in a directory that isn't part of a Git working tree.",
        "fix": _make_fix(
            (
                "Run `git init` to create a new repository here,"
                "or `git clone <url>` to clone an existing one."
            ),
            "Check if you're in the right directory: `pwd`",
            "Look for a `.git` folder: `ls -la .git`",
            "If the repo exists but `.git` was deleted, you can re-initialize and re-add the remote.",
        ),
        "related": [
            "fatal: not a git repository",
            "fatal: 'origin' does not appear to be a git repository",
        ],
    }


def _explain_git_mergeconflict(text: str, m: re.Match) -> dict[str, Any]:
    """explain git mergeconflict.

    Args:
        text: Description.
        m: Description.

    Returns:
        Description.
    """
    return {
        "problem": "Merge conflict — Git cannot automatically resolve conflicting changes.",
        "cause": (
            "Two branches modified the same part of the same file, and Git needs your help to choose"
            "what to keep."
        ),
        "fix": _make_fix(
            "Open the conflicted files (they have `<<<<<<<`, `=======`, `>>>>>>>` markers).",
            "Edit each conflict: remove the markers and keep the correct content (or merge both).",
            "After resolving: `git add <file>` to mark as resolved.",
            "Then: `git commit` to complete the merge (or `git merge --continue`).",
            "Use `git mergetool` if you have a visual diff tool configured.",
        ),
        "related": ["merge conflict in", "Automatic merge failed", "git rebase conflict"],
    }


def _explain_git_detached(text: str, m: re.Match) -> dict[str, Any]:
    """explain git detached.

    Args:
        text: Description.
        m: Description.

    Returns:
        Description.
    """
    return {
        "problem": "HEAD is in a 'detached' state — not on any branch.",
        "cause": (
            "You checked out a specific commit, tag, or remote branch without a local tracking"
            "branch."
        ),
        "fix": _make_fix(
            "If you want to keep your changes: `git switch -c new-branch-name`",
            "To discard changes and go back to a branch: `git switch main` (or your default branch)",
            "To save work before switching: `git stash` then `git switch main && git stash pop`",
            (
                "You can still commit — the commits will be orphaned"
                "unless you create a branch pointing at them."
            ),
        ),
        "related": ["HEAD detached at", "You are in 'detached HEAD' state", "git rebase detached"],
    }


def _explain_git_pushrejected(text: str, m: re.Match) -> dict[str, Any]:
    """explain git pushrejected.

    Args:
        text: Description.
        m: Description.

    Returns:
        Description.
    """
    return {
        "problem": "Git push was rejected — remote has commits you don't have locally.",
        "cause": (
            "Another developer pushed to the same branch, or"
            "you're trying to push to a protected branch."
        ),
        "fix": _make_fix(
            "Pull the latest changes first: `git pull --rebase`",
            "Resolve any conflicts, then try pushing again: `git push`",
            "If you're sure you want to overwrite (careful!): `git push --force-with-lease`",
            "Check branch protection rules on GitHub/GitLab if push is blocked.",
        ),
        "related": [
            "failed to push some refs",
            "rejected: non-fast-forward",
            "Updates were rejected",
        ],
    }


# ── TypeScript errors ────────────────────────────────────────────────────

_TS_KNOWN_ERRORS: dict[str, dict[str, Any]] = {
    "2307": {
        "problem": "TypeScript error TS2307: Cannot find module or its type declarations.",
        "cause": (
            "The module path in an import statement doesn't resolve"
            "to any file, or type declarations are missing."
        ),
        "fix": _make_fix(
            "Check the import path for typos — relative paths must start with `./` or `../`.",
            "Install the package: `npm install <package>` or `npm install -D @types/<package>`",
            "For TS paths aliases, ensure `tsconfig.json` has correct `paths` and `baseUrl`.",
            (
                "If it's a JS-only package, try: `npm install -D @types/<package>`"
                "or add a `declare module '<package>'` declaration file."
            ),
        ),
        "related": ["TS2307", "TS7016: Could not find declaration file", "Cannot find module"],
    },
    "2322": {
        "problem": "TypeScript error TS2322: Type 'X' is not assignable to type 'Y'.",
        "cause": (
            "A variable, parameter, or return value was given"
            "a value that doesn't match its declared type."
        ),
        "fix": _make_fix(
            "Check the expected type vs the actual type — they must be structurally compatible.",
            "Use a type assertion if you're sure: `value as TargetType` (but prefer proper typing).",
            "Add a type guard or refine the value before assignment.",
            "If types from different libraries conflict, check for version mismatches.",
        ),
        "related": [
            "TS2322",
            "Type 'undefined' is not assignable",
            "Type 'null' is not assignable",
        ],
    },
    "2554": {
        "problem": "TypeScript error TS2554: Expected X arguments, but got Y.",
        "cause": "A function was called with the wrong number of arguments — too many or too few.",
        "fix": _make_fix(
            "Check the function signature — how many parameters does it expect?",
            "Did you destructure an object parameter but pass separate arguments?",
            "Some parameters might be optional (marked with `?`) — are you passing enough?",
            "Check for overloaded function signatures that don't match your call.",
        ),
        "related": [
            "TS2554",
            "TS2555: Expected at least X arguments",
            "TS2575: Type is not callable",
        ],
    },
    "7016": {
        "problem": "TypeScript error TS7016: Could not find a declaration file for module.",
        "cause": "A JS library has no bundled types and no @types package exists.",
        "fix": _make_fix(
            "Install types: `npm install -D @types/<package>` if available.",
            (
                "If no @types package exists, create a local declaration"
                "file (`*.d.ts`) with: `declare module '<package>';`"
            ),
            (
                "In tsconfig, set `noImplicitAny` and `strict`"
                "carefully — you may need to relax `skipLibCheck`."
            ),
        ),
        "related": ["TS7016", "TS2307: Cannot find module", "Could not find a declaration file"],
    },
    "2741": {
        "problem": "TypeScript error TS2741: Property 'X' is missing in type 'Y' but required in type 'Z'.",
        "cause": "An object literal is missing a required property from its expected type.",
        "fix": _make_fix(
            "Add the missing property to the object literal.",
            "If the property should be optional, add `?` to the type definition.",
            (
                "Use a partial type: `Partial<SomeType>` if all"
                "properties can be optional (but be careful)."
            ),
        ),
        "related": ["TS2741", "TS2322: Type is not assignable", "TS2742"],
    },
    "2769": {
        "problem": "TypeScript error TS2769: No overload matches this call.",
        "cause": (
            "The function has multiple overload signatures, but none match the argumentsprovided."
        ),
        "fix": _make_fix(
            "Check the overload signatures and see which one your call should satisfy.",
            "The last overload (implementation signature) is not callable directly.",
            "Your argument types might need adjustment — check the exact expected types.",
        ),
        "related": ["TS2769", "TS2554: Expected X arguments", "Overload signature not callable"],
    },
}


def _explain_ts_error(text: str, m: re.Match) -> dict[str, Any]:
    """explain ts error.

    Args:
        text: Description.
        m: Description.

    Returns:
        Description.
    """
    code = m.group(1)
    if code in _TS_KNOWN_ERRORS:
        return dict(_TS_KNOWN_ERRORS[code])
    return {
        "problem": f"TypeScript error TS{code}: unknown or uncategorised.",
        "cause": "The TypeScript compiler found a type inconsistency in your code.",
        "fix": _make_fix(
            f"Look up TS{code} online or run `tsc --pretty --noEmit` for a clearer message.",
            "Check the error location — it points to exactly where the issue is.",
            "Consider enabling `strict: true` in tsconfig to catch issues early.",
        ),
        "related": [f"TS{code}", "TypeScript compilation error"],
    }


# ── Rust errors ──────────────────────────────────────────────────────────


def _explain_rust_panic(text: str, m: re.Match) -> dict[str, Any]:
    """explain rust panic.

    Args:
        text: Description.
        m: Description.

    Returns:
        Description.
    """
    msg = m.group(1) or "(no message)"
    return {
        "problem": f"Rust panicked: {msg.strip()}",
        "cause": (
            "The Rust program encountered an unrecoverable error and aborted — often an `unwrap()` on"
            "`None` or `Err`, an `expect()` that failed, or an out-of-bounds access."
        ),
        "fix": _make_fix(
            (
                "Find the `unwrap()` or `expect()` call and replace it"
                "with proper error handling (`match` or `?` operator)."
            ),
            "Use `RUST_BACKTRACE=1` and re-run to get a full stack trace.",
            "Check for array index out of bounds, division by zero, or assertion failures.",
            "Add proper Result/Option handling instead of panicking.",
        ),
        "related": [
            "thread 'main' panicked",
            "called `Option::unwrap()` on a `None` value",
            "index out of bounds",
        ],
    }


def _explain_rust_compile(text: str, m: re.Match) -> dict[str, Any]:
    """explain rust compile.

    Args:
        text: Description.
        m: Description.

    Returns:
        Description.
    """
    return {
        "problem": (
            "Rust compilation error — the code does not satisfy the borrow checker or typesystem."
        ),
        "cause": (
            "The Rust compiler rejected the code (borrow checker, type mismatch, missing lifetimes,"
            "etc.)."
        ),
        "fix": _make_fix(
            "Read the error carefully — it usually tells you exactly what's wrong and suggests a fix.",
            (
                "For borrow checker errors: check for multiple mutable"
                "borrows or references that outlive their data."
            ),
            (
                "For lifetime errors: add explicit lifetime annotations"
                "or restructure to avoid borrowing issues."
            ),
            "Run `cargo check` instead of `cargo build` for faster iteration.",
            "Use `cargo clippy` for additional lint suggestions.",
        ),
        "related": [
            "error[E0382]: borrow of moved value",
            "error[E0499]: cannot borrow as mutable more than once",
            "error[E0107]: missing lifetime specifier",
        ],
    }


# ── JSON / YAML parse errors ─────────────────────────────────────────────


def _explain_json_parse(text: str, m: re.Match) -> dict[str, Any]:
    """explain json parse.

    Args:
        text: Description.
        m: Description.

    Returns:
        Description.
    """
    detail = m.group(1) or "invalid JSON"
    return {
        "problem": f"JSON parse error: {detail.strip()}",
        "cause": (
            "The data is not valid JSON — a trailing comma, missing quote, unescaped character, or"
            "extra content."
        ),
        "fix": _make_fix(
            "Use a JSON validator (e.g. `python -m json.tool < file.json`) to find the exact position.",
            "Trailing commas in objects/arrays are not allowed in strict JSON.",
            "Strings must be double-quoted — single quotes are not valid JSON.",
            "Check for control characters or unmatched brackets.",
            "If the file was edited by hand, look for missing braces or commas.",
        ),
        "related": ["JSONDecodeError", "Unexpected token in JSON", "Unexpected end of JSON input"],
    }


def _explain_yaml_parse(text: str, m: re.Match) -> dict[str, Any]:
    """explain yaml parse.

    Args:
        text: Description.
        m: Description.

    Returns:
        Description.
    """
    detail = m.group(1) or "invalid YAML"
    return {
        "problem": f"YAML parse error: {detail.strip()}",
        "cause": (
            "The YAML file has incorrect indentation, a mapping key collision, or unquoted special"
            "characters."
        ),
        "fix": _make_fix(
            (
                "YAML is indentation-sensitive — make sure all"
                "levels use consistent spacing (tabs not allowed)."
            ),
            "Check for special characters in strings — wrap them in quotes if needed.",
            "Look for duplicate keys (some parsers reject them).",
            "Use a YAML linter: `yamllint <file>`",
        ),
        "related": [
            "yaml.parser.ParserError",
            "yaml.scanner.ScannerError",
            "mapping values are not allowed here",
        ],
    }


# ── Network errors ───────────────────────────────────────────────────────

_NETWORK_KNOWN: dict[str, dict[str, Any]] = {
    "ECONNREFUSED": {
        "problem": "Connection refused — no service is listening on that host/port.",
        "cause": (
            "The remote server is not running, a firewall is blocking the connection, or you have the"
            "wrong host/port."
        ),
        "fix": _make_fix(
            "Verify the service is running: `systemctl status <service>` or `docker ps`",
            "Check the host and port: `telnet <host> <port>` or `nc -zv <host> <port>`",
            "Check for firewall rules: `sudo ufw status` or `iptables -L`",
            "If connecting to localhost, ensure the server is bound to 0.0.0.0 or 127.0.0.1.",
        ),
        "related": ["ECONNREFUSED", "Connection refused", "Cannot connect to server"],
    },
    "ETIMEDOUT": {
        "problem": "Connection timed out — the remote host is not responding.",
        "cause": (
            "Network congestion, the server is down, a firewall is silently dropping packets, or DNS"
            "is resolved to a dead IP."
        ),
        "fix": _make_fix(
            "Ping the host: `ping <host>` to check basic connectivity.",
            "Check DNS: `nslookup <host>` or `dig <host>`",
            "The server might be overloaded or crashed — wait and retry, or check server status.",
            "A firewall might be dropping traffic without responding (blackholing).",
        ),
        "related": ["ETIMEDOUT", "Connection timed out", "Network is unreachable"],
    },
    "ENOTFOUND": {
        "problem": "DNS lookup failed — the hostname could not be resolved.",
        "cause": "The hostname doesn't exist in DNS, /etc/hosts, or the DNS server is unreachable.",
        "fix": _make_fix(
            "Check the spelling of the hostname.",
            "Try a different DNS server: add `nameserver 8.8.8.8` to /etc/resolv.conf",
            "Check your internet connection: `ping 8.8.8.8`",
            "Add an entry to /etc/hosts if you need to override DNS for local development.",
        ),
        "related": ["ENOTFOUND", "getaddrinfo ENOTFOUND", "DNS resolution failed"],
    },
    "ECONNRESET": {
        "problem": "Connection reset by peer — the remote side closed the connection abruptly.",
        "cause": "The server crashed, a proxy closed the connection, or a firewall sent a TCP RST.",
        "fix": _make_fix(
            "Retry the request — it might be a transient issue.",
            "Check if the server is overloaded and dropping connections.",
            "If using HTTPS, check for SSL/TLS version mismatches.",
            "Long-running idle connections might be killed by a load balancer or proxy.",
        ),
        "related": ["ECONNRESET", "Connection reset by peer", "Socket hang up"],
    },
    "EAI_AGAIN": {
        "problem": "DNS temporary failure (EAI_AGAIN) — the name server is not responding.",
        "cause": "The DNS server is slow or unavailable, or there's a temporary network glitch.",
        "fix": _make_fix(
            "Retry after a few seconds — this is often transient.",
            "Check DNS server health: `nslookup google.com`",
            "Switch to a more reliable DNS server (8.8.8.8, 1.1.1.1).",
        ),
        "related": ["EAI_AGAIN", "getaddrinfo EAI_AGAIN", "Temporary failure in name resolution"],
    },
}


# ── Docker errors ────────────────────────────────────────────────────────


def _explain_docker_daemon(text: str, m: re.Match) -> dict[str, Any]:
    """explain docker daemon.

    Args:
        text: Description.
        m: Description.

    Returns:
        Description.
    """
    return {
        "problem": "Cannot connect to the Docker daemon.",
        "cause": (
            "The Docker daemon (dockerd) is not running, or the current"
            "user doesn't have permission to access its socket."
        ),
        "fix": _make_fix(
            (
                "Start Docker: `sudo systemctl start docker`"
                "(Linux) or open Docker Desktop (macOS/Windows)."
            ),
            "Add your user to the docker group: `sudo usermod -aG docker $USER && newgrp docker`",
            "Check the Docker socket exists: `ls -la /var/run/docker.sock`",
            "Verify Docker is installed: `docker --version`",
        ),
        "related": [
            "Cannot connect to the Docker daemon",
            "Is the docker daemon running?",
            "docker: error during connect",
        ],
    }


def _explain_docker_conflict(text: str, m: re.Match) -> dict[str, Any]:
    """explain docker conflict.

    Args:
        text: Description.
        m: Description.

    Returns:
        Description.
    """
    name = m.group(1) or "container"
    return {
        "problem": f"Docker container/port conflict for '{name}'.",
        "cause": "The container name or port is already in use by another running container.",
        "fix": _make_fix(
            "List running containers: `docker ps`",
            f"Stop the conflicting container: `docker stop {name}` or `docker rm -f {name}`",
            "Use a different port mapping: `-p <unused-port>:<container-port>`",
            "Use `--name` with a unique name to avoid name collisions.",
        ),
        "related": [
            "port is already allocated",
            "container name already exists",
            "Bind for 0.0.0.0:... failed",
        ],
    }


# ── Generic fallback ─────────────────────────────────────────────────────


def _explain_generic(text: str) -> dict[str, Any]:
    """Fallback when no pattern matches."""
    lines = [l.strip() for l in text.strip().splitlines() if l.strip()]
    snippet = lines[0][:200] if lines else text[:200]
    return {
        "problem": f"Unrecognised error pattern.",
        "cause": f'The tool could not classify this error: "{snippet}"',
        "fix": _make_fix(
            "Copy the full error message and search it online.",
            "Check the documentation for the tool/language that produced the error.",
            "Look for typos, missing files, or incorrect configuration near the error.",
            "If this is a common error type, consider contributing a pattern to this tool.",
        ),
        "related": [],
    }


# ---------------------------------------------------------------------------
# Combined pattern registry
# ---------------------------------------------------------------------------

PATTERNS: list[tuple[re.Pattern, str, Any]] = [
    # Python: ModuleNotFoundError
    (
        re.compile(r"ModuleNotFoundError:\s*No module named ['\"](\S+?)['\"]", re.I),
        "Python ModuleNotFoundError",
        _explain_modulenotfound,
    ),
    # Python: ImportError
    (re.compile(r"ImportError\b[:\s]*(.*)", re.I), "Python ImportError", _explain_importerror),
    # Python: SyntaxError
    (
        re.compile(r"SyntaxError[:\s]*(.*?)\s*\(?\s*[Ll]ine\s*(\d+)\s*\)?", re.I),
        "Python SyntaxError",
        _explain_syntaxerror,
    ),
    (re.compile(r"SyntaxError[:\s]*(.*)", re.I), "Python SyntaxError", _explain_syntaxerror),
    # Python: TypeError
    (re.compile(r"TypeError[:\s]*(.*)", re.I), "Python TypeError", _explain_typeerror),
    # Python: ValueError
    (re.compile(r"ValueError[:\s]*(.*)", re.I), "Python ValueError", _explain_valueerror),
    # Python: AttributeError
    (
        re.compile(r"AttributeError[:\s]*(.*)", re.I),
        "Python AttributeError",
        _explain_attributeerror,
    ),
    # Python: NameError
    (
        re.compile(r"NameError[:\s]*name\s+['\"]?(.+?)['\"]?\s+is\s+not\s+defined", re.I),
        "Python NameError",
        _explain_nameerror,
    ),
    # Python: IndexError
    (re.compile(r"IndexError[:\s]", re.I), "Python IndexError", _explain_indexerror),
    # Python: KeyError
    (re.compile(r"KeyError[:\s]*['\"]?(.+?)['\"]?", re.I), "Python KeyError", _explain_keyerror),
    # Python: FileNotFoundError
    (
        re.compile(r"FileNotFoundError[:\s]*(.*?)(?:\[Errno\s*\d+\])?", re.I),
        "Python FileNotFoundError",
        _explain_filenotfound,
    ),
    # ── OS errno patterns ──
    (re.compile(r"\bENOENT\b", re.I), "ENOENT", lambda t, m: _ERRNO_KNOWN["ENOENT"]),
    (re.compile(r"\bEACCES\b", re.I), "EACCES", lambda t, m: _ERRNO_KNOWN["EACCES"]),
    (re.compile(r"\bEEXIST\b", re.I), "EEXIST", lambda t, m: _ERRNO_KNOWN["EEXIST"]),
    (re.compile(r"\bENOTDIR\b", re.I), "ENOTDIR", lambda t, m: _ERRNO_KNOWN["ENOTDIR"]),
    # ── npm errors ──
    (re.compile(r"npm ERR!.*?\bcould not\b", re.I), "npm install failed", _explain_npm_install),
    (re.compile(r"npm ERR!.*?\bfailed\b", re.I), "npm install failed", _explain_npm_install),
    (re.compile(r"npm ERR!\s*code\s+(\S+)", re.I), "npm error code", _explain_npm_errcode),
    # ── Git errors ──
    (
        re.compile(r"fatal:\s*not a git repository", re.I),
        "Git: not a repository",
        _explain_git_notrepo,
    ),
    (
        re.compile(r"(?:merge|auto-?merge)\s+conflict", re.I),
        "Git: merge conflict",
        _explain_git_mergeconflict,
    ),
    (re.compile(r"detached\s+(?:HEAD|state)", re.I), "Git: detached HEAD", _explain_git_detached),
    (
        re.compile(
            r"failed to push|rejected\s+.*non-fast-?forward|updates?\s+were\s+rejected", re.I
        ),
        "Git: push rejected",
        _explain_git_pushrejected,
    ),
    # ── TypeScript errors ──
    (re.compile(r"\bTS(\d{4})\b"), "TypeScript error", _explain_ts_error),
    (re.compile(r"error TS(\d{4}):", re.I), "TypeScript error", _explain_ts_error),
    # ── Rust errors ──
    (
        re.compile(r"thread\s+['\"].+?['\"]\s+panicked at\s+(.*)", re.I),
        "Rust panic",
        _explain_rust_panic,
    ),
    (re.compile(r"panicked at\s+['\"]?(.+?)['\"]?", re.I), "Rust panic", _explain_rust_panic),
    (re.compile(r"error\[E\d{4}\]:", re.I), "Rust compilation error", _explain_rust_compile),
    # ── JSON parse errors ──
    (re.compile(r"JSONDecodeError[:\s]*(.*)", re.I), "JSON parse error", _explain_json_parse),
    (
        re.compile(
            r"(?:Unexpected\s+token|Unexpected\s+end\s+of\s+(?:JSON|input)|JSON\.parse|Failed\s+to\s+parse\s+JSON)",
            re.I,
        ),
        "JSON parse error",
        _explain_json_parse,
    ),
    # ── YAML parse errors ──
    (
        re.compile(
            r"(?:yaml\..*Error|mapping\s+values\s+are\s+not\s+allowed|YAML\s+parse\s+error)[:\s]*(.*)",
            re.I,
        ),
        "YAML parse error",
        _explain_yaml_parse,
    ),
    # ── Network errors ──
    (
        re.compile(r"\bECONNREFUSED\b", re.I),
        "ECONNREFUSED",
        lambda t, m: _NETWORK_KNOWN["ECONNREFUSED"],
    ),
    (re.compile(r"\bETIMEDOUT\b", re.I), "ETIMEDOUT", lambda t, m: _NETWORK_KNOWN["ETIMEDOUT"]),
    (re.compile(r"\bENOTFOUND\b", re.I), "ENOTFOUND", lambda t, m: _NETWORK_KNOWN["ENOTFOUND"]),
    (re.compile(r"\bECONNRESET\b", re.I), "ECONNRESET", lambda t, m: _NETWORK_KNOWN["ECONNRESET"]),
    (re.compile(r"\bEAI_AGAIN\b", re.I), "EAI_AGAIN", lambda t, m: _NETWORK_KNOWN["EAI_AGAIN"]),
    # ── Docker errors ──
    (
        re.compile(r"Cannot\s+connect\s+to\s+the\s+Docker\s+daemon", re.I),
        "Docker daemon",
        _explain_docker_daemon,
    ),
    (
        re.compile(r"(?:Is\s+the\s+docker\s+daemon\s+running|docker.*error.*connect)", re.I),
        "Docker daemon",
        _explain_docker_daemon,
    ),
    (
        re.compile(
            r"(?:container\s+name\s+[\"']?(\S+?)[\"']?\s+is\s+already\s+in\s+use|port\s+is\s+already\s+allocated|Bind\s+for.*failed)",
            re.I,
        ),
        "Docker conflict",
        _explain_docker_conflict,
    ),
]


# ---------------------------------------------------------------------------
# Core logic
# ---------------------------------------------------------------------------


def explain_error(text: str) -> dict[str, Any]:
    """Analyse an error message and return an explanation dict.

    Returns:
        {
            "match": str | None,         # label of matched pattern or None
            "problem": str,
            "cause": str,
            "fix": list[str],
            "related": list[str],
        }
    """
    if not text or not text.strip():
        return {
            "match": None,
            **(_explain_generic("(empty input)")),
        }

    # Truncate very long input for performance
    truncated = text[:MAX_INPUT_LENGTH]

    for pattern, label, explain_fn in PATTERNS:
        m = pattern.search(truncated)
        if m:
            result = explain_fn(truncated, m)
            result["match"] = label
            return result

    return {
        "match": None,
        **(_explain_generic(text)),
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    """build parser."""
    parser = argparse.ArgumentParser(
        description="Translate error messages into plain explanations and fix suggestions.",
        epilog=(
            "Examples:\n"
            "  python error_explainer.py \"ModuleNotFoundError: No module named 'requests'\"\n"
            '  python error_explainer.py "fatal: not a git repository" --json\n'
            '  echo "npm ERR! code ENOENT" | python error_explainer.py\n'
            "  python error_explainer.py --help"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "message",
        nargs="?",
        help="Error message, traceback, or log snippet to analyse.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output the explanation as JSON.",
    )
    return parser


def main() -> int:
    """main."""
    parser = _build_parser()
    args = parser.parse_args()

    # Read from argument or stdin
    if args.message:
        text = args.message
    else:
        # Check if stdin has data (pipe mode)
        if sys.stdin.isatty():
            parser.print_help()
            return EXIT_ERROR
        text = sys.stdin.read().strip()

    result = explain_error(text)

    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        match_label = result.get("match")
        parts = [
            f"Problem:        {result['problem']}",
            f"Probable cause: {result['cause']}",
            "",
            "Fix:",
        ]
        for step in result.get("fix", []):
            parts.append(f"  {step}")

        related = result.get("related")
        if related:
            parts.extend(["", "Related:"])
            for r in related:
                parts.append(f"  • {r}")

        if match_label:
            parts.extend(["", f"[Matched pattern: {match_label}]"])

        print("\n".join(parts))

    # Exit code: 1 if we matched a known error, 0 if generic/unrecognised
    # (both are valid, but 1 signals "issues found", 0 = clean)
    return EXIT_ISSUES if result.get("match") else EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
