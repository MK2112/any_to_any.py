def parse_page_ranges(
    page_ranges: str, total_pages: int
) -> list[tuple[int, int]] | None:
    # Parse page_ranges string into list of (start, end) tuples.
    #   None, '1-5', '2-5,3-4', '3-6, 8-20, 23-45, rest', 'all', 'rest',
    #   '3-6;15-22', '1-7;8-15;20-22;rest', '3', '35', '12-end', '2-end',
    #   '2-5, 3-6, 12-end', '2-end, 3-6, 12-end', '2-end, 3-6'
    if not page_ranges or page_ranges.strip() == "":
        return None
    page_ranges = page_ranges.strip()
    lowered = page_ranges.lower()
    if lowered == "all":
        return [(page, page) for page in range(1, total_pages + 1)]
    if lowered == "rest":
        return [(1, total_pages)]

    ranges = [r.strip() for r in page_ranges.replace(";", ",").split(",")]
    if any(not r for r in ranges):
        return None

    parsed_ranges = []
    rest_start = 1

    for range_str in ranges:
        range_str = range_str.strip()
        if range_str.lower() == "rest":
            if parsed_ranges:
                max_end = max(end for _, end in parsed_ranges)
                rest_start = max_end + 1
            if rest_start <= total_pages:
                parsed_ranges.append((rest_start, total_pages))
            continue
        if range_str.isdecimal():
            page_num = int(range_str)
            if not 1 <= page_num <= total_pages:
                return None
            parsed_ranges.append((page_num, page_num))
            rest_start = max(rest_start, page_num + 1)
            continue
        if "-" in range_str:
            parts = range_str.split("-", 1)
            if len(parts) == 2:
                start_str, end_str = parts[0].strip(), parts[1].strip()
                try:
                    start = int(start_str)
                except ValueError:
                    return None
                if end_str.lower() in ("end", "rest"):
                    end = total_pages
                else:
                    try:
                        end = int(end_str)
                    except ValueError:
                        return None
                if (
                    1 <= start <= total_pages
                    and 1 <= end <= total_pages
                    and start <= end
                ):
                    parsed_ranges.append((start, end))
                    rest_start = max(rest_start, end + 1)
                    continue
        return None
    return list(dict.fromkeys(parsed_ranges)) or None
