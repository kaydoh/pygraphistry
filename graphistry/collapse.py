from typing import Union, Optional, List
import pandas as pd
import numpy as np

from .PlotterBase import Plottable

COLLAPSE_NODE = "collapse_node"
COLLAPSE_SRC = "collapse_src"
COLLAPSE_DST = "collapse_dst"
WRAP = "~"
DEFAULT_VAL = "None"
VERBOSE = True

UnionStrInt = Union[str, int]


def unpack(g: Plottable):
    """
        Helper method that unpacks graphistry instance
    ex:
        ndf, edf, src, dst, node = unpack(g)

    -----------------------------------------------------------------------------------------

    :param g: graphistry instance
    :returns node DataFrame, edge DataFrame, source column, destination column, node column
    """
    ndf = g._nodes
    edf = g._edges
    src = g._source
    dst = g._destination
    node = g._node
    return ndf, edf, src, dst, node


def get_children(g: Plottable, node_id: UnionStrInt, hops: int = 1):
    """
        Helper that gets children at k-hops from node `node_id`

    ------------------------------------------------------------------

    :returns graphistry instance of hops
    """
    g2 = g.hop(pd.DataFrame({g._node: [node_id]}), hops=hops)
    return g2


def has_edge(
    g: Plottable, n1: UnionStrInt, n2: UnionStrInt, directed: bool = True
) -> bool:
    """
        Checks if `n1` and `n2` share an (directed or not) edge

    ------------------------------------------------------------------

    :param g: graphistry instance
    :param n1: `node` to check if has edge to `n2`
    :param n2: `node` to check if has edge to `n1`
    :param directed: bool, if True, checks only outgoing edges from `n1`->`n2`, else finds undirected edges
    :returns bool, if edge exists between `n1` and `n2`

    """
    ndf, edf, src, dst, node = unpack(g)
    if directed:
        if n2 in edf[edf[src] == n1][dst].values:
            return True
    else:
        if (n2 in edf[edf[src] == n1][dst].values) or (
            n1 in edf[edf[src] == n2][dst].values
        ):
            return True
    return False


def get_edges_of_node(
    g: Plottable, node_id: UnionStrInt, directed: bool = True, hops: int = 1
):
    """
        Gets edges of node at k-hops from node

    ----------------------------------------------------------------------------------

    :param g: graphistry instance
    :param node_id: `node` to find edges from
    :param directed: bool, if true, finds all outgoing edges of `node`, default True
    :param hops: the number of hops from `node` to take, default = 1
    :returns DataFrame of edges
    """
    _, _, src, dst, _ = unpack(g)
    g2 = get_children(g, node_id, hops=hops)
    if directed:
        edges = g2._edges[dst].drop_duplicates()
    else:
        edges = pd.concat([g2._edges[src], g2._edges[dst]]).drop_duplicates()
    return edges


def get_edges_in_out_cluster(
    g: Plottable,
    node_id: UnionStrInt,
    attribute: UnionStrInt,
    column: UnionStrInt,
    directed: bool = True,
):
    """
        Traverses children of `node_id` and separates them into incluster and outcluster sets depending if they have
        `attribute` in node DataFrame `column`

    --------------------------------------------------------------------------------------------------------------------

    :param g: graphistry instance
    :param node_id: `node` with `attribute` in `column`
    :param attribute: `attribute` to collapse in `column` over
    :param column: `column` to collapse over
    :param directed:
    """
    g2 = get_children(g, node_id, hops=1)
    e = get_edges_of_node(
        g, node_id, directed=directed
    )  # False just includes the src node
    ndf, edf, src, dst, node = unpack(g2)
    tdf = ndf[ndf[column] == attribute]
    if not tdf.empty:
        # Get edges that are not in attribute (outside edges)
        outcluster = set(e.values).difference(set(tdf.node.values))
        # get edges that are internal to attribute, we will use these later to collapse those edges to supernode
        incluster = set(tdf.node.values).intersection(set(e.values))
        if VERBOSE:
            if len(outcluster):
                print(
                    f"{outcluster} are edges *not* in [[ {column}:{attribute} ]] for node {node_id}"
                )
                # get directionality
            if len(incluster):
                print(
                    f"{incluster} are edges in [[ {column}:{attribute} ]] for node {node_id}"
                )
        return outcluster, incluster, tdf
    return None, None, None


def get_cluster_store_keys(ndf: pd.DataFrame, node: UnionStrInt):
    """
        Main innovation in finding and adding to super node.
        Checks if node is a segment in any collapse_node in COLLAPSE column of nodes DataFrame

    --------------------------------------------------------------------------------------------

    :param ndf: node DataFrame
    :param node: node to find
    :returns DataFrame of bools of where `wrap_key(node)` exists in COLLAPSE column
    """
    node = wrap_key(node)
    return ndf[COLLAPSE_NODE].astype(str).str.contains(node, na=False)


