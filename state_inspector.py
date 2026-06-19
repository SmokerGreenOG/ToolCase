#!/usr/bin/env python3
"""
state_inspector.py — Analyze React/Vue/Svelte state usage and detect anti-patterns.

Detects:
  - useState that never changes (declared but setter never called)
  - useEffect without dependency sanity (empty or missing deps)
  - state that is set but never read (unused state variable)
  - props that are not used in a component
  - context providers without consumers
  - missing loading / error / selectedFile / projectOpened / terminalState /
    approvalQueue / chatState / workspacePath state patterns
  - AI-code-editor specific state gaps

Usage:
    python state_inspector.py <path>
    python state_inspector.py <path> --json
    python state_inspector.py <path> --threshold 5
"""

__maker__ = "SmokerGreenOG"

import _protect
import argparse
import json
import re
import sys
from collections import defaultdict, Counter
from pathlib import Path


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

EXCLUDE_DIRS = frozenset({
    "node_modules", "target", ".git", "__pycache__", ".venv", "venv",
    "build", "dist", ".next", ".nuxt", "coverage",
})

EXTENSIONS = frozenset({".tsx", ".ts", ".jsx", ".js", ".vue", ".svelte"})

REACT = frozenset({".tsx", ".jsx", ".js", ".ts"})
VUE = frozenset({".vue"})
SVELTE = frozenset({".svelte"})

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

EXIT_OK = 0
EXIT_ISSUES = 1
EXIT_ERROR = 2


def collect_source_files(root: Path) -> list[Path]:
    """Recursively collect source files, skipping excluded dirs."""
    files = []
    if not root.exists():
        return files
    for fp in root.rglob("*"):
        # Skip excluded dirs quickly
        rel = fp.relative_to(root).parts if fp != root else ()
        if any(p in EXCLUDE_DIRS for p in rel):
            continue
        if fp.is_file() and fp.suffix.lower() in EXTENSIONS:
            files.append(fp)
    return sorted(files)


def read_file_safe(fp: Path) -> str:
    """Read file content, return empty string on error."""
    try:
        return fp.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return ""


# ---------------------------------------------------------------------------
# AI-Code-Editor expected state checks
# ---------------------------------------------------------------------------

AI_EDITOR_EXPECTED_STATES = frozenset({
    "projectOpened",
    "selectedFile",
    "terminalState",
    "approvalQueue",
    "chatState",
    "workspacePath",
    "loading",
    "error",
})


def check_missing_expected_states(content: str, fp: Path) -> list[dict]:
    """Check if AI-code-editor expected states are missing from the codebase."""
    issues = []

    expected = set(AI_EDITOR_EXPECTED_STATES)

    # Check if state name patterns appear in the code
    for state_name in list(expected):
        pattern = re.escape(state_name)
        if re.search(pattern, content, re.IGNORECASE):
            expected.discard(state_name)

    # Special: "selectedFile" and "project" may appear as different naming
    if re.search(r'selectedFile|currentFile|activeFile|openFile', content, re.IGNORECASE):
        expected.discard("selectedFile")
    if re.search(r'projectOpened|projectOpen|isProjectOpen|project_id', content, re.IGNORECASE):
        expected.discard("projectOpened")
    if re.search(r'terminalState|terminal', content, re.IGNORECASE):
        expected.discard("terminalState")
    if re.search(r'approvalQueue|approveQueue|pendingApproval', content, re.IGNORECASE):
        expected.discard("approvalQueue")
    if re.search(r'chatState|chatMessage|conversation|messages', content, re.IGNORECASE):
        expected.discard("chatState")
    if re.search(r'workspacePath|workDir|rootPath|projectDir', content, re.IGNORECASE):
        expected.discard("workspacePath")

    for missing_state in sorted(expected):
        issues.append({
            "file": str(fp),
            "type": "missing_expected_state",
            "severity": "warning",
            "message": f"Missing expected AI-code-editor state: '{missing_state}'",
            "line": 1,
        })

    return issues


