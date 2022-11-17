import radb
import radb.ast
import radb.parse
from sqlparse import sql

cond_dict = {
    "=": 43,
    "and": 11
}

tree_types_dict = {
    "relation": 0,
    "selection": 1,
    "projection": 2,
    "cross": 3
}


class Tree:
    def __init__(self, root, type):
        self.left = None
        self.right = None
        self.parent = None
        self.root = root
        self.type = type

    def insert_node(self, new_node, type):
        if type is tree_types_dict.__getitem__("relation"):
            self.__insert_relations(new_node, type)
        else:
            global ra_tree
            left = self
            __new_tree = Tree(new_node, type)

            left.parent = __new_tree
            __new_tree.left = left

            ra_tree = __new_tree

    def get_last_left_child(self):
        if self.left is not None:
            return self.left.get_last_left_child()

        return self

    def create_ra_from_ra_tree(self, last_child):
        if last_child.parent is None:
            return last_child.root

        parent = last_child.parent
        if last_child.type is tree_types_dict.__getitem__("relation"):
            return self.__create_relation_parts(parent, last_child)

        elif last_child.type is tree_types_dict.__getitem__("selection"):
            return self.__create_selection_parts(parent, last_child)

        elif last_child.type is tree_types_dict.__getitem__("projection"):
            return self.__create_projection_parts(parent, last_child)

    def __insert_relations(self, new_node, type):
        if self.type is tree_types_dict.__getitem__("relation"):
            self.__insert_cartesian(new_node, type)
        elif self.type is tree_types_dict.__getitem__("cross"):
            if self.right is None:
                self.right = Tree(new_node, type)
                self.right.parent = self
            else:
                self.__insert_cartesian(new_node, type)

    def __insert_cartesian(self, new_node, type):
        global ra_tree

        left_node = self
        right_node = Tree(new_node, type)

        new_tree = Tree("X", tree_types_dict.__getitem__("cross"))
        left_node.parent = new_tree
        right_node.parent = new_tree

        new_tree.left = left_node
        new_tree.right = right_node

        ra_tree = new_tree

    def __create_selection_parts(self, parent, last_child):
        if parent.type is tree_types_dict.__getitem__("selection"):
            __selection = radb.ast.Select(cond=parent.root, input=last_child.root)
            parent.root = __selection
            return self.create_ra_from_ra_tree(parent)

        if parent.type is tree_types_dict.__getitem__("projection"):
            return self.__create_projection_parts(parent, last_child)

    def __create_projection_parts(self, parent, last_child):
        if parent.parent is None:
            if isinstance(parent.root, list):
                return radb.ast.Project(parent.root, last_child.root)
            else:
                return radb.ast.Project([radb.ast.AttrRef(rel=None, name=parent.root)], last_child.root)

        if parent.parent.type is tree_types_dict.__getitem__("projection"):
            parent.parent.root = [radb.ast.AttrRef(rel=None, name=parent.root),
                                  radb.ast.AttrRef(rel=None, name=parent.parent.root)]
            parent.root = last_child.root
            parent.type = last_child.type
            return self.create_ra_from_ra_tree(parent)

    def __create_relation_parts(self, parent, last_child):
        if parent.type is tree_types_dict.__getitem__("cross"):
            parent.root = radb.ast.Cross(parent.left.root, parent.right.root)
            parent.type = tree_types_dict.__getitem__("relation")
            return self.create_ra_from_ra_tree(parent)

        elif parent.type is tree_types_dict.__getitem__("selection"):
            if parent.parent is not None and parent.parent.type is tree_types_dict.__getitem__("selection"):
                parent.parent.root = radb.ast.ValExprBinaryOp(op=cond_dict.__getitem__("and"), left=parent.root,
                                                              right=parent.parent.root)
                parent.root = last_child.root
                parent.type = last_child.type
                return self.create_ra_from_ra_tree(parent)

            __selection = radb.ast.Select(cond=parent.root, input=last_child.root)
            parent.root = __selection
            return self.create_ra_from_ra_tree(parent)

        else:
            return self.__create_projection_parts(parent, last_child)


ra_tree = None


def __get_all_relation_tokens__(sql_statement):
    tokens = []
    sql_statement = sql_statement[0].tokens
    for add_token in sql_statement:
        if not hasattr(add_token, 'tokens'):
            tokens.append(add_token)
            continue

        for i in add_token.tokens:
            tokens.append(i)

    return tokens


def __create_relation(tokens):
    global ra_tree

    relations = []
    is_rename = False
    for token in tokens:
        if token.is_whitespace:
            continue

        if token.value == ",":
            is_rename = False
            continue

        if is_rename:
            last_element = len(relations) - 1
            relations[last_element] = radb.ast.Rename(relname=None, attrnames=[token.value + ": *"],
                                                      input=relations[last_element])
        else:
            relations.append(radb.ast.RelRef(token.value))
            is_rename = True

    for r in relations:
        if ra_tree is None:
            ra_tree = Tree(r, tree_types_dict.__getitem__("relation"))
        else:
            ra_tree.insert_node(r, tree_types_dict.__getitem__("relation"))


def __create_projection(sql_select_statement):
    if sql_select_statement[0].value == "*":
        return None

    only_one_projection = True
    for token in sql_select_statement[0].tokens:
        if token.value == ",":
            only_one_projection = False
            break

    global ra_tree
    if only_one_projection:
        ra_tree.insert_node(sql_select_statement[0].value, tree_types_dict.__getitem__("projection"))
        return

    for token in sql_select_statement[0].tokens:
        if token.is_whitespace or token.value == ",":
            continue

        ra_tree.insert_node(token.value, tree_types_dict.__getitem__("projection"))


def __create_valexprbinaryop(tokens):
    left_done, or_done = False, False
    left, right, op = None, None, None
    for token in tokens:
        if token.is_whitespace:
            continue

        if not left_done:
            left = radb.ast.AttrRef(rel=None, name=token.value)
            left_done = True
        elif not or_done:
            op = cond_dict.__getitem__(token.value)
            or_done = True
        else:
            right = radb.ast.RANumber(token.value)
            break

    return radb.ast.ValExprBinaryOp(op=op, left=left, right=right)


def __create_selection(sql_where_statement):
    if sql_where_statement.__len__() == 0:
        return

    for token in sql_where_statement[0].tokens:
        if token.is_whitespace or token.normalized == "WHERE":
            continue

        if type(token) is sql.Comparison:
            cond = __create_valexprbinaryop(token.tokens)
            ra_tree.insert_node(cond, tree_types_dict.__getitem__("selection"))


def __create_ra_from_ra_tree():
    global ra_tree
    return ra_tree.create_ra_from_ra_tree(ra_tree.get_last_left_child())


def __get_restart_ra_tree():
    global ra_tree
    ra_tree = None


def __separate_tokens(sqlstring):
    in_from = False
    relation, projection, selection = [], [], []

    for token in sqlstring.tokens:
        if token.is_whitespace:
            continue

        if token.is_keyword:
            if token.value.lower() == 'from':
                in_from = True
            continue

        if not in_from:
            projection.append(token)
            continue

        if token.is_group and token.value[:5].lower() == 'where':
            selection.append(token)
            continue

        relation.append(token)

    relation = __get_all_relation_tokens__(relation)
    return relation, selection, projection


def translate(sqlstring):
    __get_restart_ra_tree()

    relation, selection, projection = __separate_tokens(sqlstring)

    __create_relation(relation)
    __create_selection(selection)
    __create_projection(projection)

    # todo: optimize

    return __create_ra_from_ra_tree()
