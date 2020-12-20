# {{{ docstring

"""
Generic Shape-Based Interface
-----------------------------

.. currentmodule:: modepy

.. autofunction:: node_tuples_for_space
.. autofunction:: equispaced_nodes_for_space
.. autofunction:: edge_clustered_nodes_for_space
.. autofunction:: random_nodes_for_shape

Simplices
---------

.. autofunction:: equidistant_nodes
.. autofunction:: warp_and_blend_nodes

Also see :class:`modepy.VioreanuRokhlinSimplexQuadrature` if nodes on the
boundary are not required.

Hypercubes
----------

.. currentmodule:: modepy

.. autofunction:: tensor_product_nodes
.. autofunction:: legendre_gauss_tensor_product_nodes
.. autofunction:: legendre_gauss_lobatto_tensor_product_nodes

.. autofunction:: padua_jacobi_nodes
.. autofunction:: padua_nodes
"""

__copyright__ = "Copyright (C) 2009, 2010, 2013 Andreas Kloeckner, " \
        "Tim Warburton, Jan Hesthaven, Xueyu Zhu"

__license__ = """
Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in
all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
THE SOFTWARE.
"""

# }}}

from functools import partial, singledispatch
from typing import Optional, Sequence, Tuple, Union

import numpy as np
import numpy.linalg as la

from modepy.shapes import Shape, Simplex, TensorProductShape, unit_vertices_for_shape
from modepy.spaces import PN, FunctionSpace, TensorProductSpace


# {{{ equidistant nodes

def equidistant_nodes(
        dims: int, n: int,
        node_tuples: Optional[Sequence[Tuple[int, ...]]] = None
        ) -> np.ndarray:
    """
    :arg dims: dimensionality of desired simplex
        (e.g. 1, 2 or 3, for interval, triangle or tetrahedron).
    :arg n: Desired maximum total polynomial degree to interpolate.
    :arg node_tuples: a list of tuples of integers indicating the node order.
        Use default order if *None*, see
        :func:`pytools.generate_nonnegative_integer_tuples_summing_to_at_most`.

    :returns: An array of shape *(dims, nnodes)* containing bi-unit coordinates
        of the interpolation nodes. (see :ref:`tri-coords` and :ref:`tet-coords`)
    """

    space = PN(dims, n)
    if node_tuples is None:
        node_tuples = node_tuples_for_space(space)
    else:
        if len(node_tuples) != space.space_dim:
            raise ValueError("'node_tuples' list does not have the correct length")

    if n == 0:
        from modepy.shapes import unit_vertices_for_shape
        return (np.mean(unit_vertices_for_shape(Simplex(dims)), axis=1)
                .reshape(-1, 1))

    # shape: (dims, nnodes)
    return (np.array(node_tuples, dtype=np.float64)/n*2 - 1).T

# }}}


# {{{ warp and blend simplex nodes

def warp_factor(n, output_nodes, scaled=True):
    """Compute warp function at order *n* and evaluate it at
    the nodes *output_nodes*.
    """

    from modepy.quadrature.jacobi_gauss import legendre_gauss_lobatto_nodes

    warped_nodes = legendre_gauss_lobatto_nodes(n, force_dim_axis=True).squeeze()
    equi_nodes = np.linspace(-1, 1, n+1)

    from modepy.matrices import vandermonde
    from modepy.modes import jacobi

    basis = [partial(jacobi, 0, 0, n) for n in range(n + 1)]
    Veq = vandermonde(basis, equi_nodes)  # noqa

    # create interpolator from equi_nodes to output_nodes
    eq_to_out = la.solve(Veq.T, vandermonde(basis, output_nodes).T).T

    # compute warp factor
    warp = np.dot(eq_to_out, warped_nodes - equi_nodes)
    if scaled:
        zerof = (abs(output_nodes) < 1.0-1.0e-10)
        sf = 1.0 - (zerof*output_nodes)**2
        warp = warp/sf + warp*(zerof-1)

    return warp


# {{{ 2D nodes

