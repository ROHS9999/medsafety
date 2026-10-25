# Clean CSV file descriptions

This document describes every CSV table currently under `Dataset/clean/`. Paths below are relative to `Dataset/`. All exports are UTF-8 CSV with a BOM, comma-delimited, and contain text values. The preprocessing trims outer whitespace and removes blank and exact duplicate rows within each file. Download/access dates are recorded only when available from the supplied filenames or release notes; otherwise they are marked unknown. Column names and descriptions are also indexed in `data_dictionary.csv`.

## ATC and DDD tables

Source: `raw/ATC_DDD_new and alterations 2026_final.xlsx`. Download/access date was not recorded; the filename includes `2026_final`, but the exact release edition was not independently confirmed. Source URL and rights note are in `source_references.csv`.

- `clean/ATC_DDD/ATC_DDD_new_and_alterations_2026_final_Ark1.csv` — raw `Ark1` worksheet. Columns are `ATC`, `navn`, `DDD`, `adm.r`, `xxx`, `Note`, `Møte`, `zzz`, `Hva nytt`, `P360`, `Inn`, `Guidelines`, `norsk`, and `spansk`. Several labels are abbreviated or non-English; their exact meanings have not been confirmed, so retain the source workbook for interpretation. This sheet is not ready for clinical use without schema review.
- `clean/ATC_DDD/ATC_DDD_new_and_alterations_2026_final_ATC_level_alterations.csv` — ATC-level code changes. `Previous ATC code` and `New ATC code` identify the old and proposed codes; `ATC level name` and `Note` provide source context.
- `clean/ATC_DDD/ATC_DDD_new_and_alterations_2026_final_ATC_level_name_alterations.csv` — ATC level name changes. `ATC code` is the code; `Previous ATC level name` and `New ATC level name` hold the old and new names; `Note` is source context.
- `clean/ATC_DDD/ATC_DDD_new_and_alterations_2026_final_DDDs_alterations.csv` — defined daily dose changes. `ATC code`, `ATC level name`, `Previous DDD`, `Unit`, and `Adm.route` describe the existing assignment; `New DDD`, `Unit_2`, and `Adm.route_2` describe the new assignment; `Note` is source context. The `_2` suffix was added to disambiguate repeated source headings.
- `clean/ATC_DDD/ATC_DDD_new_and_alterations_2026_final_New_3rd_and_4th_levels.csv` — new third- and fourth-level ATC entries. Columns: `ATC code`, `New ATC level name`, and `Note`.
- `clean/ATC_DDD/ATC_DDD_new_and_alterations_2026_final_New_ATC_5th_levels.csv` — new fifth-level entries. Columns: `New ATC code`, `Substance name`, and `Note`.
- `clean/ATC_DDD/ATC_DDD_new_and_alterations_2026_final_New_DDDs.csv` — new DDD assignments. Columns: `ATC code`, `ATC level name`, `New DDD`, `Unit`, `Adm.route`, and `Note`. DDD units and routes are retained as supplied; DDD is a utilization measure, not a patient-specific dose.

## WHO essential medicines

Source: `raw/WHO Essential Medicines list.xlsx`. Download/access date and exact list edition were not identified from the workbook metadata available during this pass; verify against the source publication before use.

- `clean/WHO_Essential_Medicines/WHO_Essential_Medicines_list_Worksheet.csv` — the workbook's `Worksheet` sheet. `Medicine name` is the listed medicine; `EML section` is its list section; `Formulations` describes listed dosage forms; `Indication` is the stated use; `ATC codes` contains classification codes; `Combined with` records combination context; `Status` retains the source status. The file does not provide a validated product-level strength/route mapping for matching to catalogues.

## DDInter interaction tables

Source: the eight CSV partitions under `raw/DDIndex/`; download/access date is unknown. Each has the same columns: `DDInterID_A` and `DDInterID_B` are DDInter identifiers for the two records; `Drug_A` and `Drug_B` are source drug names; `Level` is the source's interaction level. These files do not contain a narrative interaction description in the exported fields. Do not infer one from `Level` alone.

- `clean/DDIndex/DDIndex_ddinter_downloads_code_A.csv`
- `clean/DDIndex/DDIndex_ddinter_downloads_code_B.csv`
- `clean/DDIndex/DDIndex_ddinter_downloads_code_D.csv`
- `clean/DDIndex/DDIndex_ddinter_downloads_code_H.csv`
- `clean/DDIndex/DDIndex_ddinter_downloads_code_L.csv`
- `clean/DDIndex/DDIndex_ddinter_downloads_code_P.csv`
- `clean/DDIndex/DDIndex_ddinter_downloads_code_R.csv`
- `clean/DDIndex/DDIndex_ddinter_downloads_code_V.csv`

The filenames preserve the source partitions. Their letter meanings have not been reinterpreted.

## ICD-10 diagnosis records

Source: `raw/ICD-10.csv`; source URL and date were not recorded. The source contains rows without a header. To preserve all records without guessing column meanings, the clean export uses six neutral positional fields.

