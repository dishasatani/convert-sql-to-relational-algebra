import sys
import radb
import radb.ast
import radb.parse
import sqlparse
from sqlparse import sql

# The equivalents of SQL condition in the "radb" library
cond_dict = {
    "=": 43,
    "and": 11
}

# Data types that can be on root of Node
node_types_dict = {
    "relation": 0,
    "selection": 1,
    "projection": 2,
    "cross": 3  # (cartesian product)
}


# The sql query, which is divided into statements, is turned into a tree so that each statement corresponds to a node.
# "Tree" class is the class that contains the necessary functions for these operations.
class Tree:
    def __init__(self, root, node_type):
        self.left = None
        self.right = None
        self.parent = None
        self.root = root
        self.type = node_type

    # The method that adds the node to the tree.
    def insert_node(self, new_node, node_type):
        if node_type is node_types_dict.__getitem__("relation"):
            self.__insert_relations(new_node, node_type)
        else:
            new_tree = Tree(new_node, node_type)
            new_tree.left = self
            self.parent = new_tree

    # It starts the return from sql to ra from the lowest and leftmost node of the tree.
    # This is the method that finds this node.
    def get_last_left_child(self):
        if self.left is not None:
            return self.left.get_last_left_child()

        return self

    # It converts relational algebra statements to relational algebra query,
    # moves from "the leftmost and lowest node" to the root.
    def create_ra(self, last_child):
        if last_child.parent is None:
            return last_child.root

        parent = last_child.parent
        if last_child.type is node_types_dict.__getitem__("relation"):
            return self.__create_relation_parts(parent, last_child)

        elif last_child.type is node_types_dict.__getitem__("selection"):
            return self.__create_selection_parts(parent, last_child)

        elif last_child.type is node_types_dict.__getitem__("projection"):
            return self.__create_projection_parts(parent, last_child)

    # It is a method that inserts relation type nodes into the tree. It prevents two relation type nodes from passing
    # into parent-child relation. Instead, it adds a cross(cartesian product) type node and add the related relations
    # to the right and left children of this node. Thus, it makes the optimization process easier.
    def __insert_relations(self, new_node, node_type):
        if self.type is node_types_dict.__getitem__("relation"):
            self.__insert_cartesian(new_node, node_type)
        elif self.type is node_types_dict.__getitem__("cross"):
            if self.right is None:
                self.right = Tree(new_node, node_type)
                self.right.parent = self
            else:
                self.__insert_cartesian(new_node, node_type)

    # Adds the Cartesian product. The types of right and left children always are relations.
    def __insert_cartesian(self, new_node, node_type):
        right_node = Tree(new_node, node_type)

        new_tree = Tree("X", node_types_dict.__getitem__("cross"))
        self.parent = new_tree
        right_node.parent = new_tree

        new_tree.left = self
        new_tree.right = right_node

    # It is the selection part in the translation from ra statements to ra query.
    def __create_selection_parts(self, parent, last_child):
        if parent.type is node_types_dict.__getitem__("selection"):
            __selection = radb.ast.Select(cond=parent.root, input=last_child.root)
            parent.root = __selection
            return self.create_ra(parent)

        if parent.type is node_types_dict.__getitem__("projection"):
            return self.__create_projection_parts(parent, last_child)

    # It is the projection part in the translation from ra statements to ra query.
    def __create_projection_parts(self, parent, last_child):
        if parent.parent is None:
            if isinstance(parent.root, list):
                return radb.ast.Project(parent.root, last_child.root)
            else:
                return radb.ast.Project([radb.ast.AttrRef(rel=None, name=parent.root)], last_child.root)

        if parent.parent.type is node_types_dict.__getitem__("projection"):
            parent.parent.root = [radb.ast.AttrRef(rel=None, name=parent.root),
                                  radb.ast.AttrRef(rel=None, name=parent.parent.root)]
            parent.root = last_child.root
            parent.type = last_child.type
            return self.create_ra(parent)

    # It is the relation part in the translation from ra statements to ra query.
    def __create_relation_parts(self, parent, last_child):
        if parent.type is node_types_dict.__getitem__("cross"):
            parent.root = radb.ast.Cross(parent.left.root, parent.right.root)
            parent.type = node_types_dict.__getitem__("relation")
            return self.create_ra(parent)

        elif parent.type is node_types_dict.__getitem__("selection"):
            # if parent and parent's parent is selection, it writes these two values as a new selection.
            # The new node's parent's type can still be selection.
            # Therefore, the flow continues without combining selection and relation.
            if parent.parent is not None and parent.parent.type is node_types_dict.__getitem__("selection"):
                parent.parent.root = radb.ast.ValExprBinaryOp(op=cond_dict.__getitem__("and"), left=parent.root,
                                                              right=parent.parent.root)
                parent.root = last_child.root
                parent.type = last_child.type
                return self.create_ra(parent)

            __selection = radb.ast.Select(cond=parent.root, input=last_child.root)
            parent.root = __selection
            return self.create_ra(parent)

        else:
            return self.__create_projection_parts(parent, last_child)


# If a new parent is added to the node, it sets the parent as root.
def __fix_root(tree):
    if tree is None:
        return tree

    while tree.parent is not None:
        tree = tree.parent

    return tree


# There can also be tokens inside relation tokens. It separates them.
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


# Adds the sql relational statement to the tree by converting them to the ra statements.
def __create_relation(tokens):
    tree, relations, is_rename = None, [], False

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
        if tree is None:
            tree = Tree(r, node_types_dict.__getitem__("relation"))
        else:
            tree.insert_node(r, node_types_dict.__getitem__("relation"))
            tree = __fix_root(tree)

    return tree


# Adds the sql select statement to the tree by converting them to the ra projection.
def __create_projection(sql_select_statement, tree):
    if sql_select_statement[0].value == "*":
        return tree

    only_one_projection = True
    for token in sql_select_statement[0].tokens:
        if token.value == ",":
            only_one_projection = False
            break

    if only_one_projection:
        tree.insert_node(sql_select_statement[0].value, node_types_dict.__getitem__("projection"))
        return __fix_root(tree)

    for token in sql_select_statement[0].tokens:
        if token.is_whitespace or token.value == ",":
            continue

        tree.insert_node(token.value, node_types_dict.__getitem__("projection"))
        tree = __fix_root(tree)

    return tree


# It turns tokens into an object that the ra library can understand.
# Called by the __create_selection method.
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


# Adds the sql where statement to the tree by converting them to the ra selection.
def __create_selection(sql_where_statement, tree):
    if sql_where_statement.__len__() == 0:
        return tree

    for token in sql_where_statement[0].tokens:
        if token.is_whitespace or token.normalized == "WHERE":
            continue

        if type(token) is sql.Comparison:
            cond = __create_valexprbinaryop(token.tokens)
            tree.insert_node(cond, node_types_dict.__getitem__("selection"))
            tree = __fix_root(tree)

    return tree


# The tokens returned from the sql parser are separated into the relevant statements.
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


# The main method accessed from outside the library.
def translate(sqlstring):
    relation, selection, projection = __separate_tokens(sqlstring)
    
    tree = __create_relation(relation)
    tree = __create_selection(selection, tree)
    tree = __create_projection(projection, tree)

    return tree.create_ra(tree.get_last_left_child())


if __name__ == "__main__":
    sql_string = sys.argv[1]
    stmt = sqlparse.parse(sql_string)[0]
    print(translate(stmt))
