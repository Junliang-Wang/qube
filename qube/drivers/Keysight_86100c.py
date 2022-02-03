# -*- coding: utf-8 -*-
"""
Created on Fri Jun  8 14:03:23 2018

@author: Shintaro Takada
"""

import logging
import warnings
import time

import numpy as np
from distutils.version import LooseVersion

from qcodes import Instrument
from qcodes.instrument.visa import VisaInstrument
from qcodes.instrument.channel import InstrumentChannel
from qcodes.utils import validators as vals
from qcodes.instrument.parameter import ArrayParameter

log = logging.getLogger(__name__)

# Utility functions
def convertOnOffStatement(v):
    """
    Receive the value about average on/off
    and return "ON" or "OFF"
    
    Args:
        v: returned integer 0 or 1
    """
    if int(v)==0:
        return "OFF"
    elif int(v)==1:
        return "ON"

class ScopeTrace(ArrayParameter):
    
    def __init__(self, name: str, instrument: InstrumentChannel,
                 channum: int) -> None:
        """
        The ScopeTrace parameter is attached to a channel of the oscilloscope.
        
        For now, we only support reading out the entire trace.
        """
        super().__init__(name=name,
                         shape=(1,),
                         label='Voltage', # TODO: Is this sometimes dbm?
                         unit='V',
                         setpoint_names=('Time',),
                         setpoint_labels=('Time',),
                         setpoint_units=('ns',),
                         docstring='Holds scope trace')
        self.channum = channum
        self._instrument = instrument
        
    def prepare_trace(self, setpoints_zero_origin: bool=True) -> None:
        """
        Prepare the scope for returning data, calculate the setpoints
        """
        # Select waveform data source
        self._instrument._parent.write('WAVeform:SOURce CHANnel{:d}'.format(self.channum))
        
        # setup transfer format
        self._instrument._parent.write(':WAV:FORM ASC')
        
        # Change the way to get x info (by Takada)
#        xinc = float(self._instrument._parent.ask('WAV:XINC?'))
#        xorg = float(self._instrument._parent.ask('WAV:XOR?'))
#        xref = float(self._instrument._parent.ask('WAV:XREF?'))
#        
#        self.shape = (int(self._instrument._parent.ask('ACQuire:POINts?')),)
#        self.setpoints = (tuple(((np.arange(self.shape[0]) - xref) * xinc + xorg)*1e9),)
        t_range = self._instrument._parent.time_range()
        self.shape = (int(self._instrument._parent.ask('ACQuire:POINts?')),)
        if not setpoints_zero_origin:
            t_ref = self._instrument._parent.time_reference()
            t_pos = self._instrument._parent.time_position()
            if t_ref == 'LEFT':
                self.setpoints = (tuple((np.linspace(t_pos, t_pos+t_range, num=self.shape[0]))*1e9),)
            elif t_ref == 'CENT':
                self.setpoints = (tuple((np.linspace(t_pos-t_range/2, t_pos+t_range/2, num=self.shape[0]))*1e9),)
        else:
            self.setpoints = (tuple((np.linspace(0.0, t_range, num=self.shape[0]))*1e9),)
        
        self._trace_ready = True
        # we must ensure that all this took effect before proceeding
        self._instrument._parent.ask('*OPC?')
        
    def get_raw(self, dispOn: bool = True):
        """
        Returns a trace
        """
        instr = self._instrument._parent
        
        if not self._trace_ready:
            raise ValueError('Trace not ready! Please call '
                             'prepare_trace().')
        
        # Digitize data and store it to waveform
        instr.write(':DIGitize CHANnel{:d}'.format(self.channum))
        
        # Since display is off by digitization process, make it on if required.
        if dispOn:
            instr.write('CHANnel{:d}:DISP ON'.format(self.channum))
            
        # we must ensure that all this took effect before proceeding
        instr.ask('*OPC?')
        
        # Get y data
        data = instr.ask(':WAV:DATA?')
        output = np.fromstring(data, dtype=float, sep=',')
        
        # we must ensure that all this took effect before proceeding
        instr.ask('*OPC?')

        return output
        
    
    
