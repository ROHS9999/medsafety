# Medication Safety Dataset Guide

## Purpose and scope

This folder contains cleaned CSV exports from the source files in the parent `Dataset/` folder. The source downloads remain unchanged there. The exports are grouped by their original dataset or source family; files from different sources have not been merged.

The tables are complementary reference data: medicine catalogues, drug classification and terminology, drug–drug interactions, indications and adverse effects, disease codes, and patient-facing health topics. They can support later matching and analysis, but they do not share one universal identifier. A matching medicine name is not sufficient proof that two records describe the same ingredient, formulation, strength, route, or product.

## Folder and file layout

All cleaned tables are comma-separated CSV files encoded as UTF-8 with a byte-order mark (BOM). They use standard CSV quoting for commas and quotes within values and retain values as text. Tables generally have a header row; the ICD-10 export is an exception described below. The preprocessing code strips surrounding whitespace and removes fully blank rows and exact duplicate rows within each file. It does not normalize medicine names, infer missing values, or validate clinical claims.

### `ATC_DDD/` — ATC classification and defined daily dose material

Source: `../ATC_DDD_new and alterations 2026_final.xlsx`.

- `ATC_DDD_new_and_alterations_2026_final_Ark1.csv` — the workbook's `Ark1` sheet, retained in its supplied column layout.
- `ATC_DDD_new_and_alterations_2026_final_ATC_level_alterations.csv` — changes to ATC-level codes and names.
- `ATC_DDD_new_and_alterations_2026_final_ATC_level_name_alterations.csv` — ATC level name changes.
- `ATC_DDD_new_and_alterations_2026_final_DDDs_alterations.csv` — changes to defined daily dose (DDD) assignments.
- `ATC_DDD_new_and_alterations_2026_final_New_3rd_and_4th_levels.csv` — newly added third- and fourth-level ATC entries.
- `ATC_DDD_new_and_alterations_2026_final_New_ATC_5th_levels.csv` — newly added fifth-level ATC codes and substances.
- `ATC_DDD_new_and_alterations_2026_final_New_DDDs.csv` — newly assigned DDD entries.

The ATC code is a drug classification. A DDD is a standardized drug-utilization measure; it is not a recommended dose for an individual patient. ATC codes in the WHO essential medicines table can help organize candidate comparisons, but do not imply a validated match.

### `WHO_Essential_Medicines/` — WHO essential medicines list

Source: `../WHO Essential Medicines list.xlsx`.

- `WHO_Essential_Medicines_list_Worksheet.csv` — the workbook's `Worksheet` sheet, with fields such as medicine name, EML section, formulations, indication, ATC codes, combinations, and status.

This list identifies medicines and formulations included in the supplied WHO list. Its scope and edition are determined by the original workbook; check that source before treating it as current.

### `DDIndex/` — DDInter drug–drug interaction records

Source files: `../DDIndex/ddinter_downloads_code_*.csv`.

- `DDIndex_ddinter_downloads_code_A.csv`
- `DDIndex_ddinter_downloads_code_B.csv`
- `DDIndex_ddinter_downloads_code_D.csv`
- `DDIndex_ddinter_downloads_code_H.csv`
- `DDIndex_ddinter_downloads_code_L.csv`
- `DDIndex_ddinter_downloads_code_P.csv`
- `DDIndex_ddinter_downloads_code_R.csv`
- `DDIndex_ddinter_downloads_code_V.csv`

Each table contains the source fields `DDInterID_A`, `Drug_A`, `DDInterID_B`, `Drug_B`, and `Level`: a pair of interacting drug records and the source's interaction level. The files remain partitioned as downloaded. Use the DDInter identifiers as the source-specific keys; the letter in a filename is a source partition and is not reinterpreted here.

### `ICD_10/` — ICD-10 diagnosis-code records

Source: `../ICD-10.csv`.

- `ICD-10.csv` — a comma-separated table derived from the supplied ICD-10 file.

**Header caveat:** the supplied source begins with data and has no header row. The current export code treats that first source record as the header, so it is not a trustworthy column dictionary and that first record is omitted from the exported rows. Use the unchanged `../ICD-10.csv` source until the preprocessing code is updated with a verified schema. This caveat is also reflected by the generic or unusual column names in `data_dictionary.csv`.

ICD-10 codes classify diagnoses. They describe disease concepts, not medicines, and need a separately validated clinical or terminology mapping before connecting them to indications or medicine records.

### `Jan_Aushadhi/` — Jan Aushadhi product catalogue

Source: `../Jan Aushadhi.csv`.

- `Jan_Aushadhi.csv` — product rows with `Sr No`, `Drug Code`, `Generic Name`, `Unit Size`, `MRP`, and `Group Name`.

