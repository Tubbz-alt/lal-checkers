import lalcheck.irs.basic.tree as irt
from lalcheck.irs.basic.tools import PrettyPrinter
from lalcheck.irs.basic.purpose import ExistCheck
from lalcheck.digraph import Digraph
from lalcheck.constants import lits
from lalcheck import dot_printer

from collecting_semantics import collect_semantics

from xml.sax.saxutils import escape
from collections import defaultdict


def html_render_node(node):
    return escape(PrettyPrinter.pretty_print(node))


def build_resulting_graph(file_name, cfg, infeasibles):
    def trace_id(trace):
        return str(trace)

    paths = defaultdict(list)

    for trace, derefed, precise in infeasibles:
        for node in trace:
            paths[node].append((trace, derefed, precise))

    new_node_map = {
        node: Digraph.Node(
            node.name,
            ___orig=node,
            **{
                trace_id(trace): (derefed, precise)
                for trace, derefed, precise in paths[node]
            }
        )
        for node in cfg.nodes
    }

    res_graph = Digraph(
        [new_node_map[n]
         for n in cfg.nodes],

        [Digraph.Edge(new_node_map[e.frm], new_node_map[e.to])
         for e in cfg.edges]
    )

    def print_orig(orig):
        if orig.data.node is not None:
            return (
                '<i>{}</i>'.format(html_render_node(orig.data.node)),
            )
        return ()

    def print_path_to_infeasible_access(value):
        purpose, precise = value
        prefix = html_render_node(purpose.accessed_expr)
        qualifier = "" if precise else "potential "
        res_str = ("path to {}infeasible access {}.{} due to invalid "
                   "condition on discriminant {}.{}").format(
            qualifier,
            prefix,
            escape(purpose.field_name),
            prefix,
            escape(purpose.discr_name)
        )
        return (
            '<font color="{}">{}</font>'.format('red', res_str),
        )

    with open(file_name, 'w') as f:
        f.write(dot_printer.gen_dot(res_graph, [
            dot_printer.DataPrinter('___orig', print_orig)
        ] + [
            dot_printer.DataPrinter(
                trace_id(trace),
                print_path_to_infeasible_access
            )
            for trace, _, _ in infeasibles
        ]))


class AnalysisResult(object):
    """
    Contains the results of the null dereference checker.
    """
    def __init__(self, sem_analysis, infeasibles):
        self.sem_analysis = sem_analysis
        self.infeasibles = infeasibles

    def save_results_to_file(self, file_name):
        """
        Prints the resulting graph as a DOT file to the given file name.
        At each program point, displays where the node is part of a path
        that leads to a (potential) infeasible field access.
        """
        build_resulting_graph(
            file_name,
            self.sem_analysis.cfg,
            self.infeasibles
        )


def check_variants(prog, model, merge_pred_builder):

    analysis = collect_semantics(
        prog,
        model,
        merge_pred_builder
    )

    # Retrieve nodes in the CFG that correspond to program statements.
    nodes_with_ast = (
        (node, node.data.node)
        for node in analysis.cfg.nodes
        if 'node' in node.data
    )

    # Collect those that are assume statements and that have a 'purpose' tag
    # which indicates that this assume statement was added to check
    # existence of a field.
    exist_checks = (
        (node, ast_node.expr, ast_node.data.purpose)
        for node, ast_node in nodes_with_ast
        if isinstance(ast_node, irt.AssumeStmt)
        if ExistCheck.is_purpose_of(ast_node)
    )

    # Use the semantic analysis to evaluate at those program points the
    # corresponding expression being dereferenced.
    exist_check_values = (
        (frozenset(trace) | {node}, purpose, value)
        for node, expr, purpose in exist_checks
        for anc in analysis.cfg.ancestors(node)
        for trace, value in analysis.eval_at(anc, expr).iteritems()
    )

    # Finally, keep those that might be null.
    # Store the program trace, the dereferenced expression, and whether
    # the expression "might be null" or "is always null".
    infeasibles = [
        (trace, purpose, len(value) == 1)
        for trace, purpose, value in exist_check_values
        if lits.FALSE in value
    ]

    return AnalysisResult(analysis, infeasibles)