def in_cluster_store_keys(ndf: pd.DataFrame, node: UnionStrInt) -> bool:
    """
        checks if node is in collapse_node in COLLAPSE column of nodes DataFrame

    ------------------------------------------------------------------------------

    :param ndf: nodes DataFrame
    :param node: node to find
    :returns bool
    """
    return any(get_cluster_store_keys(ndf, node))


def reduce_key(key: UnionStrInt) -> str:
    """
        Takes "1 1 2 1 2 3" -> "1 2 3

    ---------------------------------------------------

    :param key: node name
    :returns new node name with duplicates removed
    """
    uniques = " ".join(np.unique(key.split()))
    return uniques


def unwrap_key(name: UnionStrInt) -> str:
    """
        Unwraps node name: ~name~ -> name

    ----------------------------------------

    :param name: node to unwrap
    :returns unwrapped node name
    """
    return str(name).replace(WRAP, "")


def wrap_key(name: UnionStrInt) -> str:
    """
        Wraps node name -> ~name~

    -----------------------------------

    :param name: node name
    :returns wrapped node name
    """
    name = str(name)
    if WRAP in name:  # idempotency
        return name
    return f"{WRAP}{name}{WRAP}"


def melt(ndf: pd.DataFrame, node: UnionStrInt) -> str:
    """
        Reduces node if in cluster store, otherwise passes it through.
    ex:
        node = "4" will take any sequence from get_cluster_store_keys, "1 2 3", "4 3 6" and returns "1 2 3 4 6"
        when they have a common entry (3).

    -------------------------------------------------------------------------------------------------------------

    :param ndf, node DataFrame
    :param node: node to melt
    :returns new_parent_name of super node
    """
    rdf = ndf[get_cluster_store_keys(ndf, node)]
    topkey = wrap_key(node)
    if not rdf.empty:
        for key in rdf[COLLAPSE_NODE].values:  # all these are already wrapped
            # add the keys to cluster
            topkey += f" {key}"  # keep whitespace
        topkey = reduce_key(topkey)
    return topkey


def get_new_node_name(
    ndf: pd.DataFrame, parent: UnionStrInt, child: UnionStrInt
) -> str:
    """
        If child in cluster group, melts name, else makes new parent_name from parent, child

    ---------------------------------------------------------------------------------------------------------

    :param ndf: node DataFrame
    :param parent: `node` with `attribute` in `column`
    :param child: `node` with `attribute` in `column`
    :returns new_parent_name
    """
    # THIS IS IMPORTANT FUNCTION -- it is where we wrap the parent/child in WRAP
    # if child in cluster group, we melt it
    ckey = in_cluster_store_keys(ndf, child)
    pkey = in_cluster_store_keys(ndf, parent)
    # new_parent_name = wrap_key(parent)
    if ckey and pkey:
        new_parent_name = melt(ndf, child)
        new_parent_name = f"{new_parent_name} {wrap_key(parent)}"

    else:  # if not, then append child to parent as the start of a new cluster group
        # might have to escape parent and child if node names are dumb eg, 'this value key'
        new_parent_name = melt(ndf, parent)
        new_parent_name = f"{new_parent_name} {wrap_key(child)}"
    if VERBOSE:
        print(
            f"Renaming (parent:{parent}:{pkey}, child:{child}:{ckey})  ->  {new_parent_name}"
        )
    return reduce_key(new_parent_name)


def collapse_nodes_and_edges(
    g: Plottable, parent: UnionStrInt, child: UnionStrInt
) -> Plottable:
    """
        Asserts that parent and child node in ndf should be collapsed into super node.
        Sets new ndf with COLLAPSE nodes in graphistry instance g

        # this asserts that we SHOULD merge parent and child as super node
        # outside logic controls when that is the case
        # for example, it assumes parent is already in cluster keys of COLLAPSE node

    ---------------------------------------------------------------------------------------

    :param g: graphistry instance
    :param parent: `node` with `attribute` in `column`
    :param child: `node` with `attribute` in `column`
    :returns: graphistry instance
    """

    ndf, edf, src, dst, node = unpack(g)

    new_parent_name = get_new_node_name(ndf, parent, child)

    ndf.loc[ndf[node] == parent, COLLAPSE_NODE] = new_parent_name
    ndf.loc[ndf[node] == child, COLLAPSE_NODE] = new_parent_name

    edf.loc[edf[src] == parent, COLLAPSE_SRC] = new_parent_name
    edf.loc[edf[dst] == parent, COLLAPSE_DST] = new_parent_name

    edf.loc[edf[src] == child, COLLAPSE_SRC] = new_parent_name
    edf.loc[edf[dst] == child, COLLAPSE_DST] = new_parent_name

    g._edges = edf
    g._nodes = ndf
    return g


