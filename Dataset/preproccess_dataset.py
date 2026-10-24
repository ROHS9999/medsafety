from __future__ import annotations

import csv
import gzip
import hashlib
import itertools
import json
import re
import xml.etree.ElementTree as ET
import zipfile
from collections import Counter
from pathlib import Path
from typing import Iterable, Iterator, Sequence


# Resolve paths from either the repository root or the Dataset directory.
ROOT = Path.cwd() / "Dataset"
if not ROOT.exists():
    ROOT = Path.cwd()

OUTPUT_DIR = ROOT / "processed"
SUPPORTED_SUFFIXES = {".csv", ".xlsx", ".rrf", ".xml", ".gz", ".pdf", ".pgdump"}

SOURCE_INFO = {
    "WHO Essential Medicines list.xlsx": (
        "https://www.who.int/groups/expert-committee-on-selection-and-use-"
        "essential-medicines/essential-medicines-lists",
        "WHO publication terms apply; exact licence/edition not verified "
        "from supplied workbook",
    ),
    "ATC_DDD_new and alterations 2026_final.xlsx": (
        "https://atcddd.fhi.no/atc_ddd_index_and_guidelines/atc_ddd_index/",
        "WHO Collaborating Centre citation required; redistribution terms "
        "not verified from supplied workbook",
    ),
    "Jan Aushadhi.csv": (
        "https://janaushadhi.gov.in/productportfolio/ProductmrpList",
        "Not stated in supplied file; verify with PMBI",
    ),
    "ICD-10.csv": (
        "Not recorded in supplied file",
        "Not recorded; verify with source provider",
    ),
    "DDIndex": (
        "https://ddinter.scbdd.com/",
        "Not stated in supplied files; verify with DDInter",
    ),
    "RxNorm_full_prescribe_10052026": (
        "https://www.nlm.nih.gov/research/umls/rxnorm/docs/rxnormfiles.html",
        "RxNorm/UMLS terms apply; check current NLM terms before redistribution",
    ),
    "SIDER": (
        "http://sideeffects.embl.de/download/",
        "Not stated in supplied files; verify with SIDER/EMBL-EBI",
    ),
    "mplus_topics_2026-10-13.xml": (
        "https://medlineplus.gov/xml.html",
        "MedlinePlus content terms apply; verify current NLM terms",
    ),
    "Drugcentral_2026-09-25.pgdump": (
        "https://drugcentral.org/",
        "Not stated in supplied dump; verify DrugCentral terms",
    ),
    "CDSC": (
        "https://cdsco.gov.in/",
        "Exact reuse terms not stated in supplied PDFs",
    ),
    "nlem2022.pdf": (
        "https://www.mohfw.gov.in/",
        "Government publication; exact reuse terms not verified from supplied PDF",
    ),
}

RXNORM_SCHEMAS = {
    "RXNCONSO": [
        "RXCUI", "LAT", "TS", "LUI", "STT", "SUI", "ISPREF", "RXAUI",
        "SAUI", "SCUI", "SDUI", "SAB", "TTY", "CODE", "STR", "SRL",
        "SUPPRESS", "CVF",
    ],
    "RXNREL": [
        "RXCUI1", "RXAUI1", "STYPE1", "REL", "RXCUI2", "RXAUI2",
        "STYPE2", "RELA", "RUI", "SRUI", "SAB", "SL", "RG", "DIR",
        "SUPPRESS", "CVF",
    ],
    "RXNSAT": [
        "RXCUI", "LUI", "SUI", "RXAUI", "STYPE", "CODE", "ATUI",
        "SATUI", "ATN", "SAB", "ATV", "SUPPRESS", "CVF",
    ],
}


def source_metadata(path: Path) -> tuple[str, str]:
    """Return the best-known source URL and rights note for an input file."""
    relative_path = path.relative_to(ROOT).as_posix()

    for marker, metadata in SOURCE_INFO.items():
        if marker in relative_path or marker == path.name:
            return metadata

    return (
        "Not recorded in supplied files",
        "Not stated; verify with source provider",
    )


def read_delimited_rows(
    path: Path, delimiter: str | None = None
) -> Iterator[list[str]]:
    """Stream a delimited file, detecting common separators when unspecified."""
    with path.open(encoding="utf-8-sig", errors="replace", newline="") as source:
        sample = source.read(8192)

    if delimiter is None:
        try:
            delimiter = csv.Sniffer().sniff(sample, delimiters=",;\t|").delimiter
        except csv.Error:
            delimiter = ","

    with path.open(encoding="utf-8-sig", errors="replace", newline="") as source:
        yield from csv.reader(source, delimiter=delimiter)


