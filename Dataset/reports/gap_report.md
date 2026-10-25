# Starter pack gap report

## Status

The requested 20–30 medicine starter pack cannot be selected or validated from the supplied inputs. The instruction document does not name the medicines, and the user confirmed that no starter list or the referenced brand-to-salt and allergy-family source files are currently available. No starter-pack rows have been assembled, and no records have been marked `Checked = Yes`.

The existing cleaned tables are preserved under `clean/` as a reference library. They have not been filtered to a starter list. The original downloads remain unchanged under `raw/`.

## Required inputs and unresolved checks

| Requirement | Current evidence | Gap / next action |
|---|---|---|
| Approved 20–30 medicine selection | No approved selection list was supplied. | Provide the medicines with exact product/ingredient, strength, dosage form, route, and release type where known. Keep distinct products separate when these attributes differ. |
| Brand-to-salt mapping | No brand-to-salt source file is present in `raw/`. | Supply the file or identify the permitted source and the selected brands to map. |
| Allergy-family data | No allergy-family source file is present in `raw/`. | Supply the file or identify its permitted source. Ingredient-to-family matches cannot be checked without it. |
| Canonical ingredient names and synonyms | Existing sources use their own names. No cross-file synonym review has been completed. | After the medicine list and mapping files are provided, use Paracetamol as the Indian-facing canonical term where applicable and retain alternatives such as Acetaminophen in a separate synonym field. Do not merge formulations or strengths. |
| Half-life | No source-backed half-life values are included in the current cleaned CSV library. The DrugCentral PostgreSQL dump remains unexported. | For each selected medicine, obtain a permitted source-backed value with units and citation; otherwise leave it blank and list it as missing. |
| Interaction descriptions and severity | DDInter exports contain `DDInterID_A`, `Drug_A`, `DDInterID_B`, `Drug_B`, and `Level`; no narrative description field is present. | Filter to selected-list pairs after the list is supplied. Preserve DDInter's level and obtain a source-backed description only where the source provides one. |
| Cautions and risk conditions | No structured medicine-specific contraindication/caution table is present in the processed library. | Add only sourced information for selected medicines; otherwise leave fields blank and report the gap. |
| Side effects | SIDER source tables are present, but use positional fields and have not been matched to selected medicines or verified. | Confirm the SIDER schema and IDs, then filter and cite the source for selected medicines. |
| ICD-10 schema | The raw ICD-10 CSV has no header. The clean export now retains all rows under neutral `field_1`–`field_6` columns. | Obtain the provider's column definition before assigning semantic field names or mapping conditions. |
| ATC workbook sheet `Ark1` | Several headers are abbreviated or non-English (`xxx`, `zzz`, `Møte`, `Hva nytt`, etc.). | Confirm the workbook's sheet schema before using these fields. Other workbook sheets retain descriptive source labels. |
| Manual spot-checks | No manual row checks against labels or reputable medicine references have been completed in this pass. | Once the selected pack is defined, sample up to 20 rows per relevant file where practical. Add `Checked = Yes` only with recorded source evidence. |
| Unconverted source files | NLEM and CDSCO PDFs need source-specific table review; DrugCentral is a PostgreSQL custom dump. | Export only the tables/records relevant to the selected list using suitable source-aware tooling. Do not copy unrelated records into the starter pack. |
| Source rights and access dates | Some URLs are known; several licences and download/access dates are not recorded in supplied materials. | Confirm reuse rights and dates with source providers before redistributing or publishing final extracts. |

## Current cleaning caveats

- The clean folder contains broad source tables and is not the requested 20–30 medicine subset.
- Most source values are preserved as text. Only whitespace, blank rows, and exact duplicate rows were removed during the earlier cleaning.
- No medicine-name normalization, cross-source reconciliation, clinical verification, or safety review has been completed.
- Unknown fields remain explicitly positional or source-labelled; no values have been guessed or silently substituted.

## Handover decision

Do not treat the current reference library as a completed starter pack. The next data preparation step depends on the medicine selection and the two missing mapping files (or the user's confirmation that they do not exist and approval of alternative permitted sources).