def _2d_equilateral_shift(n, bary, alpha):
    from modepy.tools import EQUILATERAL_VERTICES
    equi_vertices = EQUILATERAL_VERTICES[2]

    result = np.zeros((2, bary.shape[1]))

    for i1 in range(3):
        i2, i3 = set(range(3)) - {i1}

        # Compute blending function at each node for each edge
        blend = 4*bary[i2]*bary[i3]

        # Amount of warp for each node, for each edge
        warpf = warp_factor(n, bary[i2]-bary[i3])

        # Combine blend & warp
        warp = blend*warpf*(1 + (alpha*bary[i1])**2)

        # all vertices have the same distance from the origin
        tangent = equi_vertices[i2] - equi_vertices[i3]
        tangent /= la.norm(tangent)

        result += tangent[:, np.newaxis] * warp[np.newaxis, :]

    return result


_alpha_opt_2d = [0.0000, 0.0000, 1.4152, 0.1001, 0.2751, 0.9800, 1.0999,
        1.2832, 1.3648, 1.4773, 1.4959, 1.5743, 1.5770, 1.6223, 1.6258]


def warp_and_blend_nodes_2d(n, node_tuples=None):
    try:
        alpha = _alpha_opt_2d[n-1]
    except IndexError:
        alpha = 5/3

    space = PN(2, n)
    if node_tuples is None:
        node_tuples = node_tuples_for_space(space)
    else:
        if len(node_tuples) != space.space_dim:
            raise ValueError("'node_tuples' list does not have the correct length")

    # shape: (2, nnodes)
    unit_nodes = (np.array(node_tuples, dtype=np.float64)/n*2 - 1).T

    from modepy.tools import (
        barycentric_to_equilateral,
        equilateral_to_unit,
        unit_to_barycentric,
    )
    bary = unit_to_barycentric(unit_nodes)

    return equilateral_to_unit(
        barycentric_to_equilateral(bary)
        + _2d_equilateral_shift(n, bary, alpha))

# }}}


# {{{ 3D nodes

_alpha_opt_3d = [
        0, 0, 0, 0.1002, 1.1332, 1.5608, 1.3413, 1.2577, 1.1603,
        1.10153, 0.6080, 0.4523, 0.8856, 0.8717, 0.9655]


def warp_and_blend_nodes_3d(n, node_tuples=None):
    try:
        alpha = _alpha_opt_3d[n-1]
    except IndexError:
        alpha = 1.

    space = PN(3, n)
    if node_tuples is None:
        node_tuples = node_tuples_for_space(space)
    else:
        if len(node_tuples) != space.space_dim:
            raise ValueError("'node_tuples' list does not have the correct length")

    # shape: (3, nnodes)
    unit_nodes = (np.array(node_tuples, dtype=np.float64)/n*2 - 1).T

    from modepy.tools import (
        EQUILATERAL_VERTICES,
        barycentric_to_equilateral,
        equilateral_to_unit,
        unit_to_barycentric,
    )
    bary = unit_to_barycentric(unit_nodes)
    equi = barycentric_to_equilateral(bary)

    equi_vertices = EQUILATERAL_VERTICES[3]

    # total number of nodes and tolerance
    tol = 1e-8

    shift = np.zeros_like(equi)

    for i1, i2, i3, i4, vertex_step in [
            (0, 1, 2, 3, -1),
            (1, 2, 3, 0, -1),
            (2, 3, 0, 1, -1),
            (3, 0, 1, 2, -1),
            ]:

        vi2, vi3, vi4 = ((i1 + vertex_step*i) % 4 for i in range(1, 4))

        # all vertices have the same distance from the origin
        tangent1 = equi_vertices[vi3] - equi_vertices[vi4]
        tangent1 /= la.norm(tangent1)

        tangent2 = equi_vertices[vi2] - equi_vertices[vi3]
        tangent2 -= np.dot(tangent1, tangent2)*tangent1

        tangent2 /= la.norm(tangent2)

        sub_bary = bary[[i2, i3, i4]]
        warp1, warp2 = _2d_equilateral_shift(n, sub_bary, alpha)

        l1 = bary[i1]
        l2, l3, l4 = sub_bary

        blend = l2*l3*l4

        denom = (l2+0.5*l1)*(l3+0.5*l1)*(l4+0.5*l1)
        denom_ok = denom > tol

        blend[denom_ok] = (
                (1+(alpha*l1[denom_ok])**2)
                * blend[denom_ok]
                / denom[denom_ok])

        shift = shift + (blend*warp1)[np.newaxis, :] * tangent1[:, np.newaxis]
        shift = shift + (blend*warp2)[np.newaxis, :] * tangent2[:, np.newaxis]

        is_face = (l1 < tol) & ((l2 > tol) | (l3 > tol) | (l4 > tol))

        # assign face warp separately
        shift[:, is_face] = (
                + warp1[is_face][np.newaxis, :] * tangent1[:, np.newaxis]
                + warp2[is_face][np.newaxis, :] * tangent2[:, np.newaxis]
                )

    return equilateral_to_unit(equi + shift)