# ---------------------------------------------------------------------------
# React analysis
# ---------------------------------------------------------------------------

def analyze_react(content: str, fp: Path) -> list[dict]:
    """Analyze React/TSX/JSX files for state anti-patterns."""
    issues = []
    lines = content.split("\n")

    # Track useState declarations: state_name -> (setter_name, line)
    useState_decls: dict[str, tuple[str, int]] = {}
    # Track all function/variable names that are read/used
    used_names: set[str] = set()
    # Track setter invocations
    setter_invocations: set[str] = set()

    # Extract component props from function params
    component_props: list[tuple[str, set[str], int]] = []  # (component_name, props, line)

    # Line-by-line analysis
    for i, line in enumerate(lines, 1):
        stripped = line.strip()

        # --- useState detection ---
        # const [foo, setFoo] = useState(...)
        m = re.search(
            r'const\s*\[\s*(\w+)\s*,\s*(\w+)\s*\]\s*=\s*useState\s*\(',
            stripped,
        )
        if m:
            state_var, setter = m.group(1), m.group(2)
            useState_decls[state_var] = (setter, i)
            used_names.add(state_var)  # may be removed later if never read
            continue

        # --- useEffect dependency sanity ---
        # useEffect(() => {...}, [deps])
        m_effect = re.search(r'useEffect\s*\(\s*(?:\(\)\s*=>\s*\{|function\s*\()', stripped)
        if m_effect:
            # Check the dependency array (multi-line or on same line)
            effect_body_start = i
            # Look ahead for the dep array closing bracket
            dep_line_found = None
            for j in range(i - 1, min(i + 15, len(lines) + 1)):
                l = lines[j - 1]
                # Find the dependency array [...]
                dep_m = re.search(r'\]\s*,\s*\[([^\]]*)\]\s*\)', l)  # useEffect(fn, [deps])
                if dep_m:
                    dep_line_found = j
                    raw_deps = dep_m.group(1).strip()
                    if raw_deps == "":
                        issues.append({
                            "file": str(fp),
                            "type": "empty_effect_deps",
                            "severity": "warning",
                            "message": "useEffect has empty dependency array — may miss updates",
                            "line": effect_body_start,
                        })
                    break
                else:
                    # Check for [], possibly on next line
                    empty_dep_m = re.search(r'\[\s*\]\s*\)', l)
                    if empty_dep_m:
                        dep_line_found = j
                        # Check if there are any reactive values referenced inside effect
                        issues.append({
                            "file": str(fp),
                            "type": "empty_effect_deps",
                            "severity": "warning",
                            "message": "useEffect has empty dependency array — may miss updates",
                            "line": effect_body_start,
                        })
                        break

            if not dep_line_found:
                issues.append({
                    "file": str(fp),
                    "type": "effect_missing_deps",
                    "severity": "info",
                    "message": "useEffect without explicit dependency array — may cause infinite loops",
                    "line": effect_body_start,
                })
            continue

        # --- props detection ---
        # function ComponentName({ prop1, prop2 }) or const Comp = ({ prop1 }) =>
        m_props_func = re.search(
            r'(?:function|const)\s+(\w+)\s*(?:=\s*)?\(?\s*\{\s*([^}]+)\s*\}\s*(?::?\s*\w+)?\s*(?:\)\s*)?(?:=>|\{)',
            stripped,
        )
        if m_props_func:
            comp_name = m_props_func.group(1)
            raw_props = m_props_func.group(2)
            props_set = set()
            for p in re.finditer(r'(\w+)', raw_props):
                pname = p.group(1)
                if pname not in {"props", "ref", "key", "children"}:
                    props_set.add(pname)
            if props_set:
                component_props.append((comp_name, props_set, i))
            continue

        # Track setter calls: setFoo(...)
        for state_var, (setter, _) in useState_decls.items():
            if re.search(r'\b' + re.escape(setter) + r'\s*\(', stripped):
                setter_invocations.add(state_var)

        # Track used names (identifiers read in component body)
        for token in re.findall(r'\b([a-zA-Z_]\w*)\b', stripped):
            if token not in {
                "const", "let", "var", "function", "return", "if", "else", "for",
                "while", "switch", "case", "break", "continue", "import", "export",
                "from", "default", "new", "typeof", "instanceof", "void", "delete",
                "try", "catch", "finally", "throw", "async", "await", "yield",
                "class", "extends", "this", "super", "true", "false", "null",
                "undefined", "useState", "useEffect", "useContext", "useReducer",
                "useCallback", "useMemo", "useRef", "useLayoutEffect",
                "createContext", "React",
            }:
                used_names.add(token)

    # --- Check useState that never changes ---
    for state_var, (setter, line) in useState_decls.items():
        if state_var not in setter_invocations:
            # Allow primitive values like booleans/strings used as initial values
            # Only flag if setter is NEVER called across the whole file
            issues.append({
                "file": str(fp),
                "type": "useState_never_changes",
                "severity": "warning",
                "message": f"useState '{state_var}' (setter: {setter}) is never called — state never changes",
                "line": line,
            })

    # --- Check state that is set but never read ---
    for state_var, (setter, line) in useState_decls.items():
        if setter in setter_invocations and state_var not in used_names:
            issues.append({
                "file": str(fp),
                "type": "state_set_never_read",
                "severity": "warning",
                "message": f"State '{state_var}' is set via {setter} but value never read in component",
                "line": line,
            })

    # --- Check unused props ---
    for comp_name, props_set, line in component_props:
        # For each prop, check if it appears in the rest of the component body
        # (looking through the rest of the file for usage)
        body_text = "\n".join(lines[line:])
        for prop in props_set:
            # Skip common React props that don't need explicit reading
            if prop in {"children", "key", "ref"}:
                continue
            # Check if the prop name appears in the component body (template/JSX)
            if not re.search(r'\b' + re.escape(prop) + r'\b', body_text):
                issues.append({
                    "file": str(fp),
                    "type": "unused_prop",
                    "severity": "info",
                    "message": f"Prop '{prop}' in component '{comp_name}' is declared but never used",
                    "line": line,
                })

    return issues


