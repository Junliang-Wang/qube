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

class ScopeTrace(ArrayParameter):
    
    def __init__(self, name: str, instrument: InstrumentChannel,
                 chan_name: str) -> None:
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
        self.chan_name = chan_name
        self._instrument = instrument
        
    def prepare_trace(self, setpoints_zero_origin: bool=True) -> None:
        """
        Prepare the scope for returning data, calculate the setpoints
        """
        # Select waveform data source
        self._instrument._parent.write(':WAVeform:SOURce CHANnel{}'.format(self.chan_name))
        
        t_range = self._instrument._parent.time_range()
        self.shape = (int(self._instrument._parent.ask(':ACQuire:RLEN?')),)
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
        
        # Select waveform data source
        self._instrument._parent.write(':WAVeform:SOURce CHANnel{}'.format(self.chan_name))
        
        # Get y data
        data = instr.ask(':WAVeform:YFORmat:ASCii:YDATa?')
        output = np.fromstring(data, dtype=float, sep=',')
        
        # we must ensure that all this took effect before proceeding
        instr.ask('*OPC?')

        return output
        
    
    
class ScopeChannel(InstrumentChannel):
    """
    Class to hold an input channel of the scope.
    
    Exposes: 
    """
    
    def __init__(self, parent: Instrument, name: str, chan_name: str) -> None:
        """
        Args:
            parent: The instrument to which the channel is attached
            name: The name of the channel
            channum: The number of the channel in question. Must match
            the actual number as used by the instrument (only 1 now)
        """
        self.chan_name = chan_name
        
        super().__init__(parent, name)
        
        self.add_parameter('range',
                           label='Channel {} Y range'.format(chan_name),
                           unit='V',
                           get_cmd=':CHANnel{}:YSCale?'.format(chan_name),
                           set_cmd=':CHANnel{}:YSCale {{}}'.format(chan_name),
                           get_parser=float)
        
        self.add_parameter('offset',
                           label='Channel {} Y offset'.format(chan_name),
                           unit='V',
                           get_cmd=':CHANnel{}:YOFFset?'.format(chan_name),
                           set_cmd=':CHANnel{}:YOFFset {{}}'.format(chan_name),
                           get_parser=float)
        
        self.add_parameter('display',
                           label='Display Channel {}'.format(chan_name),
                           get_cmd=':CHANnel{}:DISPlay?'.format(chan_name),
                           set_cmd=':CHANnel{}:DISPlay {{}}'.format(chan_name),
                           val_mapping={'on':1, 'off':0})
        
        #####################
        # Trace
        
        self.add_parameter('trace',
                           chan_name=self.chan_name,
                           parameter_class=ScopeTrace)
        
        self._trace_ready = False
        
    def get_period(self):
        """
        Get the period of the signal
        """
        self._parent.write(':MEASure:OSCilloscope:PERiod:SOURce {}'.format(self.chan_name))
        period = float(self._parent.ask(':MEAS:OSC:PER?'))
        if self._parent.ask(':MEAS:OSC:PER:STAT?')=='CORR':
            print('\nThe period of channel {} is {:f} ns.\n'.format(self.chan_name, period*1e9))
        else:
            print('\nPeriod could not be measured.\n')
            
        return period
    
    def get_Vpp(self):
        """
        Get the peak to peak voltage
        """
        self._parent.write(':MEAS:OSC:VPP:SOUR {}'.format(self.chan_name))
        vpp = float(self._parent.ask('MEAS:OSC:VPP?'))
        if self._parent.ask(':MEAS:OSC:VPP:STAT?')=='CORR':
            print('\nThe voltage peak-to-peak of channel {} is {:f} volts.\n'.format(self.chan_name, vpp))
        else:
            print('\nPeak-to-peak voltage could not be measured.\n')
            
        return vpp
        
