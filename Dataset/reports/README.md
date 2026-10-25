# Medication safety dataset handover

## Current status

The folder now separates unchanged source downloads, cleaned reference tables, and reports. The approved first 20–30 medicine list was not supplied, and the project contains no brand-to-salt or allergy-family source file. For that reason, `clean/` is an organized reference library, not a selected or clinically verified starter pack. No medicine records have been chosen or marked as checked.

## Folder layout

```text
Dataset/
├── raw/                         Original source files, preserved unchanged
├── clean/                       CSV reference tables, grouped by dataset
└── reports/
    ├── README.md                This handover guide
    ├── file_descriptions.md     Purpose, columns, sources, and limits per CSV
    ├── gap_report.md            Missing inputs and work blocked by those gaps
    ├── data_dictionary.csv      Column-level descriptions for the clean tables
    ├── source_references.csv    Source paths, URLs, rights notes, and output paths
    └── validation_report.csv    Row counts, missing values, duplicates, and limits
```

The active preprocessing program is `../preproccess_dataset.py`. It reads from `raw/`, writes cleaned tables to `clean/`, and regenerates the three CSV reports in `reports/`. The README, file descriptions, and gap report are maintained as handover documents and are not overwritten by a preprocessing run.

## Clean reference tables

The clean tables are UTF-8 CSV files with a BOM, comma delimiters, and quoted fields where needed. Values are stored as text. The preprocessing removes surrounding whitespace, fully blank rows, and exact duplicate rows within each file. It does not standardize clinical names, infer missing values, or verify clinical facts.

- `clean/ATC_DDD/` contains seven tables from the ATC/DDD workbook: its `Ark1` sheet, ATC-level code/name changes, DDD changes, and newly added ATC levels or DDD assignments.
- `clean/WHO_Essential_Medicines/` contains the workbook sheet listing medicine names, EML sections, formulations, indications, ATC codes, combinations, and status.
- `clean/DDIndex/` contains eight DDInter partitions. Each table holds two drug IDs and names plus the source interaction level.
- `clean/ICD_10/` contains the supplied ICD-10 code records. The source has no header, so the clean export uses neutral `field_1` through `field_6` labels and retains the first record. Field meanings still require confirmation from the source provider.
- `clean/Jan_Aushadhi/` contains the product code, generic name, unit size, listed MRP, and group from the supplied catalogue.
- `clean/MedlinePlus/` contains flattened MedlinePlus health-topic records from XML, including topic IDs, titles, URLs, descriptions, and related text.
- `clean/RxNorm/` contains RxNorm concept/atom strings, relationships, and attributes. The tables are linked by RxNorm identifiers such as `RXCUI` and `RXAUI`.
- `clean/SIDER/` contains six SIDER tables for MedDRA terms, indications, side effects, and frequency information. The source files have no headers; fields remain positional and are named `field_1`, `field_2`, and so on.

See [`file_descriptions.md`](file_descriptions.md) for the full filename list, columns, source dates, and limitations for each table. Use [`data_dictionary.csv`](data_dictionary.csv) for the field-level inventory and [`source_references.csv`](source_references.csv) for source URLs and rights notes.

## How the sources relate

ATC/DDD classifies medicines and provides defined daily dose information; the WHO list identifies medicines and formulations included in the supplied essential-medicines list. Their ATC codes can support a future comparison, but a shared code alone does not prove equivalent products.

Jan Aushadhi describes India-specific catalogue products and pack information. RxNorm supplies normalized drug concepts and relationships. Matching a catalogue item to a terminology concept requires checking its ingredients, strength, form, route, release type, and combination ingredients.

DDInter describes interaction pairs and a source severity/level. SIDER supplies separate indication, side-effect, and frequency records. ICD-10 classifies diagnoses, while MedlinePlus contains patient-facing health topics. These sources have different identifiers and purposes. A future join requires explicit, reviewed mappings; names alone are not reliable join keys.

No cross-source matching, clinical review, or manual spot-check has been completed. The specific blockers and needed inputs are listed in [`gap_report.md`](gap_report.md). Do not treat the clean reference library as a clinical decision-support dataset or as a checked medicine pack.

## Source files not converted

The following downloads remain unchanged in `raw/` and are recorded as not converted in `source_references.csv` and `validation_report.csv`:

- `raw/nlem2022.pdf` and the two PDFs under `raw/CDSC/` require source-specific PDF table extraction and review.
- `raw/Drugcentral_2026-09-25.pgdump` is a PostgreSQL custom-format dump and requires `pg_restore` plus schema-aware export.

The RxNorm readme and database-load scripts also remain in `raw/RxNorm_full_prescribe_10052026/`; they are source-release support files, not final CSV tables. Source download/access dates and licence details are recorded only where they were present or could be identified; unknown rights are explicitly marked for verification.