# ---------------------------------------------------------------------------
# Vue analysis
# ---------------------------------------------------------------------------

def analyze_vue(content: str, fp: Path) -> list[dict]:
    """Analyze Vue SFC files for state anti-patterns."""
    issues = []
    lines = content.split("\n")

    # Extract <script> section
    script_match = re.search(r'<script[^>]*>(.*?)</script>', content, re.DOTALL)
    if not script_match:
        return issues

    script_content = script_match.group(1)

    # Track ref() / reactive() declarations
    ref_decls: dict[str, int] = {}
    reactive_vars: set[str] = set()
    used_vars: set[str] = set()
    ref_setter_calls: set[str] = set()

    for i, line in enumerate(script_content.split("\n"), 1):
        stripped = line.strip()

        # ref() declarations: const foo = ref(...)
        m_ref = re.search(r'(?:const|let|var)\s+(\w+)\s*=\s*ref\s*\(', stripped)
        if m_ref:
            ref_decls[m_ref.group(1)] = i
            used_vars.add(m_ref.group(1))  # may be removed if never used
            continue

        # reactive() declarations: const foo = reactive({...})
        m_reactive = re.search(r'(?:const|let|var)\s+(\w+)\s*=\s*reactive\s*\(', stripped)
        if m_reactive:
            reactive_vars.add(m_reactive.group(1))
            used_vars.add(m_reactive.group(1))
            continue

        # Track .value assignments (setting ref value)
        for ref_var in ref_decls:
            m_set = re.search(r'\b' + re.escape(ref_var) + r'\.value\s*=', stripped)
            if m_set:
                ref_setter_calls.add(ref_var)
                continue

        # Composable props detection
        m_props = re.search(r'defineProps\s*\(\s*\{([^}]+)\}\s*\)', stripped)
        if m_props:
            # Extract prop names from the object
            for p in re.findall(r'(\w+)\s*:', m_props.group(1)):
                used_vars.add(p)
            continue

        # watch() without deep option?
        m_watch = re.search(r'watch\s*\(', stripped)
        if m_watch:
            # Check if there's a deep:true option
            watch_block = script_content[max(0, i - 1):i + 5]
            watch_block_text = "\n".join(watch_block)
            if "deep" not in watch_block_text and re.search(r'\([\s\S]{0,200}\)', watch_block_text):
                # Only mention if watching an object/reactive
                issues.append({
                    "file": str(fp),
                    "type": "vue_watch_missing_deep",
                    "severity": "info",
                    "message": "watch() may be missing { deep: true } for reactive objects",
                    "line": i,
                })

        # Track usage of variables
        for token in re.findall(r'\b([a-zA-Z_]\w*)\b', stripped):
            if token not in {"const", "let", "var", "function", "return", "if",
                             "else", "for", "while", "import", "export", "from",
                             "ref", "reactive", "computed", "watch", "defineProps",
                             "defineEmits", "defineExpose", "onMounted", "onUnmounted",
                             "nextTick", "toRefs", "toRef", "isRef", "unref",
                             "true", "false", "null", "undefined"}:
                used_vars.add(token)

    # === Check ref() never changes ===
    for ref_var, line in ref_decls.items():
        if ref_var not in ref_setter_calls:
            issues.append({
                "file": str(fp),
                "type": "vue_ref_never_changes",
                "severity": "warning",
                "message": f"ref '{ref_var}' is declared but .value is never assigned — state never changes",
                "line": line,
            })

    # === Check ref() declared but never used in template/script ===
    template_match = re.search(r'<template>(.*?)</template>', content, re.DOTALL)
    template_content = template_match.group(1) if template_match else ""

    for ref_var, line in ref_decls.items():
        if ref_var not in used_vars and re.search(r'\b' + re.escape(ref_var) + r'\b', template_content) is None:
            issues.append({
                "file": str(fp),
                "type": "vue_ref_unused",
                "severity": "warning",
                "message": f"ref '{ref_var}' is declared but never used in template or script",
                "line": line,
            })

    # === Missing loading/error state pattern ===
    if not re.search(r'loading|isLoading', content, re.IGNORECASE):
        if re.search(r'fetch|axios|request|api|getData|loadData', content, re.IGNORECASE):
            issues.append({
                "file": str(fp),
                "type": "vue_missing_loading_state",
                "severity": "warning",
                "message": "Component makes async requests but has no loading state",
                "line": 1,
            })

    if not re.search(r'error\w*|errorMessage|hasError', content, re.IGNORECASE):
        if re.search(r'fetch|axios|request|api|try\s*\{', content, re.IGNORECASE):
            issues.append({
                "file": str(fp),
                "type": "vue_missing_error_state",
                "severity": "warning",
                "message": "Component makes async requests but has no error state",
                "line": 1,
            })

    return issues


