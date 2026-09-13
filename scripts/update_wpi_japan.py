import ssl
import csv
import json
import os
import sys
import time
import urllib.parse
import urllib.request


WPI_QUERY_URL = (
    "https://vcps.nga.mil/"
    "nauticalpubs-feature/rest/services/"
    "WPI/World_Port_Index_Viewer/"
    "FeatureServer/0/query"
)

OUTPUT_FILE = "data/ports/wpi-japan.csv"

PAGE_SIZE = 2000


def fetch_json(url, params):
    query = urllib.parse.urlencode(params)
    request_url = f"{url}?{query}"

    request = urllib.request.Request(
        request_url,
        headers={
            "User-Agent": "JJ200236-WPI-Sync/1.0",
            "Accept": "application/json",
        },
    )

    # NGA WPIサーバーはGitHub Actions環境からアクセスすると
    # 自己署名証明書を含む証明書チェーンとして判定されるため、
    # このNGA固定URLへの取得時のみ証明書検証を無効化する。
    ssl_context = ssl.create_default_context()
    ssl_context.check_hostname = False
    ssl_context.verify_mode = ssl.CERT_NONE

    with urllib.request.urlopen(
        request,
        timeout=60,
        context=ssl_context,
    ) as response:
        return json.loads(
            response.read().decode("utf-8")
        )


def get_all_wpi():
    features = []
    offset = 0

    while True:
        print(
            f"WPI取得中: offset={offset}",
            flush=True,
        )

        data = fetch_json(
            WPI_QUERY_URL,
            {
                "where": "1=1",
                "outFields": "*",
                "returnGeometry": "true",
                "outSR": "4326",
                "resultOffset": offset,
                "resultRecordCount": PAGE_SIZE,
                "f": "json",
            },
        )

        if "error" in data:
            raise RuntimeError(
                "NGA API error: "
                + json.dumps(
                    data["error"],
                    ensure_ascii=False,
                )
            )

        page = data.get(
            "features",
            [],
        )

        if not page:
            break

        # 最初の1件だけ実際の属性名をログ出力
        if offset == 0:
            sample_attributes = (
                page[0].get(
                    "attributes",
                    {}
                )
            )

            print(
                "WPI実フィールド一覧:",
                flush=True,
            )

            for key in sample_attributes.keys():
                print(
                    f"  {key}",
                    flush=True,
                )

        features.extend(page)

        print(
            f"  {len(page)}件取得 "
            f"/ 累計{len(features)}件",
            flush=True,
        )

        offset += len(page)

        exceeded = bool(
            data.get(
                "exceededTransferLimit",
                False,
            )
        )

        if (
            len(page) < PAGE_SIZE
            and not exceeded
        ):
            break

        if offset > 50000:
            raise RuntimeError(
                "WPI取得件数が50,000件を超えたため停止"
            )

        time.sleep(0.5)

    return features


def normalize(value):
    if value is None:
        return ""

    return str(value).strip()


def normalize_locode(value):
    value = normalize(value).upper()

    return "".join(
        ch
        for ch in value
        if ch.isalnum()
    )


def normalize_wpi_number(value):
    if value is None:
        return ""

    # ArcGIS側ではDoubleの場合があるため
    # 12345.0 → 12345 にする
    try:
        number = float(value)

        if number.is_integer():
            return str(int(number))

    except (ValueError, TypeError):
        pass

    return normalize(value)


def pick_attr(attributes, *names):
    # 完全一致
    for name in names:
        if name in attributes:
            return attributes.get(name)

    # NGA側のフィールド名変更に多少耐える
    normalized = {
        "".join(
            ch.lower()
            for ch in str(key)
            if ch.isalnum()
        ): value
        for key, value in attributes.items()
    }

    for name in names:
        key = "".join(
            ch.lower()
            for ch in name
            if ch.isalnum()
        )

        if key in normalized:
            return normalized[key]

    return ""


def is_japan(attributes):
    country = normalize(
        pick_attr(
            attributes,
            "countryCode",
            "country_code",
            "wpi_cc",
        )
    ).upper()

    locode = normalize_locode(
        pick_attr(
            attributes,
            "unlocode",
        )
    )

    # WPIのCountry CodeはGENC系表記の可能性があるため、
    # UN/LOCODEのJPプレフィックスも併用する。
    return (
        country in {
            "JP",
            "JPN",
            "JA",
            "JAPAN",
        }
        or locode.startswith("JP")
    )


def convert_feature(feature):
    attributes = feature.get(
        "attributes",
        {},
    )

    geometry = feature.get(
        "geometry",
        {},
    )

    wpi_number = normalize_wpi_number(
        pick_attr(
            attributes,
            "wpinumber",
            "wpi_number",
        )
    )

    main_port_name = normalize(
        pick_attr(
            attributes,
            "main_port_",
            "main_port_name",
        )
    )

    alternate_port_name = normalize(
        pick_attr(
            attributes,
            "alternate_",
            "alternate_name",
            "alternate_port_name",
        )
    )

    unlocode = normalize_locode(
        pick_attr(
            attributes,
            "unlocode",
        )
    )

    latitude = normalize(
        geometry.get("y")
    )

    longitude = normalize(
        geometry.get("x")
    )

    return {
        "wpi_number": wpi_number,
        "main_port_name": main_port_name,
        "alternate_port_name": alternate_port_name,
        "unlocode": unlocode,
        "country_code": "JP",
        "latitude": latitude,
        "longitude": longitude,
    }


def validate(rows):
    if not rows:
        raise RuntimeError(
            "日本の港が0件です。"
        )

    wpi_numbers = set()

    duplicate_wpi = []

    for row in rows:
        wpi = row[
            "wpi_number"
        ]

        if not wpi:
            raise RuntimeError(
                "WPI番号が空の港があります: "
                + row["main_port_name"]
            )

        if wpi in wpi_numbers:
            duplicate_wpi.append(
                wpi
            )

        wpi_numbers.add(
            wpi
        )

    if duplicate_wpi:
        raise RuntimeError(
            "WPI番号重複: "
            + ", ".join(
                sorted(
                    set(
                        duplicate_wpi
                    )
                )
            )
        )


def write_csv(rows):
    os.makedirs(
        os.path.dirname(
            OUTPUT_FILE
        ),
        exist_ok=True,
    )

    fieldnames = [
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
            fieldnames=fieldnames,
        )

        writer.writeheader()

        writer.writerows(
            rows
        )


def main():
    features = get_all_wpi()

    print(
        f"WPI全件: {len(features)}",
        flush=True,
    )

    japan_features = [
        feature
        for feature in features
        if is_japan(
            feature.get(
                "attributes",
                {},
            )
        )
    ]

    rows = [
        convert_feature(feature)
        for feature in japan_features
    ]

    rows = [
        row
        for row in rows
        if row["main_port_name"]
    ]

    rows.sort(
        key=lambda row: (
            row["wpi_number"],
            row["main_port_name"],
        )
    )

    validate(rows)

    write_csv(rows)

    locode_count = sum(
        1
        for row in rows
        if row["unlocode"]
    )

    print(
        "",
        flush=True,
    )

    print(
        "=== 完了 ===",
        flush=True,
    )

    print(
        f"日本港: {len(rows)}件",
        flush=True,
    )

    print(
        f"UN/LOCODEあり: {locode_count}件",
        flush=True,
    )

    print(
        f"出力: {OUTPUT_FILE}",
        flush=True,
    )


if __name__ == "__main__":
    try:
        main()

    except Exception as exc:
        print(
            f"ERROR: {exc}",
            file=sys.stderr,
        )
        raise
