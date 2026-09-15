# Real-PDF test fixtures

Real, published papers used by `tests/test_pdf_identify_real.py` to validate
`bibtui.pdf.identify.extract_identifier` against actual journal/arXiv PDFs
(multi-column layouts, embedded fonts, reference-list DOIs, publisher
boilerplate, …) rather than only the hand-built single-page PDFs in
`tests/test_pdf_identify.py`. Each is kept here only because its license
permits redistribution; do not add a PDF to this directory without checking
its license first — "open access" alone does not imply that.

| File | Title | Authors | DOI | License |
| --- | --- | --- | --- | --- |
| `sensors-26-05829.pdf` | Effects of Cervical Motion Restriction on Wheelchair Propulsion Velocity and Upper-Limb Kinematics in Healthy Individuals | Sobu, Sekiguchi, Wang, Honda, Kuroki, Suzuki, Nagatomi, Ebihara | [10.3390/s26185829](https://doi.org/10.3390/s26185829) | [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/) (MDPI *Sensors*) |
| `tc-20-5061-2026.pdf` | Brief communication: Shared parameterisation for estimating snow water equivalent through cosmic ray neutron sensors in the Italian Alps | Gallarate, Colombo, Gazzola, Valt, Ronchi, Lanteri, Dinale, Nadalet, Ferraris, Gentile, Gisolo, Giardino, Freppaz, Acquaotta | [10.5194/tc-20-5061-2026](https://doi.org/10.5194/tc-20-5061-2026) | [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/) (Copernicus, *The Cryosphere*) |
| `2609.13974v1.pdf` | Fragmented uptake drives lipid accumulation in macrophage cannibalistic efferocytosis | Chambers, Keith L. | [10.48550/arXiv.2609.13974](https://arxiv.org/abs/2609.13974) (pending CrossRef registration as of 2026-09-15) | [CC BY-NC-ND 4.0](https://creativecommons.org/licenses/by-nc-nd/4.0/) (arXiv) |

An earlier fourth fixture (a 2003 `hep-lat` preprint) was removed: arXiv
papers from that era carry only its "assumed 1991-2003" license, which
grants arXiv itself distribution rights but does not clearly cover
redistribution from a third-party repository like this one.
