from argparse import ArgumentParser
import numpy as np
import json
from src.eval import process_evals as preprocessor

__author__ = 'anushabala'


def get_filtered_contexts(eval_file):
    all_contexts = json.load(open(eval_file, 'r'))
    params = { "max_prev_turns": 5 }
    print 'Filtering contexts..'
    filtered_contexts = preprocessor.process_evaluations(eval_file, params)
    filtered_context_ids = set([x['exid'] for x in filtered_contexts])
    print "After filtering: {:d} contexts".format(len(filtered_context_ids))
    all_contexts = [x for x in all_contexts if x['exid'] in filtered_context_ids]
    return all_contexts


def skip_done_contexts(all_contexts, ignore_paths):
    ignore_ids = set()
    for path in ignore_paths:
        done_contexts = json.load(open(path, 'r'))
        ignore_ids.update([x['exid'] for x in done_contexts])

    print "Skipping {:d} already evaluated contexts".format(len(ignore_ids))
    all_contexts = [x for x in all_contexts if x['exid'] not in ignore_ids]
    return all_contexts


def sample_contexts(all_contexts, n):
    idxes = np.arange(len(all_contexts))
    idxes = np.random.choice(idxes, size=n, replace=False)
    sampled = [all_contexts[i] for i in idxes]

    return sampled

if __name__ == '__main__':
    parser = ArgumentParser()
    parser.add_argument('--candidates-file', type=str, required=True, help='File containing contexts to sample from')
    parser.add_argument('--ignore', nargs='*', help='Files containing already evaluated contexts to be skipped')
    parser.add_argument('--n', type=int, default=500, help='Number of contexts to sample')
    parser.add_argument('--output', type=str, required=True, help='Path to write new contexts to')

    args = parser.parse_args()

    contexts = get_filtered_contexts(args.candidates_file)
    if len(args.ignore) > 0:
        contexts = skip_done_contexts(contexts, args.ignore)

    sampled_contexts = sample_contexts(contexts, args.n)
    print "Sampled {:d} contexts".format(len(sampled_contexts))

    json.dump(sampled_contexts, open(args.output, 'w'))



