import numpy as np


def s2dB(s):
    """
    Convert given voltage value to dB.

    Args:
        value (Union[float, List[float]]): S parameter in voltage

    Returns:
        db (Union[float, List[float]]): Magnitude of given S paremeter in dB unit
    """
    db = 20 * np.log10(np.abs(s))
    return db


def hz2GHz(hz):
    return hz / 1e9


def sec2ns(sec):
    return sec * 1e9
