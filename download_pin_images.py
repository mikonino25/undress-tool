"""
Download all images found on a Pinterest pin page into the user's Downloads folder.

Usage:
  python download_pin_images.py --url https://au.pinterest.com/pin/383791199519150265/

Options:
  --output <path>   Custom download directory (defaults to ~/Downloads/Pinterest).
  --min-aspect <n>  Minimum height/width ratio to keep (default 1.0).
  --target-width    Target portrait width (default 736px).
  --target-height   Target portrait height (default 1308px).
  --tolerance       Allowed deviation (default 120px).

Dependencies:
  pip install requests beautifulsoup4 pillow
"""

from __future__ import annotations

import argparse
import pathlib
import re
import sys
from io import BytesIO
from typing import Iterable, List, Tuple

import requests
from bs4 import BeautifulSoup

try:
    from PIL import Image  # type: ignore
except ImportError as exc:  # pragma: no cover - dependency check
    raise SystemExit("Install pillow: pip install pillow") from exc

DEFAULT_OUTPUT_DIR = pathlib.Path.home() / "Downloads" / "Pinterest"
PIN_IMAGE_PATTERN = re.compile(r"\.(?:jpe?g|png|webp)(?:\?.*)?$", re.IGNORECASE)
FILENAME_INDEX_PATTERN = re.compile(r"pin_image_(\d+)$", re.IGNORECASE)
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/118.0 Safari/537.36"
    )
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Download images from a Pinterest pin page."
    )
    parser.add_argument(
        "--url",
        help="Pinterest pin URL (e.g., https://www.pinterest.com/pin/123456789/)",
    )
    parser.add_argument(
        "--output",
        type=pathlib.Path,
        default=DEFAULT_OUTPUT_DIR,
        help="Directory to save images (default: ~/Downloads/Pinterest)",
    )
    parser.add_argument(
        "--min-aspect",
        type=float,
        default=1.0,
        help=(
            "Minimum height/width ratio to keep an image (default: 1.0 for portrait). "
            "Set to 0 to keep all orientations."
        ),
    )
    parser.add_argument(
        "--target-width",
        type=int,
        default=736,
        help="Preferred portrait width (default: 736px).",
    )
    parser.add_argument(
        "--target-height",
        type=int,
        default=1308,
        help="Preferred portrait height (default: 1308px).",
    )
    parser.add_argument(
        "--tolerance",
        type=int,
        default=120,
        help="Allowed +/- pixel deviation for width/height (default: 120px).",
    )
    return parser.parse_args()


def fetch_html(url: str) -> str:
    response = requests.get(url, headers=HEADERS, timeout=15)
    response.raise_for_status()
    return response.text


def extract_image_urls(html: str) -> List[str]:
    soup = BeautifulSoup(html, "html.parser")
    story_candidates = set()
    candidates = set()

    # Regular <img> tags
    for img in soup.find_all("img"):
        src = img.get("src") or img.get("data-src")
        if src:
            candidates.add(src)
            alt_text = (img.get("alt") or "").lower()
            element_timing = (img.get("elementtiming") or "").lower()
            classes = img.get("class") or []
            if (
                "story pin image" in alt_text
                or "storypinimageblock" in element_timing
                or "iFOUS5".lower() in [cls.lower() for cls in classes]
            ):
                story_candidates.add(src)

    # Source tags (picture elements)
    for source in soup.find_all("source"):
        srcset = source.get("srcset")
        if srcset:
            for variant in srcset.split(","):
                url_part = variant.strip().split(" ")[0]
                candidates.add(url_part)

    # Meta tags (og:image)
    for meta in soup.find_all("meta"):
        if meta.get("property") in {"og:image", "twitter:image"}:
            content = meta.get("content")
            if content:
                candidates.add(content)

    selected = story_candidates if story_candidates else candidates
    return [url for url in selected if PIN_IMAGE_PATTERN.search(url)]


def download_images(
    urls: Iterable[str],
    output_dir: pathlib.Path,
    min_aspect: float,
    target_size: tuple[int, int],
    tolerance: int,
    start_index: int,
) -> int:
    output_dir.mkdir(parents=True, exist_ok=True)
    current_index = start_index
    for url in sorted(urls):
        try:
            response = requests.get(url, headers=HEADERS, timeout=20)
            response.raise_for_status()

            if min_aspect > 0 or tolerance >= 0:
                if not matches_dimensions(
                    response.content, min_aspect, target_size, tolerance
                ):
                    print(f"[-] Skip (không đúng kích thước dọc chuẩn): {url}")
                    continue

            ext = pathlib.Path(url.split("?")[0]).suffix or ".jpg"
            filename = output_dir / f"pin_image_{current_index}{ext}"
            with open(filename, "wb") as fh:
                fh.write(response.content)
            print(f"[+] Saved {filename.name}")
            current_index += 1
        except Exception as exc:  # noqa: BLE001
            print(f"[!] Failed to download {url}: {exc}")
    return current_index


def determine_start_index(output_dir: pathlib.Path) -> int:
    if not output_dir.exists():
        return 1
    max_index = 0
    for file in output_dir.iterdir():
        if not file.is_file():
            continue
        match = FILENAME_INDEX_PATTERN.search(file.stem)
        if match:
            max_index = max(max_index, int(match.group(1)))
    return max_index + 1


def matches_dimensions(
    image_bytes: bytes,
    min_aspect: float,
    target_size: tuple[int, int],
    tolerance: int,
) -> bool:
    try:
        with Image.open(BytesIO(image_bytes)) as img:
            width, height = img.size
            if width == 0:
                return False
            aspect_ok = (height / width) >= min_aspect if min_aspect > 0 else True
            width_ok = abs(width - target_size[0]) <= tolerance

            target_height = target_size[1]
            height_ok = True
            if target_height > 0 and tolerance >= 0:
                min_height = max(1, target_height - tolerance)
                height_ok = height >= min_height

            return aspect_ok and width_ok and height_ok
    except Exception:
        return False


def process_pin(pin_url: str, args: argparse.Namespace) -> bool:
    try:
        html = fetch_html(pin_url)
    except Exception as exc:  # noqa: BLE001
        print(f"[!] Could not fetch {pin_url}: {exc}")
        return False

    urls = extract_image_urls(html)
    if not urls:
        print("[!] No images found on the page. Double-check the pin URL.")
        return False

    print(
        f"[+] Found {len(urls)} image candidates. "
        f"Downloading portrait images near {args.target_width}x{args.target_height}"
        f" (±{args.tolerance}px, ratio >= {args.min_aspect}) to {args.output}"
    )
    start_index = determine_start_index(args.output)
    download_images(
        urls,
        args.output,
        args.min_aspect,
        (args.target_width, args.target_height),
        args.tolerance,
        start_index,
    )
    print("[✓] Done\n")
    return True


def main() -> int:
    args = parse_args()

    if args.url:
        return 0 if process_pin(args.url, args) else 1

    print("Nhập link pin Pinterest (Enter trống để thoát).")
    while True:
        pin_url = input("> ").strip()
        if not pin_url:
            print("Tạm biệt!")
            return 0
        process_pin(pin_url, args)


if __name__ == "__main__":
    sys.exit(main())

