# -*- coding: utf-8 -*-
"""
Created on Tue Jul  3 17:41:57 2018

@author: DCR
"""

import numpy as np

from qcodes import Instrument
from qcodes.instrument.visa import VisaInstrument
from qcodes.instrument.channel import InstrumentChannel
from qcodes.instrument.parameter import ArrayParameter
from qcodes import validators as vals

class sTrace(ArrayParameter):
    
    def __init__(self, name: str, instrument: InstrumentChannel,
                 channum: int, s_param_choice: str, real: bool) -> None:
        """
        
        """
        super().__init__(name=name,
                         shape=(1,),
                         label=s_param_choice,
                         unit='dB',
                         setpoint_names=('Frequency',),
                         setpoint_labels=('Frequency',),
                         setpoint_units=('Hz',),
                         docstring='Holds s-parameter trace')
        self.channum = channum
        self.real = real
        self._instrument = instrument
        
    def prepare_trace(self) -> None:
        """
        Prepare to get trace
        """
        inst = self._instrument._parent
        pts = int(inst.sweep_pts())
        self.shape = (pts,)
        f_start = inst.f_start()
        f_stop = inst.f_stop()
        self.setpoints = (tuple(np.linspace(f_start, f_stop, pts, dtype=np.float)),)
        self._trace_ready = True
        # we must ensure that all this took effect before proceeding
        inst.opc()
        
    def get_raw(self):
        """
        Measure and get data.
        """
        if not self._trace_ready:
            raise ValueError('Trace not ready! Please call '
                             'prepare_trace().')
            
        inst = self._instrument._parent
            
        inst.write('CALC:PAR{:d}:SEL'.format(self.channum))
        data = np.array(inst.ask('CALC:DATA:SDAT?').split(','), dtype=np.float)
        if self.real:
            data = data.reshape((2,self.shape[0]), order='F')[0,:]
        else:
            data = data.reshape((2,self.shape[0]), order='F')[1,:]
        inst.opc()
        return data
        
class display(InstrumentChannel):
    """
    Class to hold a s parameter info.
    Since each s parameter is assigned to each window,
    this class holds scale info for that window.
    """
    def __init__(self, parent: Instrument, name: str, channum: int) -> None:
        if channum not in [1, 2, 3, 4]:
            raise ValueError('Invalid diaplay number! Must be 1 ~ 4.')
        
        self.channum = channum
        
        super().__init__(parent, name)
        self.add_parameter('y_scale_bottom',
                           label = 'Y scale bottom',
                           unit = 'dB',
                           set_cmd='DISPlay:WINDow:TRACe{}:Y:BOTTom {{}}'.format(channum),
                           get_cmd='DISPlay:WINDow:TRACe{}:Y:BOTTom?'.format(channum),
                           get_parser=float)
        
        self.add_parameter('y_scale_top',
                           label = 'Y scale top',
                           unit = 'dB',
                           set_cmd='DISPlay:WINDow:TRACe{}:Y:TOP {{}}'.format(channum),
                           get_cmd='DISPlay:WINDow:TRACe{}:Y:TOP?'.format(channum),
                           get_parser=float)
        
        self.add_parameter('trace_r',
                           channum=self.channum,
                           s_param_choice=self._parent.s_params[self.channum-1],
                           real = True,
                           parameter_class=sTrace)
        
        self.add_parameter('trace_i',
                           channum=self.channum,
                           s_param_choice=self._parent.s_params[self.channum-1],
                           real = False,
                           parameter_class=sTrace)
        
        self._trace_ready = False
                
    def auto_scale(self):
        self.write('DISPlay:WINDow:TRACe{}:Y:AUTO'.format(self.channum))
        