class ScopeChannel(InstrumentChannel):
    """
    Class to hold an input channel of the scope.
    
    Exposes: 
    """
    
    def __init__(self, parent: Instrument, name: str, channum: int) -> None:
        """
        Args:
            parent: The instrument to which the channel is attached
            name: The name of the channel
            channum: The number of the channel in question. Must match
            the actual number as used by the instrument (only 1 now)
        """
        if channum not in [1]:
            raise ValueError('Invalid channel number! Must be 1.')
            
        self.channum = channum
        
        super().__init__(parent, name)
        
        self.add_parameter('range',
                           label='Channel {} Y range'.format(channum),
                           unit='V',
                           get_cmd='CHANnel{}:RANGe?'.format(channum),
                           set_cmd='CHANnel{}:RANGe {{}}'.format(channum),
                           get_parser=float)
        
        self.add_parameter('offset',
                           label='Channel {} Y offset'.format(channum),
                           unit='V',
                           get_cmd='CHANnel{}:OFFSet?'.format(channum),
                           set_cmd='CHANnel{}:OFFSet {{}}'.format(channum),
                           get_parser=float)
        
        #####################
        # Trace
        
        self.add_parameter('trace',
                           channum=self.channum,
                           parameter_class=ScopeTrace)
        
        self._trace_ready = False
        
    def get_period(self):
        """
        Get the period of the signal
        """
        period = float(self._parent.ask('MEAS:PER? CHAN{:d}'.format(self.channum)))
        if period > 9.99e37:
            print('\nPeriod could not be measured.\n')
        else:
            print('\nThe period of channel {:d} is {:f} ns.\n'.format(self.channum, period*1e9))
        return period
    
    def get_Vpp(self):
        """
        Get the peak to peak voltage
        """
        vpp = float(self._parent.ask('MEAS:VPP? CHAN{:d}'.format(self.channum)))
        if vpp > 9.99e37:
            print('\nPeak-to-peak voltage could not be measured.\n')
        else:
            print('\nThe voltage peak-to-peak of channel {:d} is {:f} volts.\n'.format(self.channum, vpp))
        return vpp
        
