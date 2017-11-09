"""
Provides tools for using the Basic IR.
"""

from lalcheck.utils import KeyCounter, Bunch
from lalcheck.digraph import Digraph
from lalcheck.domain_ops import boolean_ops
import visitors

from funcy.calc import memoize


class CFGBuilder(visitors.ImplicitVisitor):
    """
    A visitor that can be used to build the control-flow graph of the given
    program as an instance of a Digraph. Nodes of the resulting control-flow
    graph will have the following data attached to it:
    - 'widening_point': "True" iff the node can be used as a widening point.
    - 'node': the corresponding IR node which this CFG node was built from,
      or None.
    """
    def __init__(self):
        self.nodes = None
        self.edges = None
        self.start_node = None
        self.key_counter = KeyCounter()

    def fresh(self, name):
        return "{}{}".format(name, self.key_counter.get_incr(name))

    def visit_program(self, prgm):
        self.nodes = []
        self.edges = []

        start = self.build_node("start")
        self.visit_stmts(prgm.stmts, start)

        return Digraph(self.nodes + [start], self.edges)

    def visit_split(self, splitstmt, start):
        end_fst = self.visit_stmts(splitstmt.fst_stmts, start)
        end_snd = self.visit_stmts(splitstmt.snd_stmts, start)

        join = self.build_node("split_join")
        self.register_and_link([end_fst, end_snd], join)

        return join

    def visit_loop(self, loopstmt, start):
        loop_start = self.build_node("loop_start", is_widening_point=True)

        end = self.visit_stmts(loopstmt.stmts, loop_start)
        join = self.build_node("loop_join")

        self.register_and_link([start, end], loop_start)
        self.register_and_link([loop_start], join)
        return join

    def visit_assign(self, assign, start):
        n = self.build_node("assign", orig_node=assign)
        self.register_and_link([start], n)
        return n

    def visit_read(self, read, start):
        n = self.build_node("read", orig_node=read)
        self.register_and_link([start], n)
        return n

    def visit_use(self, use, start):
        n = self.build_node("use", orig_node=use)
        self.register_and_link([start], n)
        return n

    def visit_assume(self, assume, start):
        n = self.build_node("assume", orig_node=assume)
        self.register_and_link([start], n)
        return n

    def visit_stmts(self, stmts, cur):
        for stmt in stmts:
            cur = stmt.visit(self, cur)
        return cur

    def build_node(self, name, is_widening_point=False, orig_node=None):
        return Digraph.Node(
            name=self.fresh(name),
            is_widening_point=is_widening_point,
            node=orig_node
        )

    def register_and_link(self, froms, new_node):
        self.nodes.append(new_node)
        for f in froms:
            self.edges.append(Digraph.Edge(f, new_node))


class Models(visitors.Visitor):
    """
    A Models object is constructed from a typer and a type interpreter.
    With these two components, it can derive the interpretation of a type
    from the type hint provided by the frontend.

    It can then be used to build models of the given programs. A model
    can be queried for information about a node of a program. Such information
    includes the domain used to represent the value computed by that node (if
    relevant), how an operation must be interpreted (i.e. a binary addition),
    etc.
    """
    def __init__(self, typer, type_interpreter):
        """
        Creates a Models object from a typer (that maps type hints to types)
        and a type interpreter (that maps types to interpretations).
        """
        self.typer = typer
        self.type_interpreter = type_interpreter

    @memoize
    def _hint_to_type(self, hint):
        # Memoization is required to get the same type instances
        # for each identical hint
        return self.typer.from_hint(hint)

    @memoize
    def _type_to_interp(self, tpe):
        # Memoization is required to get the same interpretations
        # for each identical type
        return self.type_interpreter.from_type(tpe)

    def _typeable_to_interp(self, node):
        return self._type_to_interp(self._hint_to_type(node.data.type_hint))

    def visit_unexpr(self, unexpr, node_domains, defs, inv_defs, builders):
        dom = node_domains[unexpr]
        expr_dom = node_domains[unexpr.expr]
        tpe = (expr_dom, dom)

        return Bunch(
            domain=dom,
            definition=defs(unexpr.un_op.sym, tpe),
            inverse=inv_defs(unexpr.un_op.sym, tpe)
        )

    def visit_binexpr(self, binexpr, node_domains, defs, inv_defs, builders):
        dom = node_domains[binexpr]
        lhs_dom = node_domains[binexpr.lhs]
        rhs_dom = node_domains[binexpr.rhs]
        tpe = (lhs_dom, rhs_dom, dom)

        return Bunch(
            domain=dom,
            definition=defs(binexpr.bin_op.sym, tpe),
            inverse=inv_defs(binexpr.bin_op.sym, tpe)
        )

    def visit_ident(self, ident, node_domains, defs, inv_defs, builders):
        return Bunch(
            domain=node_domains[ident]
        )

    def visit_lit(self, lit, node_domains, defs, inv_defs, builders):
        dom = node_domains[lit]
        return Bunch(
            domain=dom,
            builder=builders[dom]
        )

    @staticmethod
    def _has_type_hint(node):
        return 'type_hint' in node.data

    @staticmethod
    def _aggregate_provider(providers):
        def f(name, signature):
            for provider in providers:
                definition = provider(name, signature)
                if definition:
                    return definition
            raise LookupError("No provider for '{}' {}".format(
                name, signature
            ))

        return f

    def of(self, *programs):
        """
        Returns a model of the given programs, that is, a dictionary that has
        an entry for any node in the given programs that has a type hint.
        This entry associates to the node valuable information, such as the
        domain used to represent the value it computes, the referenced
        definition if any, etc.
        """
        model = {}
        node_domains = {}
        def_providers = set()
        inv_def_providers = set()
        builders = {}

        for prog in programs:
            typeable = visitors.findall(prog, self._has_type_hint)

            for node in typeable:
                interp = self._typeable_to_interp(node)
                domain, domain_defs, domain_inv_defs, domain_builder = interp

                node_domains[node] = domain
                def_providers.add(domain_defs)
                inv_def_providers.add(domain_inv_defs)
                builders[domain] = domain_builder

        for node in node_domains.keys():
            model[node] = node.visit(
                self,
                node_domains,
                Models._aggregate_provider(def_providers),
                Models._aggregate_provider(inv_def_providers),
                builders
            )

        return model


