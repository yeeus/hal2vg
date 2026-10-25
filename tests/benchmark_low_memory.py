#!/usr/bin/env python3
"""Small synthetic SNP-rich memory comparison; this does not predict full-chromosome RSS."""
import pathlib
import random
import re
import subprocess

ROOT = pathlib.Path(__file__).resolve().parents[1]
work = ROOT / 'low_memory_benchmark'
work.mkdir(exist_ok=True)
rng = random.Random(20261025)
length = 20000
reference = ''.join(rng.choice('ACGT') for _ in range(length))
maf, hal = work / 'stress.maf', work / 'stress.hal'
with maf.open('w') as out:
    out.write(f'##maf version=1\n\na score=0\ns ref.chr 0 {length} + {length} {reference}\n')
    for i in range(256):
        bases = ''.join(rng.choice('ACGT'.replace(base, '')) if rng.randrange(10) == 0 else base
                        for base in reference)
        out.write(f's h{i}.chr 0 {length} + {length} {bases}\n')
    out.write('\n')
subprocess.run([str(ROOT / 'deps/hal/bin/maf2hal'), str(maf), str(hal)],
               stdout=subprocess.DEVNULL, check=True)
peaks, spellings = {}, []
for mode in ['baseline', 'low']:
    timing, graph = work / f'{mode}.time.log', work / f'{mode}.vg'
    command = ['/usr/bin/time', '-v', '-o', str(timing), str(ROOT / 'hal2vg'), str(hal),
               '--inMemory', '--progress']
    if mode == 'low':
        command.append('--lowMemory')
    with graph.open('wb') as out, (work / f'{mode}.log').open('w') as err:
        subprocess.run(command, stdout=out, stderr=err, check=True)
    subprocess.run(['vg', 'validate', str(graph)], check=True)
    data, name = {}, None
    for line in subprocess.check_output(['vg', 'paths', '-F', '-x', str(graph)], text=True).splitlines():
        if line.startswith('>'):
            name = line[1:]
            data[name] = ''
        else:
            data[name] += line.upper()
    spellings.append(data)
    peaks[mode] = int(re.search(r'Maximum resident set size \(kbytes\): (\d+)', timing.read_text())[1])
    print(f'{mode}: peak={peaks[mode]} KiB; paths={len(data)}', flush=True)
assert spellings[0] == spellings[1], 'synthetic path sequences differ'
print(f"Peak RSS reduction: {100 * (peaks['baseline'] - peaks['low']) / peaks['baseline']:.1f}%")
