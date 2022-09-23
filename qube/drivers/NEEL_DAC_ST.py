# -*- coding: utf-8 -*-
"""
Created on Thu Dec 20 16:10:38 2018

@author: Shintaro
"""

from qcodes import Instrument, validators as vals
from qcodes.instrument.channel import InstrumentChannel, ChannelList
from qcodes.utils.validators import Validator
from qcodes.instrument.parameter import ArrayParameter

from typing import List, Dict, Callable, Union

from nifpga import Session
from nifpga import nifpga
import time
import numpy as np

import logging

log = logging.getLogger(__name__)

bit_file = '..\\tools\\drivers\\fpgabatchhewodan_sbRIO9612RIO0_hewodan_kUFBPXPrLOs.lvbitx'
ip_address = '192.168.0.3'

"""-------------------------
 Utility functions
-------------------------"""
def split_number(a, size = 32):
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
        if i < size//2:
            c += a & 2**i
        else:
            if (a & 2**i) != 0:
                b += 2**(i-size//2)
                
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

def join_8_8bit264bit(a,b,c,d,e,f,g,h):
    """
    Join 8 8bit unsigned integer into 64bit unsigned integer.
    Args:
        a,b,c,d,: 8bit unsigned integers
        (a: uuu, b: uul, c: ulu, d: ull, ...)
        
    Returns:
        result: 64 bit unsined integer
    """
    i = join_numbers(a,b,16)
    j = join_numbers(c,d,16)
    k = join_numbers(e,f,16)
    l = join_numbers(g,h,16)
    
    m = join_numbers(i,j,32)
    n = join_numbers(k,l,32)
    
    result = join_numbers(m,n,64)
    
    return result

def ms2FS_divider(ms:Union[int, float] = 3.0) -> int:
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
        ms = int(ms /3 * 6661)
    else:
        ms = int(ms / 20 * 44439)
    
    return ms

"""----------------
Define classes
------------------"""    
class NEEL_DAC_channel(InstrumentChannel):
    """
    This class holds information about each DAC channel.
    
    Args:
        parent (InstrumentChannel): NEEL_DAC_Panel
        name (str): name of the channel
        channel (int): channel number (0 ~ 7)
        value (float): output value of the DAC.
    """
    def __init__(self, parent: InstrumentChannel, name:str, channel:int,
                 value:float=-0.0003, **kwargs) -> None:
        super().__init__(parent, name, **kwargs)
        self.dac = self._parent.dac
        self.panel = self._parent.bus_number
        self.channel = channel
        self.val = value
        
        self.add_parameter('value',
                           label='value',
                           unit='V',
                           scale = 1.0,
                           get_cmd = self.get_value,
                           set_cmd = self.set_value,
                           get_parser = float,
                           set_parser = float,
                           vals = vals.Numbers(-5.0, 0.3))
        
    def get_value(self):
        return self.val
    
    def set_value(self, val:float):
        # Set DAC value if it is not np.nan.
        if not np.isnan(val):
            self.dac.DAC_set_value(panel_channel={'panel':self.panel, 'channel':self.channel},
                                   DAC_goto_value=val)
        self.val = val
    
class NEEL_DAC_Bus(InstrumentChannel):
    """
    This class holds information about a bus containing 8 DAC channels.
    
    Args:
        parent (Instrument): NEEL_DAC
        name (str): name of the bus
        bus_number (int): panel_number (typically 0 ~ 4, max 7)
        
    """
    def __init__(self, parent: Instrument, name:str, bus_number:int, **kwargs) -> None:
        super().__init__(parent, name, **kwargs)
        self.dac = self._parent
        self.bus_number = bus_number
        
        # Add dummy parameter since we get error with snapshot without it.
        self.add_parameter('dummy',
                           label='dummy',
                           get_cmd = self.get_dummy,
                           get_parser = int,
                           )
        
        for i in range(8):
            s = 'c{:d}'.format(i)
            chan = NEEL_DAC_channel(self, s, i)
            self.add_submodule(s, chan)
            
    def get_dummy(self):
        return 0
    
class NEEL_DAC(Instrument):
    """
    This is the qcodes driver for NEEL DAC controlled by National Instruments single board RIO 9612.
    
    Args:
        name (str): name of the instrument
        bitFilePath(str): path to the bit file
        address (str): IP address of NI sbrio9612 (can be checked by NI MAX)
        LI_frequency (float): lock-in frequency
        LI_amplitude (float): lock-in amplitude
        LI_channel (int): panel = N // 8, channel = N % 8
        LI_status (bool): status of lock-in (On: True, Off: False)
        used_buses (List[int]): list of DAC value to be used
        ms2wait (int): wait time between each DAC bit movement
        FS_divider (Union[float, int]): For fast sequence ramp mode it determines time between each DAC step (ms). (trigger from DIO1/panel 9)
                          For fast sequence mode it determines time of pulse from DIO1/panel 9.
        FS_ramp (bool): ramp mode (True) or not (False)
        FS_pulse_len (int): Length of trigger (check minimum trigger length of each instrument, which accept the trigger.)
        FS_chan_list (List[int]): List of fast sequence channel (up to 16 channels). Pannel = N //8, channel = N % 8, Dummy = 255
        FS_status (bool): whether fast sequence is running (True) or not (False).
        FS_sample_count (int): Length of the fast sequence slot
        FS_move_limit (List[float, float]): minimum and maximum for the dac movement for fast ramp and sequence.
    """
    def __init__(self, name:str,bitFilePath:str=bit_file,
                 address:str=ip_address, LI_frequency:float=23.3,
                 LI_amplitude:float=0.0, LI_channel:int=0, LI_status:bool=False,
                 used_buses:List[int]=[0,1,2,3], ms2wait:int=1,
                 FS_divider:Union[int, float]=3, FS_ramp:bool=True, FS_pulse_len:int=100,
                 FS_chan_list:List[int]=list(range(16)), FS_status:bool=False,
                 FS_sample_count:int=10, FS_move_limit:List[float]=[-0.5, 0.3],
                 **kwargs) -> None:
        super().__init__(name, **kwargs)
        # Address information
        self.bitFilePath = bitFilePath
        self.address =address
        # Define reference to access FPGA.
        self.ref = None
        self.openRef()
        # lock-in related parameters
        self._LI_status = LI_status
        self._LI_frequency = LI_frequency
        self._LI_amplitude = LI_amplitude
        self._LI_channel = LI_channel
        # DAC related parameters
        self._used_buses = used_buses
        self._ms2wait = ms2wait
        # Fast sequence realted parameters
        self._FS_divider = FS_divider
        self._FS_ramp = FS_ramp
        self._FS_pulse_len = FS_pulse_len
        self._FS_chan_list = FS_chan_list
        self._FS_status = FS_status
        self._FS_sample_count = FS_sample_count
        self._FS_move_limit = FS_move_limit
        
        seq = np.zeros((2,10), dtype=float)
        seq[:, 0] = [101, 0]
        seq[:, 9] = [103, 9]
        self._FS_slots = seq
        
        self.add_parameter('LI_status',
                           label='Lock-in status',
                           get_cmd=self.get_lock_in_status,
                           set_cmd=self.set_lock_in_status)
        
        self.add_parameter('LI_frequency',
                           label='Lock-in frequency',
                           get_cmd=self.get_lock_in_frequency,
                           set_cmd=self.set_lock_in_frequency,
                           get_parser=float,
                           set_parser=float,
                           vals=vals.Numbers(0.0, 50000.0))
        
        self.add_parameter('LI_amplitude',
                           label='Lock-in amplitude',
                           get_cmd=self.get_lock_in_amplitude,
                           set_cmd=self.set_lock_in_amplitude,
                           get_parser=float,
                           set_parser=float,
                           vals=vals.Numbers(0.0, 2.0))
        
        self.add_parameter('LI_channel',
                           label='Lock-in channel',
                           get_cmd=self.get_lock_in_channel,
                           set_cmd=self.set_lock_in_channel,
                           get_parser=int,
                           set_parser=int,
                           vals=vals.Ints(0, 63))
        
        self.add_parameter('value',
                           label='Used DAC value',
                           get_cmd=self.get_used_buses,
                           set_cmd=self.set_used_buses)
        
        self.add_parameter('ms2wait',
                           label='Wait time of DAC bit movement',
                           unit = 'ms',
                           get_cmd=self.get_ms2wait,
                           set_cmd=self.set_ms2wait,
                           get_parser=int,
                           set_parser=int,
                           vals=vals.Ints(0,5))
        
        self.add_parameter('FS_divider',
                           label='Fast sequence divider',
                           unit = 'ms',
                           get_cmd = self.get_FS_divider,
                           set_cmd = self.set_FS_divider,
                           get_parser=float,
                           set_parser=float,
                           vals=vals.Numbers(4.6e-4, 450))
        
        self.add_parameter('FS_ramp',
                           label='Fast sequence ramp mode',
                           get_cmd = self.get_FS_ramp,
                           set_cmd = self.set_FS_ramp,
                           get_parser = bool,
                           set_parser = bool)
        
        self.add_parameter('FS_pulse_len',
                           label='Fast sequence pulse length',
                           get_cmd = self.get_FS_pulse_len,
                           set_cmd = self.set_FS_pulse_len,
                           get_parser = int,
                           set_parser = int,
                           vals=vals.Ints(100, 10000))
        
        self.add_parameter('FS_chan_list',
                           label='Fast sequence channel list',
                           get_cmd = self.get_FS_chan_list,
                           set_cmd = self.set_FS_chan_list)
        
        self.add_parameter('FS_status',
                           label='Fast sequence status',
                           get_cmd = self.get_FS_status,
                           set_cmd = self.set_FS_status,
                           get_parser=bool,
                           set_parser=bool)
        
        self.add_parameter('FS_sample_count',
                           label='Fast sequence sample count',
                           get_cmd = self.get_FS_sample_count,
                           set_cmd = self.set_FS_sample_count,
                           get_parser=int,
                           set_parser=int,
                           vals=vals.Ints(1, 100000))
        
        self.add_parameter('FS_move_limit',
                           label='Fast sequence DAC move limit',
                           unit = 'V',
                           get_cmd = self.get_FS_move_limit,
                           set_cmd = self.set_FS_move_limit)
        
        self.add_parameter('FS_slots',
                           label = 'Fast sequence slots',
                           get_cmd = self.get_FS_slots,
                           set_cmd = self.set_FS_slots,
                           snapshot_get = False,
                           snapshot_value = False,)
        
        # Initialize used value
        self.set_used_buses(used_buses)
        self.set_ms2wait(ms2wait)
        # Define Buses
        for n in self._used_buses:
            if 0 <= n <=7:
                s = 'p{:d}'.format(n)
                bus = NEEL_DAC_Bus(self, s, n)
                self.add_submodule(s, bus)
        
    def get_lock_in_status(self):
        return self._LI_status
    
    def set_lock_in_status(self, val: bool):
        self._LI_status = val
        self.lock_in_send_order(order=3,
                                inhibate = not val)
    
    def get_lock_in_frequency(self):
        return self._LI_frequency
    
    def set_lock_in_frequency(self, val: float):
        self._LI_frequency = val
        if self._LI_status:
            # If lock-in is running, once stop it and restart after change.
            self.set_lock_in_status(False)
            self.lock_in_send_order(order=0,
                                    frequency = val)
            self.set_lock_in_status(True)
        else:
            self.lock_in_send_order(order=0,
                                    frequency = val)
    
    def get_lock_in_amplitude(self):
        return self._LI_amplitude
    
    def set_lock_in_amplitude(self, val: float):
        self._LI_amplitude = np.abs(val)
        if self._LI_status:
            # If lock-in is running, once stop it and restart after change.
            self.set_lock_in_status(False)
            self.lock_in_send_order(order=2,
                                    amplitude = val)
            self.set_lock_in_status(True)
        else:
            self.lock_in_send_order(order=2,
                                    amplitude = val)
        
    def get_lock_in_channel(self):
        return self._LI_channel
    
    def set_lock_in_channel(self, val: int):
        self._LI_channel = val
        if self._LI_status:
            # If lock-in is running, once stop it and restart after change.
            self.set_lock_in_status(False)
            self.lock_in_send_order(order=1,
                                    panel_channel={'panel':val // 8, 'channel':val % 8})
            self.set_lock_in_status(True)
        else:
            self.lock_in_send_order(order=1,
                                    panel_channel={'panel':val // 8, 'channel':val % 8})
        
    def get_used_buses(self):
        return self._used_buses
    
    def set_used_buses(self, val: List[int]):
        self._used_buses = val
        
        busses_to_use = [False]*8
        for n in val:
            if n > 7:
                print('Bus{:d} is out of range.'.format(n))
            else:
                busses_to_use[n] = True
            
        self.DAC_send_order(order=1,
                            busses_to_use=busses_to_use)
        
    def get_ms2wait(self):
        return self._ms2wait
    
    def set_ms2wait(self, val: int):
        self._ms2wait = val
        self.DAC_send_order(order=2,
                            delay_between_steps_ms = val)
        
    def get_FS_divider(self):
        return self._FS_divider
    
    def set_FS_divider(self, val: Union[int, float]):
        if self._FS_status:
            # stop fast sequence if running.
            self.set_FS_status(False)
            
        self._FS_divider = val
        self.fastseq_set_orders(order = 1,
                                divider = ms2FS_divider(val))
        
    def get_FS_ramp(self):
        return self._FS_ramp
    
    def set_FS_ramp(self, val: bool):
        if self._FS_status:
            # stop fast sequence if running.
            self.set_FS_status(False)
            
        self._FS_ramp = val
        if val:
            # When ramp mode, unset stop count.
            self.fastseq_set_orders(order=3)
        else:
            # When fast cycle mode ('start'), unset ramp.
            self.fastseq_set_orders(order=2)
        
    def get_FS_pulse_len(self):
        return self._FS_pulse_len
    
    def set_FS_pulse_len(self, val:int):
        if self._FS_status:
            # stop fast sequence if running.
            self.set_FS_status(False)
        self._FS_pulse_len = val
        self.fastseq_set_orders(order=4,
                                pulse_length=val)
        
    def get_FS_chan_list(self):
        return self._FS_chan_list
    
    def set_FS_chan_list(self, val:List[int]):
        if self._FS_status:
            # stop fast sequence if running.
            self.set_FS_status(False)
            
        self._FS_chan_list = val
        size = len(val)
        for i in range(16):
            if i < size:
                v = val[i]
                if 0 <= v < 64:
                    panel = v // 8
                    channel = v % 8
                    self.fastseq_set_fastChannel(fast_chan_number=i,
                                                 panel_channel={'panel':panel, 'channel':channel},
                                                 is_dummy = False)
                else:
                    # set dummy
                    self.fastseq_set_fastChannel(fast_chan_number=i,
                                                 panel_channel={'panel':0, 'channel':0},
                                                 is_dummy = True)
                    
            else:
                self.fastseq_set_fastChannel(fast_chan_number=i,
                                             panel_channel={'panel':0, 'channel':0},
                                             is_dummy = True)
                
    def get_FS_status(self):
        return self._FS_status
    
    def set_FS_status(self, val:bool, sample_count=True):
        # Control star and stop of fast sequence.
        # When we start the fast sequence, each time we have to set sample count.
        # Therefore I include it from the beggining.
        if val:
            if sample_count:
                # Set sample count.
                self.FS_sample_count(self.FS_sample_count())
            # Start fast sequence
            self.fastseq_set_orders(order=6)
        else:
            # Stop fast sequence
            self.fastseq_set_orders(order=0)
        self._FS_status = val
            
    def get_FS_sample_count(self):
        return self._FS_sample_count
    
    def set_FS_sample_count(self, val:int):
        if self._FS_status:
            # stop fast sequence if running.
            self.set_FS_status(False)
            
        self._FS_sample_count = val
        if self._FS_ramp:
            # Ramp mode
            #- For ramp mode we add trigger count +2 (make sure that ADC obtain enough amount of trigger pulse.)
            self.fastseq_set_orders(order=5,
                                    sample_count=val+2)
        else:
            # Fast cycle mode
            self.DAC_set_stop_sample_count(sample_count = val)
            
    def get_FS_move_limit(self):
        return self._FS_move_limit
    
    def set_FS_move_limit(self, val:List[float]):
        self._FS_move_limit = val
            
    def get_FS_slots(self):
        return self._FS_slots
    
    def set_FS_slots(self, val:np.ndarray, store_seq2meta=True):
        shape = val.shape
        # Check shape of the input variable
        if not len(shape) == 2:
            raise ValueError('Shape of fast sequence array is invalid.')
        else:
            if not shape[0]==2:
                raise ValueError('Shape of fast sequence array is invalid.')
        
        self.fast_seq_set_slots(val)
        
        if store_seq2meta:
            self.FS_slots.metadata['fast_seq'] = [list(val[0,:]), list(val[1,:])]
        
        self._FS_slots = val
            
    def get_DAC_values(self, mode:int=0, fill_modules:bool = True):
        """
        Get all the DAC values from FPGA.
        
        Args:
            mode (int): 0: returns 8 by 8 array,
                        1: returns information only for used value
            fill_modules (bool): whether we set obtained values to sub-modules or not
                                It is useful when we first define the instrument.
        """
        dac_values = self.DAC_current_values()
        
        if mode==1:
            a = np.zeros((len(self._used_buses), 8), dtype=float)
            for i, n in enumerate(self._used_buses):
                a[i,:] = dac_values[n,:]
            dac_values = a
            
        # Set values to submodules
        if fill_modules:
            for n in self._used_buses:
                panel = getattr(self, 'p{:d}'.format(n))
                for c in range(8):
                    ch = getattr(panel, 'c{:d}'.format(c))
                    ch.value(dac_values[n, c])
            
        return dac_values
    
    """-----------------------
    Control functions
    ------------------------"""
    def DAC_start_movement(self):
        """
        Start DAC movement
        """
        self.DAC_send_order(order=0)
        
    def DAC_init_values(self, value:float=0.0):
        """
        Initialize all the DAC values in the used value to "value".
        
        For the procedure once move all the DAC to -0.1 V and come back 
        to the given "value".
        """
        for i in self._used_buses:
            for j in range(8):
                self.DAC_set_value(panel_channel={'panel':i, 'channel':j},
                                   DAC_goto_value=-0.1)
        self.DAC_start_movement()
        self.DAC_wait_end_of_move()
        
        for i in self._used_buses:
            for j in range(8):
                self.DAC_set_value(panel_channel={'panel':i, 'channel':j},
                                   DAC_goto_value = value)
        self.DAC_start_movement()
        self.DAC_wait_end_of_move()
        
    """===================================
    FPGA control functions from LabVIEW
    ==================================="""
    def openRef(self):
        # Open FPGA reference and return it.
        self.ref = Session(bitfile=self.bitFilePath, resource='rio://'+self.address+'/RIO0')
        if not (self.ref.fpga_vi_state==nifpga.FpgaViState.Running):
            # If not run, run.
            self.ref.run()
        # perform lock-in-configure
        self.lock_in_configure_analysis()
        
    def close(self):
        # Close FPGA reference
        self.ref.close()
        
    """---------------------
    Lock-in related functions
    ------------------------"""
    def lock_in_configure_analysis(self):
        """
        Function to setup FPGA at the beggining.
        """
        # Data set to host
        self.lock_in_send_analysis(order = {'NULL':0, 'Data_sent_to_host':1, 'dt/tau':2, 'Voltage_range':3}['Data_sent_to_host'],
                                  voltage_range = {'10V':0, '5V':1, '1V':2}['10V'],
                                  dt_over_tau = 0.0,
                                  data_sent_back = {'LI':0, 'average':1}['average'],
                                  )
        # dt/tau
        self.lock_in_send_analysis(order = {'NULL':0, 'Data_sent_to_host':1, 'dt/tau':2, 'Voltage_range':3}['dt/tau'],
                                  voltage_range = {'10V':0, '5V':1, '1V':2}['10V'],
                                  dt_over_tau = 8.00006091594696044921875000000000E-6,
                                  data_sent_back = {'LI':0, 'average':1}['average'],
                                  )
    
    def lock_in_send_analysis(self,
                              order = {'NULL':0, 'Data_sent_to_host':1, 'dt/tau':2, 'Voltage_range':3}['Data_sent_to_host'],
                              voltage_range = {'10V':0, '5V':1, '1V':2}['10V'],
                              dt_over_tau = 0.0,
                              data_sent_back = {'LI':0, 'average':1}['average'],
                              ):
        """
        Function to perform initial setup of FPGA.
        
        Args:
            order (int): selection of operation
            votage_range (int): voltage range
            dt_over_tau (float): ??
            data_sent_back (int): ??
        """
        # 1st frame of LabVIEW program
        if order == 0:
            # NULL
            order_number = join_8_8bit264bit(3,0,0,0,0,0,0,0)
        elif order == 1:
            # Data set to host
            order_number = join_8_8bit264bit(3,1,0,0,0,0,0,data_sent_back)
        elif order == 2:
            # dt/tau
            dt_over_tau = dt_over_tau * (2**32)         # Convert Fixed point to 32 bit integer
            order_number = join_numbers(3,2,16)
            order_number = join_numbers(order_number, 0, 32)
            order_number = join_numbers(order_number, dt_over_tau, 64)
        elif order == 3:
            # Voltage range
            order_number = join_8_8bit264bit(3,3,0,0,0,0,0,voltage_range)
       
        # 2nd frame of LabVIEW program
        order_in = self.ref.registers['order in']
        order_in.write(np.uint64(order_number))
        orderXmitted = self.ref.registers['order Xmitted']
        orderXmitted.write(True)
        
        # 3rd frame of LabVIEW program
        time.sleep(0.01)
        orderXmitted.write(False)
        
        # 4th frame of LabVIEW program
        if order == 2:
            # dt/tau
            # Wait until move bus gets ready.
            move_bus_ready = self.ref.registers['move bus ready'].read()
            while move_bus_ready == False:
                move_bus_ready = self.ref.registers['move bus ready'].read()
                
    def lock_in_send_order(self,
                           order = {'frequency':0, 'channel':1, 'amplitude':2, 'inhibate':3}['inhibate'],
                           frequency = 0.0,
                           amplitude = 0.0,
                           inhibate = False,
                           panel_channel = {'panel':0, 'channel':0},
                           ):
        """
        Send order to lock-in sub-system.
        """
        if order == 0:
            # Frequency (Hz)
            f = 25000/frequency
            if f < 1:
                f = 1
            elif f > 4e9:
                f = 4e9
            f = np.uint32(f)
            a,b = split_number(f, size=32)
            c,d = split_number(a, size=16)
            e,f = split_number(b, size=16)
            order_number = join_8_8bit264bit(2,4,0,0,c,d,e,f)
        elif order == 1:
            # channel
            order_number = join_8_8bit264bit(2,1,0,0,0,0,panel_channel['panel'],panel_channel['channel'])
        elif order == 2:
            # Amplitude
            if amplitude < -5:
                amplitude = -5
            elif amplitude > 5:
                amplitude = 5
#            a = amplitude/5.0*(2**16)
            a = amplitude/10.0*(2**16)
            a = np.uint16(a)
            b,c = split_number(a, 16)
            
            order_number = join_8_8bit264bit(2,2,0,0,0,0,b,c)
        elif order == 3:
            # Inhibate
            if inhibate:
                v = 1
            else:
                v = 0
            order_number = join_8_8bit264bit(2,3,0,0,0,0,0,v)
        self.DAC_Xmit_order(order = order_number)
        
    def DAC_lock_in_init(self,
                         frequency = 0.0,
                         amplitude = 0.0,
                         inhibate = True,
                         panel_channel = {'panel':0, 'channel':0},
                         ):
        """
        Initialize lock-in
        """
        # Stop lock-in before changing the setup.
        self.lock_in_send_order(order = {'frequency':0, 'channel':1, 'amplitude':2, 'inhibate':3}['inhibate'],
                               frequency = frequency,
                               amplitude = amplitude,
                               inhibate = True,
                               panel_channel = panel_channel,
                               )
        # Set panel and channel
        self.lock_in_send_order(order = {'frequency':0, 'channel':1, 'amplitude':2, 'inhibate':3}['channel'],
                               frequency = frequency,
                               amplitude = amplitude,
                               inhibate = inhibate,
                               panel_channel = panel_channel,
                               )
        # Set frequency
        self.lock_in_send_order(order = {'frequency':0, 'channel':1, 'amplitude':2, 'inhibate':3}['frequency'],
                               frequency = frequency,
                               amplitude = amplitude,
                               inhibate = inhibate,
                               panel_channel = panel_channel,
                               )
        # Set amplitude
        self.lock_in_send_order(order = {'frequency':0, 'channel':1, 'amplitude':2, 'inhibate':3}['amplitude'],
                               frequency = frequency,
                               amplitude = amplitude,
                               inhibate = inhibate,
                               panel_channel = panel_channel,
                               )
        # Start or not
        self.lock_in_send_order(order = {'frequency':0, 'channel':1, 'amplitude':2, 'inhibate':3}['inhibate'],
                               frequency = frequency,
                               amplitude = amplitude,
                               inhibate = inhibate,
                               panel_channel = panel_channel,
                               )
                
    """===================
    DAC related functions
    ==================="""
    def DAC_set_use_buses(self,
                          busses_to_use = [False]*8,
                          delay_between_steps_ms = 2,
                          ):
        if True in busses_to_use:
            # Buses to use
            self.DAC_send_order(order = {'start movement':0, 'busses to use':1, 'delay':2, 'value':3, 'stop':4}['busses to use'],
                              busses_to_use = busses_to_use,
                              panel_channel = {'panel':0, 'channel':0},
                              DAC_goto_value = 0.0,
                              delay_between_steps_ms = delay_between_steps_ms,
                              )
            # delay between each DAC movement
            self.DAC_send_order(order = {'start movement':0, 'busses to use':1, 'delay':2, 'value':3, 'stop':4}['delay'],
                              busses_to_use = busses_to_use,
                              panel_channel = {'panel':0, 'channel':0},
                              DAC_goto_value = 0.0,
                              delay_between_steps_ms = delay_between_steps_ms,
                              )
    
    def DAC_send_order(self,
                      order = {'start movement':0, 'busses to use':1, 'delay':2, 'value':3, 'stop':4}['busses to use'],
                      busses_to_use = [False]*8,
                      panel_channel = {'panel':0, 'channel':0},
                      DAC_goto_value = 0.0,
                      delay_between_steps_ms = 2,
                       ):
        """
        This function is used to send an order to DAC.
        
        Security for DAC go to value will be implemented at different location.
        """
        if order == 0:
            # Start movement
            order_number = join_8_8bit264bit(1,2,0,0,0,0,0,0)
        elif order == 1:
            # value to use
            bus = 0
            for i, b in enumerate(busses_to_use):
                if b:
                    bus += 2**i
            order_number = join_8_8bit264bit(1,1,0,0,0,0,0,bus)
        elif order == 2:
            # delay
            order_number = join_8_8bit264bit(1,3,0,0,0,0,0,delay_between_steps_ms)
        elif order == 3:
            # value
            value = np.int16(DAC_goto_value/5.0*32768) + 32768
            a,b = split_number(value, size=16)
            order_number = join_8_8bit264bit(1,4,0,0,panel_channel['panel'],panel_channel['channel'],a,b)
        elif order == 4:
            # stop
            order_number = join_8_8bit264bit(1,5,0,0,0,0,0,0)
            
        self.DAC_Xmit_order(order=order_number)
    
    def DAC_Xmit_order(self,
                       order=0):
        """
        Main program to send an order to FPGA.
        
        Arg:
            order: uint64
        """
        order_in = self.ref.registers['order in']
        order_Xmitted = self.ref.registers['order Xmitted']
        
        order_in.write(order)
        order_Xmitted.write(True)
        
        i=0
        while order_Xmitted.read()==True:
           i+=1
           
    def DAC_set_value(self,
                      panel_channel = {'panel':0, 'channel':0},
                      DAC_goto_value = 0.0,
                      ):
        """
        Set goto value of DAC.
        
        Note:
            Meanwhile I do not implement safety check here since for QuCoDeS there is another safety chaeck.
        """
        self.DAC_send_order(order = {'start movement':0, 'busses to use':1, 'delay':2, 'value':3, 'stop':4}['value'],
                          busses_to_use = [False]*8,
                          panel_channel = panel_channel,
                          DAC_goto_value = DAC_goto_value,
                          delay_between_steps_ms = 2,
                           )
        
    def DAC_wait_end_of_move(self):
        """
        Wait until all the DAC movement finishes.
        """
        move_bus_ready = self.ref.registers['move bus ready']
        i=0
        while move_bus_ready.read()==False:
            i += 1
            
    def DAC_current_values(self):
        """
        Get current values of DAC
        """
        # Get rid of an eventual unfinished retrieving sequence
        get_DAC_value = self.ref.registers['get DAC value']
        got_DAC_value = self.ref.registers['got DAC value']
        got_DAC_value.write(True)
        while get_DAC_value.read()==True:
            got_DAC_value.write(True)
            
        # Read values
        values = np.zeros((8,8),dtype=float)
        DAC_to_retrieve = self.ref.registers['DAC to retrieve']
        DAC_data = self.ref.registers['DAC data']
        for i in range(64):
            DAC_to_retrieve.write(i)
            got_DAC_value.write(True)
            get_DAC_value.write(True)
            j=0
            while got_DAC_value.read()==True:
               j+=1
            data = DAC_data.read()
            panel_channel, value = split_number(data, size=32)
            panel = int(panel_channel)//8
            channel = int(panel_channel)%8
            
            value = (value - 32768)/32768*5.0 # Convert to real unit
            values[panel, channel] = value
            
            got_DAC_value.write(True)
        return values
    
    """========================================
    Fast sequence related functions
    ========================================"""
    def fastseq_set_orders(self,
                           order={'stop':0, 'set divider':1, 'unset ramp mode':2, 'unset stop count':3, 'set pulse length':4, 'set ramp':5, 'start':6}['stop'],
                           divider = 6661,
                           pulse_length=0,
                           sample_count = 0,
                           ):
        """
        Program to send an order to fast sequence sub-system.
        """
        if order == 0:
            # stop
            order_number = join_8_8bit264bit(5,1,0,0,0,0,0,0)
        elif order == 1:
            # set divider
            order_number = join_numbers(5,7, final_size=16)
            order_number = join_numbers(order_number, 0, final_size=32)
            order_number = join_numbers(order_number, divider, final_size=64)
        elif order == 2:
            # unset ramp mode
            order_number = join_8_8bit264bit(6,9,0,0,0,0,0,0)
        elif order == 3:
            # unset stop count
            order_number = join_8_8bit264bit(5,6,0,0,0,0,0,0)
        elif order == 4:
            # set pulse length
            order_number = join_numbers(5, 10, final_size=16)
            order_number = join_numbers(order_number, 0, final_size=32)
            pulse_length = join_numbers(0, pulse_length, final_size=32)
            order_number = join_numbers(order_number, pulse_length, final_size=64)
        elif order == 5:
            # set ramp
            order_number = join_numbers(5, 8, final_size=16)
            order_number = join_numbers(order_number, 0, final_size=32)
            sample_count = join_numbers(0, sample_count, final_size=32)
            order_number = join_numbers(order_number, sample_count, final_size=64)
        elif order == 6:
            # start
            order_number = join_8_8bit264bit(5,2,0,0,0,0,0,0)
            
        self.DAC_Xmit_order(order = order_number)
        
    def fastseq_set_fastChannel(self,
                                fast_chan_number=0,
                                panel_channel = {'panel':0, 'channel':0},
                                is_dummy = False,
                                ):
        """
        Allocate DAC panel_channel to fast sequence channels (up to 16 DACs).
        """
        panel = panel_channel['panel']
        if is_dummy:
            # Dummy channel is 255.
            channel = 255
        else:
            channel = panel_channel['channel']
        # Check whether fast_chan_number is out of range or not.
        if fast_chan_number < 0:
            fast_chan_number = 0
            print('fast channel number is out of range and cast to closest available value.')
        elif fast_chan_number > 15:
            fast_chan_number = 15
            print('fast channel number is out of range and cast to closest available value.')
            
        order_number = join_8_8bit264bit(5,3,0,0,fast_chan_number,0,panel,channel)
        
        self.DAC_Xmit_order(order = order_number)
        
    def fastseq_set_slot(self,
                         choice={'DAC':0, 'timing':1, 'triggers':2, 'jump':3}['DAC'],
                         slot_number=0,
                         fast_chan_number=0,
                         DAC_Offset = 0.0,
                         time_ms = 0.0,
                         trigger = {'trig1_ramp':False, 'trig2':False, 'trig3':False, 'trig4':False, 'stop':False},
                         jump2 = 0,
                         ):
        """
        Set fast sequence slot
        """
        if choice == 0:
            #DAC
            if fast_chan_number < 0:
                fast_chan_number = 0
            elif fast_chan_number > (2**4-1):
                fast_chan_number = (2**4-1)
            val = fast_chan_number + (choice << 4)
            
            order_number = join_numbers(5,4,final_size=16)
            val = join_numbers(val, 0, final_size=16)
            
            order_number = join_numbers(order_number, val, final_size=32)
            
            # detailed safe check will be performed elsewhere
            # here we only check the value is smaller than |5|.
            if DAC_Offset < -5.0:
                DAC_Offset = -5.0
                print('DAC offset input value is not normal. Please check it.')
            elif DAC_Offset > 5.0:
                DAC_Offset = 5.0
                print('DAC offset input value is not normal. Please check it.')
                
            DAC_Offset = DAC_Offset/5.0 * 32768
            
            if slot_number < 0:
                slot_number = 0
            elif slot_number > (2**16-1):
                slot_number = 65535
            val = join_numbers(slot_number, DAC_Offset, final_size=32)
            
            order_number = join_numbers(order_number, val, final_size=64)
        elif choice == 1:
            # Timing
            val = (choice << 4)
            order_number = join_numbers(5,4,final_size=16)
            val = join_numbers(val,0,final_size=16)
            
            order_number = join_numbers(order_number, val, final_size=32)
            
            # Convert time to us
            time_ms = np.abs(time_ms*1000.0)
            if time_ms < 1:
                # Force wait time above 1 us.
                time_ms = 1.0
            val = np.int64(np.floor(np.log2(time_ms))) - 10
            if val < 0:
                val = 0
            time_ms = np.floor(time_ms * (2.0**(-val)))
            if time_ms > ((2**11)-1):
                # Time(ms) is casted to 11bit in LabVIEW program
                # so I will do the same.
                time_ms = ((2**11)-1)
            val = time_ms + (val << 11)
            val = join_numbers(slot_number, val, final_size=32)
            
            order_number = join_numbers(order_number, val, final_size=64)
        elif choice == 2:
            # triggers
            val = (choice << 4)
            
            order_number = join_numbers(5,4,final_size=16)
            val = join_numbers(val,0,final_size=16)
            
            order_number = join_numbers(order_number, val, final_size=32)
            
            val = 0
            if trigger['trig1_ramp']:
                val += 2**0
            if trigger['trig2']:
                val += 2**1
            if trigger['trig3']:
                val += 2**2
            if trigger['trig4']:
                val += 2**3
            if trigger['stop']:
                val += 2**15
            val = join_numbers(slot_number, val, final_size=32)
            
            order_number = join_numbers(order_number, val, final_size=64)
        elif choice == 3:
            # jump
            val = (choice << 4)
            
            order_number = join_numbers(5,4,final_size=16)
            val = join_numbers(val,0,final_size=16)
            
            order_number = join_numbers(order_number, val, final_size=32)
            val = join_numbers(slot_number, jump2, final_size=32)
            
            order_number = join_numbers(order_number, val, final_size=64)
        
        self.DAC_Xmit_order(order = order_number)
        
    def fast_seq_set_slots(self,
                           seq_array: np.ndarray):
        """
        This function set slots of fast sequence by the given array.
        
        Args:
            seq_array: (2,N) dimensional array
            
            [Limitation for N: 1<= N <= 4096
            (0,:) is parameter (0 ~ 15: fast channels, 101: trigger,
            102: timing (ms), 103: jump, else: jump to its index)
            
	        (1,:) is values. (DAC = value offset,
            trigger = bit wise value for each trigger (1~4, stop)
		    timing = ms to wait, jump = # of slot ot jump)]
        """
        # Check array size and cut down if it is too large.
        if seq_array.shape[1] > 4096:
            seq_array = seq_array[:,0:4096]
        
        N = seq_array.shape[1]
        for i in range(N):
            tp = int(seq_array[0,i])
            value = seq_array[1,i]
            if tp < 16:
                # DAC shift
                dac_move_min = min(self._FS_move_limit[0], self._FS_move_limit[1])
                dac_move_max = max(self._FS_move_limit[0], self._FS_move_limit[1])
                # Limit check
                if value < dac_move_min:
                    value = dac_move_min
                    print('Compliance is applied and dac move value is cast to {:f}'.format(dac_move_min))
                if value > dac_move_max:
                    value = dac_move_max
                    print('Compliance is applied and dac move value is cast to {:f}'.format(dac_move_max))
                    
                self.fastseq_set_slot(choice=0,
                                     slot_number=i,
                                     fast_chan_number=tp,
                                     DAC_Offset = value)
            elif tp == 101:
                # Trigger control
                trigger = {'trig1_ramp':False, 'trig2':False, 'trig3':False, 'trig4':False, 'stop':False}
                value = int(value)
                if not (value & 2**0)==0:
                    trigger['trig1_ramp']=True
                if not (value & 2**1)==0:
                    trigger['trig2']=True
                if not (value & 2**2)==0:
                    trigger['trig3']=True
                if not (value & 2**3)==0:
                    trigger['trig4']=True
                if not (value & 2**4)==0:
                    trigger['stop']=True
                    
                self.fastseq_set_slot(choice=2,
                                     slot_number=i,
                                     trigger = trigger)
            elif tp == 102:
                # Timing (wait) (ms)
                self.fastseq_set_slot(choice=1,
                                     slot_number=i,
                                     time_ms = value)
            elif tp == 103:
                # Jump to slot ??
                self.fastseq_set_slot(choice=3,
                                     slot_number=i,
                                     jump2 = np.uint16(value))
            else:
                raise ValueError('fast sequence contains undefined type number.')
        
    def DAC_set_stop_sample_count(self,
                                  sample_count=0,
                                  ):
        order_number = join_numbers(5,5,final_size=16)
        
        order_number = join_numbers(order_number,0,final_size=32)
        val = join_numbers(0,sample_count,final_size=32)
        
        order_number = join_numbers(order_number, val, final_size=64)
        
        self.DAC_Xmit_order(order = order_number)
        
if __name__=='__main__':
    dac = NEEL_DAC('dac')
    #------------------------
    # Test DAC movement
    #------------------------
    dac.p0.c0.value(-0.1)
    dac.DAC_start_movement()
    dac.DAC_wait_end_of_move()
    
    # # Test lock-in
    # dac.LI_status(False)
    # dac.LI_frequency(20.0)
    # dac.LI_amplitude(0.2)
    # dac.LI_channel(0)
    # dac.LI_status(False)
    
    # #------------------------
    # # Test fast sequence
    # #------------------------
    # ramp = True
    # divider = 6661
    # sample_count = 403
    
    # # Stop fast sequence
    # dac.FS_status(False)
    # # Set fast sequence divider
    # dac.FS_divider(divider)
    # # set operation mode ('ramp' or 'start')
    # dac.FS_ramp(ramp)
    # # Set fast sequence channels
    # dac.FS_chan_list(list(range(16)))
    # # Set pulse length
    # dac.FS_pulse_len(1000)
    
    # # Set fast sequence
    # seq_array = np.zeros((2,sample_count))
    # seq_array[:,0] = [101,0]
    # seq_array[1,1:sample_count-1] = np.linspace(0.0, -0.5,num=sample_count-2)
    # seq_array[:,sample_count-1] = [103, sample_count-1]
    # dac.FS_slots(seq_array)
    
    # # Set sample count
    # size = seq_array.shape[1]
    # dac.FS_sample_count(size)
    
    # dac.FS_status(True)
    
    # # sleep
    # sleep_time = 4.5e-7*divider*sample_count+5
    # time.sleep(sleep_time)
    
    # dac.FS_status(False)
    
    dac.close()