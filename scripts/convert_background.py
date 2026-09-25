#!/usr/bin/env python3

from pathlib import Path
from PIL import Image


# Paths are relative to the repository root.
INPUT_FILE = Path("assets/background.png")
OUTPUT_FILE = Path("include/BackgroundImage.h")

IMAGE_WIDTH = 240
IMAGE_HEIGHT = 240

# Set to True to make pixels outside the round display black.
# Set to False to retain the complete square image.
APPLY_CIRCULAR_MASK = True

CIRCLE_CENTRE_X = 120
CIRCLE_CENTRE_Y = 120
CIRCLE_RADIUS = 119


def rgb888_to_rgb332(red: int, green: int, blue: int) -> int:
    """
    Convert an RGB888 pixel to RGB332.

    Bits 7 to 5: red
    Bits 4 to 2: green
    Bits 1 to 0: blue
    """
    return (
        (red & 0xE0)
        | ((green & 0xE0) >> 3)
        | ((blue & 0xC0) >> 6)
    )


def is_inside_circle(x: int, y: int) -> bool:
    dx = x - CIRCLE_CENTRE_X
    dy = y - CIRCLE_CENTRE_Y

    return (
        dx * dx + dy * dy
        <= CIRCLE_RADIUS * CIRCLE_RADIUS
    )


def main() -> None:
    if not INPUT_FILE.exists():
        raise FileNotFoundError(
            f"Could not find input image: {INPUT_FILE}"
        )

    image = Image.open(INPUT_FILE).convert("RGB")

    if image.size != (IMAGE_WIDTH, IMAGE_HEIGHT):
        raise ValueError(
            f"Input image must be "
            f"{IMAGE_WIDTH}x{IMAGE_HEIGHT} pixels. "
            f"The supplied image is "
            f"{image.width}x{image.height} pixels."
        )

    output_values: list[int] = []

    for y in range(IMAGE_HEIGHT):
        for x in range(IMAGE_WIDTH):
            if (
                APPLY_CIRCULAR_MASK
                and not is_inside_circle(x, y)
            ):
                output_values.append(0x00)
                continue

            red, green, blue = image.getpixel((x, y))

            output_values.append(
                rgb888_to_rgb332(red, green, blue)
            )

    OUTPUT_FILE.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    with OUTPUT_FILE.open(
        "w",
        encoding="ascii",
        newline="\n"
    ) as output:
        output.write("#pragma once\n\n")
        output.write("#include <Arduino.h>\n\n")

        output.write(
            f"constexpr uint16_t "
            f"BACKGROUND_IMAGE_WIDTH = "
            f"{IMAGE_WIDTH};\n"
        )

        output.write(
            f"constexpr uint16_t "
            f"BACKGROUND_IMAGE_HEIGHT = "
            f"{IMAGE_HEIGHT};\n\n"
        )

        output.write(
            "const uint8_t BackgroundImage[] PROGMEM = {\n"
        )

        values_per_line = 16

        for index in range(
            0,
            len(output_values),
            values_per_line
        ):
            line_values = output_values[
                index:index + values_per_line
            ]

            formatted_values = ", ".join(
                f"0x{value:02X}"
                for value in line_values
            )

            if (
                index + values_per_line
                < len(output_values)
            ):
                suffix = ","
            else:
                suffix = ""

            output.write(
                f"    {formatted_values}{suffix}\n"
            )

        output.write("};\n\n")

        output.write(
            "static_assert(\n"
            "    sizeof(BackgroundImage) ==\n"
            "        BACKGROUND_IMAGE_WIDTH *\n"
            "        BACKGROUND_IMAGE_HEIGHT,\n"
            '    "Background image size is incorrect."\n'
            ");\n"
        )

    print(
        f"Created {OUTPUT_FILE} with "
        f"{len(output_values)} RGB332 pixels."
    )

    print(
        f"Embedded image size: "
        f"{len(output_values)} bytes."
    )


if __name__ == "__main__":
    main()