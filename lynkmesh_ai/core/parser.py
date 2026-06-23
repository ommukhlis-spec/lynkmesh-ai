"""
ModuleParser — AST-based Python source parser.

Extracts imports, function calls, class/function definitions, and
module-level metadata from Python source files.
"""

from __future__ import annotations

import ast
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)


class ModuleInfo:
    """Parsed information about a single Python module."""

    __slots__ = (
        "name",
        "file_path",
        "package",
        "imports",
        "from_imports",
        "function_calls",
        "classes",
        "functions",
        "async_functions",
        "top_level_names",
        "lines_of_code",
        "docstring",
        "has_entry_point",
        "decorators",
        "class_bases",
        "class_methods",
    )

    def __init__(
        self,
        name: str = "",
        file_path: str = "",
        package: str = "",
    ) -> None:
        self.name = name
        self.file_path = file_path
        self.package = package
        self.imports: List[str] = []
        self.from_imports: List[Tuple[str, str]] = []  # (module, name)
        self.function_calls: Set[str] = set()
        self.classes: List[str] = []
        self.functions: List[str] = []
        self.async_functions: List[str] = []
        self.top_level_names: Set[str] = set()
        self.lines_of_code: int = 0
        self.docstring: Optional[str] = None
        self.has_entry_point: bool = False
        self.decorators: Dict[str, List[str]] = {}  # func_name → [decorator_names]
        self.class_bases: Dict[str, List[str]] = {}  # class_name → [base_class_names]
        self.class_methods: Dict[str, List[str]] = {}  # class_name → [method_names]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "file_path": self.file_path,
            "package": self.package,
            "imports": self.imports,
            "from_imports": [(m, n) for m, n in self.from_imports],
            "function_calls": sorted(self.function_calls),
            "classes": self.classes,
            "functions": self.functions,
            "async_functions": self.async_functions,
            "lines_of_code": self.lines_of_code,
            "docstring": self.docstring,
            "has_entry_point": self.has_entry_point,
            "class_bases": dict(self.class_bases),
            "class_methods": dict(self.class_methods),
        }