# }}}


# {{{ generic interface to warp-and-blend nodes

def warp_and_blend_nodes(
        dims: int, n: int,
        node_tuples: Optional[Sequence[Tuple[int, ...]]] = None) -> np.ndarray:
    """Return interpolation nodes as described in [warburton-nodes]_

    .. [warburton-nodes] Warburton, T.
        "An Explicit Construction of Interpolation Nodes on the Simplex."
        Journal of Engineering Mathematics 56, no. 3 (2006): 247-262.
        http://dx.doi.org/10.1007/s10665-006-9086-6

    :arg dims: dimensionality of desired simplex
        (1, 2 or 3, i.e. interval, triangle or tetrahedron).
    :arg n: Desired maximum total polynomial degree to interpolate.
    :arg node_tuples: a list of tuples of integers indicating the node order.
        Use default order if *None*, see
        :func:`pytools.generate_nonnegative_integer_tuples_summing_to_at_most`.
    :returns: An array of shape *(dims, nnodes)* containing unit coordinates
        of the interpolation nodes. (see :ref:`tri-coords` and :ref:`tet-coords`)

    The generated nodes have benign
    `Lebesgue constants
    <https://en.wikipedia.org/wiki/Lebesgue_constant_(interpolation)>`_.
    (See also :func:`modepy.tools.estimate_lebesgue_constant`)
    """
    if n == 0:
        from modepy.shapes import unit_vertices_for_shape
        return (np.mean(unit_vertices_for_shape(Simplex(dims)), axis=1)
                .reshape(-1, 1))

    if dims == 0:
        return np.empty((0, 1), dtype=np.float64)

    elif dims == 1:
        from modepy.quadrature.jacobi_gauss import legendre_gauss_lobatto_nodes
        result = legendre_gauss_lobatto_nodes(n, force_dim_axis=True)

        if node_tuples is not None:
            new_result = np.empty_like(result)
            if len(node_tuples) != n + 1:
                raise ValueError("node_tuples list does not have the correct length")

            for i, (nti,) in enumerate(node_tuples):
                new_result[:, i] = result[:, nti]

            result = new_result

        return result

    elif dims == 2:
        return warp_and_blend_nodes_2d(n, node_tuples)

    elif dims == 3:
        return warp_and_blend_nodes_3d(n, node_tuples)

    else:
        raise NotImplementedError("%d-dimensional node sets" % dims)

# }}}

# }}}


# {{{ tensor product nodes

