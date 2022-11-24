from qcodes.instrument.base import InstrumentBase


class Experiment(InstrumentBase):
    # .sweeper --> .create_sweep()
    # .controls --> from a parameter group class
    # .readouts --> from a parameter group class
    # .layoutviewer
    pass
