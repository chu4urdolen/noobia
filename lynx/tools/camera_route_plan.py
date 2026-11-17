"""Exact media-ctl link changes for the V53 sensor4/sensor2 CAMSV-0 routes.

The IDs are pinned to the saved /dev/media1 graph. This module produces
complete source-to-sink descriptors; a caller must verify the live graph.
"""

ROUTES = {
    4: ((45, 0, 27, 0), (27, 1, 615, 0)),
    2: ((71, 0, 53, 0), (53, 1, 615, 0)),
}


def link_descriptor(link, enabled):
    source, source_pad, sink, sink_pad = link
    # Media Controller requires the DYNAMIC bit (4) on these links even when
    # disabling them. A bare [0] is rejected by this vendor media-ctl.
    return f"{source}:{source_pad}->{sink}:{sink_pad}[{5 if enabled else 4}]"


def plan_route(current, target):
    if current not in ROUTES or target not in ROUTES or current == target:
        raise ValueError("route must switch between sensor4 and sensor2")
    return ([link_descriptor(link, False) for link in reversed(ROUTES[current])]
            + [link_descriptor(link, True) for link in ROUTES[target]])