class Keysight_86100c(VisaInstrument):
    """
    QCoDeS Instrument driver for the
    Keysight 86100c sampling oscilloscope.
    """
    
    def __init__(self, name: str, address: str, terminator: str='\n',
                 timeout: float=5., **kwargs) -> None:
        """
        Args:
            name: name of the instrument
            address: VISA resource address
            timeout: The VISA query timeout
            terminator: Command termination character to strip from VISA commands.
            
        For the moment data acquisition is limited to 'BYTE' format
        """
        super().__init__(name=name, address=address, timeout=timeout,
             terminator=terminator, **kwargs)
        
        self.num_chans = 1      # For the moment only 1 channel is available
        
        self.add_function('reset', call_cmd='*RST')
        self.add_function('clear', call_cmd='*CLS')
        self.add_function('opc', call_cmd='*OPC?')
        
        ###########################
        # System parameter
        self.add_parameter('system_header',
                           label='System header',
                           set_cmd='SYSTem:HEADer' + ' {}',
                           get_cmd='SYSTem:HEADer?',
                           vals=vals.Enum('ON', 'OFF'),
                           get_parser=convertOnOffStatement
                           )
        self.add_parameter('Meas_error_report',
                           label='Measurement error report',
                           set_cmd='MEAS:SEND {}',
                           get_cmd='MEAS:SEND?',
                           vals=vals.Ints(0,1),
                           get_parser=int)
        
        ############################
        # Triggering
        self.add_parameter('trigger_level',
                           label='Trigger level',
                           set_cmd='TRIGger:LEVel' + ' {}',
                           get_cmd='TRIGger:LEVel?',
                           vals=vals.Numbers(-1.0,1.0),
                           get_parser=float)
        
        self.add_parameter('trigger_slope',
                           label='Edge trigger slope',
                           set_cmd='TRIGger:SLOPe' + ' {}',
                           get_cmd='TRIGger:SLOPe?',
                           vals=vals.Enum('POS', 'NEG'))
        
        self.add_parameter('trigger_source',
                           label='Trigger source',
                           set_cmd='TRIGger:SOURce' + ' {}',
                           get_cmd='TRIGger:SOURce?',
                           vals=vals.Enum('FPAN', 'FRUN', 'LMODule', 'RMODule'))
        
        self.add_parameter('p_lock',
                           label='Pattern lock',
                           set_cmd = 'TRIGger:PLOCk {}',
                           get_cmd = 'TRIGger:PLOCk?',
                           val_mapping = {'on':1, 'off':0})
        
        self.add_parameter('p_len_auto',
                           label = 'Pattern length autodetection',
                           set_cmd = 'TRIG:PLEN:AUT {}',
                           get_cmd = 'TRIG:PLEN:AUT?',
                           val_mapping={'on':1, 'off':0})
        
        self.add_parameter('p_len',
                           label='Pattern length',
                           set_cmd = 'TRIG:PLEN {}',
                           get_cmd = 'TRIG:PLEN?',
                           vals=vals.Ints(1,2**23),
                           get_parser=int)
        
        self.add_parameter('bit_rate_auto',
                           label='Bit rate autodetection',
                           set_cmd = 'TRIGger:BRATe:AUTodetect {}',
                           get_cmd = 'TRIGger:BRATe:AUTodetect?',
                           val_mapping={'on':1, 'off':0})
        
        self.add_parameter('bit_rate',
                           label='Bit rate',
                           unit='bit/s',
                           set_cmd = 'TRIGger:BRATe {}',
                           get_cmd = 'TRIGger:BRATe?',
                           get_parser=float)
        
        ###############################
        # Horizontal setting
        self.add_parameter('time_reference',
                           label='Time reference',
                           set_cmd='TIMebase:REFerence' + ' {}',
                           get_cmd='TIMebase:REFerence?',
                           vals=vals.Enum('LEFT', 'CENT'))
        
        self.add_parameter('time_range',
                           label='Time range',
                           unit='s',
                           set_cmd='TIMebase:RANGe' + ' {}',
                           get_cmd='TIMebase:RANGe?',
                           get_parser=float)
        
        self.add_parameter('time_position',
                           label='Time position',
                           unit='s',
                           set_cmd='TIMebase:POSition' + ' {}',
                           get_cmd='TIMebase:POSition?',
                           get_parser=float)
        
        #########################
        # Acquisition
        self.add_parameter('run_mode',
                           label='RUN/acquisition mode of the scope',
                           get_cmd='SYSTem:MODE?',
                           set_cmd='SYSTem:MODE' + ' {}',
                           vals=vals.Enum('OSC', 'EYE', 'TDR', 'JITT'))
        
        self.add_parameter('average',
                           label='Averaging',
                           set_cmd='ACQuire:AVERage' + ' {}',
                           get_cmd='ACQuire:AVERage?',
                           vals=vals.Enum('ON', 'OFF'),
                           get_parser=convertOnOffStatement
                           )
        
        self.add_parameter('average_count',
                           label='Average count',
                           set_cmd='ACQuire:COUNt' + ' {}',
                           get_cmd='ACQuire:COUNt?',
                           vals=vals.Ints(1, 4096),
                           get_parser=int)
        
        self.add_parameter('num_acquisitions',
                           label='Number of acquisition points',
                           set_cmd='ACQuire:POINts' + ' {}',
                           get_cmd='ACQuire:POINts?',
                           vals=vals.Ints(16, 16384),
                           get_parser=int)
        
        ###########################
        # Waveform
        self.add_parameter('dataformat',
                           label='Export data format',
                           set_cmd='WAVeform:FORMat' + ' {}',
                           get_cmd='WAVeform:FORMat?',
                           vals=vals.Enum('ASCii', 'BYTE'))
        
        ###########################
        # Add the channels to the instrument
        for ch in range(1, self.num_chans+1):
            chan = ScopeChannel(self, 'channel{}'.format(ch), ch)
            self.add_submodule('ch{}'.format(ch), chan)
            
        self.connect_message()
        
    # function        
    def run_cont(self) -> None:
        """
        Set the instrument in 'RUN CONT' mode
        """
        self.write('RUN')
        
    def stop(self) -> None:
        """
        Stop data acquisition
        """
        self.write('STOP')
        
    def auto_scale(self) -> None:
        """
        Perform auto scale.
        """
        self.write('AUT')