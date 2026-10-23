# hal2vg
[![Build Status](https://travis-ci.org/ComparativeGenomicsToolkit/hal2vg.svg?branch=master)](https://travis-ci.org/ComparativeGenomicsToolkit/hal2vg)

Convert [HAL](https://github.com/glennhickey/hal) to [vg](https://github.com/vgteam/vg)-compatible sequence graph.

Supports the three sequence graph formats in [libbdsg](https://github.com/vgteam/libbdsg):
* PackedGraph (default)
* ODGI
* HashGraph

## Algorithm

1. Each sequence in the HAL is added as a thread to a [Pinch Graph](https://github.com/ComparativeGenomicsToolkit/pinchesAndCacti).
2. Exact pairwise alignment blocks (no gaps or substitutions) are extracted from each branch in the HAL tree and "pinched" in the graph
3. For each branch, bases in the child that have substitutions in the parent (snps) are aligned across the tree using the column iterator and all exact matches are extracted and pinched.
4. Pinch graph is cleaned up by merging trivial joins
5. Each HAL sequence is traced through the pinch graph, adding nodes and edges to the output sequence graph.  A table is maintained to map each pinch graph block to a sequence graph node.

## Suggested Postprocessing:

*  Sort the output with `vg ids --sort`.  

## Installation

### Binary Release

You can download a standalone binary for the latest release [here](https://github.com/ComparativeGenomicsToolkit/hal2vg/releases).

### Compile From Source

You can use the the [Dockerfile](Dockerfile) as a guide to see how all dependencies are installed with `apt` on Ubuntu.  More details on installing HDF5 can be found in the [HAL README](https://github.com/ComparativeGenomicsToolkit/hal)

**Cloning:** Don't forget to clone submodules with the `--recursive` option:

     git clone https://github.com/glennhickey/hal2vg.git --recursive

**Compiling:**

     make

hal2vg links against [jemalloc](https://github.com/jemalloc/jemalloc), which is vendored as
a submodule and needs `autoconf` to build.  It saves a substantial amount of memory on large
conversions, since the pinch graph hal2vg builds internally is dominated by small, uniformly
sized allocations that jemalloc packs much more tightly than the system allocator.  It is
skipped automatically on macOS; build with `DISABLE_JEMALLOC=1 make` to use the system
allocator anywhere else.

## Usage

It is required to use the `--inMemory` option for all but trivial inputs.

`vg` has been tuned to work best on graphs with nodes chopped to at most 32 bases.  It is therefore recommended to use the `--chop 32` option.

```
hal2vg input.hal --inMemory --chop 32 --progress > output.pg
```

**Note**: The output graph is only readable by vg version 1.24.0 and greater.

## Genome-lifetime memory experiment

This fork closes each child genome after `pinch_genome()` returns. `--inMemory`
is still supported and the pinching algorithm is unchanged. For an A/B comparison,
`--keepPinchedGenomes` restores the original child-genome lifetime in the same binary.
Parent genomes can remain open; this first experiment does not change their lifetime.
The later `build_id_to_sequence()` still opens all thread genomes and retains their
sequence pointers, so this change does **not** promise a lower peak for the complete
conversion.

With `--progress`, stderr also contains lines such as:

```text
[hal2vg-memory] stage=after_pinching elapsed_ms=12345 rss_kib=123456 peak_rss_kib=234567
```

On Linux, `rss_kib` is current process RSS (`VmRSS`) and `peak_rss_kib` is its
high-water mark (`VmHWM`), both in KiB. On other platforms, the memory fields are
`unavailable`. `elapsed_ms` is wall time since the parsed command started. These
diagnostics never go to the graph on stdout. Stage boundaries surround both joins,
the ID-to-sequence lookup, base splitting, graph conversion, and serialization.
The last boundary reached helps locate a failure; a rising high-water mark alone
does not show whether the corresponding memory is still allocated.

### Build on the cluster

Use the compiler/HDF5 build environment from the existing Cactus installation.
The build requires a C++20-capable compiler, `h5c++`/HDF5 development files,
autoconf for jemalloc, and the lz4, zstd and jansson development
libraries. No change to the installed Cactus executable is needed for this test.

```bash
git clone --recursive https://github.com/yeeus/hal2vg.git hal2vg-memory-step1
cd hal2vg-memory-step1
make -j 16 hal2vg
./hal2vg --help
```

`make test` runs the repository tests when `vg`, `jq`, `prove`, and the build
dependencies are available. The small-HAL test checks the original and new genome
lifetimes against each other, including ordered path steps.

### Profile the same chr21 HAL with both lifetimes

Run on an allocated compute node with enough memory for the previously completed
chr21 conversion. In the chromosome directory, activate the existing Cactus runtime
first, then set `HAL2VG` to the **absolute path** of the newly built executable:

```bash
set -eo pipefail
source ./cactus.config.sh
export OMP_NUM_THREADS=1
HAL2VG=/absolute/path/to/hal2vg-memory-step1/hal2vg
HAL="$PWD/align/chr21.hal"
mkdir -p ./hal2vg_step1

for mode in close baseline; do
    args=(--progress --inMemory --ignoreGenomes Anc0
          --refGenomes _MINIGRAPH_,GRCh38,CHM13v2,CN1v1)
    if [[ "$mode" == baseline ]]; then
        args+=(--keepPinchedGenomes)
    fi
    /usr/bin/time -v -o "./hal2vg_step1/${mode}.time.log" \
        "$HAL2VG" "$HAL" "${args[@]}" \
        > "./hal2vg_step1/${mode}.vg" \
        2> "./hal2vg_step1/${mode}.log"
done

grep -H '\[hal2vg-memory\]' ./hal2vg_step1/*.log
```

`close` uses the new default; `baseline` uses the original lifetime. These are
sequential full conversions. Keep both graph outputs for comparison; do not use
the existing production output filenames. A failure stops the loop. To run only
one mode, replace `for mode in close baseline` with `for mode in close` or
`for mode in baseline`.

For this Cactus comparison, deliberately omit `--chop 32`. It is a standalone
hal2vg recommendation, not the Cactus export default. Cactus `7f34bb7` exports with
`--progress --inMemory`, then its join stage enforces `maxNodeLength=1024` using
`vg mod -X`. In hal2vg, chopping happens after pinch-graph cleanup and graph
conversion, so it cannot reduce an earlier peak in pinching or base splitting.
See the pinned [export configuration](https://github.com/ComparativeGenomicsToolkit/cactus/blob/7f34bb7a65af5816835ef79b7ae5e2f3c277b305/src/cactus/cactus_progressive_config.xml#L683-L688),
[join configuration](https://github.com/ComparativeGenomicsToolkit/cactus/blob/7f34bb7a65af5816835ef79b7ae5e2f3c277b305/src/cactus/cactus_progressive_config.xml#L626-L652),
and [join chopping step](https://github.com/ComparativeGenomicsToolkit/cactus/blob/7f34bb7a65af5816835ef79b7ae5e2f3c277b305/src/cactus/refmap/cactus_graphmap_join.py#L1557-L1574).

Copyright (C) 2020 by UCSC Computational Genomics Lab