The drug code identifies a product in this catalogue. Generic names, pack sizes, and listed prices may change and should be checked against the current PMBI catalogue before use. This catalogue describes marketed products and pack information, while the WHO list describes essential-medicine selection; neither is a substitute for the other.

### `MedlinePlus/` — MedlinePlus health-topic records

Source: `../MedlinePlus drug information/mplus_topics_2026-10-13.xml`.

- `MedlinePlus_drug_information_mplus_topics_2026-10-13.csv` — one row per health topic, flattened from the XML. Topic attributes and child elements are represented as columns; repeated child text is joined with ` | `.

The XML topic `id`, URL, and text fields identify and describe patient-facing health topics. This file is not a medicine product catalogue. A topic URL may provide context for later presentation, but it does not establish that a particular medicine record is safe or appropriate.

### `RxNorm/` — RxNorm current prescribable content

Source files: `../RxNorm_full_prescribe_10052026/rrf/`.

- `RxNorm_full_prescribe_10052026_rrf_RXNCONSO.csv` — concept and atom names, codes, vocabularies, and language/type attributes (`RXCUI`, `RXAUI`, `STR`, and related fields).
- `RxNorm_full_prescribe_10052026_rrf_RXNREL.csv` — relationships between RxNorm concepts and atoms, including relationship and source-vocabulary fields.
- `RxNorm_full_prescribe_10052026_rrf_RXNSAT.csv` — attributes associated with RxNorm concepts and atoms.

These are the RxNorm RRF tables exported as CSV. `RXCUI` is an RxNorm concept identifier; `RXAUI` is an atom identifier. The tables are related through those identifiers and should be joined using the documented key fields and release documentation, not by row order or display name alone.

### `SIDER/` — side-effect, indication, and frequency tables

Source files: `../SIDER/*.tsv.gz`.

- `SIDER_meddra_tsv.csv` — source table named `meddra.tsv.gz`.
- `SIDER_meddra_all_indications_tsv.csv` — source table named `meddra_all_indications.tsv.gz`.
- `SIDER_meddra_all_label_indications_tsv.csv` — source table named `meddra_all_label_indications.tsv.gz`.
- `SIDER_meddra_all_label_se_tsv.csv` — source table named `meddra_all_label_se.tsv.gz`.
- `SIDER_meddra_all_se_tsv.csv` — source table named `meddra_all_se.tsv.gz`.
- `SIDER_meddra_freq_tsv.csv` — source table named `meddra_freq.tsv.gz`.

The supplied SIDER text files have no header rows. To avoid inventing schema labels, the exports use positional columns named `field_1`, `field_2`, and so on. Interpret each field using the matching SIDER release documentation; the positional field dictionary is not a substitute for that documentation. By their source filenames, these files cover MedDRA terms, indications, side effects, and frequency information. Use source-defined compound identifiers and MedDRA identifiers when relating SIDER records; do not join on names alone.

## Documentation and validation files

- `data_dictionary.csv` — one row per cleaned file and column. `cleaned_file` gives a path relative to this folder; `description` explains the field or flags positional/unverified fields; `type_policy` describes how values were exported.
- `source_references.csv` — one row per input data file, with its original relative path, source URL when known, licence or rights note, output CSV path(s), and processing status. Rights marked unverified must be checked with the provider before redistribution.
- `validation_report.csv` — one row per cleaned table plus rows for inputs not converted. For each exported table it reports input/output row counts, exact duplicate and blank rows removed, per-column missing-value counts, limitations, and the status of record verification.
- `../preproccess_dataset.py` — the Python preprocessing program. Run it from the repository root or `Dataset/` to rebuild the tables and documentation. It uses only the Python standard library.

## How the datasets relate

- **Classification and selection:** ATC/DDD provides drug classification and utilization measures; the WHO EML identifies selected medicines and formulations. The EML's ATC codes can provide a starting reference to the ATC files.
- **Product and terminology:** Jan Aushadhi provides India-specific product codes, generic names, pack sizes, and listed prices. RxNorm provides normalized drug concepts, atoms, attributes, and relationships. Product-to-concept matching requires ingredient, strength, dose form, route, and combination checks.
- **Interactions and effects:** DDInter describes drug pairs and interaction levels. SIDER provides drug-associated indications, side effects, and frequencies. These are separate evidence sources and should not be treated as interchangeable or necessarily complete.
- **Conditions and health information:** ICD-10 classifies diagnoses. MedlinePlus provides health-topic content. Diagnosis codes, topic records, and medicine indications require explicit, validated mappings before they can be connected.

No cross-source joins, identity resolution, clinical review, regulatory verification, or currentness check has been performed in these exports. Resolve identifiers with each source's documentation and release, preserve provenance through any later join, and review ambiguous or unverified matches before using them in medicine-safety workflows.


