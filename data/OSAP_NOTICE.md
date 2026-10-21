# osap_SignalDoc.csv.gz

A verbatim, gzipped copy of `SignalDoc.csv` from the Open Source Asset Pricing project
(https://github.com/OpenSourceAP/CrossSection, downloaded 2026-10-20; 331 signals, 212 of them predictors).
It documents each published cross-sectional predictor: acronym, authors, year, journal, data category, sign, the
original paper's t-stat and long-short return, and a detailed definition.

The file is distributed under the GNU General Public License v2 (the repository's licence). Cite:

Chen, Andrew Y. and Tom Zimmermann (2022), "Open Source Cross-Sectional Asset Pricing", Critical Finance Review 11(2),
207-264. https://papers.ssrn.com/abstract=3604626

HYPOLAB reads it with `ideaengine.collectors.read_osap()` (Ideas app: Leads > From outside > Published predictors >
Load the bundled list). "Download the latest" fetches the current version from GitHub instead.
