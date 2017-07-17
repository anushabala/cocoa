__author__ = 'anushabala'
from argparse import ArgumentParser
import json
from collections import Counter


def get_candidate_reusability_histogram():
    pass


def consolidate_ratings(raw_responses):
    responses = zip(*raw_responses)
    maj_ratings = [Counter(r).most_common(1)[0][0] for r in responses]
    return maj_ratings


def get_frac_accepted(ratings):
    count = sum([1 for x in ratings if x == 1])
    return float(count)/float(len(ratings))


def process_results():
    avg_frac = 0.
    for context in eval_results:
        ratings = consolidate_ratings(context['results'])
        avg_frac += get_frac_accepted(ratings)
    print "Avg acceptance rate: {:.2f}".format(avg_frac/len(eval_results))

if __name__ == "__main__":
    parser = ArgumentParser()
    parser.add_argument('--results', type=str, required=True, help='Path to candidate evaluation results file (JSON)')
    args = parser.parse_args()

    eval_results = json.load(open(args.results, 'r'))
    process_results()