# ---------------------------------------------------------------------------
# Svelte analysis
# ---------------------------------------------------------------------------

def analyze_svelte(content: str, fp: Path) -> list[dict]:
    """Analyze Svelte files for state anti-patterns."""
    issues = []
    lines = content.split("\n")
    all_text = content

    # Track exported props and local state
    export_lets: list[tuple[str, int]] = []  # props
    local_lets: list[tuple[str, int]] = []   # local state
    writable_stores: list[tuple[str, int]] = []
    used_names: set[str] = set()
    mutated_names: set[str] = set()

    # Svelte 5 runes
    svelte5_state: list[tuple[str, int]] = []

    for i, line in enumerate(lines, 1):
        stripped = line.strip()

        # export let propName — Svelte props
        m_export_let = re.search(r'export\s+let\s+(\w+)', stripped)
        if m_export_let:
            export_lets.append((m_export_let.group(1), i))
            used_names.add(m_export_let.group(1))
            continue

        # let variable — local state
        m_let = re.search(r'(?:^|\s)let\s+(\w+)\s*(?::\s*\w+)?\s*=', stripped)
        if m_let and not stripped.startswith("export"):
            local_lets.append((m_let.group(1), i))
            used_names.add(m_let.group(1))
            continue

        # writable/readable stores
        m_store = re.search(r'(?:const|let)\s+(\w+)\s*=\s*(?:writable|readable|derived)\s*\(', stripped)
        if m_store:
            writable_stores.append((m_store.group(1), i))
            continue

        # Svelte 5: $state() rune
        m_svelte5 = re.search(r'(?:let|const)\s+(\w+)\s*=\s*\$state\s*\(', stripped)
        if m_svelte5:
            svelte5_state.append((m_svelte5.group(1), i))
            used_names.add(m_svelte5.group(1))
            continue

        # $: reactive statements
        m_reactive = re.search(r'\$:\s*(\w+)', stripped)
        if m_reactive:
            used_names.add(m_reactive.group(1))
            continue

        # Track mutations (assignment to local variables)
        for name, _ in local_lets:
            if re.search(r'\b' + re.escape(name) + r'\s*=', stripped):
                mutated_names.add(name)

        # Track mutations for Svelte 5 state
        for name, _ in svelte5_state:
            if re.search(r'\b' + re.escape(name) + r'\s*=', stripped):
                mutated_names.add(name)

        # Track store assignments ($name = ...)
        for name, _ in writable_stores:
            if re.search(r'\$' + re.escape(name) + r'\s*=', stripped) or \
               re.search(r'\b' + re.escape(name) + r'\.(set|update)\s*\(', stripped):
                mutated_names.add(name)

        # Track usage
        for token in re.findall(r'\b([a-zA-Z_]\w*)\b', stripped):
            if token not in {"let", "const", "var", "function", "return", "if",
                             "else", "for", "each", "while", "import", "export",
                             "from", "default", "async", "await", "true", "false",
                             "null", "undefined", "writable", "readable", "derived",
                             "onMount", "beforeUpdate", "afterUpdate", "onDestroy",
                             "tick", "getContext", "setContext", "hasContext",
                             "class", "dispatch", "createEventDispatcher"}:
                used_names.add(token)

    # === Check props never used ===
    template_match = re.search(r'(?:<template>)?(.*?)(?:</template>)?', content, re.DOTALL)
    template_text = content  # Svelte template is top-level

    for prop_name, line in export_lets:
        if prop_name in {"$$props", "$$restProps", "$$slots"}:
            continue
        # Check if prop is referenced in template or script body after declaration
        if not re.search(r'(?<!export\s+)let\s+' + re.escape(prop_name) + r'\b', all_text):
            if re.search(r'\{' + re.escape(prop_name) + r'\}', template_text) is None and \
               re.search(r'\b' + re.escape(prop_name) + r'\b', all_text[all_text.find(prop_name) + len(prop_name):]) is None:
                issues.append({
                    "file": str(fp),
                    "type": "svelte_unused_prop",
                    "severity": "info",
                    "message": f"Exported prop '{prop_name}' is never used in template",
                    "line": line,
                })

    # === Check local state never changes ===
    for name, line in local_lets:
        if name not in mutated_names:
            issues.append({
                "file": str(fp),
                "type": "svelte_state_never_changes",
                "severity": "warning",
                "message": f"Local state '{name}' is declared but never reassigned — state never changes",
                "line": line,
            })

    # === Check Svelte 5 $state never changes ===
    for name, line in svelte5_state:
        if name not in mutated_names:
            issues.append({
                "file": str(fp),
                "type": "svelte5_state_never_changes",
                "severity": "warning",
                "message": f"$state '{name}' is declared but never reassigned — state never changes",
                "line": line,
            })

    # === Check writable store never updated ===
    for name, line in writable_stores:
        if name not in mutated_names:
            issues.append({
                "file": str(fp),
                "type": "svelte_store_never_updated",
                "severity": "warning",
                "message": f"Store '{name}' is declared but never set/updated",
                "line": line,
            })

    # === Missing loading/error state ===
    if not re.search(r'loading|isLoading', content, re.IGNORECASE):
        if re.search(r'fetch|onMount\s*\(.*\{|load\s*function', content, re.IGNORECASE):
            issues.append({
                "file": str(fp),
                "type": "svelte_missing_loading_state",
                "severity": "warning",
                "message": "Component loads data but has no loading state",
                "line": 1,
            })

    if not re.search(r'error\w*|hasError', content, re.IGNORECASE):
        if re.search(r'fetch|try\s*\{|catch', content, re.IGNORECASE):
            issues.append({
                "file": str(fp),
                "type": "svelte_missing_error_state",
                "severity": "warning",
                "message": "Component handles async operations but has no error state",
                "line": 1,
            })

    return issues


