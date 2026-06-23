# Contributing to LynkMesh AI

Thanks for your interest. This guide will help you get started.

## Architecture

LynkMesh AI has a strict layer architecture:

```
reasoning/  ->  semantic/ + knowledge/  ->  core/
```

- **No circular dependencies between layers.** Upper layers may import from lower layers; lower layers must never import from upper layers.
- **No external dependencies.** Everything uses the Python 3.11+ standard library. Before importing a third-party package, discuss it in an issue.
- **Backward compatible serialization.** All new fields on ContextPackage, KnowledgeFact, and graph types must have sensible defaults so old JSON files load without errors.

## Setup

```bash
git clone https://github.com/ommukhlis-spec/lynkmesh-ai.git
cd lynkmesh-ai
python -m venv .venv
source .venv/bin/activate   # or .venv\Scripts\activate on Windows
pip install -e .

# Verify
lynkmesh-ai scan --dir examples/sample_project
lynkmesh-ai run --module auth.service --dir examples/sample_project
```

## Making Changes

1. **Open an issue first** for features or significant refactors. Bug fixes can go straight to a PR.
2. **Create a branch** from `main`: `git checkout -b feature/my-change`
3. **Write the code.** Follow the patterns in existing modules:
   - Dataclasses for data (`to_dict` / `from_dict` / `save` / `load`)
   - Composition over inheritance when wrapping core types
   - Logging with `logging.getLogger(__name__)`
4. **Test manually.** Run the smoke tests:
   ```bash
   lynkmesh-ai scan --dir examples/sample_project
   lynkmesh-ai run --module auth.service --dir examples/sample_project --semantic --reason
   lynkmesh-ai --help
   ```
5. **Verify backward compatibility.** The old pipeline must still work:
   ```bash
   lynkmesh-ai run --module auth.service --dir examples/sample_project
   ```
6. **Submit a PR** using the pull request template.

## Adding a New Analyzer

If you are adding a new analyzer to `semantic/` or `reasoning/`:

1. Create the new module in the correct subpackage
2. Add type dataclasses with `to_dict()` / `from_dict()`
3. Add a separate serializer method if needed
4. Wire it into the orchestrator (`SemanticAnalyzer` or the reasoning pipeline)
5. Add CLI subcommands in `cli.py`
6. Update `__init__.py` exports
7. Update CHANGELOG.md

## Commit Messages

Use conventional commit style:

```
feat(semantic): add dead-code detector
fix(graph): handle empty edge list in topological_sort
docs(readme): add installation instructions for Windows
```

## Questions?

Open a [discussion](https://github.com/ommukhlis-spec/lynkmesh-ai/discussions) or ask in an issue.