class ExprEvaluator(visitors.Visitor):
    """
    Can be used to evaluate expressions in the Basic IR.
    """
    def __init__(self, model):
        """
        Constructs an ExprEvaluator given a model. The expression evaluator
        must only be invoked to evaluate expression which nodes have a meaning
        in the given model.
        """
        self.model = model

    def eval(self, expr, env):
        """
        Given an environment (a map from Identifier to value), evaluates
        the given expression.
        """
        return expr.visit(self, env)

    def visit_ident(self, ident, env):
        return env[ident]

    def visit_binexpr(self, binexpr, env):
        lhs = binexpr.lhs.visit(self, env)
        rhs = binexpr.rhs.visit(self, env)
        return self.model[binexpr].definition(lhs, rhs)

    def visit_unexpr(self, unexpr, env):
        expr = unexpr.expr.visit(self, env)
        return self.model[unexpr].definition(expr)

    def visit_lit(self, lit, env):
        return self.model[lit].builder(lit.val)


class ExprSolver(visitors.Visitor):
    """
    Can be used to solve expressions in the Basic IR.
    """
    def __init__(self, model):
        """
        Constructs an ExprSolver given a model. The expression solver must
        only be invoked to solve expressions which nodes have a meaning in
        the given model.
        """
        self.model = model
        self.eval = ExprEvaluator(model).eval

    def solve(self, expr, env):
        """
        Given an environment (a map from Identifier to value), solves
        the given predicate expression (i.e. of boolean type), that is,
        constructs a new environment for which the given expression evaluates
        to true.

        The new environment may in fact not evaluate to True because it is an
        over-approximation of the optimal solution. However, it should
        never constructs a solution that does not contain the optimal one,
        thus making it sound for abstract interpretation.
        """
        new_env = env.copy()
        if not expr.visit(self, new_env, boolean_ops.true):
            return {}
        return new_env

    def visit_ident(self, ident, env, expected):
        dom = self.model[ident].domain
        env[ident] = dom.meet(env[ident], expected)
        return True

    def visit_binexpr(self, binexpr, env, expected):
        lhs_val = self.eval(binexpr.lhs, env)
        rhs_val = self.eval(binexpr.rhs, env)
        inv_res = self.model[binexpr].inverse(
            expected, lhs_val, rhs_val
        )

        if inv_res is None:
            return False

        expected_lhs, expected_rhs = inv_res
        return (binexpr.lhs.visit(self, env, expected_lhs) and
                binexpr.rhs.visit(self, env, expected_rhs))

    def visit_unexpr(self, unexpr, env, expected):
        expr_val = self.eval(unexpr.expr, env)
        expected_expr = self.model[unexpr].inverse(expected, expr_val)
        if expected_expr is None:
            return False
        return unexpr.expr.visit(self, env, expected_expr)

    def visit_lit(self, lit, env, expected):
        lit_dom = self.model[lit].domain
        lit_val = self.eval(lit, env)
        return not lit_dom.is_empty(lit_dom.meet(expected, lit_val))