# ---------------------------------------------------------------------------
# Context provider/consumer analysis (cross-file via filename heuristics)
# ---------------------------------------------------------------------------

def analyze_context_providers(files: list[Path]) -> list[dict]:
    """Scan for context providers without consumers in the project."""
    issues = []
    context_records: dict[str, dict[str, list[Path]]] = {}

    for fp in files:
        content = read_file_safe(fp)
        if not content:
            continue

        # Find createContext calls
        for m in re.finditer(r'(\w+)\s*=\s*createContext\s*\(', content):
            ctx = m.group(1)
            # Check if also consumed with useContext in same file
            if re.search(r'useContext\s*\(\s*' + re.escape(ctx) + r'\s*\)', content) is None:
                context_records.setdefault(ctx, {"providers": [], "consumers": []})
                context_records[ctx]["providers"].append(fp)

        # Find Provider usage (ContextName.Provider)
        for m in re.finditer(r'(\w+)\.Provider\b', content):
            ctx = m.group(1)
            context_records.setdefault(ctx, {"providers": [], "consumers": []})
            if fp not in context_records[ctx]["providers"]:
                context_records[ctx]["providers"].append(fp)

        # Find useContext calls
        for m in re.finditer(r'useContext\s*\(\s*(\w+)\s*\)', content):
            ctx = m.group(1)
            context_records.setdefault(ctx, {"providers": [], "consumers": []})
            context_records[ctx]["consumers"].append(fp)

    for ctx_name, info in context_records.items():
        providers = info["providers"]
        consumers = info["consumers"]
        if providers and not consumers:
            for fp in providers:
                issues.append({
                    "file": str(fp),
                    "type": "context_provider_no_consumer",
                    "severity": "warning",
                    "message": f"Context '{ctx_name}' is provided but never consumed via useContext anywhere in project",
                    "line": 1,
                })
        elif consumers and not providers:
            for fp in consumers:
                issues.append({
                    "file": str(fp),
                    "type": "context_consumer_no_provider",
                    "severity": "info",
                    "message": f"Context '{ctx_name}' is consumed but never provided in project",
                    "line": 1,
                })

    return issues


