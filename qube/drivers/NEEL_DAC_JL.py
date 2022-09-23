# -*- coding: utf-8 -*-
"""
Created 2018/12 by Shintaro
Modified 2021/02 by Hermann for usage at Wodan; look for "HE:"
Updated 2022/09 by Junliang
"""

import logging
from collections import OrderedDict
from typing import Union, List, Optional

import numpy as np
from nifpga import Session
from qcodes import Instrument, Parameter, DelegateParameter
from qcodes import validators as vals
from qcodes.instrument.channel import InstrumentChannel

from qube.utils.misc import rhasattr, rgetattr

log = logging.getLogger(__name__)

"""-------------------------
 Utility functions
-------------------------"""


def split_number(a, size=32):
    """
    Split for example 32bit uint to 2 16bit uint.

    Args:
        a:      Input number
        size:   bit size of the input number

    Returns:
        b: from upper bits
        c: from lower bits

    """
    b = 0
    c = 0
    for i in range(size):
        if i < size // 2:
            c += a & 2 ** i
        else:
            if (a & 2 ** i) != 0:
                b += 2 ** (i - size // 2)

    if size == 64:
        b = np.uint32(b)
        c = np.uint32(c)
    elif size == 32:
        b = np.uint16(b)
        c = np.uint16(c)
    elif size == 16:
        b = np.uint8(b)
        c = np.uint8(c)

    return b, c


def join_numbers(a, b, final_size=32):
    """
    Join 2 numbers and make a number with double bit size
    Args:
        a:          input1 (Becomes upper bits)
        b:          input2 (Becomes lower bits)
        final_size: bit size of the returned number

    Returns:
        c:      Joined number
    """
    if final_size == 64:
        a = np.uint32(a)
        b = np.uint32(b)
        c = (a << 32) + b
        c = np.uint64(c)
    elif final_size == 32:
        a = np.uint16(a)
        b = np.uint16(b)
        c = (a << 16) + b
        c = np.uint32(c)
    elif final_size == 16:
        a = np.uint8(a)
        b = np.uint8(b)
        c = (a << 8) + b
        c = np.uint16(c)

    return c


def join_8_8bit264bit(a, b, c, d, e, f, g, h):
    """
    Join 8 8bit unsigned integer into 64bit unsigned integer.
    Args:
        a,b,c,d,: 8bit unsigned integers
        (a: uuu, b: uul, c: ulu, d: ull, ...)

    Returns:
        result: 64 bit unsined integer
    """
    i = join_numbers(a, b, 16)
    j = join_numbers(c, d, 16)
    k = join_numbers(e, f, 16)
    l = join_numbers(g, h, 16)

    m = join_numbers(i, j, 32)
    n = join_numbers(k, l, 32)

    result = join_numbers(m, n, 64)

    return result


def ms2FS_divider(ms: Union[int, float] = 3.0) -> int:
    """
    Convert duration (ms) of pulse for ramp mode.
    Typical values: 3 ms -> 6661, 20 ms -> 44439

    Args:
        ms (float): Duration between each trigger pulse for ramp mode (trigger 1, active when it is off).

    Return:
        divider (int)
    """
    if ms < 0:
        # Make minimum to be about 100 us.
        ms = 220
    elif ms < 10.0:
        ms = int(ms / 3 * 6661)
    else:
        ms = int(ms / 20 * 44439)

    return ms


def get_FS_channel(panel, channel):
    return panel * 8 + channel


def split_FS_channel(number):
    panel = number // 8
    channel = number % 8
    return panel, channel


"""----------------
Define classes
------------------"""


class NEEL_DAC(Instrument):
    """
    This is the qcodes driver for NEEL DAC controlled by National Instruments single board RIO 9612.

    Args:
        name (str): name of the instrument
        bitfile(str): path to the bit file
        address (str): IP address of NI sbrio9612 (can be checked by NI MAX)
        panels (List[int]): list of DAC value to be used
        delay_between_steps (int): time delay between DAC movements for DC value in ms
    """

    def __init__(self, name: str,
                 bitfile: str,
                 address: str,
                 panels: List[int],
                 delay_between_steps: int = 1,
                 initial_value=None,
                 **kwargs) -> None:
        super().__init__(name, **kwargs)
        self.bitfile = bitfile
        self.address = address
        self.ref = None  # FPGA reference
        self.last_retrieved_values = None  # array of panels x channels

        # Hardware limitations
        self.max_panels = 8
        self.max_channels = 8
        self.bits_resolution = 15  # 2**bits
        self.voltage_range = 5  # +/- value

        # Parameters
        self._panels = panels
        self._delay_between_steps = delay_between_steps

        self.add_parameter('panels',
                           label='Used DAC value',
                           get_cmd=self.get_panels,
                           set_cmd=self.set_panels,
                           initial_value=panels,
                           )

        self.add_parameter('delay_between_steps',
                           label='Wait time of DAC bit movement',
                           unit='ms',
                           get_cmd=self.get_delay_between_steps,
                           set_cmd=self.set_delay_between_steps,
                           get_parser=int,
                           set_parser=int,
                           vals=vals.Ints(0, 5),  # is it correct this limit?
                           initial_value=delay_between_steps,
                           )

        self.sequencer = NEEL_DAC_Sequencer(parent=self)
        self.open()
        if initial_value:
            self.move_all_to(initial_value)

    """===================================
    Communication
    ==================================="""

    def open(self):
        """
        Open FPGA reference and return it.
        """
        self.ref = Session(bitfile=self.bitfile, resource='rio://' + self.address + '/RIO0')
        return self.ref

    def close(self):
        """
        Close FPGA reference
        """
        self.ref.close()

    def send_Xmit_order(self, order=0):
        """
        Main program to send an order to FPGA.

        Arg:
            order: uint64
        """
        order_in = self.ref.registers['order in']
        order_Xmitted = self.ref.registers['order Xmitted']

        order_in.write(order)
        order_Xmitted.write(True)

        i = 0
        while order_Xmitted.read():
            i += 1

    """===================================
    Alias for methods
    ==================================="""
    # def initialize(self, *args, **kwargs):
    #     pass
    #     initialize = init;
    #
    # initialise = init;
    # DAC_init_values = init

    """===================================
    Movements
    ==================================="""

    def move(self):
        """
        Start DAC movement and optional waiting until the end
        """
        self.start()
        self.wait_end_of_move()

    def start(self):
        """
        Start DAC movement
        """
        order_number = join_8_8bit264bit(1, 2, 0, 0, 0, 0, 0, 0)
        self.send_Xmit_order(order_number)

    def stop(self):
        """
        Stop DAC movement
        """
        order_number = join_8_8bit264bit(1, 5, 0, 0, 0, 0, 0, 0)
        self.send_Xmit_order(order_number)

    def wait_end_of_move(self):
        """
        Wait until all the DAC movement finishes.
        """
        move_bus_ready = self.ref.registers['move bus ready']
        i = 0
        while move_bus_ready.read():
            i += 1

    def move_all_to(self, value: Union[int, float]):
        """
        Move all DAC values in the used value to "value".
        Hardware problem: sometimes it does not move to the target value
        Solution: move to value-0.01 and then value to ensure the movement
        Note: 0.01 is a hardcoded value but it can be different
        Comment: set all values before move to move in parallel (to be checked)
        """
        for v in [value - 0.01, value]:
            for i in self.get_panels():
                for j in range(self.max_channels):
                    self.set_value(panel=i, channel=j, value=v)
            self.move()

    def move_to(self, panel: int, channel: int, value: Union[int, float]):
        """
        Move a DAC channel to a target value.
        Hardware problem: sometimes it does not move to the target value
        Solution: move to value-0.01 and then value to ensure the movement
        Note: 0.01 is a hardcoded value but it can be different
        """
        self.set_value(panel=panel, channel=channel, value=value - 0.01)
        self.move()
        self.set_value(panel=panel, channel=channel, value=value)
        self.move()

    def set_value(self, panel: int, channel: int, value: Union[int, float]):
        """
        Change the DAC value of a given panel-channel
        """
        ch = rgetattr(self, f'p{panel}.c{channel}')
        ch.v(value)

    def get_values(self, precision: int = 4, from_buffer: bool = False):
        if self.last_retrieved_values is None or from_buffer is False:
            value = self.get_current_values()
        else:
            value = self.last_retrieved_values
        return np.round(value, precision)

    def get_current_values(self):
        """
        Get current values of DAC
        """
        # TODO: move this block to dac.panel.channel and check if panel or channel is first

        # Get rid of an eventual unfinished retrieving sequence
        get_value = self.ref.registers['get DAC value']
        got_value = self.ref.registers['got DAC value']
        got_value.write(True)
        while get_value.read():
            got_value.write(True)

        # Read values
        retrieve = self.ref.registers['DAC to retrieve']
        data = self.ref.registers['DAC data']

        max_num = self.max_panels * self.max_channels
        res = 2 ** self.bits_resolution
        vrange = self.voltage_range
        to_real_unit = lambda v: (v - res) / res * vrange

        values = np.zeros((self.max_panels, self.max_channels), dtype=float)
        for i in range(max_num):
            retrieve.write(i)
            got_value.write(True)
            get_value.write(True)
            j = 0
            while got_value.read():
                j += 1
            value = data.read()
            panel_channel, value = split_number(value, size=32)
            panel = int(panel_channel) // self.max_panels
            channel = int(panel_channel) % self.max_channels

            value = to_real_unit(value)
            values[panel, channel] = value

            got_value.write(True)
        self.last_retrieved_values = values
        return values

    """===================================
    get/set for parameters
    ==================================="""

    def get_panels(self):
        return self._panels

    def set_panels(self, value: List[int]):
        # Validate value
        panels_to_use = [False] * self.max_panels
        for n in value:
            if n >= self.max_channels:
                raise ValueError('Panel{:d} is out of range.'.format(n))
            else:
                panels_to_use[n] = True

        # Generate and send Xmit order
        order_number = self._Xmit_order_panels(panels_to_use)
        self.send_Xmit_order(order=order_number)
        self._panels = value

        # Add submodules
        self.create_panels()

    def create_panels(self):
        self.submodules = {}
        for n in self._panels:
            name = f'p{n}'  # p for panel
            panel = NEEL_DAC_Panel(parent=self, name=name, panel_number=n)
            self.add_submodule(name, panel)

    def _Xmit_order_panels(self, value: List[bool]):
        panel = 0
        for i, b in enumerate(value):
            if b:
                panel += 2 ** i
        order_number = join_8_8bit264bit(1, 1, 0, 0, 0, 0, 0, panel)
        return order_number

    def get_delay_between_steps(self):
        return self._delay_between_steps

    def set_delay_between_steps(self, value: int):
        self._delay_between_steps = value
        order_number = self._Xmit_order_delay_between_steps(value)
        self.send_Xmit_order(order=order_number)

    def _Xmit_order_delay_between_steps(self, value: int):
        order_number = join_8_8bit264bit(1, 3, 0, 0, 0, 0, 0, value)
        return order_number


class NEEL_DAC_Panel(InstrumentChannel):
    """
    This class holds information about a panel containing 8 DAC channels.

    Args:
        parent (Instrument): NEEL_DAC
        name (str): name of the panel
        panel_number (int): panel_number (typically 0 ~ 4, max 7)

    """

    def __init__(self, parent: Instrument, name: str, panel_number: int, **kwargs) -> None:
        super().__init__(parent, name, **kwargs)
        self.dac = self._parent
        self.panel_number = panel_number

        # Add dummy parameter since we get error with snapshot without it.
        self.add_parameter('dummy',
                           label='dummy',
                           get_cmd=self.get_dummy,
                           get_parser=int,
                           )

        self.create_channels()

    def create_channels(self):
        for channel in range(self.dac.max_channels):
            name = 'c{:d}'.format(channel)  # c stands for channel
            channel_instance = NEEL_DAC_Channel(self, name, channel)
            self.add_submodule(name, channel_instance)

    def get_dummy(self):
        return 0


class NEEL_DAC_Channel(InstrumentChannel):
    """
    This class holds information about each DAC channel.

    Args:
        parent (InstrumentChannel): NEEL_DAC_Panel
        name (str): name of the channel
        channel (int): channel number (0 ~ 7)
        value (float): output value of the DAC.
    """

    def __init__(self,
                 parent: InstrumentChannel,
                 name: str,
                 channel: int,
                 value: float = -0.0003,  # JL: weird default value
                 vmax: float = 5.0,
                 vmin: float = -5.0,
                 alias: str = None,
                 **kwargs) -> None:
        super().__init__(parent, name, **kwargs)
        self.dac = self._parent.dac
        self.panel = self._parent.panel_number
        self.channel = channel
        self.value = value
        self.alias = alias  # JL: not used?
        self.last_retrieved_value = None

        self.add_parameter('v',
                           label='Value',
                           unit='V',
                           scale=1.0,
                           get_cmd=self.get_value,
                           set_cmd=self.set_value,
                           get_parser=float,
                           set_parser=float,
                           vals=vals.Numbers(vmin, vmax),
                           )

    def get_value(self):
        # # Get rid of an eventual unfinished retrieving sequence
        # dac = self.dac
        # ref = dac.ref
        # get_value = ref.registers['get DAC value']
        # got_value = ref.registers['got DAC value']
        # got_value.write(True)
        # while get_value.read():
        #     got_value.write(True)
        #
        # # Read values
        # retrieve = ref.registers['DAC to retrieve']
        # data = ref.registers['DAC data']
        #
        # res = 2 ** dac.bits_resolution
        # vrange = dac.voltage_range
        # to_real_unit = lambda v: (v - res) / res * vrange
        #
        # values = np.zeros((self.max_panels, self.max_channels), dtype=float)
        #
        # num = self.panel * dac.max_panels + self.channel
        # for i in range(max_num):
        #     retrieve.write(i)
        #     got_value.write(True)
        #     get_value.write(True)
        #     j = 0
        #     while got_value.read():
        #         j += 1
        #     value = data.read()
        #     panel_channel, value = split_number(value, size=32)
        #     panel = int(panel_channel) // self.max_panels
        #     channel = int(panel_channel) % self.max_channels
        #
        #     value = to_real_unit(value)
        #     values[panel, channel] = value
        #
        #     got_value.write(True)
        # self.last_retrieved_values = values
        return self.value

    def set_value(self, value: float):
        # Set DAC value if it is not np.nan.
        if not np.isnan(value):
            # self.dac.move_to(panel=self.panel, channel=self.channel, value=value)
            self._send_value_order(value)
            self.dac.move()
        self.value = value

    def _send_value_order(self, value: float):
        res = 2 ** self.dac.bits_resolution
        vrange = self.dac.voltage_range
        bit_value = np.int16(value / vrange * res) + res
        a, b = split_number(bit_value, size=16)
        order_number = join_8_8bit264bit(1, 4, 0, 0, self.panel, self.channel, a, b)
        self.dac.send_Xmit_order(order_number)


class NEEL_DAC_Sequencer(InstrumentChannel):
    """
    This class holds information about fast sequence

    Args:
        parent (Instrument): NEEL_DAC
        n_channels (int): number of usable channels for pulse sequence (for old bitfile: 16)
    """

    def __init__(self,
                 parent: Instrument,
                 n_channels: int = 16,
                 divider: Union[int, float] = 1,  # ms
                 sample_count: int = 3,
                 trigger_length: int = 100,  # us
                 ramp_mode: bool = False,
                 **kwargs) -> None:
        super().__init__(parent, 'sequence', **kwargs)
        self.dac = self._parent
        self.n_channels = int(n_channels)
        self.default_orders_ref = {
            # 'end': 100,  # DEPRECATED
            'trigger': 101,  # DEPRECATED
            'wait': 102,  # DEPRECATED
            'jump': 103,  # DEPRECATED
            'dummy': 255,  # DEPRECATED
        }
        # Add default references 0-15
        for i in range(self.n_channels):
            self.default_orders_ref[i] = i
        self.valid_raw_orders = tuple(list((self.default_orders_ref.values())))
        self.orders_ref = dict(self.default_orders_ref)

        # Slots
        self.slots = OrderedDict()  # parameter for each slot
        self.used_channels = []
        self._raw_orders = []
        self._raw_values = []
        self.orders = []  # user-friendly order-value list

        # Presequence
        self.prelength = 0
        self.n_loop = 1

        # Parameters
        self._status = False
        self._divider = divider  # ms
        self._sample_count = sample_count
        self._trigger_length = trigger_length  # us
        self._ramp_mode = ramp_mode

        self.add_parameter('status',
                           label='Fast sequence status',
                           get_cmd=self.get_status,
                           set_cmd=self.set_status,
                           get_parser=bool,
                           set_parser=bool,
                           initial_value=self._status,
                           )

        self.add_parameter('divider',
                           label='Fast sequence divider',
                           unit='ms',
                           get_cmd=self.get_divider,
                           set_cmd=self.set_divider,
                           get_parser=float,
                           set_parser=float,
                           vals=vals.Numbers(4.6e-4, 450),
                           initial_value=self._divider,
                           )

        # JL: I have no clue what is the difference between ramp mode T or F
        self.add_parameter('ramp_mode',
                           label='Use ramp mode?',
                           get_cmd=self.get_ramp_mode,
                           set_cmd=self.set_ramp_mode,
                           get_parser=bool,
                           set_parser=bool,
                           initial_value=self._ramp_mode,
                           )

        self.add_parameter('sample_count',
                           label='Fast sequence sample count',
                           get_cmd=self.get_sample_count,
                           set_cmd=self.set_sample_count,
                           get_parser=int,
                           set_parser=int,
                           vals=vals.Ints(1, 2 ** 12),  # 4096 Hardware limitation?
                           initial_value=self._sample_count,
                           )

        self.add_parameter('trigger_length',
                           label='Trigger pulse length',
                           unit='us',
                           get_cmd=self.get_trigger_length,
                           set_cmd=self.set_trigger_length,
                           get_parser=int,
                           set_parser=int,
                           vals=vals.Ints(100, 10000),
                           initial_value=self._trigger_length,
                           )

    def reset(self):
        self.stop()
        self.reset_orders()
        self.reset_channels()
        self.set_ramp_mode(False)
        self.set_sample_count(3)
        self.prelength = 0
        self.n_loop = 1

    def reset_orders(self):
        self.slots = OrderedDict()
        self.orders_ref = dict(self.default_orders_ref)
        self._raw_orders = []
        self._raw_values = []
        self.orders = []

    def reset_channels(self):
        for index in range(self.n_channels):
            self.set_sequence_channel(index, is_dummy=True)
        self.used_channels = []

    def stop(self):
        """
        Stop fast sequence if running.
        """
        self.status(False)

    def start(self):
        """
        Start fast sequence
        Each time fast sequence is started, it is necessary to set sample count.
        """
        self.status(True)

    def get_slot_param_by_index(self, index: int):
        return list(self.slots.values())[index]

    def get_slot_param_by_name(self, name: str):
        if name in self.slots.keys():
            return self.slots[name]
        else:
            raise KeyError(f'Slot parameter ({name}) not found')

    def get_sequence_array(self):
        """
        DEPRECATED
        Old format of setting fast sequence with (2, N) array
        """
        if len(self._raw_orders) != len(self._raw_values):
            raise ValueError('Mismatch between number of orders_ref and values')
        n = len(self._raw_values)
        raw_array = np.array([self._raw_orders, self._raw_values])
        return raw_array

    def send_Xmit_order(self, order: int, stop: bool = True):
        """
        order: Xmit order
        stop: flag to stop fast sequence before sending the order
        """
        if self._status and stop:  # running and stop flag
            self.stop()
        self.dac.send_Xmit_order(order)

    def get_status(self):
        return self._status

    def set_status(self, value: bool):
        """
        Start/Stop fast sequence
        Each time fast sequence is started, it is necessary to set sample count.
        """
        # self.start() if value else self.stop()
        if value:
            sample_count = self.get_sample_count()
            self.set_sample_count(sample_count) if sample_count else 0
        order_number = self._Xmit_order_status(value)
        self.send_Xmit_order(order=order_number, stop=False)  # deactivate stop flag
        self._status = value

    def _Xmit_order_status(self, value: bool):
        n = 2 if value else 1
        order_number = join_8_8bit264bit(5, n, 0, 0, 0, 0, 0, 0)
        return order_number

    def get_divider(self):
        return self._divider

    def set_divider(self, value: Union[int, float]):
        order_number = self._Xmit_order_divider(value)
        self.send_Xmit_order(order=order_number)
        self._divider = value

    def _Xmit_order_divider(self, value: Union[int, float]):
        divider = ms2FS_divider(value)
        order_number = join_numbers(5, 7, final_size=16)
        order_number = join_numbers(order_number, 0, final_size=32)
        order_number = join_numbers(order_number, divider, final_size=64)
        return order_number

    def get_ramp_mode(self):
        return self._ramp_mode

    def set_ramp_mode(self, value: bool):
        self._ramp_mode = value

        if value:
            order_number = self._Xmit_order_unset_stop_count()
        else:
            order_number = self._Xmit_order_unset_ramp()
        self.send_Xmit_order(order=order_number)

        # JL: Reset sample counts because it depends on the mode, but I don't know what's the difference
        self.set_sample_count(self.get_sample_count())

    def _Xmit_order_unset_stop_count(self):
        order_number = join_8_8bit264bit(5, 6, 0, 0, 0, 0, 0, 0)
        return order_number

    def _Xmit_order_unset_ramp(self):
        order_number = join_8_8bit264bit(6, 9, 0, 0, 0, 0, 0, 0)
        return order_number

    def get_sample_count(self):
        return self._sample_count

    def set_sample_count(self, value: int):
        ramp = self.get_ramp_mode()
        if ramp:
            order_number = self._Xmit_order_ramp_sample_count(value)
        else:
            order_number = self._Xmit_order_sequence_sample_count(value)
        self.send_Xmit_order(order=order_number)
        self._sample_count = value

    def _Xmit_order_ramp_sample_count(self, value: int):
        order_number = join_numbers(5, 8, final_size=16)
        order_number = join_numbers(order_number, 0, final_size=32)
        value = join_numbers(0, value, final_size=32)
        order_number = join_numbers(order_number, value, final_size=64)
        return order_number

    def _Xmit_order_sequence_sample_count(self, value: int):
        order_number = join_numbers(5, 5, final_size=16)
        order_number = join_numbers(order_number, 0, final_size=32)
        value = join_numbers(0, value, final_size=32)
        order_number = join_numbers(order_number, value, final_size=64)
        return order_number

    def get_trigger_length(self):
        return self._trigger_length

    def set_trigger_length(self, value: int):
        order_number = self._Xmit_order_trigger_length(value)
        self.send_Xmit_order(order=order_number)
        self._trigger_length = value

    def _Xmit_order_trigger_length(self, value: int):
        order_number = join_numbers(5, 10, final_size=16)
        order_number = join_numbers(order_number, 0, final_size=32)
        length = join_numbers(0, value, final_size=32)
        order_number = join_numbers(order_number, length, final_size=64)
        return order_number

    def add_channel(self, param: Union[Parameter, DelegateParameter]):
        orders = dict(self.orders_ref)
        index = len(self.used_channels)
        if index + 1 > self.n_channels:
            raise ValueError(f'Maximum number of DAC channel for sequencing ({self.n_channels}) is reached ')

        if rhasattr(param, 'source.instrument.panel'):
            # For DelegateParameter from controls
            instr = param.source.instrument
            panel = getattr(instr, 'panel')
            channel = getattr(instr, 'channel')
            name = param.name
        elif rhasattr(param, 'instrument.panel'):
            # For NEEL_DAC_Channel.v
            instr = param.instrument
            panel = getattr(instr, 'panel')
            channel = getattr(instr, 'channel')
            name = instr.name
        else:
            raise ValueError('Not a valid sequence channel to move')

        attr_str = f'p{panel}.c{channel}'
        if attr_str not in orders.keys():
            # Set sequence and update orders_ref and used_channels
            self.set_sequence_channel(index, panel=panel, channel=channel, is_dummy=False)
            orders[attr_str] = index
            orders[name] = index
            self.orders_ref = orders
            self.used_channels.append(attr_str)
        else:
            # Retrieve index from order dictionary
            index = orders[attr_str]
        return name, index

    def set_sequence_channel(self, index: int, panel: int = 0, channel: int = 0, is_dummy: bool = False):
        """
        Allocate DAC panel_channel to fast sequence channels
        """
        if is_dummy:
            panel = 0
            channel = 255
        order_number = join_8_8bit264bit(5, 3, 0, 0, index, 0, panel, channel)
        self.send_Xmit_order(order=order_number)

    def add_slot(self, order: str, *args, **kwargs):
        if order == 'wait':
            self.add_slot_wait(*args, **kwargs)
        elif order == 'jump':
            self.add_slot_jump(*args, **kwargs)
        elif order == 'trigger':
            self.add_slot_trigger(*args, **kwargs)
        elif order == 'move':
            self.add_slot_move(*args, **kwargs)
        elif order == 'end':
            self.add_slot_end()
        else:
            raise KeyError(f'{order} is an invalid sequence order')

    def add_slot_wait(self, value: Union[int, float], alias: Optional[str] = None):
        index = self._add_slot_order(
            order='wait',
            value=value,
        )

        def _get():
            return self.orders[index][1]

        def _set(v):
            self.orders[index][1] = v
            self._raw_values[index] = v
            self._set_slot_wait(v, index)

        name = str(alias) if alias else f's{index}_wait'
        label = f'[{index}] {name}' if alias else f'[{index}] Wait'
        p = Parameter(name=name,
                      label=label,
                      unit='ms',
                      set_cmd=_set,
                      get_cmd=_get,
                      initial_value=value,
                      )
        self._add_parameter_to_slots(p)
        self._update_sample_count()
        return p

    def _set_slot_wait(self, value: Union[int, float], slot_number: int):
        val = (1 << 4)
        order_number = join_numbers(5, 4, final_size=16)
        val = join_numbers(val, 0, final_size=16)

        order_number = join_numbers(order_number, val, final_size=32)

        # Convert time to us
        time_ms = np.abs(value * 1000.0)
        if time_ms < 1:
            # Force wait time above 1 us.
            time_ms = 1.0
        val = np.int64(np.floor(np.log2(time_ms))) - 10
        if val < 0:
            val = 0
        time_ms = np.floor(time_ms * (2.0 ** (-val)))
        if time_ms > ((2 ** 11) - 1):
            # Time(ms) is casted to 11bit in LabVIEW program
            # so I will do the same.
            time_ms = ((2 ** 11) - 1)
        val = time_ms + (val << 11)
        val = join_numbers(slot_number, val, final_size=32)
        order_number = join_numbers(order_number, val, final_size=64)
        self.send_Xmit_order(order_number)

    def add_slot_jump(self, value: int, alias: Optional[str] = None):
        index = self._add_slot_order(
            order='jump',
            value=value,
        )

        def _get():
            return self.orders[index][1]

        def _set(v):
            self.orders[index][1] = v
            self._raw_values[index] = v
            self._set_slot_jump(v, index)

        name = str(alias) if alias else f's{index}_jump'
        label = f'[{index}] {name}' if alias else f'[{index}] Jump'
        p = Parameter(name=name,
                      label=label,
                      unit='index',
                      set_cmd=_set,
                      get_cmd=_get,
                      # vals=vals.Ints(0, self.get_sample_count()),
                      initial_value=value,
                      )
        self._add_parameter_to_slots(p)
        self._update_sample_count()

        return p

    def _set_slot_jump(self, value: int, slot_number: int):
        val = (3 << 4)
        order_number = join_numbers(5, 4, final_size=16)
        val = join_numbers(val, 0, final_size=16)
        order_number = join_numbers(order_number, val, final_size=32)
        val = join_numbers(slot_number, value, final_size=32)
        order_number = join_numbers(order_number, val, final_size=64)
        self.send_Xmit_order(order_number)

    def add_slot_end(self):
        index = self.get_last_slot_index()
        param = self.add_slot_jump(index + 1, alias='end')
        return param

    def add_slot_trigger(self, value, alias: Optional[str] = None):
        """
        value = [ True, False, True, ...] or [1,0,1,...] or '1011'
        """

        index = self._add_slot_order(
            order='trigger',
            value=[0] * 5,
        )

        def _set(v):
            int_value = 0
            for i, vi in enumerate(v):
                if vi not in [0, 1, False, True, '0', '1']:
                    raise ValueError(f'Invalid trigger value: {vi}')
                elif vi in [True, 1]:
                    int_value += 2 ** i
            self._raw_values[index] = int_value
            self._set_slot_trigger(int_value, index)

        def _get():
            """
            :return a list of boolean like [ True, False, True, ...]
            """
            int_value = self._raw_values[index]
            value = []
            for i in range(5):  # hardcoded due to 5 trigger ports
                if not (int_value & 2 ** i) == 0:
                    value.append(True)
                else:
                    value.append(False)
            return value

        name = str(alias) if alias else f's{index}_trigger'
        label = f'[{index}] {name}' if alias else f'[{index}] Trigger'
        p = Parameter(name=name,
                      label=label,
                      unit='index',
                      set_cmd=_set,
                      get_cmd=_get,
                      initial_value=value,
                      )
        self._add_parameter_to_slots(p)
        self._update_sample_count()

        return p

    def _set_slot_trigger(self, value: int, slot_number: int):
        val = (3 << 4)
        order_number = join_numbers(5, 4, final_size=16)
        val = join_numbers(val, 0, final_size=16)
        order_number = join_numbers(order_number, val, final_size=32)
        val = join_numbers(slot_number, value, final_size=32)
        order_number = join_numbers(order_number, val, final_size=64)
        self.send_Xmit_order(order_number)

    def add_slot_move(self, param: Union[Parameter, DelegateParameter], value: Union[int, float],
                      alias: Optional[str] = None, relative=False):
        """
        param: Parameter of NEEL_DAC_Channel or DelegateParameter from controls
        relative: delta voltage shift with respect to the current DC value
        """
        if relative:
            return self.add_slot_move_relative(param, value, alias=alias)
        else:
            return self.add_slot_move_absolute(param, value, alias=alias)

    def add_slot_move_absolute(self, param: Union[Parameter, DelegateParameter], value: Union[int, float],
                               alias: Optional[str] = None):
        """
        param: Parameter of NEEL_DAC_Channel or DelegateParameter from controls
        relative: delta voltage shift with respect to the current DC value
        """
        order_key, channel_index = self.add_channel(param)

        index = self._add_slot_order(
            order=order_key,
            value=value,
        )

        def _get():
            return self.orders[index][1]

        def _set(v):
            dc_value = param()
            delta = v - dc_value
            self.orders[index][1] = v
            self._raw_values[index] = delta
            self._set_slot_move(delta, index, channel_index)

        name = str(alias) if alias else f's{index}_move_{order_key}'
        label = f'[{index}] {name}' if alias else f'[{index}] {order_key}'

        # Find limits
        vrange = abs(self.dac.voltage_range)
        plims = param.vals.valid_values
        lims = plims if plims else [-vrange, +vrange]

        # Create parameter
        p = Parameter(name=name,
                      label=label,
                      unit=param.unit,
                      set_cmd=_set,
                      get_cmd=_get,
                      initial_value=value,
                      vals=vals.Numbers(*lims),
                      instrument=param.instrument,
                      )
        self._add_parameter_to_slots(p)
        self._update_sample_count()

        return p

    def add_slot_move_relative(self, param: Union[Parameter, DelegateParameter], value: Union[int, float],
                               alias: Optional[str] = None):
        """
        param: Parameter of NEEL_DAC_Channel or DelegateParameter from controls
        """
        order_key, channel_index = self.add_channel(param)

        index = self._add_slot_order(
            order=order_key,
            value=value,
        )

        def _get():
            return np.array(self.orders)[index, 1]

        def _set(v):
            dc_value = param()
            target = dc_value + v
            if param.vals.valid_values:
                dc_min, dc_max = param.vals.valid_values
                if not dc_min < target < dc_max:
                    raise ValueError(f'Relative move of {param.name} exceeds the safety limit of the DAC channel')
            self.orders[index][1] = target
            self._raw_values[index] = v
            self._set_slot_move(v, index, channel_index)

        name = str(alias) if alias else f's{index}_move_dV_{order_key}'
        label = f'[{index}] {name}' if alias else f'[{index}] dV_{order_key}'

        p = Parameter(name=name,
                      label=label,
                      unit=param.unit,
                      set_cmd=_set,
                      get_cmd=_get,
                      initial_value=value,
                      instrument=param.instrument,
                      )
        self._add_parameter_to_slots(p)
        self._update_sample_count()

        return p

    def _set_slot_move(self, value: Union[int, float], slot_number: int, channel: int):
        val = channel + (0 << 4)
        order_number = join_numbers(5, 4, final_size=16)
        val = join_numbers(val, 0, final_size=16)
        order_number = join_numbers(order_number, val, final_size=32)

        res = 2 ** self.dac.bits_resolution
        vrange = self.dac.voltage_range
        bit_value = value / vrange * res
        val = join_numbers(slot_number, bit_value, final_size=32)
        order_number = join_numbers(order_number, val, final_size=64)
        self.send_Xmit_order(order_number)

    def _update_sample_count(self):
        index = self.get_last_slot_index()
        self.set_sample_count(index + 1)

    def _add_slot_order(self, order: str, value):
        if order in self.orders_ref.keys():
            self.orders.append([order, value])
        else:
            raise KeyError(f'{order} is not a valid order')
        index = self._add_raw_order_value(self.orders_ref[order], value)
        return index

    def _add_raw_order_value(self, raw_order: int, value):
        self._raw_orders.append(raw_order)
        self._raw_values.append(value)
        index = len(self._raw_values) - 1
        return index

    def _add_parameter_to_slots(self, param: Union[Parameter, DelegateParameter]):
        key = param.name
        if key in self.slots.keys():
            raise KeyError(f'Parameter with name {key} is already in use')
        self.slots[key] = param

    def get_last_slot_index(self):
        return len(self.slots) - 1

    def get_sequence_init_index(self):
        return self.prelength

    def set_sequence_with_array(self, arr):
        """
        DEPRECATED
        This function set slots of fast sequence by the given array.

        Args:
            arr: (2,N) dimensional array

            [Limitation for N: 1<= N <= 2**12 (4096) Hardware limitation?
            (0,:) is parameter (0 ~ 15: fast channels, 101: trigger,
            102: timing (ms), 103: jump, else: jump to its index)

            (1,:) is values. (DAC = value offset,
            trigger = bit wise value for each trigger (1~4, stop)
            timing = ms to wait
            jump = # of slot ot jump
        """
        max_len = 2 ** 12  # why? hardware limitation?
        if arr.shape[1] > max_len:
            arr = arr[:, 0:max_len]

        n = arr.shape[1]
        for index in range(n):
            order = arr[0, index]
            value = arr[1, index]
            if 0 >= order > self.n_channels:
                self._set_slot_move(value, index, order)
            # elif order == 100:
            #     self._set_end_slot(value, index)
            elif order == 101:
                self._set_slot_trigger(value, index)
            elif order == 102:
                self._set_timing_slot(value, index)
            elif order == 103:
                self._set_slot_jump(value, index)
            else:
                raise ValueError(f'{order} is not a valid sequence order number.')

    def end_presequence(self):
        index = self.get_last_slot_index()
        self.prelength = index + 1

    def add_slot_jump_to_init(self):
        index = self.get_sequence_init_index()
        param = self.add_slot_jump(index)
        return param

    def set_loop(self, n: int):
        if n == 0:
            # TODO infinite loop
            pass
        elif n > 0:
            # TODO set new sampling rate accordingly
            pass
        else:
            raise ValueError(f'Invalid loop number (0 = infinite)')
        # self.n_loop = n
        # self.set_sample_count(counts)


# TODO
class NEEL_DAC_LockIn(InstrumentChannel):
    """
    This class holds information about fast sequence

    Args:
        parent (Instrument): NEEL_DAC
    """

    def __init__(self,
                 parent: Instrument,
                 **kwargs) -> None:
        super().__init__(parent, 'lock_in', **kwargs)
        self.dac = self._parent

    def send_Xmit_order(self, order: int):
        self.dac.send_Xmit_order(order)


class Virtual_NEEL_DAC(NEEL_DAC):
    print_order = True

    def open(self):
        print(f'Connected to: Virtual_NEEL_DAC with {self.address}')

    def close(self):
        print(f'Closed connection')

    def send_Xmit_order(self, order=0):
        if self.print_order:
            print(f'Send Xmit order: {order}')

    def create_panels(self):
        self.submodules = {}
        for n in self._panels:
            name = f'p{n}'  # p for panel
            panel = Virtual_NEEL_DAC_Panel(parent=self, name=name, panel_number=n)
            self.add_submodule(name, panel)

    def move(self):
        """
        Start DAC movement and optional waiting until the end
        """
        # self.start()
        # self.wait_end_of_move()
        pass


class Virtual_NEEL_DAC_Panel(NEEL_DAC_Panel):

    def create_channels(self):
        for channel in range(self.dac.max_channels):
            name = 'c{:d}'.format(channel)  # c stands for channel
            channel_instance = Virtual_NEEL_DAC_Channel(self, name, channel)
            self.add_submodule(name, channel_instance)


class Virtual_NEEL_DAC_Channel(NEEL_DAC_Channel):

    def set_value(self, value: float):
        self.value = value


if __name__ == '__main__':
    from qube.measurement.controls import Controls

    dac = Virtual_NEEL_DAC(
        name='DAC',
        bitfile='bitfile',
        address='address',
        panels=[1, 2, 3, 4],
        delay_between_steps=1,
        # initial_value=0,
    )
    dac.print_order = False

    controls = Controls('controls')
    TRR = controls.add_control(
        'TRR',
        source=dac.p2.c2.v,
        label='TRR',
        unit='V',
        initial_value=-1.20,
        vals=vals.Numbers(-2.2, 0.3),
    )

    TRC = controls.add_control(
        'TRC',
        source=dac.p3.c3.v,
        label='TRC',
        unit='V',
        initial_value=-1.30,
        vals=vals.Numbers(-2.2, 0.3),
    )

    seq = dac.sequencer
    seq.set_ramp_mode(False)
    # seq.set_channels([dac.p1.c1, gate1, dac.p3.c3.v, 'random'])
    # print(seq.orders_ref)
    seq.add_slot_trigger([0, 0, 0, 0, 0])
    seq.add_slot_wait(1)  # ms
    seq.add_slot_trigger([0, 1, 0, 0, 0])  # trigger ADC
    TRR_load = seq.add_slot_move(TRR, -0.1, alias='TRR_load', relative=False)
    TRC_load = seq.add_slot_move(TRC, -0.2, alias='TRC_load', relative=True)
    p4c4 = seq.add_slot_move(dac.p4.c4.v, -0.5, alias='p4c4', relative=True)
    random = seq.add_slot_move(dac.p4.c4.v, -1.0, alias='random', relative=False)
    seq.add_slot_end()

    # TRR_back = seq.add_move_slot(TRR, -2.3, alias='TRR_back', relative=False)
    # TRC_back = seq.add_move_slot(TRC, 3, alias='TRC_back', relative=True)

    """
    My snippet for fast sequence

    seq.add_trigger_slot([0,0,0,0,0])
    seq.add_wait_slot(1) # ms
    seq.add_trigger_slot([0,1,0,0,0]) # trigger ADC
    TRR_load = seq.add_move_slot(TRR, -0.1, alias='TRR_load')
    TRC_load = seq.add_move_slot(TRC, -0.2, alias='TRC_load')
    wait_load = seq.add_wait_slot(0.1, alias='wait_load') # ms
    seq.add_move_slot(TRR, 0, alias='TRR_load_back')
    seq.add_move_slot(TRC, 0, alias='TRC_load_back')
    seq.add_wait_slot(1, alias='wait_rise_seg0') # ms
    seq.add_wait_slot(5, alias='wait_int_seg0') # ms
    seq.add_trigger_slot([0,0,0,0,0]) # prepare trigger for SAW
    trigger_SAW = seq.add_trigger_slot([0,0,1,0,0], alias='trigger_SAW') # trigger SAW

    controls.add_control(TRR_load, ...)
    controls.add_control(TRC_load, ...)
    controls.add_control(wait_load, ...)
    controls.add_control(trigger_SAW, ...)

    seq.start()
    """
