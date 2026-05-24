# Minting a Zenodo DOI for AWB releases

Zenodo provides a citable DOI for every GitHub release of AWB so academic
work can cite a specific version without ambiguity. The integration is
one-time setup, then automatic on every tagged release.

**Status: ENABLED.** The Zenodo-GitHub integration is active on
`xmpuspus/ai-workflow-benchmark`. v1.3.0 was the first release to mint a
DOI through this pipeline.

- **Concept DOI** (always-latest): [10.5281/zenodo.20361437](https://doi.org/10.5281/zenodo.20361437)
- **v1.3.0 version DOI**: [10.5281/zenodo.20361438](https://doi.org/10.5281/zenodo.20361438)

## One-time setup (already done for this repo)

1. Sign in at <https://zenodo.org> using your GitHub account.
2. Open <https://zenodo.org/account/settings/github/>.
3. Find `xmpuspus/ai-workflow-benchmark` in the list and toggle it ON.
4. Verify the repo's `CITATION.cff` and `codemeta.json` are present
   (they live at the repo root and ship with v1.2.0+).

## Per-release

1. Tag a release: `git tag v1.3.0 && git push origin v1.3.0`.
2. Create a GitHub release for that tag, either via the web UI or
   `gh release create v1.3.0 --title "..." --notes "..."`. Use the
   `gh` form when scripting — it triggers the same Zenodo webhook.
3. Zenodo's GitHub webhook fires (visible at
   `gh api repos/xmpuspus/ai-workflow-benchmark/hooks/<hook-id>/deliveries`)
   and accepts the event with HTTP 202. Mint typically completes within
   60 seconds; public search indexing lags by a few minutes.
4. Fetch the new DOI via the latest-DOI badge URL (resolves to the
   current version DOI):
   ```bash
   curl -sIL "https://zenodo.org/badge/latestdoi/$(gh api repos/xmpuspus/ai-workflow-benchmark --jq .id)" \
     | grep -i 'location: https://doi.org/' | head -1
   ```
5. Update the README badge + BibTeX with the new version DOI. The
   concept DOI (`10.5281/zenodo.20361437`) stays the same across
   releases — only the version-specific DOI changes.

## Concept DOI vs version DOI

Zenodo issues two DOIs:
- **Concept DOI** — resolves to the latest version (use in living docs)
- **Version DOI** — resolves to one specific release (use in papers)

Cite the version DOI when reporting numbers; cite the concept DOI when
pointing at the project in general.

## Citation example (BibTeX)

After the DOI is minted, the citation in a paper looks like:

```bibtex
@software{puspus_awb_2026,
  author       = {Puspus, Xavier},
  title        = {{AWB: AI Workflow Benchmark}},
  month        = apr,
  year         = 2026,
  publisher    = {Zenodo},
  version      = {1.2.0},
  doi          = {10.5281/zenodo.XXXXXXX},
  url          = {https://doi.org/10.5281/zenodo.XXXXXXX}
}
```