def tensor_product_nodes(
        dims_or_nodes: Union[int, Sequence[np.ndarray]],
        nodes_1d: Optional[np.ndarray] = None) -> np.ndarray:
    """
    :returns: an array of shape ``(dims, nnodes_1d**dims)``.

    .. versionadded:: 2017.1

    .. versionchanged:: 2020.3

        The node ordering has changed and is no longer documented.

    .. versionchanged:: 2021.3

        *dims_or_nodes* can contain nodes of general size ``(dims, nnodes)``,
        not only one dimensional nodes.

    .. versionchanged:: 2022.1

        The node ordering changed once again, and it is now accessible, via
        :func:`modepy.tools.reshape_array_for_tensor_product_space`.
    """
    if isinstance(dims_or_nodes, int):
        if nodes_1d is None:
            raise ValueError("nodes_1d must be supplied if the first argument "
                                        "is the number of dimensions")
        nodesets: Sequence[np.ndarray] = [nodes_1d.reshape(1, -1)] * dims_or_nodes
        dims = dims_or_nodes
    else:
        if nodes_1d is not None:
            raise ValueError("nodes_1d must not be supplied if the first argument "
                    "is a sequence of node arrays")
        nodesets = [(n.reshape(1, -1) if n.ndim == 1 else n) for n in dims_or_nodes]
        dims = sum(n.shape[0] for n in nodesets)

    result = np.empty((dims, *tuple([n.shape[-1] for n in nodesets])))

    d = 0
    for nodes in nodesets:
        node_dims, _ = nodes.shape
        result[d:d+node_dims] = nodes.reshape(nodes.shape + (1,)*(dims-node_dims-d))
        d += node_dims

    if dims == 0:
        return result.reshape(dims, 1)
    else:
        return result.reshape((dims, -1), order="F").copy(order="C")


def legendre_gauss_tensor_product_nodes(dims: int, n: int) -> np.ndarray:
    """
    :arg n: the degree of polynomial exactly interpolated by the nodes.
        The one-dimensional base quadrature has *n+1* nodes.

    .. versionadded:: 2024.2
    """
    from modepy.quadrature.jacobi_gauss import LegendreGaussQuadrature
    gl_quad = LegendreGaussQuadrature(n, force_dim_axis=True)
    gl_nodes = gl_quad.nodes.reshape(1, -1)

    return tensor_product_nodes(dims, gl_nodes)


def legendre_gauss_lobatto_tensor_product_nodes(dims: int, n: int) -> np.ndarray:
    """
    :arg n: the degree of polynomial exactly interpolated by the nodes.
        The one-dimensional base quadrature has *n+1* nodes.
    """
    from modepy.quadrature.jacobi_gauss import legendre_gauss_lobatto_nodes
    return tensor_product_nodes(dims,
        legendre_gauss_lobatto_nodes(n, force_dim_axis=True))

# }}}


# {{{ Padua nodes

def _make_padua_grid_nodes(
        alpha: float, beta: float, order: int
        ) -> Tuple[np.ndarray, np.ndarray]:
    from modepy.quadrature.jacobi_gauss import jacobi_gauss_lobatto_nodes
    mu = jacobi_gauss_lobatto_nodes(alpha, beta, order)
    eta = jacobi_gauss_lobatto_nodes(alpha, beta, order + 1)

    return mu, eta


def _make_padua_jacobi_nodes(
        mu: np.ndarray, eta: np.ndarray, odd_or_even: int
        ) -> np.ndarray:
    nodes = np.stack(np.meshgrid(mu, eta, indexing="ij"))
    indices = np.sum(
            np.meshgrid(np.arange(mu.size), np.arange(eta.size), indexing="ij"),
            axis=0)

    return nodes[:, indices % 2 == odd_or_even].reshape(2, -1)


def _first_padua_jacobi_nodes(alpha: float, beta: float, order: int) -> np.ndarray:
    mu, eta = _make_padua_grid_nodes(alpha, beta, order)
    return _make_padua_jacobi_nodes(mu, eta, 0)


def _second_padua_jacobi_nodes(alpha: float, beta: float, order: int) -> np.ndarray:
    # NOTE: these are just "rotated" by pi/2 from the first family
    mu, eta = _make_padua_grid_nodes(alpha, beta, order)
    return _make_padua_jacobi_nodes(eta, mu, 0)


def _third_padua_jacobi_nodes(alpha: float, beta: float, order: int) -> np.ndarray:
    # NOTE: these are just "rotated" by pi from the first family
    mu, eta = _make_padua_grid_nodes(alpha, beta, order)
    return _make_padua_jacobi_nodes(mu, eta, 1)