def write_table(
    relative_name: str, headers: Sequence[str], rows: Iterable[Sequence[object]]
) -> dict:
    """Write one cleaned CSV and return summary statistics for the report."""
    normalized_headers = [
        str(value).strip().lstrip("\ufeff") or f"column_{index + 1}"
        for index, value in enumerate(headers)
    ]

    header_counts: Counter[str] = Counter()
    columns: list[str] = []
    for header in normalized_headers:
        header_counts[header] += 1
        suffix = f"_{header_counts[header]}" if header_counts[header] > 1 else ""
        columns.append(f"{header}{suffix}")

    output_path = OUTPUT_DIR / relative_name
    output_path.parent.mkdir(parents=True, exist_ok=True)

    seen_hashes: set[bytes] = set()
    duplicate_rows = blank_rows = rows_in = rows_out = 0
    missing_counts = [0] * len(columns)

    with output_path.open("w", encoding="utf-8-sig", newline="") as output_file:
        writer = csv.writer(output_file, lineterminator="\n")
        writer.writerow(columns)

        for source_row in rows:
            rows_in += 1
            row = [
                str(value).strip() if value is not None else ""
                for value in source_row
            ]
            row = (row + [""] * len(columns))[: len(columns)]

            if not any(row):
                blank_rows += 1
                continue

            row_hash = hashlib.sha256("\0".join(row).encode("utf-8")).digest()
            if row_hash in seen_hashes:
                duplicate_rows += 1
                continue

            seen_hashes.add(row_hash)
            rows_out += 1
            writer.writerow(row)

            for index, value in enumerate(row):
                missing_counts[index] += not bool(value)

    missing_values = {
        column: missing_counts[index] for index, column in enumerate(columns)
    }
    return {
        "file": relative_name,
        "rows_in": rows_in,
        "rows_out": rows_out,
        "duplicates": duplicate_rows,
        "blank": blank_rows,
        "missing": missing_values,
        "columns": columns,
    }


def read_xlsx_sheets(path: Path) -> Iterator[tuple[str, list[list[str]]]]:
    """Read worksheet cell values from an XLSX archive using the standard library."""
    namespaces = {
        "main": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
        "relationships": (
            "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
        ),
    }

    with zipfile.ZipFile(path) as workbook:
        members = set(workbook.namelist())
        shared_strings: list[str] = []

        if "xl/sharedStrings.xml" in members:
            shared_root = ET.fromstring(workbook.read("xl/sharedStrings.xml"))
            shared_strings = [
                "".join(
                    text.text or ""
                    for text in item.findall(".//main:t", namespaces)
                )
                for item in shared_root.findall("main:si", namespaces)
            ]

        workbook_root = ET.fromstring(workbook.read("xl/workbook.xml"))
        relationships_root = ET.fromstring(
            workbook.read("xl/_rels/workbook.xml.rels")
        )
        targets = {
            relationship.attrib["Id"]: relationship.attrib["Target"]
            for relationship in relationships_root
        }

        for sheet in workbook_root.findall("main:sheets/main:sheet", namespaces):
            relationship_id = sheet.attrib[f"{{{namespaces['relationships']}}}id"]
            target = targets[relationship_id].lstrip("/")
            member = target if target.startswith("xl/") else f"xl/{target}"
            sheet_root = ET.fromstring(workbook.read(member))
            rows: list[list[str]] = []

            for source_row in sheet_root.findall(
                ".//main:sheetData/main:row", namespaces
            ):
                values: list[str] = []

                for cell in source_row.findall("main:c", namespaces):
                    column_reference = re.match(
                        r"[A-Z]+", cell.attrib.get("r", "A1")
                    ).group()
                    column_number = 0
                    for character in column_reference:
                        column_number = column_number * 26 + ord(character) - 64

                    while len(values) < column_number:
                        values.append("")

                    value_node = cell.find("main:v", namespaces)
                    value = (
                        value_node.text
                        if value_node is not None and value_node.text
                        else ""
                    )

                    if cell.attrib.get("t") == "s" and value:
                        value = shared_strings[int(value)]
                    elif cell.attrib.get("t") == "inlineStr":
                        value = "".join(
                            text.text or ""
                            for text in cell.findall(".//main:t", namespaces)
                        )

                    values[column_number - 1] = value

                rows.append(values)

            yield sheet.attrib.get("name", "Sheet"), rows


