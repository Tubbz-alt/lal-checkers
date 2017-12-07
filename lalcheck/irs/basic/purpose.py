class Purpose(object):
    """
    A purpose object is to be attached to a node of the program in order
    to provide more involved information about it. This information can
    be used by checkers to provide more precise results.
    """
    def __str__(self):
        return "{}{}".format(
            self.__class__.__name__,
            str(self.__dict__)
        )

    @classmethod
    def is_purpose_of(cls, node):
        """
        :param tree.Node node: The Basic IR Node.
        :return: True if the node has a purpose of this type.
        """
        if 'purpose' in node.data:
            return isinstance(node.data.purpose, cls)

        return False


class DerefCheck(Purpose):
    """
    Attached to a node that was created for the purpose of checking a
    dereference.
    """
    def __init__(self, derefed_expr):
        """
        :param tree.Expr derefed_expr: The derefed expression.
        """
        self.expr = derefed_expr


class SyntheticVariable(Purpose):
    """
    Attached to an identifier that was created synthetically. (For example,
    to hold a temporary value.)
    """
    pass


class FieldAssignment(Purpose):
    """
    Attached to a function call that is the result of the translation of a
    field assignment. (p.x = 2 ==> p = Updated_I(p, 2))
    """
    def __init__(self, field_index, field_type_hint):
        """
        :param int field_index: The index of the updated field
        :param lal.AdaNode field_type_hint: The type of the updated field
        """
        self.field_index = field_index
        self.field_type_hint = field_type_hint
