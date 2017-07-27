__author__ = 'anushabala'
import json
from src.model.negotiation.preprocess import markers as SpecialMarkers
from flask import Markup
import string
import numpy as np
import copy

START_THRESHOLD = 3
ACCEPT = 'ACCEPT'
REJECT = 'REJECT'
OFFER = 'OFFER'
QUIT = 'QUIT'
PRICE = 'PRICE'
START = 'START'



def preprocess_utterance(tokens):
    s = ""
    for (idx, token) in enumerate(tokens):
        if isinstance(token, str) or isinstance(token, unicode):
            if token == SpecialMarkers.EOS:
                if idx != len(tokens) - 1:
                    token = "<br>"
                else:
                    token = ""
            elif token == SpecialMarkers.GO_S or token == SpecialMarkers.GO_B:
                continue
            elif token == "_start_":
                token = "START"
            elif token.startswith("<") and token.endswith(">"):
                token = token.upper().strip("<").strip(">")

            if token not in string.punctuation and not token.startswith("'") and not "'" in token:
                s += " " + token
            else:
                s += token

        elif isinstance(token, list):
            if token[1][1] == 'price':
                s += " " + "PRICE"
            else:
                s += " " + token[0]
    s = s.strip()
    if s == "<br>":
        s = ""
    return Markup(s)


def preprocess_candidates(raw_candidates):
    candidates = []
    for c in raw_candidates:
        if 'response' not in c.keys():
            continue
        c['response'] = preprocess_utterance(c['response'])
        c['true_label'] = None
        candidates.append(c)
    return candidates


def preprocess_dialogue_context(e, params):
    prev_turns = e['prev_turns']
    prev_roles = e['prev_roles']
    if len(prev_turns) == 1:
        turn = prev_turns[0]
        u = preprocess_utterance(turn)
        if len(u) == 0:
            e['display_prev_turns'] = ['START']
        else:
            e['display_prev_turns'] = [ u ]
        e['display_prev_roles'] = prev_roles
    else:
        processed_turns = []
        processed_roles = e['prev_roles']
        for turn in prev_turns:
            u = preprocess_utterance(turn)
            processed_turns.append(u)

        if len(processed_turns[0]) == 0:
            processed_turns = processed_turns[1:]
            processed_roles = processed_roles[1:]

        if len(processed_turns) > params["max_prev_turns"]:
            curr_len = len(processed_turns)
            processed_turns = processed_turns[curr_len-params["max_prev_turns"]:]
            processed_roles = processed_roles[curr_len-params["max_prev_turns"]:]
        e['display_prev_turns'] = processed_turns
        e['display_prev_roles'] = processed_roles

    e['prev_turns'] = prev_turns
    e['prev_roles'] = prev_roles
    assert len(e['display_prev_turns']) == len(e['display_prev_roles'])

    return e


def skip_context(e):
    if 'exid' not in e or 'prev_roles' not in e:
        return True
    if e['candidates'] is None:
        return True
    return False


def is_dialogue_start(context):
    prev_turns = context['prev_turns']
    return len(prev_turns) <= START_THRESHOLD


def is_dialogue_end(context):
    candidates = context['display_candidates']
    for c in candidates:
        response = c['response']
        if ACCEPT not in response and REJECT not in response:
            return False
    # print 'End of dialogue context'
    # print 'Context ID: {:s}'.format(context['exid'])
    # for c in candidates:
    #     print '\t{:s}'.format(c['response'])
    # print ''

    return True


def find_negative_sanity_check_candidate(all_contexts, role, category, num_candidates=2):
    possible_targets = []
    for c in all_contexts:
        if c['role'] == role or c['kb']['item']['Category'] == category:
            continue
        if is_dialogue_start(c) or is_dialogue_end(c):
            # don't really need to check for dialogue end here since those contexts were already skipped
            continue

        target = c['display_target']
        if ACCEPT in target or REJECT in target or OFFER in target \
                or QUIT in target or PRICE in target or START in target:
            continue

        possible_targets.append(target)

    return np.random.choice(possible_targets, size=num_candidates, replace=False)


def shuffle_candidates(candidates):
    idxes = np.arange(len(candidates))
    np.random.shuffle(idxes)
    shuffled_candidates = []
    for i in idxes:
        shuffled_candidates.append(candidates[i])

    return shuffled_candidates


def add_sanity_checks(evals, num_neg_candidates=2):
    processed = []
    for e in evals:
        role = e['role']
        category = e['kb']['item']['Category']
        target = e['display_target']
        candidates = e['display_candidates']

        # print 'Context ID: {:s}'.format(e['exid'])
        # print 'Role: {:s}'.format(role)
        # print 'Category: {:s}'.format(category)
        # print 'Target: {:s}'.format(target)
        # print 'Previous turns:', e['prev_turns']
        # print 'Previous turns (display)', e['display_prev_turns']
        # add negative examples for sanity check
        neg_responses = find_negative_sanity_check_candidate(evals, role, category, num_candidates=num_neg_candidates)
        for response in neg_responses:
            candidate = {
                'response': response,
                'true_label': -1
            }
            candidates.append(candidate)
            # print 'Negative candidate: ', candidate

        # add target as positive sanity check
        candidate = {
            'response': target,
            'true_label': 1
        }
        candidates.append(candidate)

        # print 'Positive candidate: ', candidate

        # shuffle candidates for each context
        candidates = shuffle_candidates(candidates)
        e['display_candidates'] = candidates

        # print ''
        processed.append(e)

    return processed


def process_evaluations(eval_file, params):
    raw_evals = json.load(open(eval_file, 'r'))
    processed = []

    for e in raw_evals:
        if skip_context(e):
            continue

        candidates = copy.deepcopy(e['candidates'])
        e['display_candidates'] = preprocess_candidates(e['candidates'])
        e['candidates'] = candidates
        if is_dialogue_end(e):
            continue

        e = preprocess_dialogue_context(e, params)
        e['display_target'] = preprocess_utterance(e['target'])
        processed.append(e)

    processed = add_sanity_checks(processed)

    return processed