- `clean/ICD_10/ICD-10.csv` — `field_1` through `field_6` retain the six source positions as text. The source provider's schema is needed to assign safe names and meanings. Do not use positional values as verified diagnosis fields until that schema is confirmed.

## Jan Aushadhi catalogue

Source: `raw/Jan Aushadhi.csv`; download/access date is unknown. The catalogue lists `Sr No` (source row number), `Drug Code` (catalogue product code), `Generic Name`, `Unit Size` (pack/unit description), `MRP` (listed maximum retail price; currency is not stated in the file), and `Group Name` (source product group). Values and prices may be time-sensitive. Verify against the current PMBI source before use.

- `clean/Jan_Aushadhi/Jan_Aushadhi.csv`

## MedlinePlus topics

Source: `raw/MedlinePlus drug information/mplus_topics_2026-10-13.xml`. The supplied XML filename and metadata date the generated topic file to 2026-10-13; download/access time is otherwise unknown.

- `clean/MedlinePlus/MedlinePlus_drug_information_mplus_topics_2026-10-13.csv` — one flattened row per health topic. Columns: `id` and `url` identify the topic; `title` and `language` identify its title and language; `date-created` is the source creation date; `meta-desc` and `full-summary` contain descriptive text; `also-called` contains alternate topic labels; `group`, `mesh-heading`, `primary-institute`, and `site` retain source categorization/attribution; `language-mapped-topic`, `other-language`, `related-topic`, and `see-reference` retain cross-reference fields. Repeated XML child text is joined with ` | `. These are health-topic records, not drug-specific contraindication or half-life records.

## RxNorm tables

Source: `raw/RxNorm_full_prescribe_10052026/rrf/`. The accompanying release readme identifies an October 5, 2026 prescribable content release. Local download date is unknown. Column meanings follow RxNorm RRF conventions; see the release documentation and readme before joins.

- `clean/RxNorm/RxNorm_full_prescribe_10052026_rrf_RXNCONSO.csv` — concept/atom names and source terms. `RXCUI` is a concept ID; `RXAUI` is an atom ID; `STR` is the term string; `LAT`, `TS`, `LUI`, `STT`, `SUI`, and `ISPREF` describe language/term and atom status; `SAUI`, `SCUI`, `SDUI`, `SAB`, `TTY`, and `CODE` preserve source identifiers and term type; `SRL`, `SUPPRESS`, and `CVF` are source status/version fields.
- `clean/RxNorm/RxNorm_full_prescribe_10052026_rrf_RXNREL.csv` — relationships between concepts/atoms. `RXCUI1`/`RXCUI2` are concept IDs; `RXAUI1`/`RXAUI2` are atom IDs; `STYPE1`/`STYPE2` identify endpoint types; `REL` and `RELA` identify relationship types; `RUI` and `SRUI` are relationship identifiers; `SAB`, `SL`, `RG`, `DIR`, `SUPPRESS`, and `CVF` retain source, direction, status, and version attributes.
- `clean/RxNorm/RxNorm_full_prescribe_10052026_rrf_RXNSAT.csv` — concept/atom attributes. `RXCUI` and `RXAUI` identify the associated concept/atom; `LUI`, `SUI`, `STYPE`, and `CODE` retain source identifiers/types; `ATUI` and `SATUI` identify attribute records; `ATN` is the attribute name; `SAB` is the source; `ATV` is the attribute value; `SUPPRESS` and `CVF` retain status/version information.

IDs must be treated as strings. RxNorm concepts, atoms, and source codes are distinct key types; use the relevant identifiers and release documentation, not display names or row order, to connect these tables.

## SIDER tables

Source: the six gzip-compressed TSV files in `raw/SIDER/`; download/access date is unknown. The source files have no header row, so the exports use neutral positional names. A complete field-by-field interpretation requires the matching SIDER release schema. No semantics have been invented for `field_N`.

- `clean/SIDER/SIDER_meddra_tsv.csv` — source `meddra.tsv.gz`, the MedDRA term table.
- `clean/SIDER/SIDER_meddra_all_indications_tsv.csv` — source `meddra_all_indications.tsv.gz`, indication records.
- `clean/SIDER/SIDER_meddra_all_label_indications_tsv.csv` — source `meddra_all_label_indications.tsv.gz`, label indication records.
- `clean/SIDER/SIDER_meddra_all_label_se_tsv.csv` — source `meddra_all_label_se.tsv.gz`, label side-effect records.
- `clean/SIDER/SIDER_meddra_all_se_tsv.csv` — source `meddra_all_se.tsv.gz`, side-effect records.
- `clean/SIDER/SIDER_meddra_freq_tsv.csv` — source `meddra_freq.tsv.gz`, side-effect frequency records.

Use the source-defined drug and MedDRA identifiers and the release schema to interpret records. These tables have not been matched to a selected medicine list or independently checked.
