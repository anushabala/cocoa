from collections import defaultdict
import json
from argparse import ArgumentParser

__author__ = 'anushabala'


def combine_results(paths, output):
    all_results = defaultdict(list)
    all_contexts = {}
    for p in paths:
        contexts = json.load(open(p, 'r'))
        for c in contexts:
            exid = c['exid']
            results = c['results']

            c.pop('results')
            if exid not in all_contexts:
                all_contexts[exid] = c
            # sanity check to ensure that the results being combined are for the same context
            assert all_contexts[exid] == c

            all_results[exid].extend(results)

    output_contexts = []
    for exid in all_contexts.keys():
        c = all_contexts[exid]
        c['results'] = all_results[exid]
        print 'Got {:d} total results for example {:s}'.format(len(all_results[exid]), exid)
        output_contexts.append(c)

    json.dump(output_contexts, open(output, 'w'))

if __name__ == '__main__':
    parser = ArgumentParser()
    parser.add_argument('--paths', required=True, nargs='+', help='Paths of results files to combine')
    parser.add_argument('--output', required=True, help='Path to write combined results to')
    args = parser.parse_args()

    combine_results(args.paths, args.output)
