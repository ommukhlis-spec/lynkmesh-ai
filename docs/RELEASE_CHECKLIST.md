# Release Checklist

Use this checklist for every release of LynkMesh AI.

## Pre-Release

### Clean Clone Test

```bash
cd /tmp
git clone https://github.com/ommukhlis-spec/lynkmesh-ai.git
cd lynkmesh-ai
```

### Install Test

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
```

### Smoke Tests

```bash
# 1. Import
python -c "import lynkmesh_ai; print(lynkmesh_ai.__version__)"

# 2. CLI help
lynkmesh-ai --help

# 3. Scan
lynkmesh-ai scan --dir examples/sample_project

# 4. Run (backward compat -- no flags)
lynkmesh-ai run --module auth.service --dir examples/sample_project

# 5. Run (semantic)
lynkmesh-ai run --module auth.service --dir examples/sample_project --semantic

# 6. Run (reasoning)
lynkmesh-ai run --module auth.service --dir examples/sample_project --reason

# 7. Semantic CLI
lynkmesh-ai semantic analyze --dir examples/sample_project
lynkmesh-ai semantic patterns --all --dir examples/sample_project
lynkmesh-ai semantic role --module auth.service --dir examples/sample_project

# 8. Reasoning CLI
lynkmesh-ai reasoning analyze --dir examples/sample_project
lynkmesh-ai reasoning risk --module auth.service --dir examples/sample_project

# 9. Knowledge CLI
lynkmesh-ai knowledge summary --dir examples/sample_project

# 10. Status
lynkmesh-ai status --dir examples/sample_project
```

### Pre-Release Checks

- [ ] `CHANGELOG.md` updated with this version's changes
- [ ] `__init__.py` version bumped
- [ ] `pyproject.toml` version matches
- [ ] `README.md` reflects current features
- [ ] All `.ai/` runtime artifacts gitignored (verify: `git status` shows no `.ai/` files)
- [ ] No secrets in source (`grep -rE "api_key|token.*=|password.*=" lynkmesh_ai/`)
- [ ] `pip install -e .` succeeds on clean Python 3.11+

## Release

### Git

```bash
git checkout main
git pull origin main
git tag -a vX.Y.Z -m "vX.Y.Z: <one-line summary>"
git push origin main --tags
```

### GitHub Release

1. Go to https://github.com/ommukhlis-spec/lynkmesh-ai/releases/new
2. Choose the tag `vX.Y.Z`
3. Title: `vX.Y.Z -- <release name>`
4. Copy the relevant section from CHANGELOG.md into the description
5. Publish

## Post-Release

- [ ] Verify the release appears on GitHub
- [ ] Verify the tag is visible
- [ ] Announce in relevant channels (Discord, Twitter, etc.)
- [ ] Bump version in `__init__.py` to next dev version (e.g., `0.4.0.dev0`)
