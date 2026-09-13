import csv
import os
import sys


OUTPUT_FILE = "data/ports/wpi-japan.csv"


def normalize(value):
    if value is None:
        return ""
    return str(value).strip()


def normalize_header(value):
    return "".join(
        ch.lower()
        for ch in normalize(value)
        if ch.isalnum()
    )


def normalize_locode(value):
    return "".join(
        ch
        for ch in normalize(value).upper()
        if ch.isalnum()
    )


def normalize_wpi_number(value):
    value = normalize(value)

    if not value:
        return ""

    try:
        number = float(value)

        if number.is_integer():
            return str(int(number))
    except ValueError:
        pass

    return value


def find_column(headers, *candidates):
    normalized_headers = {
        normalize_header(header): header
        for header in headers
    }

    for candidate in candidates:
        key = normalize_header(candidate)

        if key in normalized_headers:
            return normalized_headers[key]

    return None


def get_value(row, column):
    if not column:
        return ""

    return normalize(
        row.get(column, "")
    )


def is_japan(country, locode):
    country = normalize(country).upper()
    locode = normalize_locode(locode)

    return (
        country in {
            "JP",
            "JPN",
            "JA",
            "JAPAN",
        }
        or locode.startswith("JP")
    )


def main():
    if len(sys.argv) < 2:
        raise RuntimeError(
            "入力CSVファイルを指定してください。"
        )

    input_file = sys.argv[1]

    if not os.path.exists(input_file):
        raise RuntimeError(
            f"入力CSVがありません: {input_file}"
        )

    with open(
        input_file,
        "r",
        encoding="utf-8-sig",
        newline="",
        errors="replace",
    ) as file:

        reader = csv.DictReader(file)

        headers = reader.fieldnames or []

        print(
            "===== WPI CSV columns ====="
        )

        for header in headers:
            print(
                f"  {header}"
            )

        col_wpi = find_column(
            headers,
            "World Port Index Number",
            "WPI Number",
            "WPI_Number",
            "wpinumber",
        )

        col_name = find_column(
            headers,
            "Main Port Name",
            "Main_Port_Name",
            "main_port_",
        )

        col_alt = find_column(
            headers,
            "Alternate Port Name",
            "Alternate_Port_Name",
            "alternate_",
        )

        col_locode = find_column(
            headers,
            "UN/LOCODE",
            "UNLOCODE",
            "unlocode",
        )

        col_country = find_column(
            headers,
            "Country Code",
            "Country_Code",
            "countryCode",
        )

        col_lat = find_column(
            headers,
            "Latitude",
            "latitude",
            "Latitude_deg",
        )

        col_lon = find_column(
            headers,
            "Longitude",
            "longitude",
            "Longitude_deg",
        )

        required = {
            "WPI番号": col_wpi,
            "港名": col_name,
        }

        missing = [
            label
            for label, column in required.items()
            if not column
        ]

        if missing:
            raise RuntimeError(
                "必要な列が見つかりません: "
                + ", ".join(missing)
            )

        print("")
        print("===== 使用列 =====")
        print(f"WPI番号: {col_wpi}")
        print(f"港名: {col_name}")
        print(f"別名: {col_alt}")
        print(f"UN/LOCODE: {col_locode}")
        print(f"国: {col_country}")
        print(f"緯度: {col_lat}")
        print(f"経度: {col_lon}")

        rows = []

        for source in reader:
            country = get_value(
                source,
                col_country
            )

            locode = normalize_locode(
                get_value(
                    source,
                    col_locode
                )
            )

            if not is_japan(
                country,
                locode
            ):
                continue

            row = {
                "wpi_number":
                    normalize_wpi_number(
                        get_value(
                            source,
                            col_wpi
                        )
                    ),

                "main_port_name":
                    get_value(
                        source,
                        col_name
                    ),

                "alternate_port_name":
                    get_value(
                        source,
                        col_alt
                    ),

                "unlocode":
                    locode,

                "country_code":
                    "JP",

                "latitude":
                    get_value(
                        source,
                        col_lat
                    ),

                "longitude":
                    get_value(
                        source,
                        col_lon
                    ),
            }

            if not row[
                "main_port_name"
            ]:
                continue

            rows.append(row)

    if not rows:
        raise RuntimeError(
            "日本の港を1件も抽出できませんでした。"
        )

    seen_wpi = set()

    duplicates = []

    valid_rows = []

    for row in rows:
        wpi = row[
            "wpi_number"
        ]

        if not wpi:
            print(
                "WARNING: WPI番号なし:",
                row["main_port_name"],
            )
            continue

        if wpi in seen_wpi:
            duplicates.append(
                wpi
            )
            continue

        seen_wpi.add(
            wpi
        )

        valid_rows.append(
            row
        )

    if duplicates:
        print(
            "WARNING: WPI番号重複:",
            ", ".join(
                sorted(
                    set(
                        duplicates
                    )
                )
            ),
        )

    valid_rows.sort(
        key=lambda row: (
            row["wpi_number"],
            row["main_port_name"],
        )
    )

    os.makedirs(
        os.path.dirname(
            OUTPUT_FILE
        ),
        exist_ok=True,
    )

    fields = [
        "wpi_number",
        "main_port_name",
        "alternate_port_name",
        "unlocode",
        "country_code",
        "latitude",
        "longitude",
    ]

    with open(
        OUTPUT_FILE,
        "w",
        encoding="utf-8",
        newline="",
    ) as file:

        writer = csv.DictWriter(
            file,
            fieldnames=fields,
        )

        writer.writeheader()
        writer.writerows(
            valid_rows
        )

    locode_count = sum(
        1
        for row in valid_rows
        if row["unlocode"]
    )

    print("")
    print("===== 完了 =====")
    print(
        f"日本港: {len(valid_rows)}件"
    )
    print(
        f"UN/LOCODEあり: {locode_count}件"
    )
    print(
        f"出力: {OUTPUT_FILE}"
    )


if __name__ == "__main__":
    main()