def read_medlineplus_xml(path: Path) -> tuple[list[str], list[list[str]]]:
    """Flatten MedlinePlus health-topic records into a tabular representation."""
    root = ET.parse(path).getroot()
    records: list[dict[str, str]] = []

    for topic in root.findall(".//health-topic"):
        record = dict(topic.attrib)

        for child in topic:
            tag = child.tag.split("}")[-1]
            text = " | ".join(
                item.strip() for item in child.itertext() if item.strip()
            )
            if text:
                existing = record.get(tag, "")
                record[tag] = f"{existing} | {text}" if existing else text

        records.append(record)

    columns = (
        sorted(set().union(*(record.keys() for record in records)))
        if records
        else []
    )
    rows = [[record.get(column, "") for column in columns] for record in records]
    return columns, rows


def dataset_folder(path: Path) -> str:
    """Choose the output folder associated with a source dataset."""
    relative_path = path.relative_to(ROOT).as_posix()

    if relative_path.startswith("DDIndex/"):
        return "DDIndex"
    if relative_path.startswith("RxNorm_full_prescribe_"):
        return "RxNorm"
    if relative_path.startswith("SIDER/"):
        return "SIDER"
    if path.name.startswith("ATC_DDD"):
        return "ATC_DDD"
    if path.name.startswith("WHO Essential Medicines"):
        return "WHO_Essential_Medicines"
    if path.name.startswith("Jan Aushadhi"):
        return "Jan_Aushadhi"
    if path.name.startswith("ICD-10"):
        return "ICD_10"
    if path.name.startswith("mplus_topics"):
        return "MedlinePlus"

    return "Other"


def discover_source_files() -> list[Path]:
    """Find supported source data while excluding generated output files."""
    return sorted(
        path
        for path in ROOT.rglob("*")
        if path.is_file()
        and OUTPUT_DIR not in path.parents
        and path.suffix.lower() in SUPPORTED_SUFFIXES
    )


def process_sources(files: Sequence[Path]) -> tuple[list[dict], list[tuple[str, str]]]:
    """Convert supported source tables and collect files needing special handling."""
    results: list[dict] = []
    skipped: list[tuple[str, str]] = []

    for path in files:
        relative_path = path.relative_to(ROOT).as_posix()
        stem = re.sub(
            r"[^A-Za-z0-9_-]+", "_", relative_path.rsplit(".", 1)[0]
        ).strip("_")
        folder = dataset_folder(path)

        try:
            if path.suffix.lower() == ".csv":
                rows = read_delimited_rows(path)
                headers = next(rows, None)
                if headers is None:
                    skipped.append((relative_path, "Empty CSV"))
                else:
                    results.append(write_table(f"{folder}/{stem}.csv", headers, rows))

            elif path.suffix.lower() == ".rrf":
                schema = RXNORM_SCHEMAS[path.stem.upper()]
                results.append(
                    write_table(
                        f"{folder}/{stem}.csv",
                        schema,
                        read_delimited_rows(path, "|"),
                    )
                )

            elif path.suffix.lower() == ".xlsx":
                for sheet_name, rows in read_xlsx_sheets(path):
                    safe_sheet_name = re.sub(
                        r"[^A-Za-z0-9_-]+", "_", sheet_name
                    ).strip("_")
                    output_name = f"{folder}/{stem}_{safe_sheet_name}.csv"

                    if rows:
                        results.append(write_table(output_name, rows[0], rows[1:]))
                    else:
                        skipped.append((relative_path, f"Empty sheet: {sheet_name}"))

            elif path.suffix.lower() == ".gz":
                with gzip.open(
                    path, "rt", encoding="utf-8", errors="replace", newline=""
                ) as source:
                    rows = csv.reader(source, delimiter="\t")
                    first_row = next(rows, None)

                    if first_row is not None:
                        width = len(first_row)
                        headers = [f"field_{index + 1}" for index in range(width)]
                        results.append(
                            write_table(
                                f"{folder}/{stem}.csv",
                                headers,
                                itertools.chain([first_row], rows),
                            )
                        )

            elif path.suffix.lower() == ".xml":
                headers, rows = read_medlineplus_xml(path)
                results.append(write_table(f"{folder}/{stem}.csv", headers, rows))

            else:
                reason = (
                    "PDF extraction needs source-specific table review"
                    if path.suffix.lower() == ".pdf"
                    else "PostgreSQL custom dump requires pg_restore and "
                    "schema-aware export"
                )
                skipped.append((relative_path, reason))

        except Exception as error:
            skipped.append(
                (relative_path, f"Processing error: {type(error).__name__}: {error}")
            )

    return results, skipped


