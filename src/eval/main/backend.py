import json
import datetime

__author__ = 'anushabala'
import hashlib
import sqlite3
import time
import numpy as np
import uuid as uuid_gen
from web_logger import WebLogger

m = hashlib.md5()
m.update("bot")


def current_timestamp_in_seconds():
    return int(time.mktime(datetime.datetime.now().timetuple()))


class EvalBackend(object):
    def __init__(self, params, evaluations):
        self.params = params
        self.conn = sqlite3.connect(params["db"]["location"])
        self.evaluations = evaluations
        self.logger = WebLogger.get_logger()

    def create_user_if_not_exists(self, userid):
        with self.conn:
            cursor = self.conn.cursor()
            try:
                cursor.execute('''INSERT OR IGNORE INTO active_user VALUES (?,?,?,?)''',
                               (userid, -1, "[]", current_timestamp_in_seconds()))
                self.conn.commit()
            except sqlite3.IntegrityError:
                print("WARNING: Rolled back transaction")

    def generate_code(self, userid):
        if not self.is_user_finished(userid):
            raise ValueError("User {:s} has not completed {:d} evaluations".format(userid,
                                                                                   self.params["evals_per_worker"]))
        code = "EC_" + uuid_gen.uuid4().hex
        self.logger.debug("User {:s} has completion code {:s}".format(userid, code))
        with self.conn:
            cursor = self.conn.cursor()
            try:
                cursor.execute('''INSERT INTO completion_code VALUES (?,?,?)''',
                               (userid, code, current_timestamp_in_seconds()))
                self.conn.commit()
                return code
            except sqlite3.IntegrityError:
                print("WARNING: Rolled back transaction")

    def is_user_finished(self, userid):
        with self.conn:
            cursor = self.conn.cursor()
            try:
                cursor.execute('''SELECT evaluated FROM active_user WHERE userid=?''', (userid, ))
                evaluated = cursor.fetchone()
                if evaluated is None:
                    self.logger.error("No entry found for user with ID {:s}. Creating user...".format(userid))
                    self.create_user_if_not_exists(userid)
                    return False
                evaluated = int(evaluated[0])
                return evaluated == self.params["evals_per_worker"]
            except sqlite3.IntegrityError:
                print("WARNING: Rolled back transaction")

    def is_user_starting(self, userid):
        with self.conn:
            cursor = self.conn.cursor()
            try:
                cursor.execute('''SELECT evaluated FROM active_user WHERE userid=?''', (userid,))
                evaluated = cursor.fetchone()
                if evaluated is None:
                    self.logger.error("No entry found for user with ID {:s}. Creating user...".format(userid))
                    self.create_user_if_not_exists(userid)
                    return True
                evaluated = int(evaluated[0])
                return evaluated == -1
            except sqlite3.IntegrityError:
                print("WARNING: Rolled back transaction")

    def get_task_num(self, userid):
        with self.conn:
            cursor = self.conn.cursor()
            try:
                cursor.execute('''SELECT evaluated FROM active_user WHERE userid=?''', (userid,))
                evaluated = cursor.fetchone()
                if evaluated is None:
                    self.logger.error("No entry found for user with ID {:s}. Creating user...".format(userid))
                    self.create_user_if_not_exists(userid)
                    return self.is_user_finished(userid)
                evaluated = int(evaluated[0])
                return evaluated + 1
            except sqlite3.IntegrityError:
                print("WARNING: Rolled back transaction")

    def start_user_session(self, userid):
        with self.conn:
            cursor = self.conn.cursor()
            try:
                cursor.execute('''UPDATE active_user SET evaluated=0 WHERE userid=?''', (userid,))
                self.conn.commit()
            except sqlite3.IntegrityError:
                print("WARNING: Rolled back transaction")

    def cleanup_active_evals(self):
        def _get_timed_out_users(uuid):
            timed_out = []
            cursor.execute('''SELECT userid, timestamp FROM assigned_eval WHERE id=?''', (uuid,))
            now = current_timestamp_in_seconds()
            for (assigned_userid, timestamp) in cursor.fetchall():
                timestamp = float(timestamp)
                if (now - timestamp) > self.params["eval_timeout"]:
                    timed_out.append(assigned_userid)
            return timed_out

        with self.conn:
            cursor = self.conn.cursor()
            try:
                cursor.execute('''SELECT id, active FROM evaluation''')
                results = cursor.fetchall()
                for result in results:
                    uuid, active = result
                    active = set(json.loads(active))
                    timed_out_users = _get_timed_out_users(uuid)
                    for u in timed_out_users:
                        if u in active:
                            self.logger.debug("Timing out evaluation {:s} for user {:s}".format(uuid, u))
                            active.remove(u)
                    active = json.dumps(list(active))
                    cursor.execute('''UPDATE evaluation SET active=? WHERE id=?''', (active, uuid))
                self.conn.commit()

            except sqlite3.IntegrityError:
                print("WARNING: Rolled back transaction")

    def get_next_evaluation(self, userid):
        evaluation = self.get_new_evaluation_context(userid)
        uuid = evaluation["exid"]
        self.logger.debug("Assigning example {:s} to user {:s}".format(uuid, userid))
        with self.conn:
            try:
                cursor = self.conn.cursor()
                cursor.execute('''SELECT active FROM evaluation WHERE id=?''', (uuid,))
                active = json.loads(cursor.fetchone()[0])
                active.append(userid)
                cursor.execute('''UPDATE evaluation SET active=? WHERE id=?''', (json.dumps(active), uuid))
                self.conn.commit()

                cursor.execute('''INSERT INTO assigned_eval VALUES (?,?,?)''', (
                    userid, uuid, current_timestamp_in_seconds()
                ))
                self.conn.commit()
                return evaluation
            except sqlite3.IntegrityError:
                print("WARNING: Rolled back transaction")

    def get_new_evaluation_context(self, userid):
        def _is_eval_pending(uuid):
            cursor.execute('''SELECT active, completed FROM evaluation WHERE id=?''', (uuid,))
            active, completed = cursor.fetchone()
            active = json.loads(active)
            completed = json.loads(completed)
            # Check if database has been updated since last time we checked (i.e. make sure evaluation context
            # is actually still pending)
            return len(active) + len(completed) < self.params["workers_per_eval"]

        def _select_pending_eval():
            try:
                cursor.execute('''SELECT * FROM evaluation''')
                evals = cursor.fetchall()
                cursor.execute('''SELECT skipped FROM active_user WHERE userid=?''', (userid,))
                skipped = cursor.fetchone()[0]
                skipped = set(json.loads(skipped))
                pending_evals = set()
                inactive_evals = set()
                all_evals = set()
                for (uuid, active, completed) in evals:
                    if uuid in skipped:
                        # If a user previously skipped an evaluation, don't show it to them again
                        continue
                    active = set(json.loads(active))
                    completed = set(json.loads(completed))
                    if userid in completed:
                        # Don't show a user the same eval twice
                        continue
                    all_evals.add(uuid)
                    if len(active) == 0 and len(completed) < self.params["workers_per_eval"]:
                        inactive_evals.add(uuid)
                    if len(completed) + len(active) < self.params["workers_per_eval"]:
                        pending_evals.add(uuid)

                if len(pending_evals) > 0:
                    uuid = np.random.choice(list(pending_evals))
                    if not _is_eval_pending(uuid):
                        # if evaluation is no longer pending, recurse and try to find another pending eval
                        self.logger.debug("Expired state: found {:s} is no longer pending while "
                                          "assigning to user {:s}. Recursing....".format(uuid, userid))
                        return _select_pending_eval()

                    self.logger.debug("Randomly selected pending eval {:s} for user {:s}".format(uuid, userid))
                    return self.evaluations[uuid]

                # If no evals are pending, try to select a random eval from the full set of evals (pick one that isn't
                # currently active)
                if len(inactive_evals) > 0:
                    uuid = np.random.choice(list(inactive_evals))
                    self.logger.debug("No pending evals: selecting currently inactive eval {:s}".format(uuid))
                else:
                    # otherwise, select any eval at random
                    uuid = np.random.choice(list(all_evals))
                    self.logger.debug("No pending evals: selecting one at random with ID {:s}".format(uuid))
                return self.evaluations[uuid]

            except sqlite3.IntegrityError:
                print("WARNING: Rolled back transaction")

        self.cleanup_active_evals()
        with self.conn:
            cursor = self.conn.cursor()
            return _select_pending_eval()

    def validate_response(self, eval_id, response):
        evaluated = self.evaluations[eval_id]
        candidates = evaluated['display_candidates']
        for (lbl, c) in zip(response, candidates):
            lbl = int(lbl)
            if c['true_label'] is not None:
                if c['true_label'] == -1 and lbl == 1:
                    return False
                if c['true_label'] == 1 and lbl != 1:
                    return False
        return True

    def skip(self, userid, eval_id):
        with self.conn:
            try:
                cursor = self.conn.cursor()
                self.logger.debug("User {:s} skipped evaluation {:s}".format(userid, eval_id))
                cursor.execute('''SELECT active FROM evaluation WHERE id=?''', (eval_id,))
                active = cursor.fetchone()[0]
                active = set(json.loads(active))
                if userid in active:
                    active.remove(userid)
                active = json.dumps(list(active))
                cursor.execute('''UPDATE evaluation SET active=? WHERE id=?''', (active, eval_id))
                self.conn.commit()

                # update evaluations skipped by this user
                cursor.execute('''SELECT skipped FROM active_user WHERE userid=?''', (userid, ))
                skipped = cursor.fetchone()[0]
                skipped = set(json.loads(skipped))
                skipped.add(eval_id)
                skipped = json.dumps(list(skipped))
                cursor.execute('''UPDATE active_user SET skipped=? WHERE userid=?''', (skipped, userid))
                self.conn.commit()

            except sqlite3.IntegrityError:
                print("WARNING: Rolled back transaction")

    def submit(self, userid, eval_id, response):
        # make sure that submit() is never called without validating the response
        assert self.validate_response(eval_id, response)

        with self.conn:
            try:
                cursor = self.conn.cursor()
                self.logger.debug("User {:s} submitted response for {:s}".format(userid, eval_id))
                cursor.execute('''INSERT INTO response VALUES (?,?,?)''',
                               (userid, eval_id, json.dumps(response)))
                cursor.execute('''UPDATE active_user SET evaluated = evaluated + 1 WHERE userid=?''', (userid,))
                self.conn.commit()
                cursor.execute('''SELECT active, completed FROM evaluation WHERE id=?''', (eval_id,))

                active, completed = cursor.fetchone()
                active = set(json.loads(active))
                if userid in active:
                    active.remove(userid)
                active = json.dumps(list(active))

                completed = json.loads(completed)
                completed.append(userid)
                completed = json.dumps(completed)

                cursor.execute('''UPDATE evaluation SET active=? WHERE id=?''', (active, eval_id))
                cursor.execute('''UPDATE evaluation SET completed=? WHERE id=?''', (completed, eval_id))

                self.conn.commit()

            except sqlite3.IntegrityError:
                print("WARNING: Rolled back transaction")

    def close(self):
        self.conn.close()
        self.conn = None

