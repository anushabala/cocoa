import os

__author__ = 'anushabala'
from argparse import ArgumentParser
import json
import numpy as np
from collections import Counter, defaultdict
import sqlite3
import csv


HIGH_ACCEPT_THRESHOLD = 1.0

def get_candidate_reusability_histogram():
    pass


def map_codes_to_turkers(turk_results_file):
    reader = csv.reader(open(turk_results_file, 'r'))
    header = reader.next()
    code_col = header.index('Answer.surveycode')
    workerid_col = header.index('WorkerId')
    codes_to_turkers = {}
    for row in reader:
        code = row[code_col]
        workerid = row[workerid_col]

        codes_to_turkers[code] = workerid

    return codes_to_turkers


def analyze_high_accept_users(turk_results, ratings_per_context=3):
    def _find_high_accept_users_for_context(exid):
        cursor.execute('''SELECT userid, response FROM response WHERE id=?''', (exid,))
        users = cursor.fetchall()
        r = []
        for userid, response in users[:ratings_per_context]:
            response = json.loads(response)
            response = [int(x) for x in response]
            count = response.count(1)
            if count >= len(response) * HIGH_ACCEPT_THRESHOLD:
                r.append(userid)
        return r

    def _get_code_for_user(userid):
        cursor.execute('''SELECT code FROM completion_code WHERE userid=?''', (userid,))
        code = cursor.fetchone()[0]
        return code

    high_accept_evals = 0.  # total number of evals with high acceptance %
    high_accept_contexts = {}  # total number of contexts where majority of evals have high acceptance %
    total_contexts = 0.
    total_evals = 0.  # total number of evals ( total # of contexts * ratings per context)

    # map from MTurk user --> number of HITs with high acceptace % (to identify misbehaving turkers)
    mturk_high_accept_users = defaultdict(list)
    codes_to_turkers = map_codes_to_turkers(turk_results)
    evals_per_turker = dict((workerid, len([x for x in codes_to_turkers.keys() if codes_to_turkers[x] == workerid]))
                            for workerid in codes_to_turkers.values())

    for context in eval_results:
        total_contexts += 1
        total_evals += ratings_per_context
        high_accept_users = _find_high_accept_users_for_context(context['exid'])
        high_accept_evals += len(high_accept_users)
        if len(high_accept_users) > ratings_per_context / 2.:
            # do a majority of the evals for context have high acceptance rate % ?
            high_accept_contexts[context['exid']] = len(high_accept_users)
        for uid in high_accept_users:
            code = _get_code_for_user(uid)
            if code in codes_to_turkers.keys():
                workerid = codes_to_turkers[code]
                mturk_high_accept_users[workerid].append(context['exid'])

    print 'Total # of contexts: {:.1f}'.format(total_contexts)
    print 'Total # of contexts with high acceptance %: {:.2f}\t({:.2f}%)'.format(
        len(high_accept_contexts.keys()),
        len(high_accept_contexts.keys()) * 100./total_contexts
    )

    print 'Total # of evaluations: {:.1f}'.format(total_evals)
    print 'Total # of evaluations with high acceptance %: {:.2f}\t({:.2f}%)'.format(
        high_accept_evals,
        high_accept_evals * 100./total_evals
    )

    sorted_turkers = sorted(mturk_high_accept_users.items(), key=lambda x: len(x[1]), reverse=True)
    print 'MTurk workers with most # of high-acceptance evals:'
    for (workerid, completed_evals) in sorted_turkers:
        num_evals = float(len(completed_evals))
        print '\t{:20s}:\t{:2.1f}/{:2.1f} evals\t{:s}'.format(workerid, num_evals,
                                                            evals_per_turker[workerid],
                                                            ", ".join(completed_evals))

    sorted_contexts = sorted(high_accept_contexts.items(), key=lambda x: x[1], reverse=True)
    print 'Contexts with high acceptance %:'
    print 'Context ID\t# evals'
    for (exid, num_evals) in sorted_contexts:
        print '{:s}\t{:5d}'.format(exid, num_evals)


def consolidate_ratings(raw_responses, ratings_per_eval=3):
    assert len(raw_responses) >= ratings_per_eval
    raw_responses = raw_responses[:ratings_per_eval]
    responses = zip(*raw_responses)
    return responses


def get_majority_ratings(consolidated_ratings, ratings_per_eval=3):
    top_counts = [Counter(r).most_common(1)[0] for r in consolidated_ratings]
    maj_ratings = []
    for (rating, count) in top_counts:
        if ratings_per_eval > 1 and count == 1:
            rating = 0
        maj_ratings.append(rating)
    return maj_ratings


def get_frac_accepted(ratings):
    count = sum([1 for x in ratings if x == 1])
    return float(count) / float(len(ratings))


def get_statistics(ratings_per_eval=3):
    avg_frac = 0.
    all_ratings = []
    for context in eval_results:
        ratings = consolidate_ratings(context['results'], ratings_per_eval)
        all_ratings.extend(ratings)
        maj_ratings = get_majority_ratings(ratings, ratings_per_eval)
        avg_frac += get_frac_accepted(maj_ratings)

    print "Avg acceptance rate: {:.2f}".format(avg_frac / len(eval_results))
    kappa = get_agreement_score(all_ratings)
    print "Agreement score: {:.2f}".format(kappa)


def get_agreement_score(ratings, ratings_per_eval=3):
    N = len(ratings)
    p = {
        -1: 0.,
        0: 0.,
        1: 0.
    }
    for candidate_ratings in ratings:
        for r in candidate_ratings:
            p[r] += 1
    p = dict((key, v / (N * ratings_per_eval)) for (key, v) in p.items())
    assert sum([p[key] for key in p.keys()]) == 1.

    P_i = []
    for candidate_ratings in ratings:
        nij = {
            -1: float(candidate_ratings.count(-1)),
            0: float(candidate_ratings.count(0)),
            1: float(candidate_ratings.count(1))
        }
        fac = (1.0 / (ratings_per_eval * (ratings_per_eval - 1))) * (sum([nij[j] * nij[j] for j in nij.keys()])
                                                                     - ratings_per_eval)
        P_i.append(fac)

    P_bar = np.mean(P_i)
    P_bar_e = sum([p[j] * p[j] for j in p.keys()])

    return (P_bar - P_bar_e) / (1 - P_bar_e)

if __name__ == "__main__":
    parser = ArgumentParser()
    parser.add_argument('--output', type=str, required=True, help='Path to directory containing website output')
    parser.add_argument('--turk-results', type=str, help='Path to results file from Mechanical Turk')
    parser.add_argument('--ratings-per-eval', type=int, default=3)
    args = parser.parse_args()

    results_path = os.path.join(args.output, 'results', 'eval_results.json')
    eval_results = json.load(open(results_path, 'r'))
    get_statistics(ratings_per_eval=args.ratings_per_eval)

    if args.turk_results is not None:
        db_path = os.path.join(args.output, 'web_state.db')
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        analyze_high_accept_users(args.turk_results, args.ratings_per_eval)