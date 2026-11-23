# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT

"""Where Bit World's music plays: the sound outputs, listed and picked from the script.

Needs: boarddev; endpointkit and appkit to list and pick, without which the
music plays through the board's audio out as always.
"""

from boarddev import env_get


def pick_audio_out():
    """Print the sound outputs, choose the one ``BIT_WORLD_AUDIO`` names, and
    return the device to open: None for the default.

    A word of the output's name is enough (``BIT_WORLD_AUDIO=USB``). Without
    it the music plays where the device's choice is, from the connections
    picker or an earlier script. A script picks the same way::

        import endpointkit
        from appkit import connections

        connections.register()
        for ep in endpointkit.endpoints("audio.out"):
            print(ep.id, ep.label)
        endpointkit.select("audio.out", ep.id)
    """
    try:
        import endpointkit
        from appkit import connections
    except ImportError:  # no endpointkit: the board's audio out, as always
        return None
    connections.register()
    want = env_get("BIT_WORLD_AUDIO")
    for ep in endpointkit.endpoints("audio.out"):
        print("Bit World: audio out %r (%s)" % (ep.label, ep.id))
        if want and want.lower() in ep.label.lower():
            endpointkit.select("audio.out", ep.id)
            want = None
    chosen = endpointkit.selected("audio.out")
    if chosen:
        print("Bit World: playing to %r" % chosen[0].label)
    return connections.device(chosen)