def write_documentation(
    files: Sequence[Path], results: Sequence[dict], skipped: Sequence[tuple[str, str]]
) -> None:
    """Write the data dictionary, source references, and validation report."""
    dictionary: list[dict[str, str]] = []

    for result in results:
        for column in result["columns"]:
            if column.startswith("field_"):
                position = column.removeprefix("field_")
                meaning = (
                    f"Unlabeled source field at position {position}; interpret using "
                    "the matching SIDER release documentation."
                )
            else:
                meaning = (
                    "Source column retained; meaning follows the source documentation "
                    "and has not been independently verified."
                )

            if column in {"RXCUI", "RXCUI1", "RXCUI2"}:
                meaning = "RxNorm concept identifier."
            elif column in {"RXAUI", "RXAUI1", "RXAUI2"}:
                meaning = "RxNorm atom identifier."
            elif column == "STR":
                meaning = "RxNorm atom string/name."

            dictionary.append(
                {
                    "cleaned_file": result["file"],
                    "column": column,
                    "description": meaning,
                    "type_policy": (
                        "UTF-8 text; source value retained after trimming "
                        "outer whitespace"
                    ),
                }
            )

    with (OUTPUT_DIR / "data_dictionary.csv").open(
        "w", encoding="utf-8-sig", newline=""
    ) as output_file:
        writer = csv.DictWriter(
            output_file,
            fieldnames=["cleaned_file", "column", "description", "type_policy"],
        )
        writer.writeheader()
        writer.writerows(dictionary)

    with (OUTPUT_DIR / "source_references.csv").open(
        "w", encoding="utf-8-sig", newline=""
    ) as output_file:
        fieldnames = [
            "source_file", "source_url", "licence_or_rights",
            "cleaned_csv_files", "processing_status",
        ]
        writer = csv.DictWriter(output_file, fieldnames=fieldnames)
        writer.writeheader()

        for path in files:
            relative_path = path.relative_to(ROOT).as_posix()
            url, rights = source_metadata(path)
            base = re.sub(
                r"[^A-Za-z0-9_-]+", "_", relative_path.rsplit(".", 1)[0]
            ).strip("_")
            outputs = "; ".join(
                result["file"]
                for result in results
                if Path(result["file"]).stem.startswith(base)
            )
            status = "cleaned to CSV" if outputs else next(
                (reason for source, reason in skipped if source == relative_path),
                "not exported",
            )
            writer.writerow(
                {
                    "source_file": relative_path,
                    "source_url": url,
                    "licence_or_rights": rights,
                    "cleaned_csv_files": outputs,
                    "processing_status": status,
                }
            )

    with (OUTPUT_DIR / "validation_report.csv").open(
        "w", encoding="utf-8-sig", newline=""
    ) as output_file:
        fieldnames = [
            "cleaned_file", "rows_in", "rows_out", "exact_duplicate_rows_removed",
            "blank_rows_removed", "missing_values_by_column", "limitations",
            "unverified_records",
        ]
        writer = csv.DictWriter(output_file, fieldnames=fieldnames)
        writer.writeheader()

        for result in results:
            writer.writerow(
                {
                    "cleaned_file": result["file"],
                    "rows_in": result["rows_in"],
                    "rows_out": result["rows_out"],
                    "exact_duplicate_rows_removed": result["duplicates"],
                    "blank_rows_removed": result["blank"],
                    "missing_values_by_column": json.dumps(
                        result["missing"], ensure_ascii=False
                    ),
                    "limitations": (
                        "No semantic validation or cross-source reconciliation "
                        "performed."
                    ),
                    "unverified_records": (
                        "All records remain unverified against live authoritative "
                        "sources."
                    ),
                }
            )

        for source, reason in skipped:
            writer.writerow(
                {
                    "limitations": f"Not converted: {reason}",
                    "unverified_records": f"Source: {source}",
                }
            )

    # README.md is maintained as a detailed guide and is not regenerated here,
    # so preprocessing runs do not replace it with a short summary.


def main() -> None:
    """Run preprocessing and write the generated datasets and documentation."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    source_files = discover_source_files()
    results, skipped = process_sources(source_files)
    write_documentation(source_files, results, skipped)

    print(
        f"Wrote {len(results)} cleaned CSV tables and three generated "
        "documentation files "
        f"to {OUTPUT_DIR}"
    )
    print("Not converted:")
    for source, reason in skipped:
        print(f"- {source}: {reason}")


if __name__ == "__main__":
    main()
