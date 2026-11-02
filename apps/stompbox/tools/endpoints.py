"""Open given WASAPI endpoints instead of the defaults, for this process only.

audiodev's win_audio always opens the default endpoint. use(out_id, in_id)
swaps uwin32's default-endpoint lookup for IMMDeviceEnumerator::GetDevice on
the IDs given, so Windows' own defaults never change. An ID looks like
"{0.0.0.00000000}.{786d5d70-...}" (render) or "{0.0.1.00000000}.{...}"
(capture); None keeps the default for that direction.
"""

import uwin32 as win


def _wide(text):
    b = bytearray()
    for ch in text:
        b.append(ord(ch) & 0xFF)
        b.append(ord(ch) >> 8)
    b.extend(b"\0\0")
    return b


def _get_device(enumerator, endpoint_id):
    if win._use_ffi:
        import uctypes

        wid = _wide(endpoint_id)
        out = bytearray(win._PTR_SIZE)
        win._check(win._vcall(enumerator, 5, "i", "pp", wid, out), "GetDevice")
        return win._ptr_read(uctypes.addressof(out))
    from ctypes import POINTER, byref, c_void_p, c_wchar_p

    dev = c_void_p()
    win._check(win._vcall(enumerator, 5, win.HRESULT, (c_wchar_p, POINTER(c_void_p)),
                          endpoint_id, byref(dev)), "GetDevice")
    return dev.value


def use(out_id=None, in_id=None):
    default = win.IMMDeviceEnumerator_GetDefaultAudioEndpoint

    def chosen(enumerator, data_flow, role=win.eConsole):
        want = out_id if data_flow == win.eRender else in_id
        if want:
            return _get_device(enumerator, want)
        return default(enumerator, data_flow, role)

    win.IMMDeviceEnumerator_GetDefaultAudioEndpoint = chosen