def _fourth_padua_jacobi_nodes(alpha: float, beta: float, order: int) -> np.ndarray:
    # NOTE: these are just "rotated" by 2 pi/3 from the first family
    mu, eta = _make_padua_grid_nodes(alpha, beta, order)
    return _make_padua_jacobi_nodes(eta, mu, 1)


def padua_jacobi_nodes(
        alpha: float, beta: float, order: int,
        family: str = "first") -> np.ndarray:
    r"""Generalized Padua-Jacobi nodes.

    The Padua-Jacobi nodes are constructed from an interlaced grid of
    standard Jacobi-Gauss-Lobatto nodes, making use of
    :func:`~modepy.quadrature.jacobi_gauss.jacobi_gauss_lobatto_nodes`.
    This construction is detailed in

        M. Briani, A. Sommariva, M. Vianello,
        *Computing Fekete and Lebesgue Points: Simplex, Square, Disk*,
        Journal of Computational and Applied Mathematics, Vol. 236,
        pp. 2477--2486, 2012, `DOI <http://dx.doi.org/10.1016/j.cam.2011.12.006>`_.

    The values of the parameters :math:`(\alpha, \beta)` can have an effect
    on the Lebesgue constant of the resulting set, but all of them have
    optimal growth of :math:`\mathcal{O}(\log^2 n)`.

    The Padua-Jacobi nodes are not rotationally symmetric.

    :arg family: one of the four families of Padua-Jacobi nodes. The three
        additional families are :math:`90^\circ` rotations of the first one.
    """

    if family == "first":
        nodes = _first_padua_jacobi_nodes(alpha, beta, order)
    elif family == "second":
        nodes = _second_padua_jacobi_nodes(alpha, beta, order)
    elif family == "third":
        nodes = _third_padua_jacobi_nodes(alpha, beta, order)
    elif family == "fourth":
        nodes = _fourth_padua_jacobi_nodes(alpha, beta, order)
    else:
        raise ValueError(f"unknown Padua-Jacobi node family: '{family}'")

    return nodes


def padua_nodes(order: int, family: str = "first") -> np.ndarray:
    r"""Standard Padua nodes.

    Padua nodes are Padua-Jacobi nodes with :math:`\alpha = \beta = -0.5`,
    i.e. they are constructed from the Chebyshev-Gauss-Lobatto nodes.
    """

    return padua_jacobi_nodes(-0.5, -0.5, order, family=family)

# }}}


# {{{ space-based interface

@singledispatch
def node_tuples_for_space(space: FunctionSpace) -> Sequence[Tuple[int]]:
    raise NotImplementedError(type(space).__name__)


@singledispatch
def equispaced_nodes_for_space(space: FunctionSpace, shape: Shape) -> np.ndarray:
    raise NotImplementedError((type(space).__name__, type(shape).__name__))


@singledispatch
def edge_clustered_nodes_for_space(space: FunctionSpace, shape: Shape) -> np.ndarray:
    raise NotImplementedError((type(space).__name__, type(shape).__name__))


@singledispatch
def random_nodes_for_shape(
        shape: Shape, nnodes: int,
        rng: Optional[np.random.Generator] = None) -> np.ndarray:
    """
    :arg rng: a :class:`numpy.random.Generator`.

    :returns: a :class:`numpy.ndarray` of shape `(dim, nnodes)` of random
        nodes in the reference *shape*.
    """
    raise NotImplementedError(type(shape).__name__)

# }}}


# {{{ PN

@node_tuples_for_space.register(PN)
def _node_tuples_for_pn(space: PN):
    from pytools import (
        generate_nonnegative_integer_tuples_summing_to_at_most as gnitsam,
    )
    return tuple(gnitsam(space.order, space.spatial_dim))


