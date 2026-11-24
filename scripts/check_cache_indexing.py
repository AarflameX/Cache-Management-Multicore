"""Check the pinned baseline geometry in both gem5 configuration dumps."""

import argparse
import configparser
import json
from pathlib import Path


def check(outdir, cores):
    ini = configparser.ConfigParser(interpolation=None)
    with (outdir / "config.ini").open() as stream:
        ini.read_file(stream)
    with (outdir / "config.json").open() as stream:
        board = json.load(stream)["board"]

    def expect(obj, **fields):
        path = obj["path"]
        for name, wanted in fields.items():
            for source, value in (("json", obj[name]), ("ini", ini[path][name])):
                if str(value).lower() != str(wanted).lower():
                    raise ValueError(
                        f"config.{source} {path}.{name} = {value}, expected {wanted}"
                    )

    ruby = board["cache_hierarchy"]["ruby_system"]
    expect(board, cache_line_size=64)
    expect(ruby, block_size_bytes=64)
    l1s = ruby["l1_controllers"]
    l2s = ruby["l2_controllers"]
    if len(l1s) != cores or len(l2s) != 2:
        raise ValueError(f"expected {cores} L1 controllers and 2 L2 banks, "
                         f"found {len(l1s)} and {len(l2s)}")

    # CacheMemory::init inherits Ruby's block size when block_size is zero.
    def check_cache(cache, size, assoc, start):
        expect(cache, size=size, assoc=assoc, start_index_bit=start)
        expect(cache, block_size=cache["block_size"])
        if (cache["block_size"] or ruby["block_size_bytes"]) != 64:
            raise ValueError(f"{cache['path']} must use 64-byte lines")

    for controller in l1s:
        expect(controller, enable_prefetch=False, l2_select_num_bits=1)
        for name in ("L1Icache", "L1Dcache"):
            check_cache(controller[name], 32768, 2, 6)
    for bank in l2s:
        check_cache(bank["L2cache"], 262144, 8, 7)
    print(f"{outdir}: verified {cores} L1I/D pairs and 2 L2 banks in INI and JSON")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("outdir", type=Path)
    parser.add_argument("--cores", type=int, required=True)
    args = parser.parse_args()
    try:
        check(args.outdir, args.cores)
    except (ValueError, KeyError, OSError, configparser.Error) as error:
        parser.exit(1, f"{error}\n")