def has_property(
    g: Plottable, ref_node: str, attribute: UnionStrInt, column: UnionStrInt
) -> bool:
    """
        Checks if ref_node is in node dataframe in column with attribute

    -------------------------------------------------------------------------

    :param attribute:
    :param column:
    :param g: graphistry instance
    :param ref_node: `node` to check if it as `attribute` in `column`
    :returns bool"""
    ndf, edf, src, dst, node = unpack(g)
    ref_node = unwrap_key(ref_node)
    return ref_node in ndf[ndf[column] == attribute][node].values


def check_default_columns_present_and_coerce_to_string(g: Plottable):
    """
        Helper to set COLLAPSE columns to nodes and edges dataframe, while converting src, dst, node to dtype(str)

    -------------------------------------------------------------------------

    :param g: graphistry instance
    :returns graphistry instance
    """
    ndf, edf, src, dst, node = unpack(g)
    if COLLAPSE_NODE not in ndf.columns:
        ndf[COLLAPSE_NODE] = DEFAULT_VAL
        ndf[node] = ndf[node].astype(str)
        print(f"Converted ndf to type({type(ndf[node].values[0])})")
        g._nodes = ndf
    if COLLAPSE_SRC not in edf.columns:
        edf[COLLAPSE_SRC] = DEFAULT_VAL
        edf[COLLAPSE_DST] = DEFAULT_VAL
        edf[src] = edf[src].astype(str)
        edf[dst] = edf[dst].astype(str)
        print(f"Converted edf to type({type(edf[src].values[0])})")
        g._edges = edf
    return g


def collapse(
    g: Plottable,
    child: UnionStrInt,
    parent: UnionStrInt,
    attribute: UnionStrInt,
    column: UnionStrInt,
    seen: dict,
):
    """
        Basically candy crush over graph properties in a topology aware manner

        Checks to see if child node has desired property from parent, we will need to check if
        (start_node=parent: has_attribute , children nodes: has_attribute) by case
        (T, T), (F, T), (T, F) and (F, F),
        we start recursive collapse (or not) on the children, reassigning nodes and edges.

        if (T, T), append children nodes to start_node, re-assign the name of the node, and update the edge table with new name,

        if (F, T) start k-(potentially new) super nodes, with k the number of children of start_node.
                Start node keeps k outgoing edges.

        if (T, F) it is the end of the cluster, and we keep new node as is; keep going

        if (F, F); keep going

    --------------------------------------------------------------------------------------------------------------------

    :param seen:
    :param g: graphistry instance
    :param child: child node to start traversal, for first traversal, set child=parent or vice versa.
    :param parent: parent node to start traversal, in main call, this is set to child.
    :param attribute: attribute to collapse by
    :param column: column in nodes dataframe to collapse over.
    :returns graphistry instance with collapsed nodes.
    """
    g = check_default_columns_present_and_coerce_to_string(g)

    compute_key = f"{parent} {child}"

    # parent = str(parent)
    # child = str(child)

    if compute_key in seen:  # it has already traversed this path, skip
        return g
    else:
        if has_property(g, parent, attribute, column):  # if (T, *)
            # add start node to super node index
            tkey = f"{parent} {parent}"  # it will reduce this to `parent` but can add to `seen`
            if tkey not in compute_key:  # its love!
                seen[tkey] = 1
                g = collapse_nodes_and_edges(g, parent, parent)
            if has_property(g, child, attribute, column):  # if (T, T)
                if VERBOSE:
                    print("-" * 80)
                    print(
                        f" ** [ parent: {parent}, child: {child} ] both have property"
                    )
                g = collapse_nodes_and_edges(
                    g, parent, child
                )  # will make a new parent off of parent, child names
                # add to seen
                seen[compute_key] = 1
                for e in get_edges_of_node(
                    g, parent, directed=True, hops=1
                ).values:  # False just includes the child node and goes into infinite loop when parent = child
                    collapse(
                        g, e, child, attribute, column, seen
                    )  # now child is the parent, and the edges are the start node
        # else do nothing collapse-y to parent, move on to child
        else:  # if (F, *)
            #  do nothing to child, parent is child, and child is edge and recurse
            for e in get_edges_of_node(g, child, directed=True, hops=1).values:
                if VERBOSE:
                    print(
                        f" -- Parent {parent} does not have property, looking at node <[ {e} from {child} ]>"
                    )
                collapse(
                    g, e, child, attribute, column, seen
                )  # now child is the parent, and the edges are the start node
    return g