@equispaced_nodes_for_space.register(PN)
def _equispaced_nodes_for_pn(space: PN, shape: Simplex):
    if not isinstance(shape, Simplex):
        raise NotImplementedError((type(space).__name__, type(shape).__name__))
    if space.spatial_dim != shape.dim:
        raise ValueError("spatial dimensions of shape and space must match")

    if space.order == 0:
        return (
                np.mean(unit_vertices_for_shape(shape), axis=1)
                .reshape(-1, 1))
    else:
        return (np.array(node_tuples_for_space(space), dtype=np.float64)
                / space.order*2 - 1).T


@edge_clustered_nodes_for_space.register(PN)
def _edge_clustered_nodes_for_pn(space: PN, shape: Simplex):
    if not isinstance(shape, Simplex):
        raise NotImplementedError((type(space).__name__, type(shape).__name__))
    if space.spatial_dim != shape.dim:
        raise ValueError("spatial dimensions of shape and space must match")

    if space.spatial_dim <= 3:
        return warp_and_blend_nodes(space.spatial_dim, space.order)
    else:
        return equidistant_nodes(space.spatial_dim, space.order)


@random_nodes_for_shape.register(Simplex)
def _random_nodes_for_simplex(shape: Simplex, nnodes: int, rng=None):
    if rng is None:
        rng = np.random.default_rng()

    result = np.zeros((shape.dim, nnodes))
    nnodes_obtained = 0
    while True:
        new_nodes = rng.uniform(-1.0, 1.0, size=(shape.dim, nnodes-nnodes_obtained))
        new_nodes = new_nodes[:, new_nodes.sum(axis=0) < 2-shape.dim]
        nnew_nodes = new_nodes.shape[1]
        result[:, nnodes_obtained:nnodes_obtained+nnew_nodes] = new_nodes
        nnodes_obtained += nnew_nodes

        if nnodes_obtained == nnodes:
            return result

# }}}


# {{{ generic tensor product space

@node_tuples_for_space.register(TensorProductSpace)
def _node_tuples_for_tp(space: TensorProductSpace):
    from pytools import generate_nonnegative_integer_tuples_below as gnitb
    tuples_for_space = [node_tuples_for_space(s) for s in space.bases]

    def concat(tuples):
        return sum(tuples, ())

    # ensure that these start numbering (0,0), (1,0), (i.e. x-axis first)
    space_index_tuples = (
            [tp[::-1] for tp in gnitb([len(tp) for tp in tuples_for_space[::-1]])])
    return tuple([
        concat((
            tuples_for_space[i][j]
            for i, j in enumerate(tp)
            ))
        for tp in space_index_tuples])


@equispaced_nodes_for_space.register(TensorProductSpace)
def _equispaced_nodes_for_tp(
        space: TensorProductSpace,
        shape: TensorProductShape):
    if not isinstance(shape, TensorProductShape):
        raise NotImplementedError((type(space).__name__, type(shape).__name__))

    if space.spatial_dim != shape.dim:
        raise ValueError("spatial dimensions of shape and space must match")

    return tensor_product_nodes([
        equispaced_nodes_for_space(b, s)
        for b, s in zip(space.bases, shape.bases)
        ])


@edge_clustered_nodes_for_space.register(TensorProductSpace)
def _edge_clustered_nodes_for_tp(
        space: TensorProductSpace,
        shape: TensorProductShape):
    if not isinstance(shape, TensorProductShape):
        raise NotImplementedError((type(space).__name__, type(shape).__name__))

    if space.spatial_dim != shape.dim:
        raise ValueError("spatial dimensions of shape and space must match")

    return tensor_product_nodes([
        edge_clustered_nodes_for_space(b, s)
        for b, s in zip(space.bases, shape.bases)
        ])


@random_nodes_for_shape.register(TensorProductShape)
def _random_nodes_for_tp(shape: TensorProductShape, nnodes: int, rng=None):
    if rng is None:
        rng = np.random.default_rng()

    d = 0
    nodes = np.empty((shape.dim, nnodes))
    for s in shape.bases:
        nodes[d:d + s.dim, :] = random_nodes_for_shape(s, nnodes, rng=rng)
        d += s.dim

    return nodes

# }}}

# vim: foldmethod=marker
