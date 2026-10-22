# Data sources

## Synthetic samples (in this repository)

Everything under `samples/` was written for this project. The company "Acme Shop" is fictional.

## Real ADRs (downloaded, not committed)

`scripts/fetch_real_adrs.py` downloads real Architecture Decision Records into `data/real-adrs/`
(git-ignored), only from repositories under a permissive licence, and writes `ATTRIBUTION.md`
listing every source repository and its licence.

The ADRs are selected with the dataset of:

> G. Buchgeher, S. Schöberl, V. Geist, B. Dorninger, P. Haindl and R. Weinreich,
> "Using Architecture Decision Records in Open Source Projects – An MSR Study on GitHub",
> *IEEE Access*, 2023. DOI: [10.1109/ACCESS.2023.3287654](https://doi.org/10.1109/ACCESS.2023.3287654)

as packaged in the replication package of "Evaluating Large Language Models for Detecting
Architectural Decision Violations" ([arXiv 2602.07609](https://arxiv.org/abs/2602.07609),
[Zenodo 10.5281/zenodo.17799431](https://doi.org/10.5281/zenodo.17799431)).
Dataset licence: CC BY 4.0; scripts: MIT. The dataset contains metadata only: each ADR remains
under the licence of its own repository.