class Keysight_FieldFox(VisaInstrument):
    """
    This is the qcodes driver for the Keysight FieldFox microwave analyzer
    in Network Analyzer mode. The driver is tested by N9118a.
    
    Meanwhile I use this device by splitting the window to 4 and set
    each window to measure s11, s12, s21, s22, respectively.
    
    Args:
        name(str): given name of instrument
        address(str): IP address of FieldFox
        timeout(float): timeout of communication (s)
    """
    
    def __init__(self, name: str, address: str,
                 timeout: float=180.0, **kwargs):
        super().__init__(name, 'TCPIP::{}::inst0::INSTR'.format(address), timeout, **kwargs)
        
        self.s_params = ['S11', 'S12', 'S21', 'S22']
        
        self.add_parameter('f_start',
                           label='Start frequency',
                           unit='Hz',
                           set_cmd='FREQ:STAR {:e}',
                           get_cmd='FREQ:STAR?',
                           get_parser=int,
                           vals=vals.Numbers(30e3,26.5e9))
        
        self.add_parameter('f_stop',
                           label='Stop frequency',
                           unit='Hz',
                           set_cmd='FREQ:STOP {:e}',
                           get_cmd='FREQ:STOP?',
                           get_parser=int,
                           vals=vals.Numbers(30e3,26.5e9))
        
        self.add_parameter('power',
                           label='Source power',
                           unit='dBm',
                           set_cmd='SOURce:POWer {:f}',
                           get_cmd='SOURce:POWer?',
                           get_parser=float,
                           vals=vals.Numbers(-45, 3))
        
        self.add_parameter('ifbw',
                           label='IF Bandwidth',
                           unit='Hz',
                           set_cmd='BWID {:e}',
                           get_cmd='BWID?',
                           get_parser=float,
                           vals=vals.Numbers(5.56e-5, 30.0e3))
        
        self.add_parameter('sweep_pts',
                           label='Sweep points',
                           unit='pts',
                           set_cmd='SWE:POIN {:d}',
                           get_cmd='SWE:POIN?',
                           get_parser=int,
                           vals=vals.Ints(2, 10001))
        
        self.add_parameter('avg_count',
                           label='Average counts',
                           set_cmd='AVER:COUN {:d}',
                           get_cmd='AVER:COUN?',
                           get_parser=int,
                           vals=vals.Ints(1, 10000))
        
        # Initialize instrument
        self.initialize()
        
        # Add displays
        for i, s in enumerate(self.s_params):
            chan = display(self, s, i+1)
            self.add_submodule(s, chan)
        
        self.connect_message()
        
    def run(self):
        self.write('INIT:IMM')
        
    def run_continuous(self):
        self.write('INIT:CONT 1')
        
    def hold(self):
        self.write('INIT:CONT 0')
        
    def clear_average(self):
        self.write('AVER:CLE')
        
    def auto_scale_all(self):
        for i in range(1, len(self.s_params)+1):
            self.write('DISPlay:WINDow:TRACe{:d}:Y:AUTO'.format(i))
        
    def opc(self):
        return self.ask('*OPC?')
        
    def initialize(self):
        # Reset the instrument
        self.write('*RST')
        # Select Network Analyzer (NA) mode
        self.write('INST:SEL "NA"')
        
        # Split display to 4. Then set measurement parameter to s11, s12
        # s21, s22, respectively.
        self.write('DISP:WIND:SPL D12_34')
        
        for i, s in enumerate(self.s_params):
            self.write('CALC:PAR{:d}:DEF {}'.format(i+1, s))
        
        # Set display data format
        for i in range(1,len(self.s_params)+1):
            self.write('CALC:PAR{}:SEL'.format(i))
            self.write('CALC:FORM MLOG')
        
        # Set data format to be ascii
        self.write('FORM ASCii,0')
        
        self.opc()
        
    def measure(self):
        # Clear averaging
        self.clear_average()
        # Set to HOLD mode; wait
        self.hold()
        self.opc()
        # Trigger measurements
        for i in range(self.avg_count()):
            self.run()
            self.opc()
       
        pts = int(self.sweep_pts())
        f_start = self.f_start()
        f_stop = self.f_stop()
        for s in self.s_params:
            chan = getattr(self, s)
            chan.trace_r.shape = (pts,)
            chan.trace_r.setpoints = (tuple(np.linspace(f_start, f_stop, pts, dtype=np.float)),)
            chan.trace_r._trace_ready = True
            chan.trace_i.shape = (pts,)
            chan.trace_i.setpoints = (tuple(np.linspace(f_start, f_stop, pts, dtype=np.float)),)
            chan.trace_i._trace_ready = True