"""
ContextFormatter — renders ContextPackage data into various output formats.

Supports:
- Markdown (for task files and human review)
- JSON (for machine consumption)
- Plain text summary (for CLI output)
"""

from __future__ import annotations

import textwrap
from typing import List

from lynkmesh_ai.context.schema import ContextPackage, ContextFile, ContextDependency, RecentChange


class ContextFormatter:
    """
    Formats ContextPackage data for different consumers.

    Each formatter takes a ContextPackage and returns a string.
    """

    # ------------------------------------------------------------------
    # Markdown (primary format for Claude task files)
    # ------------------------------------------------------------------

    @staticmethod
    def to_markdown(pkg: ContextPackage, title: str = "Context Package") -> str:
        """Render a ContextPackage as a structured Markdown document."""
        sections: List[str] = []

        # Header
        sections.append(f"# {title}")
        sections.append("")
        sections.append(f"**Module:** `{pkg.module}`")
        sections.append(f"**Risk Score:** `{pkg.risk_score}`")
        sections.append(f"**Files:** {pkg.file_count} | **Dependencies:** {pkg.dependency_count}")
        sections.append(f"**Generated:** {pkg.metadata.get('generated_at', 'N/A')}")
        sections.append("")
        sections.append("---")
        sections.append("")

        # Files section
        if pkg.files:
            sections.append("## Files")
            sections.append("")
            for f in pkg.files:
                sections.extend(ContextFormatter._format_file_md(f))
            sections.append("")

        # Dependencies section
        if pkg.dependencies:
            sections.append("## Dependencies")
            sections.append("")
            sections.append("| Source | Target | Type | Weight |")
            sections.append("|--------|--------|------|--------|")
            for dep in pkg.dependencies:
                sections.append(f"| `{dep.source}` | `{dep.target}` | {dep.relation_type} | {dep.weight} |")
            sections.append("")

        # Recent Changes section
        if pkg.recent_changes:
            sections.append("## Recent Changes")
            sections.append("")
            for ch in pkg.recent_changes:
                sections.extend(ContextFormatter._format_change_md(ch))
            sections.append("")

        # Metadata section
        if pkg.metadata:
            sections.append("## Metadata")
            sections.append("")
            sections.append("```json")
            import json
            meta_copy = {k: v for k, v in pkg.metadata.items() if k != "graph_stats"}
            sections.append(json.dumps(meta_copy, indent=2, default=str))
            sections.append("```")
            sections.append("")

        return "\n".join(sections)

    @staticmethod
    def _format_file_md(f: ContextFile) -> List[str]:
        """Format a single ContextFile as markdown."""
        lines = [
            f"### `{f.module_name}`",
            f"**Path:** `{f.path}`",
            f"**LoC:** {f.lines_of_code}",
        ]
        if f.classes:
            lines.append(f"**Classes:** {', '.join(f'`{c}`' for c in f.classes)}")
        if f.functions:
            lines.append(f"**Functions:** {', '.join(f'`{fn}`' for fn in f.functions)}")
        if f.imports:
            imports_display = f.imports[:10]
            suffix = "..." if len(f.imports) > 10 else ""
            lines.append(f"**Imports:** {', '.join(f'`{i}`' for i in imports_display)}{suffix}")
        if f.docstring:
            doc = textwrap.shorten(f.docstring, width=120, placeholder="...")
            lines.append(f"**Doc:** {doc}")

        if f.content_snippet:
            lines.append("")
            lines.append("```python")
            lines.append(f.content_snippet)
            lines.append("```")

        lines.append("")
        return lines

    @staticmethod
    def _format_change_md(ch: RecentChange) -> List[str]:
        """Format a RecentChange as markdown."""
        lines = [
            f"- **{ch.change_type.upper()}** — `{ch.file_path}`",
        ]
        if ch.commit_hash:
            lines.append(f"  - Commit: `{ch.commit_hash[:8]}`")
        if ch.lines_added or ch.lines_removed:
            lines.append(f"  - +{ch.lines_added}/-{ch.lines_removed} lines")
        if ch.diff_snippet:
            lines.append("")
            lines.append("```diff")
            lines.append(ch.diff_snippet[:500])
            lines.append("```")
        return lines

    # ------------------------------------------------------------------
    # JSON (machine-readable)
    # ------------------------------------------------------------------

    @staticmethod
    def to_json(pkg: ContextPackage, indent: int = 2) -> str:
        """Render a ContextPackage as formatted JSON."""
        return pkg.to_json(indent=indent)

    # ------------------------------------------------------------------
    # Plain text summary (CLI output)
    # ------------------------------------------------------------------

    @staticmethod
    def to_summary(pkg: ContextPackage) -> str:
        """Render a one-page plain-text summary for CLI output."""
        lines = [
            "╔══════════════════════════════════════════════════╗",
            "║        LynkMesh AI — Context Summary             ║",
            "╚══════════════════════════════════════════════════╝",
            "",
            f"  Module:        {pkg.module}",
            f"  Risk Score:    {pkg.risk_score.upper()}",
            f"  Files:         {pkg.file_count}",
            f"  Dependencies:  {pkg.dependency_count}",
            f"  Changes:       {len(pkg.recent_changes)}",
            f"  Total LoC:     {pkg.total_loc}",
            "",
        ]

        if pkg.files:
            lines.append("  Files:")
            for f in pkg.files:
                lines.append(f"    - {f.module_name} ({f.lines_of_code} loc)")

        if pkg.dependencies:
            lines.append("")
            lines.append("  Key Dependencies:")
            # Show top 10 weighted deps
            sorted_deps = sorted(pkg.dependencies, key=lambda d: d.weight, reverse=True)[:10]
            for dep in sorted_deps:
                lines.append(f"    - {dep.source} ──{dep.relation_type}──▶ {dep.target}")

        if pkg.recent_changes:
            lines.append("")
            lines.append("  Recent Changes:")
            for ch in pkg.recent_changes:
                lines.append(f"    - [{ch.change_type}] {ch.file_path}")

        lines.append("")
        return "\n".join(lines)