class ModuleParser:
    """
    Parses Python source files into structured ModuleInfo objects.

    Uses the built-in `ast` module — no external dependencies.
    """

    # Standard library module names for filtering
    _STDLIB_MODULES: Set[str] = {
        "abc", "aifc", "argparse", "array", "ast", "asynchat", "asyncio",
        "asyncore", "atexit", "audioop", "base64", "bdb", "binascii", "binhex",
        "bisect", "builtins", "bz2", "calendar", "cgi", "cgitb", "chunk", "cmath",
        "cmd", "code", "codecs", "codeop", "collections", "colorsys", "compileall",
        "concurrent", "configparser", "contextlib", "contextvars", "copy", "copyreg",
        "cProfile", "crypt", "csv", "ctypes", "curses", "dataclasses", "datetime",
        "dbm", "decimal", "difflib", "dis", "distutils", "doctest", "email",
        "encodings", "enum", "errno", "faulthandler", "fcntl", "filecmp",
        "fileinput", "fnmatch", "formatter", "fractions", "ftplib", "functools",
        "gc", "getopt", "getpass", "gettext", "glob", "grp", "gzip", "hashlib",
        "heapq", "hmac", "html", "http", "idlelib", "imaplib", "imghdr", "imp",
        "importlib", "inspect", "io", "ipaddress", "itertools", "json", "keyword",
        "lib2to3", "linecache", "locale", "logging", "lzma", "mailbox", "mailcap",
        "marshal", "math", "mimetypes", "mmap", "modulefinder", "multiprocessing",
        "netrc", "nis", "nntplib", "numbers", "operator", "optparse", "os",
        "ossaudiodev", "parser", "pathlib", "pdb", "pickle", "pickletools",
        "pipes", "pkgutil", "platform", "plistlib", "poplib", "posix", "posixpath",
        "pprint", "profile", "pstats", "pty", "pwd", "py_compile", "pyclbr",
        "pydoc", "queue", "quopri", "random", "re", "readline", "reprlib",
        "resource", "rlcompleter", "runpy", "sched", "secrets", "select",
        "selectors", "shelve", "shlex", "shutil", "signal", "site", "smtpd",
        "smtplib", "sndhdr", "socket", "socketserver", "sqlite3", "ssl", "stat",
        "statistics", "string", "stringprep", "struct", "subprocess", "sunau",
        "symbol", "symtable", "sys", "sysconfig", "syslog", "tabnanny", "tarfile",
        "telnetlib", "tempfile", "termios", "test", "textwrap", "threading",
        "time", "timeit", "tkinter", "token", "tokenize", "trace", "traceback",
        "tracemalloc", "tty", "turtle", "turtledemo", "types", "typing",
        "unicodedata", "unittest", "urllib", "uu", "uuid", "venv", "warnings",
        "wave", "weakref", "webbrowser", "winreg", "winsound", "wsgiref", "xdrlib",
        "xml", "xmlrpc", "zipapp", "zipfile", "zipimport", "zlib",
        "__future__", "_thread",
    }

    def __init__(self, target_dir: Optional[Path] = None) -> None:
        self.target_dir = target_dir or Path.cwd()
        self._parsed: Dict[str, ModuleInfo] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def parse_directory(self, directory: Optional[Path] = None, recursive: bool = True) -> List[ModuleInfo]:
        """
        Parse all Python files in a directory.

        Args:
            directory: Target directory (defaults to self.target_dir).
            recursive: Whether to recurse into subdirectories.

        Returns:
            List of ModuleInfo for each parsed file.
        """
        target = directory or self.target_dir
        target = Path(target)
        results: List[ModuleInfo] = []

        pattern = "**/*.py" if recursive else "*.py"
        for py_file in target.glob(pattern):
            # Skip __pycache__, .venv, etc.
            if any(part.startswith(".") or part == "__pycache__" for part in py_file.parts):
                continue
            info = self.parse_file(py_file)
            if info:
                results.append(info)

        logger.info(f"Parsed {len(results)} Python files from {target}")
        return results

    def parse_file(self, file_path: Path) -> Optional[ModuleInfo]:
        """
        Parse a single Python file into a ModuleInfo.

        Args:
            file_path: Path to the .py file.

        Returns:
            ModuleInfo or None if parsing fails.
        """
        file_path = Path(file_path)
        if not file_path.exists() or file_path.suffix != ".py":
            logger.warning(f"Skipping non-Python file: {file_path}")
            return None

        try:
            source = file_path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            logger.error(f"Failed to read {file_path}: {exc}")
            return None

        try:
            tree = ast.parse(source, filename=str(file_path))
        except SyntaxError as exc:
            logger.error(f"Syntax error in {file_path}: {exc}")
            return None

        # Determine module name
        module_name = self._resolve_module_name(file_path)
        package = self._resolve_package(file_path)

        info = ModuleInfo(
            name=module_name,
            file_path=str(file_path.resolve()),
            package=package,
        )
        info.lines_of_code = len(source.splitlines())
        info.docstring = ast.get_docstring(tree)

        # Walk the AST
        visitor = _ModuleVisitor(info)
        visitor.visit(tree)

        # Check for entry point
        info.has_entry_point = self._check_entry_point(tree)

        self._parsed[module_name] = info
        return info

    def get_info(self, module_name: str) -> Optional[ModuleInfo]:
        """Retrieve previously parsed module info."""
        return self._parsed.get(module_name)

    # ------------------------------------------------------------------
    # Resolution helpers
    # ------------------------------------------------------------------

    def _resolve_module_name(self, file_path: Path) -> str:
        """
        Convert a file path to a dotted module name relative to target_dir.

        Example: src/lynkmesh_ai/core/graph.py → lynkmesh_ai.core.graph
        """
        rel = file_path.resolve().relative_to(self.target_dir.resolve())
        parts = list(rel.parts)
        if parts[-1] == "__init__.py":
            parts = parts[:-1]
        else:
            parts[-1] = parts[-1].replace(".py", "")
        return ".".join(parts)

    def _resolve_package(self, file_path: Path) -> str:
        """Extract the top-level package name from the file path."""
        rel = file_path.resolve().relative_to(self.target_dir.resolve())
        parts = list(rel.parts)
        if parts[0].endswith(".py"):
            return ""
        return parts[0]

    def _check_entry_point(self, tree: ast.Module) -> bool:
        """Check if the module has an `if __name__ == '__main__'` block."""
        for node in ast.walk(tree):
            if isinstance(node, ast.If):
                test_str = ast.unparse(node.test) if hasattr(ast, "unparse") else ""
                if "__name__" in test_str and "__main__" in test_str:
                    return True
        return False

    @classmethod
    def is_stdlib(cls, module_name: str) -> bool:
        """Check if a module name is in the Python standard library."""
        top_level = module_name.split(".")[0]
        return top_level in cls._STDLIB_MODULES


