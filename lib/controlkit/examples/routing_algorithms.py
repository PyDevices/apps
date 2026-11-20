# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""List the 32 classic six-operator FM algorithms as graphs.

Each entry of ALGORITHMS is ``(edges, carriers, feedback)`` for operators
1 to 6. An edge ``(6, 5)`` means operator 6 modulates operator 5, the
carriers are the operators that are heard, and the feedback pair is the
loop: ``(6, 6)`` is an operator that feeds itself. ``graph(number)`` gives
the four arguments a `RoutingDiagram` takes.

Needs: nothing. It is data, and imports nothing.

Run it:

    from routing_algorithms import graph
    nodes, edges, carriers, feedback = graph(5)

Tested on: the unix port of MicroPython and CPython 3.12 on Linux, through
controls_routing.py.
"""

OPERATORS = (1, 2, 3, 4, 5, 6)

ALGORITHMS = (
    (((2, 1), (6, 5), (5, 4), (4, 3)), (1, 3), (6, 6)),  # 1
    (((2, 1), (6, 5), (5, 4), (4, 3)), (1, 3), (2, 2)),  # 2
    (((3, 2), (2, 1), (6, 5), (5, 4)), (1, 4), (6, 6)),  # 3
    (((3, 2), (2, 1), (6, 5), (5, 4)), (1, 4), (4, 6)),  # 4
    (((2, 1), (4, 3), (6, 5)), (1, 3, 5), (6, 6)),  # 5
    (((2, 1), (4, 3), (6, 5)), (1, 3, 5), (5, 6)),  # 6
    (((2, 1), (4, 3), (5, 3), (6, 5)), (1, 3), (6, 6)),  # 7
    (((2, 1), (4, 3), (5, 3), (6, 5)), (1, 3), (4, 4)),  # 8
    (((2, 1), (4, 3), (5, 3), (6, 5)), (1, 3), (2, 2)),  # 9
    (((3, 2), (2, 1), (5, 4), (6, 4)), (1, 4), (3, 3)),  # 10
    (((3, 2), (2, 1), (5, 4), (6, 4)), (1, 4), (6, 6)),  # 11
    (((2, 1), (4, 3), (5, 3), (6, 3)), (1, 3), (2, 2)),  # 12
    (((2, 1), (4, 3), (5, 3), (6, 3)), (1, 3), (6, 6)),  # 13
    (((2, 1), (4, 3), (5, 4), (6, 4)), (1, 3), (6, 6)),  # 14
    (((2, 1), (4, 3), (5, 4), (6, 4)), (1, 3), (2, 2)),  # 15
    (((2, 1), (3, 1), (5, 1), (4, 3), (6, 5)), (1,), (6, 6)),  # 16
    (((2, 1), (3, 1), (5, 1), (4, 3), (6, 5)), (1,), (2, 2)),  # 17
    (((2, 1), (3, 1), (4, 1), (5, 4), (6, 5)), (1,), (3, 3)),  # 18
    (((3, 2), (2, 1), (6, 4), (6, 5)), (1, 4, 5), (6, 6)),  # 19
    (((3, 1), (3, 2), (5, 4), (6, 4)), (1, 2, 4), (3, 3)),  # 20
    (((3, 1), (3, 2), (6, 4), (6, 5)), (1, 2, 4, 5), (3, 3)),  # 21
    (((2, 1), (6, 3), (6, 4), (6, 5)), (1, 3, 4, 5), (6, 6)),  # 22
    (((3, 2), (6, 4), (6, 5)), (1, 2, 4, 5), (6, 6)),  # 23
    (((6, 3), (6, 4), (6, 5)), (1, 2, 3, 4, 5), (6, 6)),  # 24
    (((6, 4), (6, 5)), (1, 2, 3, 4, 5), (6, 6)),  # 25
    (((3, 2), (5, 4), (6, 4)), (1, 2, 4), (6, 6)),  # 26
    (((3, 2), (5, 4), (6, 4)), (1, 2, 4), (3, 3)),  # 27
    (((2, 1), (5, 4), (4, 3)), (1, 3, 6), (5, 5)),  # 28
    (((4, 3), (6, 5)), (1, 2, 3, 5), (6, 6)),  # 29
    (((5, 4), (4, 3)), (1, 2, 3, 6), (5, 5)),  # 30
    (((6, 5),), (1, 2, 3, 4, 5), (6, 6)),  # 31
    ((), (1, 2, 3, 4, 5, 6), (6, 6)),  # 32
)


def graph(number):
    """The nodes, edges, carriers and feedback of algorithm *number*, 1 to 32."""
    edges, carriers, feedback = ALGORITHMS[number - 1]
    return OPERATORS, edges, carriers, feedback
