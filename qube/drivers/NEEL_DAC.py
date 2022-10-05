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
from math import ceil, floor

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


def floor_decimal(number, decimal):
    """
    number: input number to be rounded down
    decimal: final number of decimals after rounded down
    """
    fact = 10 ** decimal
    n = number * fact
    n = floor(n) / fact
    return n


def ceil_decimal(number, decimal):
    """
    number: input number to be rounded up
    decimal: final number of decimals after rounded up
    """
    fact = 10 ** decimal
    n = number * fact
    n = ceil(n) / fact
    return n


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
        min_value (Optional[float]): safety value for minimum voltage for all channels (if None: use -voltage_range)
        max_value (Optional[float]): safety value for maximum voltage for all channels (if None: use +voltage_range)
    """

    def __init__(self, name: str,
                 bitfile: str,
                 address: str,
                 panels: List[int],
                 delay_between_steps: int = 1,
                 initial_value: Optional[float] = None,
                 min_value: Optional[float] = None,
                 max_value: Optional[float] = None,
                 **kwargs) -> None:
        super().__init__(name, **kwargs)
        self.bitfile = bitfile
        self.address = address
        self.ref = None  # FPGA reference
        self.open()

        # Hardware limitations
        self.max_panels = 8
        self.max_channels = 8
        self.bits_resolution = 15  # 2**bits
        self.voltage_range = 5.0  # +/- value
        self.min_value = float(min_value) if min_value is not None else -self.voltage_range
        self.max_value = float(max_value) if max_value is not None else +self.voltage_range

        # Parameters
        self._panels = panels
        self._delay_between_steps = delay_between_steps

        self.add_parameter('panels',
                           label='List of used panels',
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
        self.lockin = NEEL_DAC_LockIn(parent=self)
        if initial_value is not None:
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

    def move(self, wait_until_end: bool = True):
        """
        Start DAC movement and optional waiting until the end
        """
        self.start()
        if wait_until_end:
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
        while move_bus_ready.read() == False:
            i += 1

    def move_all_to(self, value: Union[int, float]):
        """
        Move all DAC values in the used value to "value".
        Hardware problem: sometimes it does not move to the target value
        Solution: move to value-0.01 and then value to ensure the movement
        Note: 0.01 is a hardcoded value but it can be different
        Comment: set all values before move to move in parallel (to be checked)
        """
        v = [value - 0.01, value]
        for vi in v:
            arr = np.ones((self.max_panels, self.max_panels)) * vi
            self.set_values(arr)

    def move_to(self, panel: int, channel: int, value: Union[int, float]):
        """
        Move a DAC channel to a target value.
        Hardware problem: sometimes it does not move to the target value
        Solution: move to value-0.01 and then value to ensure the movement
        Note: 0.01 is a hardcoded value, but it can be different
        """
        v = [value - 0.01, value]
        for vi in v:
            self.set_value(panel=panel, channel=channel, value=vi)

    def set_value(self, panel: int, channel: int, value: Union[int, float]):
        """
        Change the DAC value of a given panel-channel
        """
        self._send_value_order(panel, channel, value)
        self.move()

    def set_values(self, arr):
        """
        arr: array of values with shape (max_panels x max_channels) --> same as get_values()
        """
        arr = np.array(arr)
        shape = (self.max_panels, self.max_panels)
        if arr.shape != shape:
            raise ValueError(f'Shape of value array should be {shape}')
        for i in range(shape[0]):
            for j in range(shape[1]):
                # Allow parallel movement
                self._send_value_order(panel=i, channel=j, value=arr[i, j])
        self.move()

    def _send_value_order(self, panel, channel, value: float):
        if not self.min_value <= value <= self.max_value:
            raise ValueError(f'{value} is out of the safety limits ({self.min_value} V, {self.max_value} V)')
        res = 2 ** self.bits_resolution
        vrange = self.voltage_range
        bit_value = np.int16(value / vrange * res) + res
        a, b = split_number(bit_value, size=16)
        order_number = join_8_8bit264bit(1, 4, 0, 0, panel, channel, a, b)
        self.send_Xmit_order(order_number)

    def get_values(self, precision: Optional[int] = 4):
        """
        Get current values of DAC
        """
        # TODO: move this block to dac.panel.channel and check if panel or channel is first
        values = np.zeros((self.max_panels, self.max_channels), dtype=float)
        for panel in self.panels():
            for channel in range(self.max_channels):
                values[panel, channel] = self.get_value(panel, channel, precision)
        return values

    def get_value(self, panel, channel, precision: Optional[int] = 4):
        # Get rid of an eventual unfinished retrieving sequence
        get_value = self.ref.registers['get DAC value']
        got_value = self.ref.registers['got DAC value']
        got_value.write(True)
        while get_value.read():
            got_value.write(True)

        # Read values
        retrieve = self.ref.registers['DAC to retrieve']
        data = self.ref.registers['DAC data']

        res = 2 ** self.bits_resolution
        vrange = self.voltage_range
        to_real_unit = lambda v: (v - res) / res * vrange

        num = panel * self.max_panels + channel
        retrieve.write(num)
        got_value.write(True)
        get_value.write(True)
        while got_value.read():
            pass
        value = data.read()
        panel_channel, value = split_number(value, size=32)
        # panel = int(panel_channel) // self.max_panels
        # channel = int(panel_channel) % self.max_channels
        value = to_real_unit(value)
        got_value.write(True)
        if precision:
            value = np.round(value, precision)
        return value

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
    JL: I don't like that this is an instrument channel. It can be simply a Parameter class.

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
                 # value: float = -0.0003,  # JL: weird default value
                 alias: str = None,
                 **kwargs) -> None:
        super().__init__(parent, name, **kwargs)
        self.dac = self._parent.dac
        self.panel = self._parent.panel_number
        self.channel = channel
        self._v = None
        self.alias = alias  # JL: not used?

        self.add_parameter('v',
                           label='Value',
                           unit='V',
                           scale=1.0,
                           get_cmd=self.get_value,
                           set_cmd=self.set_value,
                           get_parser=float,
                           set_parser=float,
                           vals=vals.Numbers(self.dac.min_value, self.dac.max_value),
                           )

    def get_value(self):
        return self.dac.get_value(self.panel, self.channel)

    def set_value(self, value: float):
        # Set DAC value if it is not np.nan.
        if not np.isnan(value):
            # self.dac.move_to(panel=self.panel, channel=self.channel, value=value)
            self.dac._send_value_order(panel=self.panel, channel=self.channel, value=value)
            # self.dac.move(wait_until_end=wait_until_end)
        self._v = value


class NEEL_DAC_Sequencer(InstrumentChannel):
    """
    This class holds information about fast sequence

    Args:
        parent (Instrument): NEEL_DAC
        n_channels (int): number of usable channels for pulse sequence (for old bitfile: 16)

    Comments:
        [JL] Ramp mode = True --> the time between each order is set to be "sample_time" value (in ms)
        [JL] Ramp mode = False --> it won't use the sample_time value
        [JL] Total sequence time = max((sample_count + 1 ) * sample_time, sum(wait))
        [JL] Do not let the user change sample_count, autoset sample_count instead to avoid problems
        [JL] I don't find any effect of trigger_length...
    """

    # [27/09/2022] Calibrated time delays with DAC of Wodan by Junliang
    delay_move = 16.14  # us
    delay_wait_offset = 1.26  # us
    delay_wait_value = 1.05
    delay_trigger = 0.028  # us
    delay_jump = 0.488  # us

    # ramp_wait_correction = 0.951  # for sample_time > 500 us

    def __init__(self,
                 parent: Instrument,
                 n_channels: int = 16,
                 ramp_mode: bool = False,
                 sample_time: Union[int, float] = 1,  # ms
                 trigger_length: int = 100,  # us
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
        self.max_slots = 4096  # hardcoded from old driver

        self.n_loop = 1
        self.default_flags = {
            'start': 0,
            'end_presequence': 0,
            'end_sequence': 1,
        }
        self.flags = dict(self.default_flags)

        # Parameters
        self._status = False
        self._sample_time = sample_time  # ms
        self._sample_count = 3
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

        # JL: divider is not the best name --> sample_time
        self.add_parameter('sample_time',
                           label='Time between each sample count',
                           unit='ms',
                           get_cmd=self.get_sample_time,
                           set_cmd=self.set_sample_time,
                           get_parser=float,
                           set_parser=float,
                           vals=vals.Numbers(4.6e-4, 450),
                           initial_value=self._sample_time,
                           )

        # JL: ramp_mode is not the best name
        # Ramp mode means sequential execution of orders with "divider" time in between
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
                           vals=vals.Ints(-1, 4096),  # 4096 Hardware limitation? -1 is for testing
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

        self.reset()

    """
    reset/start/stop sequence
    """

    def reset(self):
        self.stop()
        self.set_sample_count(1)
        self._reset_orders()
        self._reset_channels()
        self.n_loop = 1
        self.flags = dict(self.default_flags)
        self.add_slot_init()

    def _reset_orders(self):
        self.slots = OrderedDict()
        self.orders_ref = dict(self.default_orders_ref)
        self._raw_orders = []
        self._raw_values = []
        self.orders = []

    def _reset_channels(self):
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
        Trigger the start of the pulse sequence.
        It verifies and corrects the orders prior execution.
        - Find if there is at least one "jump" order. If not, add it.
        - Correct jump value depending on the number of loops.
        - Set sample_count according to the number of sequence repetitions
        """
        self.correct_sequence()
        self._update_sample_count()
        self._start()

    def correct_sequence(self):
        # Find jump order
        has_jump_slot, slot_index, jump_param = self._find_first_jump_order()
        if not has_jump_slot:
            jump_param = self.add_slot_end()
            last_index = self.get_last_slot_index()
        else:
            self._remove_slots_after_index(slot_index)
            jump_value = jump_param()
            last_index = self.get_last_slot_index()
            if jump_value != last_index:
                self.flags['end_presequence'] = jump_value

        # update end_sequence flag
        self.flags['end_sequence'] = last_index + 1

        # Update jump value for loop
        if self.n_loop == 1:
            jump_param(last_index)
        else:
            jump_param(self.flags['end_presequence'])

    def _find_first_jump_order(self):
        try:
            slot_index = next(i for i, info in enumerate(self.orders) if info[0] == 'jump')
            jump_param = self.get_slot_param_by_index(slot_index)
            has_jump_slot = True
        except:
            has_jump_slot = False
            slot_index, jump_param = None, None
        return has_jump_slot, slot_index, jump_param

    def _remove_slots_after_index(self, idx):
        idx = idx + 1  # keep slot at idx; remove from next one
        self.orders = self.orders[:idx]
        self._raw_orders = self._raw_orders[:idx]
        self._raw_values = self._raw_values[:idx]
        slots = OrderedDict()
        for i, (key, value) in enumerate(self.slots.items()):
            if i == idx:
                break
            slots[key] = value
        self.slots = slots

    def _update_sample_count(self):
        ramp = self.ramp_mode()
        if ramp:
            sc = self._calculate_sample_count_ramp()
        else:
            sc = self._calculate_sample_count()
        self.sample_count(sc)

    def _start(self):
        """
        Start fast sequence
        """
        self.status(True)

    @property
    def presequence_orders(self):
        idx = self.flags['end_presequence']
        return self.orders[:idx]

    @property
    def sequence_orders(self):
        idx1 = self.flags['end_presequence']
        idx2 = self.flags['end_sequence']
        return self.orders[idx1:idx2]

    """
    Calculate timing for parallel execution (ramp_mode = False)
    """

    def _calculate_sample_count_ramp(self):
        preseq_sc = self._orders_ramp_sample_count(self.presequence_orders)
        single_seq_sc = self._orders_ramp_sample_count(self.sequence_orders)
        total_sc = preseq_sc + single_seq_sc * self.n_loop
        return total_sc

    def _orders_ramp_sample_count(self, orders):
        """
        Args:
            orders: list of order and value. For example: [['wait', 1], ['jump',0], ...]

        Returns: sample count for ramp mode

        """
        waits = []
        moves = []
        for info in orders:
            order, value = info
            if order == 'wait':
                waits.append(value)
            elif order not in ['jump', 'trigger']:
                moves.append(value)

        st = self.sample_time()
        # Wait value has been corrected with the factor
        fact = st  # * self.ramp_wait_correction
        sc_wait = sum([ceil_decimal(vi, 2) // fact for vi in waits])
        sc_move = len(moves)
        sc = int(sc_wait + sc_move)
        return sc

    """
    Calculate sample count for parallel execution (ramp_mode = False)
    """

    def _calculate_sample_count(self):
        if self.n_loop <= 0:
            sample_count = 0
        else:
            total_time = self.estimate_execution_time()
            sample_time = self.sample_time()  # ms
            sample_count = floor(total_time / sample_time)
        return sample_count

    def _orders_execution_time(self, orders):
        """
        Args:
            orders: list of order and value. For example: [['wait', 1], ['jump',0], ...]

        Returns: execution time of orders in ms

        """
        time_us = 0
        for slot in orders:
            order, value = slot
            if order == 'trigger':
                time_us += self.delay_trigger
            elif order == 'wait':
                value = value * 1e3  # to us
                # raw_value of wait has been corrected with self.delay_wait_value
                # therefore value in self.orders is the good one
                time_us += self.delay_wait_offset + value  # * self.delay_wait_value
            elif order == 'jump':  # jump means end of sequence
                time_us += self.delay_jump
                break
            else:  # DAC movement
                time_us += self.delay_move
        time_ms = time_us * 1e-3
        return time_ms

    """
    Time estimation
    """

    def estimate_execution_time(self):
        pre_time = self.estimate_presequence_time()
        seq_time = self.estimate_single_sequence_time()
        total_time = pre_time + seq_time * self.n_loop  # us
        return total_time

    def estimate_presequence_time(self):
        return self.estimate_execution_time_until_flag('end_presequence')

    def estimate_single_sequence_time(self):
        return self.estimate_execution_time_between_flags('end_presequence', 'end_sequence')

    def estimate_execution_time_until_index(self, index):
        return self._orders_execution_time(self.orders[:index])

    def estimate_execution_time_until_flag(self, flag):
        index = self.flags[flag]
        return self.estimate_execution_time_until_index(index)

    def estimate_execution_time_between_indexes(self, index1, index2):
        orders = self.orders[index1:index2]
        ramp = self.ramp_mode()
        if ramp:
            sc = self._orders_ramp_sample_count(orders)
            time = sc * self.sample_time()
        else:
            time = self._orders_execution_time(orders)
        return time

    def estimate_execution_time_between_flags(self, flag1, flag2):
        i1 = self.flags[flag1]
        i2 = self.flags[flag2]
        return self.estimate_execution_time_between_indexes(i1, i2)

    """
    User-friendly print
    """

    def print(self):
        idx_dict = {}
        for name, idx in self.flags.items():
            if idx not in idx_dict.keys():
                idx_dict[idx] = []
            idx_dict[idx].append(name)

        max_idx = max(max(idx_dict.keys()), self.get_last_slot_index())
        text_lines = {i: [] for i in range(max_idx + 1)}
        for idx, names in idx_dict.items():
            flags = ', '.join(names)
            text_lines[idx].append(f'[flags] {flags}')
        for idx, info in enumerate(self.orders):
            order, value = info
            text_lines[idx].append(f'[{idx}] {order}: {value}')
        text = '\n'.join(['\n'.join(line) for line in text_lines.values()])
        print(text)
        if self.n_loop <= 0:
            print(f'Estimated execution time: infinite loop')
        else:
            print(f'Estimated execution time: {self.estimate_execution_time():.2f} ms')

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

    """
    Parameters
    """

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

    def get_sample_time(self):
        return self._sample_time

    def set_sample_time(self, value: Union[int, float]):
        order_number = self._Xmit_order_sample_time(value)
        self.send_Xmit_order(order=order_number)
        self._sample_time = value

    def _Xmit_order_sample_time(self, value: Union[int, float]):
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
        # It is hardcoded (in the bitfile probably) that sample_count = 0 is equivalent to 1
        # Manually correct this by subtracting 1 pt
        value -= 1
        order_number = join_numbers(5, 8, final_size=16)
        order_number = join_numbers(order_number, 0, final_size=32)
        value = join_numbers(0, value, final_size=32)
        order_number = join_numbers(order_number, value, final_size=64)
        return order_number

    def _Xmit_order_sequence_sample_count(self, value: int):
        # It is hardcoded (in the bitfile probably) that sample_count = 0 is equivalent to 1
        # Manually correct this by subtracting 1 pt
        value -= 1
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

    def add_channel(self, param: Union[Parameter, DelegateParameter, NEEL_DAC_Channel]):
        index = len(self.used_channels)
        if index + 1 > self.n_channels:
            raise ValueError(f'Maximum number of DAC channel for sequencing ({self.n_channels}) is reached ')

        if rhasattr(param, 'source.instrument.panel'):
            # For DelegateParameter from controls
            instr = param.source.instrument
            name = param.name
        elif rhasattr(param, 'instrument.panel'):
            # For NEEL_DAC_Channel.v
            instr = param.instrument
            name = instr.name
        elif rhasattr(param, 'panel'):
            # For NEEL_DAC_Channel
            instr = param
            name = instr.v.name
        else:
            raise ValueError('Not a valid sequence channel to move')

        panel = getattr(instr, 'panel')
        channel = getattr(instr, 'channel')
        attr_str = f'p{panel}.c{channel}'
        orders = dict(self.orders_ref)
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
            corrected_v = v / self.delay_wait_value
            self.orders[index][1] = v
            self._raw_values[index] = corrected_v
            self._set_slot_wait(corrected_v, index)

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
            last_index = self.get_last_slot_index()
            if 0 <= v <= last_index:
                self.orders[index][1] = v
                self._raw_values[index] = v
                self._set_slot_jump(v, index)
            else:
                raise ValueError(f'Jump index ({v}) has to be between 0 and the last index ({last_index})')

        name = str(alias) if alias else f's{index}_jump'
        label = f'[{index}] {name}' if alias else f'[{index}] Jump'
        p = Parameter(name=name,
                      label=label,
                      unit='index',
                      set_cmd=_set,
                      get_cmd=_get,
                      initial_value=value,
                      )
        self._add_parameter_to_slots(p)
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
        param = self.add_slot_jump(index + 1)
        return param

    def add_slot_trigger(self, value, alias: Optional[str] = None):
        """
        value = [ True, False, True, ...] or [1,0,1,...] or '1011'
        """

        index = self._add_slot_order(
            order='trigger',
            value=value,
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
            self.orders[index][1] = v

        def _get():
            """
            return a list of boolean like [ True, False, True, ...]
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
        return p

    def _set_slot_trigger(self, value: int, slot_number: int):
        val = (2 << 4)
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
                      # instrument=param.instrument,
                      )
        self._add_parameter_to_slots(p)
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
                      # instrument=param.instrument,
                      )
        self._add_parameter_to_slots(p)
        return p

    def _set_slot_move(self, value: Union[int, float], slot_number: int, channel: int):
        val = channel + (0 << 4)
        order_number = join_numbers(5, 4, final_size=16)
        val = join_numbers(val, 0, final_size=16)
        order_number = join_numbers(order_number, val, final_size=32)

        value = value * 2  # correction
        res = 2 ** self.dac.bits_resolution
        vrange = self.dac.voltage_range
        bit_value = value / vrange * res
        val = join_numbers(slot_number, bit_value, final_size=32)
        order_number = join_numbers(order_number, val, final_size=64)
        self.send_Xmit_order(order_number)

    def add_slot_init(self):
        """
        Default first slot for initializing the sequence.
        This is automatically applied when self.reset() to avoid unexpected behaviours
        """
        param = self.add_slot_trigger([0] * 5, alias='init_triggers')
        return param

    def _add_slot_order(self, order: str, value):
        if order in self.orders_ref.keys():
            self.orders.append([order, value])
        else:
            raise KeyError(f'{order} is not a valid order')
        if len(self.slots) >= self.max_slots:
            raise ValueError(f'Maximum number of slots ({self.max_slots} has been reached')
        index = self._add_raw_order_value(self.orders_ref[order], value)
        self.flags['end_sequence'] = index + 1
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
        return len(self.orders) - 1

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

    def add_flag(self, name, overwrite=False):
        index = self.get_last_slot_index() + 1
        if not overwrite and name in self.flags.keys():
            raise KeyError(f'Flag "{name}" is already defined')
        self.flags[name] = index
        return index

    def flag_end_presequence(self):
        self.add_flag('end_presequence', overwrite=True)

    def add_slot_jump_to_init(self):
        index = self.flags['end_presequence']
        param = self.add_slot_jump(index)
        return param

    def repeat_sequence(self, n: int):
        """
        n: number of sequence repetitions (n=0: infinite loop)
        """
        self.n_loop = n

    def repeat_infinite(self):
        self.repeat_sequence(n=0)


class NEEL_DAC_LockIn(InstrumentChannel):
    """
    This class holds information about Lock-In mode
    NOTE: not tested

    Args:
        parent (Instrument): NEEL_DAC
    """

    def __init__(self,
                 parent: Instrument,
                 **kwargs) -> None:
        super().__init__(parent, 'lock_in', **kwargs)
        self.dac = self._parent
        self._status = False
        self._frequency = 1  # Hz
        self._amplitude = 0  # V
        self._channel = [0, 0]  # [panel, channel]

        self.add_parameter('status',
                           label='Lock-in status',
                           get_cmd=self.get_status,
                           set_cmd=self.set_status,
                           initial_value=self._status,
                           )

        self.add_parameter('frequency',
                           label='Lock-in frequency',
                           unit='Hz',
                           get_cmd=self.get_frequency,
                           set_cmd=self.set_frequency,
                           get_parser=float,
                           set_parser=float,
                           post_delay=0.45,  # HE: wait after move such that the lock-in-detector can follow
                           vals=vals.Numbers(1.0, 50000.0),
                           initial_value=self._frequency,
                           )

        self.add_parameter('amplitude',
                           label='Lock-in amplitude',
                           unit='V',
                           get_cmd=self.get_amplitude,
                           set_cmd=self.set_amplitude,
                           get_parser=float,
                           set_parser=float,
                           post_delay=0.45,  # HE: wait after move such that the lock-in-detector can follow
                           # vals=vals.Numbers(0.0, abs(self.dac.voltage_range)),
                           initial_value=self._amplitude,
                           )

        self.add_parameter('channel',  # HE
                           label='Lock-in channel',
                           get_cmd=self.get_channel,
                           set_cmd=self.set_channel,
                           get_parser=list,
                           set_parser=list,
                           vals=vals.Lists(vals.Ints(0, self.dac.max_channels)),
                           initial_value=self._channel,
                           )

        self.configure_analysis()
        self.stop()

    def stop(self):
        """
        Stop lock-in output if running.
        """
        self.status(False)

    def start(self):
        """
        Start lock-in output
        """
        self.status(True)

    def send_Xmit_order(self, order: int, stop: bool = True):
        """
        order: Xmit order
        stop: flag to stop lock-in output before sending the order
        """
        if self._status and stop:  # running and stop flag
            self.stop()
        self.dac.send_Xmit_order(order)

    def get_status(self):
        return self._status

    def set_status(self, val: bool):
        self._status = val
        stop = not val
        v = 1 if stop else 0
        order_number = join_8_8bit264bit(2, 3, 0, 0, 0, 0, 0, v)
        self.send_Xmit_order(order_number, stop=False)

    def get_frequency(self):
        return self._frequency

    def set_frequency(self, value: float):
        """
        Stop before sending order + Start
        value: frequency in Hz
        """
        self._frequency = value
        order_number = self._Xmit_order_frequency(value)
        self.send_Xmit_order(order_number, stop=True)

    def _Xmit_order_frequency(self, value: float):
        f = 25000 / value
        if f < 1:
            f = 1
        elif f > 4e9:
            f = 4e9
        f = np.uint32(f)
        a, b = split_number(f, size=32)
        c, d = split_number(a, size=16)
        e, f = split_number(b, size=16)
        order_number = join_8_8bit264bit(2, 4, 0, 0, c, d, e, f)
        return order_number

    def get_amplitude(self):
        return self._amplitude

    def set_amplitude(self, value: float):
        self._amplitude = np.abs(value)
        order_number = self._Xmit_order_amplitude(value)
        self.send_Xmit_order(order_number, stop=True)

    def _Xmit_order_amplitude(self, value: float):
        vrange = abs(self.dac.voltage_range)
        value = -vrange if value < -vrange else value
        value = +vrange if value > +vrange else value
        vmax = 2 * vrange

        value = value * 2  # correction
        res = 2 ** self.dac.bits_resolution
        a = value / vmax * res
        a = np.uint16(a)
        b, c = split_number(a, 16)
        order_number = join_8_8bit264bit(2, 2, 0, 0, 0, 0, b, c)
        return order_number

    def get_channel(self):
        return self._channel

    def set_channel(self, value: List[int]):
        panel, channel = value
        order_number = join_8_8bit264bit(2, 1, 0, 0, 0, 0, panel, channel)
        self.send_Xmit_order(order_number, stop=True)
        self._channel = value

    def set_channel_by_param(self, param: Union[Parameter, DelegateParameter, NEEL_DAC_Channel]):
        if rhasattr(param, 'source.instrument.panel'):
            # For DelegateParameter from controls
            instr = param.source.instrument
        elif rhasattr(param, 'instrument.panel'):
            # For NEEL_DAC_Channel.v
            instr = param.instrument
        elif rhasattr(param, 'panel'):
            # For NEEL_DAC_Channel
            instr = param
        else:
            raise ValueError('Not a valid parameter')
        panel = instr.panel
        channel = instr.channel
        self.set_channel([panel, channel])

    """
    Analysis
    JL: What are all these "analysis" parameters?
    """

    def configure_analysis(self):
        # JL: I don't know what is this so I copy/paste from the old driver
        self.set_anlaysis_send_back_data(1)  # average
        self.set_analysis_dt_over_tau(8.00006091594696044921875000000000E-6)

    def set_anlaysis_send_back_data(self, value: int):
        """
        value: 0 (lock-in) and 1 (average)
        JL: What is this?
        """
        order_number = join_8_8bit264bit(3, 1, 0, 0, 0, 0, 0, value)
        self.send_Xmit_order(order_number, stop=True)

    def set_analysis_dt_over_tau(self, value):
        """
        value: ???
        JL: What is this?
        """
        dt_over_tau = value * (2 ** 32)  # Convert Fixed point to 32 bit integer
        order_number = join_numbers(3, 2, 16)
        order_number = join_numbers(order_number, 0, 32)
        order_number = join_numbers(order_number, dt_over_tau, 64)
        self.send_Xmit_order(order_number, stop=True)

    def set_analysis_null(self):
        order_number = join_8_8bit264bit(3, 0, 0, 0, 0, 0, 0, 0)
        self.send_Xmit_order(order_number, stop=True)

    def set_analysis_voltage_range(self, value: int):
        """
        value: 0 (10V), 1 (5V), 2 (1V)
        JL: What is this?
        """
        order_number = join_8_8bit264bit(3, 3, 0, 0, 0, 0, 0, value)
        self.send_Xmit_order(order_number, stop=True)


class Virtual_NEEL_DAC(NEEL_DAC):
    print_order = False

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        shape = (self.max_panels, self.max_panels)
        self._values = np.zeros(shape)

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

    def move(self, **kwargs):
        """
        Start DAC movement and optional waiting until the end

        Args:
            **kwargs:
        """
        # self.start()
        # self.wait_end_of_move()
        pass

    def get_values(self, *args, **kwargs):
        return self._values

    def set_values(self, arr):
        """
        arr: array of values with shape (max_panels x max_channels) --> same as get_values()
        """
        super().set_values(arr)
        self._values = arr

    def set_value(self, panel: int, channel: int, value: Union[int, float]):
        """
        Change the DAC value of a given panel-channel
        """
        super().set_value(panel, channel, value)
        self._values[panel, channel] = value


class Virtual_NEEL_DAC_Panel(NEEL_DAC_Panel):

    def create_channels(self):
        for channel in range(self.dac.max_channels):
            name = 'c{:d}'.format(channel)  # c stands for channel
            channel_instance = Virtual_NEEL_DAC_Channel(self, name, channel)
            self.add_submodule(name, channel_instance)


class Virtual_NEEL_DAC_Channel(NEEL_DAC_Channel):

    def set_value(self, value: float):
        self.value = value
        self.dac._values[self.panel, self.channel] = value


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
    li = dac.lockin

    """
    seq.add_slot_trigger([0, 0, 0, 0, 0])
    seq.add_slot_wait(1)  # ms
    seq.add_slot_trigger([0, 1, 0, 0, 0])  # trigger ADC
    seq.flag_end_presequence()
    TRR_load = seq.add_slot_move(TRR, -0.1, alias='TRR_load', relative=False)
    TRC_load = seq.add_slot_move(TRC, -0.2, alias='TRC_load', relative=True)
    seq.repeat_sequence(n=100)
    
    """
