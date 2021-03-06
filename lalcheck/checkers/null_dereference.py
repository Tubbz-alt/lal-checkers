from collections import defaultdict
from xml.sax.saxutils import escape

from lalcheck.ai.irs.basic.analyses import abstract_semantics
from lalcheck.ai.irs.basic.purpose import DerefCheck
from lalcheck.ai.irs.basic.tools import PrettyPrinter
from lalcheck.ai.utils import dataclass
from lalcheck.checkers.support.checker import (
    AbstractSemanticsChecker, DiagnosticPosition,
    abstract_semantics_checker_keepalive
)
from lalcheck.checkers.support.components import AbstractSemantics
from lalcheck.checkers.support.kinds import AccessCheck
from lalcheck.checkers.support.utils import (
    format_text_for_output, collect_assumes_with_purpose, eval_expr_at
)
from lalcheck.tools import dot_printer
from lalcheck.tools.digraph import Digraph

from lalcheck.tools.scheduler import Task, Requirement


def html_render_node(node):
    return escape(PrettyPrinter.pretty_print(node))


def build_resulting_graph(file_name, cfg, null_derefs):
    def trace_id(trace):
        return str(trace)

    paths = defaultdict(list)

    for trace, derefed, precise in null_derefs:
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

    def print_path_to_null_deref(value):
        derefed, precise = value
        qualifier = "" if precise else "potential "
        res_str = "path to {}null dereference of {}".format(
            qualifier, html_render_node(derefed)
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
                print_path_to_null_deref
            )
            for trace, _, _ in null_derefs
        ]))


class Results(AbstractSemanticsChecker.Results):
    """
    Contains the results of the null dereference checker.
    """
    def __init__(self, sem_analysis, null_derefs):
        super(Results, self).__init__(sem_analysis, null_derefs)

    def save_results_to_file(self, file_name):
        """
        Prints the resulting graph as a DOT file to the given file name.
        At each program point, displays where the node is part of a path
        that leads to a (potential) null dereference.
        """
        build_resulting_graph(
            file_name,
            self.analysis_results.cfg,
            self.diagnostics
        )

    @classmethod
    def diag_report(cls, diag):
        trace, derefed, precise = diag

        if ('orig_node' in derefed.data
                and derefed.data.orig_node is not None):
            if precise:
                frmt = "null dereference of '{}'"
            else:
                frmt = "(potential) null dereference of '{}'"

            return (
                DiagnosticPosition.from_node(derefed.data.orig_node),
                frmt.format(
                    format_text_for_output(derefed.data.orig_node.text)
                ),
                AccessCheck,
                cls.gravity(precise)
            )


def check_derefs(prog, model, merge_pred_builder):
    analysis = abstract_semantics.compute_semantics(
        prog,
        model,
        merge_pred_builder
    )

    return find_null_derefs(analysis)


def find_null_derefs(analysis):
    abstract_semantics_checker_keepalive()

    # Collect assume statements that have a DerefCheck purpose.
    deref_checks = collect_assumes_with_purpose(analysis.cfg, DerefCheck)

    # Use the semantic analysis to evaluate at those program points the
    # corresponding expression being dereferenced.
    derefed_values = [
        (trace, purpose, value)
        for node, check_expr, purpose in deref_checks
        for trace, value in eval_expr_at(analysis, node, check_expr)
    ]

    # Finally, keep those that might be null.
    # Store the program trace, the dereferenced expression, and whether
    # the expression "might be null" or "is always null".
    null_derefs = [
        (trace, purpose.expr, len(value) == 1)
        for trace, purpose, value in derefed_values
        if False in value
    ]

    return Results(analysis, null_derefs)


@Requirement.as_requirement
def NullDerefs(provider_config, model_config, files):
    return [NullDerefFinder(
        provider_config, model_config, files
    )]


@dataclass
class NullDerefFinder(Task):
    def __init__(self, provider_config, model_config, files):
        self.provider_config = provider_config
        self.model_config = model_config
        self.files = files

    def requires(self):
        return {
            'sem_{}'.format(i): AbstractSemantics(
                self.provider_config,
                self.model_config,
                self.files,
                f
            )
            for i, f in enumerate(self.files)
        }

    def provides(self):
        return {
            'res': NullDerefs(
                self.provider_config,
                self.model_config,
                self.files
            )
        }

    def run(self, **sems):
        return {
            'res': [
                find_null_derefs(analysis)
                for sem in sems.values()
                for analysis in sem
            ]
        }


class DerefChecker(AbstractSemanticsChecker):
    @classmethod
    def name(cls):
        return "null_dereference"

    @classmethod
    def description(cls):
        return ("Reports a message of kind '{}' when attempting to dereference"
                " a reference that could be null.").format(AccessCheck.name())

    @classmethod
    def kinds(cls):
        return [AccessCheck]

    @classmethod
    def create_requirement(cls, *args, **kwargs):
        return cls.requirement_creator(NullDerefs)(*args, **kwargs)


checker = DerefChecker


if __name__ == "__main__":
    print("Please run this checker through the run-checkers.py script")