# ---------------------------------------------------------------------------
# Generic missing loading / error state scan (all file types)
# ---------------------------------------------------------------------------

def analyze_missing_async_patterns(files: list[Path]) -> list[dict]:
    """Scan all files for components with async ops missing loading/error states."""
    issues = []

    for fp in files:
        content = read_file_safe(fp)
        if not content:
            continue

        has_async_operation = bool(re.search(
            r'fetch\s*\(|axios|\.get\s*\(|\.post\s*\(|\.put\s*\(|\.delete\s*\(|'
            r'useQuery|useMutation|useLazyQuery|apollo|graphql|'
            r'async\s+function|await\s+fetch',
            content,
        ))

        if not has_async_operation:
            continue

        has_loading = bool(re.search(
            r'loading|isLoading|isFetching|pending|isPending|status\s*[=:]\s*["\']loading["\']',
            content,
            re.IGNORECASE,
        ))

        has_error = bool(re.search(
            r'error\w*|isError|hasError|errorMessage|errorState|status\s*[=:]\s*["\']error["\']|'
            r'catch\s*\(|\.catch\s*\(|try\s*\{',
            content,
        ))

        if not has_loading:
            issues.append({
                "file": str(fp),
                "type": "missing_loading_state",
                "severity": "warning",
                "message": "Component has async operations but no loading state detected",
                "line": 1,
            })

        if not has_error:
            issues.append({
                "file": str(fp),
                "type": "missing_error_state",
                "severity": "warning",
                "message": "Component has async operations but no error state detected",
                "line": 1,
            })

    return issues


