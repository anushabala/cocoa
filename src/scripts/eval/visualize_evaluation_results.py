import json
import os

__author__ = 'anushabala'
from src.scripts.html_visualizer import NegotiationHTMLVisualizer
from argparse import ArgumentParser
from get_evaluation_statistics import consolidate_ratings, get_majority_ratings


class EvaluationVisualizer(object):
    @classmethod
    def aggregate_results(cls, results, img_path=None, css_file=None, ratings_per_eval=3):
        html = ['<!DOCTYPE html>','<html>',
                '<head><style>table{ table-layout: fixed; width: 600px; border-collapse: collapse; } '
                'tr:nth-child(n) { border: solid thin;}</style></head><body>']
        # inline css
        if css_file:
            html.append('<style>')
            with open(css_file, 'r') as fin:
                for line in fin:
                    html.append(line.strip())
            html.append('</style>')

        for context in results:
            html.extend(cls.visualize_single_result(context, img_path, ratings_per_eval=ratings_per_eval))
            html.append('<hr>')

        html.append('</body></html>')

        return html

    @classmethod
    def visualize_single_result(cls, context, img_path=None, ratings_per_eval=3):
        html_lines = ['<div class="exTitle"><h2>Example ID: %s </h2></div>' % context['exid']]
        html_lines.extend(cls.render_eval_scenario(context['kb'], img_path))
        html_lines.extend(cls.render_context(context))
        html_lines.extend(cls.render_results(context, ratings_per_eval))
        return html_lines

    @classmethod
    def visualize_results(cls, results, html_output, img_path=None, css_file=None, ratings_per_eval=3):
        if not os.path.exists(os.path.dirname(html_output)) and len(os.path.dirname(html_output)) > 0:
            os.makedirs(os.path.dirname(html_output))

        html_lines = cls.aggregate_results(results, img_path=img_path, css_file=css_file,
                                           ratings_per_eval=ratings_per_eval)

        outfile = open(html_output, 'w')
        for line in html_lines:
            outfile.write(line.encode('utf8')+"\n")
        outfile.close()

    @classmethod
    def render_eval_scenario(cls, kb, img_path=None):
        html = ["<div class=\"scenario\">"]
        # Post
        html.append("<p><b>%s ($%d)</b></p>" % (kb['item']['Title'], kb['item']['Price']))
        html.append("<p>%s</p>" % '<br>'.join(kb['item']['Description']))
        if img_path and len(kb['item']['Images']) > 0:
            html.append("<p><img src=%s></p>" % os.path.join(img_path, kb['item']['Images'][0]))

        html.append("</div>")
        return html

    @classmethod
    def render_context(cls, context):
        prev_turns = context['prev_turns']
        prev_roles = context['prev_roles']

        chat_html= ['<div class=\"chatLog\">',
                    '<div class=\"divTitle\"> Chat Log: %s </div>' % (context['uuid']),
                    '<table class=\"chat\">']

        for (turn, role) in zip(prev_turns, prev_roles):
            # TODO: factor render_event
            row = '<tr class=\"%s\">' \
                  '<td class=\"agent role\">%s</td>\
                    <td class=\"message\">%s</td>\
                   </tr>' % (role, role.title(), turn)

            chat_html.append(row)

        chat_html.extend(['</table>', '</div>'])

        return chat_html

    @classmethod
    def render_results(cls, context, ratings_per_eval=3):
        candidates = context['candidates']
        responses = consolidate_ratings(context['results'], ratings_per_eval)
        maj_ratings = get_majority_ratings(responses, ratings_per_eval)
        role = context['role']

        html = ["<div class=\"candidates\">"]
        html.append("<div class=\"divTitle\">Candidates (%s)</div>" % role)
        sensible = []
        not_sensible = []
        ambiguous = []

        # Create header
        header = ['<tr><th class="candidate_col">Candidate</th>']
        for i in xrange(1, ratings_per_eval + 1):
            header.append('<th>R{:d}</th>'.format(i))
        header.append('</tr>')

        for (idx, c) in enumerate(candidates):
            row = ['<tr>']
            all_ratings = responses[idx]
            best_r = maj_ratings[idx]

            rating_cols = []
            for r in all_ratings:
                col = '<td class=\"{:s}\">  </td>'
                if r == -1:
                    rating_cols.append(col.format('not_sensible'))
                elif r == 1:
                    rating_cols.append(col.format('sensible'))
                else:
                    rating_cols.append(col.format('ambiguous'))

            candidate_col = '<td class=\"{:s} candidate_col"\">{:s}</td>'

            if best_r == -1:
                col_color = 'maj_not_sensible'
                group = not_sensible
            elif best_r == 1:
                col_color = 'maj_sensible'
                group = sensible
            else:
                col_color = 'maj_ambiguous'
                group = ambiguous

            row.append(candidate_col.format(col_color, c['response']))
            row.extend(rating_cols)
            row.append('</tr>')
            group.extend(row)

        for group in [sensible, ambiguous, not_sensible]:
            if len(group) > 0:
                html.append("<table>")
                html.extend(header)
                for row in group:
                    html.append(row)
                html.append("</table>")
                html.append("<br>")

        html.append("</div>")
        return html


if __name__ == "__main__":
    parser = ArgumentParser()
    parser.add_argument('--results', type=str, required=True, help='Path to candidate evaluation results file (JSON)')
    parser.add_argument('--html-output', type=str, required=True, help='Name of file to write HTML output to')
    parser.add_argument('--css-file', default='chat_viewer/css/eval.css', help='css for tables/scenarios and chat logs')
    parser.add_argument('--img-path', help='path to images')
    parser.add_argument('--ratings-per-eval', type=int, default=3, help='Number of ratings per evaluation')
    args = parser.parse_args()

    results = json.load(open(args.results, 'r'))
    EvaluationVisualizer.visualize_results(results, args.html_output, img_path=args.img_path, css_file=args.css_file,
                                           ratings_per_eval=args.ratings_per_eval)
