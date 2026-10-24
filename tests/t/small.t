#!/usr/bin/env bash

BASH_TAP_ROOT=./bash-tap
. ${BASH_TAP_ROOT}/bash-tap-bootstrap

PATH=..:$PATH
PATH=../deps/hal/bin:$PATH

plan tests 7

maf2hal small/small.maf small.hal
hal2vg small.hal --inMemory --progress > small.vg 2> small.memory.log
vg view -j small.vg | jq . > small.json

is $(vg validate small.vg | wc -l) 0 "output vg validates"

# jq craziness from https://stackoverflow.com/questions/31930041/using-jq-or-alternative-command-line-tools-to-compare-json-files
is $(jq --argjson a "$(cat small.json)" --argjson b "$(cat small/truth.json)" -n 'def post_recurse(f): def r: (f | select(. != null) | r), .; r; def post_recurse: post_recurse(.[]?); ($a | (post_recurse | arrays) |= sort) as $a | ($b | (post_recurse | arrays) |= sort) as $b | $a == $b') true "output graph identical to manually verified truth graph"

hal2vg small.hal --inMemory --progress --keepPinchedGenomes > small.keep.vg 2> small.keep.memory.log
vg view -j small.keep.vg | jq . > small.keep.json
is $(jq -n --slurpfile a small.json --slurpfile b small.keep.json '($a | length) == 1 and ($b | length) == 1 and $a == $b') true "closing pinched genomes preserves the graph and ordered path steps"
is $(grep -c '^\[hal2vg-memory\] stage=before_split ' small.memory.log) 1 "stage memory diagnostics reach the split boundary"
is $(grep -c 'keep_pinched_genomes=1' small.keep.memory.log) 1 "original genome lifetime is available for comparison"
is $(grep -c '^\[hal2vg-pinch\] ' small.memory.log) 2 "pinch object snapshots cover pre-split and post-join states"
is $(grep -c 'stage=after_split .* jemalloc_stats=' small.memory.log) 1 "allocator availability is reported at the split boundary"

rm -f small.vg small.json
rm -f small.keep.vg small.keep.json small.memory.log small.keep.memory.log

rm -f small.hal 
