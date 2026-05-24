# Minting a Zenodo DOI for AWB releases

Zenodo provides a citable DOI for every GitHub release of AWB so academic
work can cite a specific version without ambiguity. The integration is
one-time setup, then automatic on every tagged release.

## One-time setup

1. Sign in at <https://zenodo.org> using your GitHub account.
2. Open <https://zenodo.org/account/settings/github/>.
3. Find `xmpuspus/ai-workflow-benchmark` in the list and toggle it ON.
4. Verify the repo's `CITATION.cff` and `codemeta.json` are present
   (they live at the repo root and ship with v1.2.0+).

## Per-release

1. Tag a release: `git tag v1.2.0-zenodo && git push origin v1.2.0-zenodo`.
2. Create a GitHub release for that tag at
   <https://github.com/xmpuspus/ai-workflow-benchmark/releases/new>.
3. Zenodo automatically:
   - Mints a DOI for that release
   - Archives the source tarball
   - Pulls metadata from `CITATION.cff`
4. Copy the DOI from the Zenodo dashboard and add it to README badges:
   ```markdown
   [![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.XXXXXXX.svg)](https://doi.org/10.5281/zenodo.XXXXXXX)
   ```

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