class _ModuleVisitor(ast.NodeVisitor):
    """AST visitor that populates a ModuleInfo object."""

    def __init__(self, info: ModuleInfo) -> None:
        self.info = info
        self._current_class: Optional[str] = None

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            self.info.imports.append(alias.name)
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        module = node.module or ""
        for alias in node.names:
            self.info.from_imports.append((module, alias.name))
            if module:
                # Track the parent module import
                top = module.split(".")[0]
                if top and top not in self.info.imports:
                    self.info.imports.append(top)
        self.generic_visit(node)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self.info.classes.append(node.name)
        self._current_class = node.name
        # Capture base class names
        bases = []
        for base in node.bases:
            base_name = _base_class_name(base)
            if base_name:
                bases.append(base_name)
        if bases:
            self.info.class_bases[node.name] = bases
        # Track decorators
        dec_names = [_get_decorator_name(d) for d in node.decorator_list]
        dec_names = [d for d in dec_names if d]
        if dec_names:
            self.info.decorators[node.name] = dec_names
        self.generic_visit(node)
        self._current_class = None

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self.info.functions.append(node.name)
        # Record method under current class
        if self._current_class:
            self.info.class_methods.setdefault(self._current_class, []).append(node.name)
        dec_names = [_get_decorator_name(d) for d in node.decorator_list]
        dec_names = [d for d in dec_names if d]
        if dec_names:
            self.info.decorators[node.name] = dec_names
        self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self.info.async_functions.append(node.name)
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        """Extract function call names."""
        name = _call_name(node)
        if name:
            self.info.function_calls.add(name)
        self.generic_visit(node)

    def visit_Assign(self, node: ast.Assign) -> None:
        """Capture top-level assigned names."""
        for target in node.targets:
            if isinstance(target, ast.Name):
                self.info.top_level_names.add(target.id)
        self.generic_visit(node)


def _get_decorator_name(node: ast.expr) -> Optional[str]:
    """Extract a decorator name from an AST node."""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return ast.unparse(node) if hasattr(ast, "unparse") else node.attr
    if isinstance(node, ast.Call):
        func = node.func
        if isinstance(func, ast.Name):
            return func.id
        if isinstance(func, ast.Attribute):
            return ast.unparse(func) if hasattr(ast, "unparse") else func.attr
    return None


def _base_class_name(node: ast.expr) -> Optional[str]:
    """Extract a base class name from an AST expression node.

    Handles: Name, Attribute, and Subscript (e.g., Generic[T]) nodes.
    """
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return ast.unparse(node) if hasattr(ast, "unparse") else node.attr
    if isinstance(node, ast.Subscript):
        # Generic[T] → extract the base name
        if isinstance(node.value, ast.Name):
            return node.value.id
        if isinstance(node.value, ast.Attribute):
            return ast.unparse(node.value) if hasattr(ast, "unparse") else node.value.attr
    if isinstance(node, ast.Call):
        # Some base classes are calls, e.g., ABCMeta()
        func = node.func
        if isinstance(func, ast.Name):
            return func.id
        if isinstance(func, ast.Attribute):
            return ast.unparse(func) if hasattr(ast, "unparse") else func.attr
    return None


def _call_name(node: ast.Call) -> Optional[str]:
    """Extract a function call name from an AST Call node."""
    func = node.func
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        if hasattr(ast, "unparse"):
            return ast.unparse(func)
        # Fallback: build dotted name
        parts = []
        current = func
        while isinstance(current, ast.Attribute):
            parts.append(current.attr)
            current = current.value
        if isinstance(current, ast.Name):
            parts.append(current.id)
        return ".".join(reversed(parts))
    return None
