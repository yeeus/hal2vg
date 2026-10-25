#!/usr/bin/env python3
"""Make a small regional HAL regression fixture through MAF export and coordinate rebasing."""
import argparse
import csv
import io
import pathlib
import shutil
import subprocess


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('hal')
    parser.add_argument('outdir')
    parser.add_argument('--ref-genome', default='GRCh38')
    parser.add_argument('--ref-sequence')
    parser.add_argument('--targets', default='GRCh38,CHM13v2,CN1v1')
    parser.add_argument('--start', type=int, default=20000000)
    parser.add_argument('--length', type=int, default=100000)
    args = parser.parse_args()
    source = str(pathlib.Path(args.hal).resolve())
    out = pathlib.Path(args.outdir).resolve()
    if out / 'mini.hal' == pathlib.Path(source):
        raise ValueError('the subset output must not overwrite the input HAL')
    out.mkdir(parents=True, exist_ok=True)
    bundled = pathlib.Path(__file__).resolve().parents[1] / 'deps/hal/bin'

    def tool(name):
        candidate = bundled / name
        return str(candidate) if candidate.exists() else (shutil.which(name) or name)

    sequence = args.ref_sequence
    if sequence is None:
        result = subprocess.run([tool('halStats'), source, '--sequenceStats', args.ref_genome],
                                capture_output=True, text=True, check=True)
        rows = list(csv.reader(io.StringIO(result.stdout)))
        if len(rows) < 2:
            raise RuntimeError('no reference sequence found')
        sequence = rows[1][0].strip()
    regional = out / 'region.original_coordinates.maf'
    subprocess.run([tool('hal2maf'), source, str(regional), '--refGenome', args.ref_genome,
                    '--refSequence', sequence, '--start', str(args.start), '--length', str(args.length),
                    '--targetGenomes', args.targets], check=True)
    lines = regional.read_text().splitlines()
    bounds = {}
    for line in lines:
        fields = line.split()
        if not fields or fields[0] != 's':
            continue
        name, start, size, strand, source_size = fields[1:6]
        start, size, source_size = int(start), int(size), int(source_size)
        forward = start if strand == '+' else source_size - start - size
        old = bounds.get(name, (forward, forward + size))
        bounds[name] = (min(old[0], forward), max(old[1], forward + size))
    if not bounds:
        raise RuntimeError('the selected region exported no aligned rows')
    rebased = out / 'region.maf'
    with rebased.open('w') as target:
        for line in lines:
            fields = line.split()
            if fields and fields[0] == 's':
                name, start, size, strand, source_size = fields[1:6]
                start, size, source_size = int(start), int(size), int(source_size)
                forward = start if strand == '+' else source_size - start - size
                begin, end = bounds[name]
                new_size = end - begin
                fields[2] = str(forward - begin if strand == '+' else new_size - (forward - begin) - size)
                fields[5] = str(new_size)
                target.write(' '.join(fields) + '\n')
            elif not fields or fields[0] in ('a', '##maf') or line.startswith('#'):
                target.write(line + '\n')
    output = out / 'mini.hal'
    subprocess.run([tool('maf2hal'), str(rebased), str(output), '--refGenome', args.ref_genome], check=True)
    print(output)
    print('This is a rebased regional regression fixture, not a lossless crop of the original HAL.')


if __name__ == '__main__':
    main()
