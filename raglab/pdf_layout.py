"""Optional extraction of bordered tables into page-local, labeled text."""

from io import BytesIO


def table_text(table) -> str:
    rows = [[" ".join((cell or "").split()) for cell in row] for row in table.extract()]
    if len(rows) < 2 or len(rows[0]) < 2:
        return ""
    # Layout boxes often look like tables but have empty or paragraph-sized headers.
    header_index = next((i for i in range(min(2, len(rows) - 1))
                         if all(0 < len(cell) <= 120 for cell in rows[i])), None)
    if header_index is None:
        return ""
    headers = rows[header_index][:]
    if header_index == 1:
        group_cells = zip(table.rows[0].cells, rows[0])
        groups = [(box, label) for box, label in group_cells if box and label and len(label) <= 120]
        for i, box in enumerate(table.rows[1].cells):
            if box:
                center = (box[0] + box[2]) / 2
                group = next((label for bounds, label in groups if bounds[0] <= center <= bounds[2]), "")
                if group:
                    headers[i] = f"{group} / {headers[i]}"
    lines = ["Table columns: " + " | ".join(headers)]
    for number, row in enumerate(rows[header_index + 1:], 1):
        if any(row):
            label = f"Table row {number} ({headers[0]}: {row[0] or '[empty]'})"
            lines.extend(f"{label} | {header}: {value or '[empty]'}" for header, value in zip(headers, row))
    return "\n".join(lines)


def extract_table_blocks(content: bytes) -> list[list[str]]:
    try:
        import pdfplumber
    except ImportError as exc:
        raise RuntimeError("请安装 requirements-pdf-layout.txt 以使用表格抽取") from exc
    with pdfplumber.open(BytesIO(content)) as pdf:
        return [[text for table in page.find_tables() if (text := table_text(table))] for page in pdf.pages]
