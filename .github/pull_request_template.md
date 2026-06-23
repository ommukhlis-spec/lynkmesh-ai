## Summary

<!-- What does this PR do? One paragraph. -->

## Type

- [ ] Bug fix
- [ ] New feature
- [ ] Architecture / refactor
- [ ] Documentation
- [ ] CI / tooling

## Layer Affected

<!-- Which layer does this change touch? Delete those that do not apply. -->

- [ ] Core (graph, parser, resolver, change tracker)
- [ ] Semantic (patterns, roles, domains, similarity)
- [ ] Knowledge (facts, base, extractor)
- [ ] Reasoning (architecture, impact, decision, risk)
- [ ] Bridges (task generator, inbox)
- [ ] CLI

## Testing

<!-- How did you test this change? -->

- [ ] Smoke test (`lynkmesh-ai scan --dir examples/sample_project`)
- [ ] Pipeline test (`lynkmesh-ai run --module auth.service`)
- [ ] New unit tests added
- [ ] Backward compatibility verified

## Checklist

- [ ] No new dependencies added (stdlib only)
- [ ] All existing CLI commands still work
- [ ] Serialization backward compatible (old JSON files load correctly)
- [ ] README / CHANGELOG updated if needed
