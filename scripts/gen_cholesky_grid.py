#!/usr/bin/env python3
"""Write the symmetric lower-triangle pattern of a 2D five-point Laplacian.

The argument is the grid SIDE, not the number of vertices. PSA omits numeric
values: SPLASH CHOLESKY supplies its own positive-definite values. Side 8
reproduces the historical (misleadingly named) cholesky-grid64.hb byte for byte.
"""
import argparse
from pathlib import Path


def generate(side):
    if side < 1:
        raise ValueError("side must be positive")
    vertices = side * side
    pointers, rows = [1], []
    for col in range(vertices):
        rows.append(col + 1)
        if col % side + 1 < side:
            rows.append(col + 2)
        if col + side < vertices:
            rows.append(col + side + 1)
        pointers.append(len(rows) + 1)
    if len(rows) + 1 > 999999:
        raise ValueError("grid exceeds the legacy I6 field width")
    pointer_lines = (len(pointers) + 11) // 12
    row_lines = (len(rows) + 11) // 12
    title = f"{side}x{side} grid pattern; numeric values supplied by CHOLESKY"
    key = f"GRID{vertices:04d}" if vertices < 10000 else f"G{vertices:07d}"
    lines = [f"{title:<72}{key}",
             "".join(f"{n:14d}" for n in
                     (pointer_lines + row_lines, pointer_lines, row_lines, 0, 0)),
             f"PSA           {vertices:14d}{vertices:14d}{len(rows):14d}{0:14d}",
             "(12I6)          (12I6)                     (1E20.12)           (1E20.12)"]
    for values in (pointers, rows):
        lines.extend("".join(f"{n:6d}" for n in values[i:i + 12])
                     for i in range(0, len(values), 12))
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("side", type=int)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    try:
        data = generate(args.side)
    except ValueError as error:
        parser.error(str(error))
    args.output.write_text(data)


if __name__ == "__main__":
    main()