class Keysight_N1094A(VisaInstrument):
    """
    QCoDeS Instrument driver for the
    Keysight N1094A sampling oscilloscope.
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
        
        self.chan_list = ['1A', '1B']      # For the moment only 1 channel is available
        
        self.add_function('reset', call_cmd='*RST')
        self.add_function('clear', call_cmd='*CLS')
        self.add_function('opc', call_cmd='*OPC?')
        
        ############################
        # Triggering
        self.add_parameter('trigger_level',
                           label='Trigger level',
                           set_cmd=':TRIGger:LEVel' + ' {}',
                           get_cmd=':TRIGger:LEVel?',
                           vals=vals.Numbers(-1.0,1.0),
                           get_parser=float)
        
        self.add_parameter('trigger_slope',
                           label='Edge trigger slope',
                           set_cmd=':TRIGger:SLOPe' + ' {}',
                           get_cmd=':TRIGger:SLOPe?',
                           vals=vals.Enum('POS', 'NEG'))
        
        self.add_parameter('p_lock',
                           label='Pattern lock',
                           set_cmd = ':TRIGger:PLOCk {}',
                           get_cmd = ':TRIGger:PLOCk?',
                           val_mapping = {'on':1, 'off':0})
        
        self.add_parameter('p_len_auto',
                           label = 'Pattern length autodetection',
                           set_cmd = ':TRIG:PLEN:AUT {}',
                           get_cmd = ':TRIG:PLEN:AUT?',
                           val_mapping={'on':1, 'off':0})
        
        self.add_parameter('p_len',
                           label='Pattern length',
                           set_cmd = ':TRIG:PLEN {}',
                           get_cmd = ':TRIG:PLEN?',
                           vals=vals.Ints(1,2**23),
                           get_parser=int)
        
        self.add_parameter('bit_rate_auto',
                           label='Bit rate autodetection',
                           set_cmd = ':TRIGger:SRATe:AUTodetect {}',
                           get_cmd = ':TRIGger:SRATe:AUTodetect?',
                           val_mapping={'on':1, 'off':0})
        
        self.add_parameter('bit_rate',
                           label='Bit rate',
                           unit='bit/s',
                           set_cmd = ':TRIGger:SRATe {}',
                           get_cmd = ':TRIGger:SRATe?',
                           get_parser=float)
        
        ###############################
        # Horizontal setting
        self.add_parameter('time_reference',
                           label='Time reference',
                           set_cmd=':TIMebase:REFerence' + ' {}',
                           get_cmd=':TIMebase:REFerence?',
                           vals=vals.Enum('LEFT', 'CENT','DIV'))
        
        self.add_parameter('time_range',
                           label='Time range',
                           unit='s',
                           set_cmd=':TIMebase:XRANGe' + ' {}',
                           get_cmd=':TIMebase:XRANGe?',
                           get_parser=float)
        
        self.add_parameter('time_position',
                           label='Time position',
                           unit='s',
                           set_cmd=':TIMebase:POSition' + ' {}',
                           get_cmd=':TIMebase:POSition?',
                           get_parser=float)
        
        #########################
        # Acquisition
        self.add_parameter('run_mode',
                           label='RUN/acquisition mode of the scope',
                           get_cmd=':SYSTem:MODE?',
                           set_cmd=':SYSTem:MODE' + ' {}',
                           vals=vals.Enum('OSC', 'EYE', 'TDR', 'JITT'))
        
        self.add_parameter('average',
                           label='Averaging',
                           set_cmd=':ACQuire:SMOothing' + ' {}',
                           get_cmd=':ACQuire:SMOothing?',
                           vals=vals.Enum('NONE', 'AVER', 'MED'),
                           )
        
        self.add_parameter('average_count',
                           label='Average count',
                           set_cmd=':ACQuire:ECOunt' + ' {}',
                           get_cmd=':ACQuire:ECOunt?',
                           vals=vals.Ints(1, 32768),
                           get_parser=int)
        
        self.add_parameter('rlen_mode',
                           label='Record length mode',
                           set_cmd = ':ACQuire:RLENgth:MODe'+' {}',
                           get_cmd = ':ACQuire:RLENGth:MODe?',
                           vals=vals.Enum('AUT', 'MAN'))
        
        self.add_parameter('rlen',
                           label='Record length',
                           set_cmd=':ACQuire:RLENgth' + ' {}',
                           get_cmd=':ACQuire:RLENgth?',
                           vals=vals.Ints(16, 131072),
                           get_parser=int)
        
        ###########################
        # Add the channels to the instrument
        for ch in self.chan_list:
            chan = ScopeChannel(self, 'ch{}'.format(ch), ch)
            self.add_submodule('ch{}'.format(ch), chan)
            
        self.connect_message()
        
    # function        
    def run_cont(self) -> None:
        """
        Set the instrument in 'RUN CONT' mode
        """
        self.write(':ACQuire:RUN')
        
    def measure(self) -> None:
        """
        Clear display and perform measurement 'average count'
        times.
        """
        # Stop measurement
        self.write(':ACQ:STOP')
        # Clear display
        self.write(':ACQ:CDIS')
        # Measure
        if not self.average() == 'NONE':
            avg_count = self.average_count()
            for i in range(avg_count):
                self.write(':ACQ:SING')
                self.ask('*OPC?')
        else:
            self.write(':ACQ:SING')
            self.ask('*OPC?')
        
        
    def stop(self) -> None:
        """
        Stop data acquisition
        """
        self.write(':ACQuire:STOP')
        
    def auto_scale(self) -> None:
        """
        Perform auto scale.
        """
        self.write(':SYSTem:AUToscale')
        
    def default_setup(self):
        """
        Recal default setup.
        """
        self.write(':SYSTem:DEFault')