# ---------------------------------------------------------------------------
# Scanning dispatcher
# ---------------------------------------------------------------------------

def analyze_file(fp: Path, content: str) -> list[dict]:
    """Dispatch to the appropriate analyzer based on file extension."""
    ext = fp.suffix.lower()
    issues = []

    if ext in REACT:
        issues.extend(analyze_react(content, fp))
    elif ext in VUE:
        issues.extend(analyze_vue(content, fp))
    elif ext in SVELTE:
        issues.extend(analyze_svelte(content, fp))

    return issues


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------

ISSUE_LABELS = {
    "useState_never_changes": "🧊 useState never changes",
    "empty_effect_deps": "⚠️  useEffect empty deps",
    "effect_missing_deps": "ℹ️  useEffect missing deps",
    "state_set_never_read": "👻 State set but never read",
    "unused_prop": "📭 Unused prop",
    "context_provider_no_consumer": "🔌 Context provider without consumer",
    "context_consumer_no_provider": "🔌 Context consumer without provider",
    "missing_loading_state": "⏳ Missing loading state",
    "missing_error_state": "❌ Missing error state",
    "missing_expected_state": "🧩 Missing expected AI-editor state",
    "vue_ref_never_changes": "🧊 Vue ref never changes",
    "vue_ref_unused": "👻 Vue ref never used",
    "vue_watch_missing_deep": "ℹ️  Vue watch missing deep",
    "vue_missing_loading_state": "⏳ Missing loading state (Vue)",
    "vue_missing_error_state": "❌ Missing error state (Vue)",
    "svelte_unused_prop": "📭 Svelte unused prop",
    "svelte_state_never_changes": "🧊 Svelte state never changes",
    "svelte5_state_never_changes": "🧊 Svelte 5 $state never changes",
    "svelte_store_never_updated": "🧊 Svelte store never updated",
    "svelte_missing_loading_state": "⏳ Missing loading state (Svelte)",
    "svelte_missing_error_state": "❌ Missing error state (Svelte)",
}


def print_issue(issue: dict) -> None:
    """Pretty-print a single issue."""
    label = ISSUE_LABELS.get(issue["type"], f"🔍 {issue['type']}")
    sev = {
        "warning": " ⚠️ ",
        "info": " ℹ️ ",
        "error": " ❌ ",
    }.get(issue["severity"], " ⚠️ ")
    print(f"  {label}  | {issue['file']}:{issue['line']}")
    print(f"     {sev}{issue['message']}")