def melt_remaining(g):
    """Sometimes traversal leaves stragglers that weren't melted
    :returns"""
    ndf, edf, src, dst, node = unpack(g)
    # get all COLLAPSE nodes
    collapse_nodes = np.unique(
        ndf[ndf[COLLAPSE_NODE] != DEFAULT_VAL][COLLAPSE_NODE].values
    )
    for supernode in collapse_nodes:
        for node in supernode.split():
            pass


def normalize_graph(
    g: Plottable,
    self_edges: bool = False,
    unwrap: bool = False,
    remove_collapse: bool = False,
):
    """
        Final step after collapse traversals are done, removes duplicates and moves COLLAPSE columns into respective
        (node, src, dst) columns of node, edges dataframe from Graphistry instance g.

    --------------------------------------------------------------------------------------------------------------------

    :param g: graphistry instance
    :param self_edges: bool, whether to keep duplicates from ndf, edf, default False
    :param unwrap: bool, whether to unwrap node text with `~`, default True
    :param remove_collapse: bool, whether to drop COLLAPSE columns from dataframe, default True
    :returns final graphistry instance
    """

    ndf, edf, src, dst, node = unpack(g)

    # move the new node names fromo COLLAPSE COL to the node column
    ndf.loc[ndf[COLLAPSE_NODE] != DEFAULT_VAL, node] = ndf.loc[
        ndf[COLLAPSE_NODE] != DEFAULT_VAL, COLLAPSE_NODE
    ]
    ndf = ndf.drop_duplicates()

    edf.loc[edf[COLLAPSE_SRC] != DEFAULT_VAL, src] = edf.loc[
        edf[COLLAPSE_SRC] != DEFAULT_VAL, COLLAPSE_SRC
    ]
    edf.loc[edf[COLLAPSE_DST] != DEFAULT_VAL, dst] = edf.loc[
        edf[COLLAPSE_DST] != DEFAULT_VAL, COLLAPSE_DST
    ]
    if not self_edges:
        edf = edf.drop_duplicates()

    if unwrap:
        ndf[node] = ndf[node].astype(str).apply(lambda x: unwrap_key(x))
        edf[src] = edf[src].astype(str).apply(lambda x: unwrap_key(x))
        edf[dst] = edf[dst].astype(str).apply(lambda x: unwrap_key(x))

    if remove_collapse:
        # remove collapse columns in ndf, edf
        ndf = ndf.drop(columns=[COLLAPSE_NODE])
        edf = edf.drop(columns=[COLLAPSE_SRC, COLLAPSE_DST])

    # set the dataframes
    g._nodes = ndf
    g._edges = edf
    return g


def collapse_by(
    g: Plottable,
    parent: UnionStrInt,
    start_node: UnionStrInt,
    attribute: UnionStrInt,
    column: UnionStrInt,
    seen: dict,
    self_edges: bool = False,
    unwrap: bool = False,
    remove_collapse: bool = False,
):
    """
        Main call in collapse.py, collapses nodes and edges by attribute, and returns normalized graphistry object.

    --------------------------------------------------------------------------------------------------------------------
    :param start_node:
    :param seen:
    :param g: graphistry instance
    :param parent: parent node to start traversal, in main call, this is set to child.
    :param attribute: attribute to collapse by
    :param column: column in nodes dataframe to collapse over.
    :returns graphistry instance with collapsed and normalized nodes.
    """
    from time import time

    n_edges = len(g._edges)
    complexity_min = int(2 * n_edges * np.log(n_edges))
    complexity_max = int(2 * n_edges ** (3 / 2))
    if VERBOSE:
        print("-" * 100)
        print(
            f"This Algorithm runs approximately between 2*n_edges*log(n_edges) and 2*n_edges**(3/2) in un-normalized units"
        )
        print(
            f"Hence, in this case, between O({complexity_min/n_edges:.2f} - {complexity_max/n_edges:.2f}) for "
            f"this graph normalized by {n_edges} edges"
        )
        print(
            "It is not recommended for large graphs -- one can expect a modern laptop CPU to scan 1-6k edges per minute"
        )
        print(f"Here we expect collapse to run in {n_edges/1000:.3f} minutes")
        print("*" * 100)
    t = time()
    collapse(g, parent, start_node, attribute, column, seen)
    t2 = time()
    delta_mins = (t2 - t) / 60
    if VERBOSE:
        print("-" * 80)
        print(
            f"Total Collapse took {delta_mins:.2f} minutes or {n_edges/delta_mins:.2f} edges per minute"
        )
    return normalize_graph(
        g, self_edges=self_edges, unwrap=unwrap, remove_collapse=remove_collapse
    )
