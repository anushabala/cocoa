import json
import os

__author__ = 'anushabala'
from src.scripts.html_visualizer import NegotiationHTMLVisualizer
from argparse import ArgumentParser
from get_evaluation_statistics import consolidate_ratings


class EvaluationVisualizer(object):
    @classmethod
    def aggregate_results(cls, results, img_path=None, css_file=None):
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
            html.extend(cls.visualize_single_result(context, img_path))
            html.append('<hr>')

        html.append('</body></html>')

        return html

    @classmethod
    def visualize_single_result(cls, context, img_path=None):
        html_lines = ['<div class="exTitle"><h2>Example ID: %s </h2></div>' % context['exid']]
        html_lines.extend(cls.render_eval_scenario(context['kb'], img_path))
        html_lines.extend(cls.render_context(context))
        html_lines.extend(cls.render_results(context))
        return html_lines

    @classmethod
    def visualize_results(cls, results, html_output, img_path=None, css_file=None):
        if not os.path.exists(os.path.dirname(html_output)) and len(os.path.dirname(html_output)) > 0:
            os.makedirs(os.path.dirname(html_output))

        html_lines = cls.aggregate_results(results, img_path=img_path, css_file=css_file)

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
                  '<td class=\"agent\">%s</td>\
                    <td class=\"message\">%s</td>\
                   </tr>' % (role, role.title(), turn)

            chat_html.append(row)

        chat_html.extend(['</table>', '</div>'])

        return chat_html

    @classmethod
    def render_results(cls, context):
        candidates = context['candidates']
        responses = consolidate_ratings(context['results'])
        role = context['role']

        html = ["<div class=\"candidates\">"]
        # Post
        html.append("<div class=\"divTitle\">Candidates (%s)</div>" % role)
        sensible = []
        not_sensible = []
        ambiguous = []
        for c, r in zip(candidates, responses):
            row = '<tr class=\"%s\"><td>%s</td></tr>'
            if r == -1:
                row_color = 'not_sensible'
                not_sensible.append(row % (row_color, c['response']))
            elif r == 1:
                row_color = 'sensible'
                sensible.append(row % (row_color, c['response']))
            else:
                row_color = 'ambiguous'
                ambiguous.append(row % (row_color, c['response']))

        for group in [sensible, ambiguous, not_sensible]:
            html.append("<table>")
            for row in group:
                html.append(row)
            html.append("</table>")
            html.append("<br>")




        html.append("</table>")
        html.append("</div>")
        return html


if __name__ == "__main__":
    parser = ArgumentParser()
    parser.add_argument('--results', type=str, required=True, help='Path to candidate evaluation results file (JSON)')
    parser.add_argument('--html-output', type=str, required=True, help='Name of file to write HTML output to')
    parser.add_argument('--css-file', default='chat_viewer/css/eval.css', help='css for tables/scenarios and chat logs')
    parser.add_argument('--img-path', help='path to images')
    args = parser.parse_args()

    results = json.load(open(args.results, 'r'))
    EvaluationVisualizer.visualize_results(results, args.html_output, img_path=args.img_path, css_file=args.css_file)