def print_report(all_issues: list[dict]) -> None:
    """Print a human-readable report of all issues."""
    if not all_issues:
        print("\n ✅ No state issues found!")
        print()
        return

    # Group by type
    by_type: dict[str, list[dict]] = defaultdict(list)
    for iss in all_issues:
        by_type[iss["type"]].append(iss)

    print(f"\n{'='*70}")
    print(f"  State Inspector Report — {len(all_issues)} issue(s) found")
    print(f"{'='*70}")

    # Summary
    severity_counts = Counter(iss["severity"] for iss in all_issues)
    print(f"  Warnings: {severity_counts.get('warning', 0)}  |  "
          f"Info: {severity_counts.get('info', 0)}  |  "
          f"Errors: {severity_counts.get('error', 0)}")
    print()

    for type_name, iss_list in sorted(by_type.items()):
        label = ISSUE_LABELS.get(type_name, type_name)
        print(f"  [{label}] — {len(iss_list)} occurrence(s)")
        for iss in iss_list[:5]:
            print(f"    • {iss['file']}:{iss['line']} — {iss['message']}")
        if len(iss_list) > 5:
            print(f"    ... and {len(iss_list) - 5} more")
        print()

    if severity_counts.get("warning", 0) > 0:
        print(" ⚠️  State issues detected — review warnings above")
    else:
        print(" ℹ️  Informational findings only")
    print()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description=("state_inspector.py — Analyze React/Vue/Svelte state usage and detect"
               "anti-patterns"),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
Examples:
  python state_inspector.py .
  python state_inspector.py src/ --json
  python state_inspector.py src/ --threshold 5
        """,
    )
    parser.add_argument("path", nargs="?", default=".", help="Project root directory")
    parser.add_argument("--json", "-j", action="store_true", help="Output as JSON")
    parser.add_argument("--threshold", "-t", type=int, default=3,
                        help="Minimum occurrences to report (default: 3)")
    parser.add_argument("--version", action="version",
                        version="state_inspector.py v1.0.0")

    args = parser.parse_args()

    target = Path(args.path).resolve()
    if not target.exists():
        print(f" ❌ '{args.path}' does not exist", file=sys.stderr)
        sys.exit(EXIT_ERROR)

    print(f"\n🔍 State Inspector v1.0.0 — scanning {target}")

    files = collect_source_files(target)
    if not files:
        print(" No source files found (.tsx .ts .jsx .js .vue .svelte)")
        sys.exit(EXIT_OK)

    print(f"   {len(files)} file(s) to scan")

    all_issues: list[dict] = []

    # Per-file analysis
    for fp in files:
        content = read_file_safe(fp)
        if not content:
            continue
        issues = analyze_file(fp, content)
        all_issues.extend(issues)

        # Also check for missing expected AI-code-editor states
        expected_issues = check_missing_expected_states(content, fp)
        all_issues.extend(expected_issues)

    # Cross-file analysis
    context_issues = analyze_context_providers(files)
    all_issues.extend(context_issues)

    # Global async pattern analysis
    async_issues = analyze_missing_async_patterns(files)
    all_issues.extend(async_issues)

    # Deduplicate by (file, type, line, message)
    seen = set()
    deduped = []
    for iss in all_issues:
        key = (iss["file"], iss["type"], iss["line"], iss["message"])
        if key not in seen:
            seen.add(key)
            deduped.append(iss)
    all_issues = deduped

    # Apply threshold filtering
    type_counts = Counter(iss["type"] for iss in all_issues)
    filtered = [iss for iss in all_issues if type_counts[iss["type"]] >= args.threshold]

    if args.json:
        print(json.dumps(filtered, indent=2, ensure_ascii=False))
    else:
        if len(filtered) < len(all_issues):
            print(f"\n   (Threshold >= {args.threshold} — "
                  f"{len(all_issues) - len(filtered)} low-frequency issue(s) hidden)")
        print_report(filtered)

    # Exit code
    if any(iss["severity"] == "warning" for iss in filtered):
        sys.exit(EXIT_ISSUES)

    sys.exit(EXIT_OK)


if __name__ == "__main__":
    main()
