# -*- coding: utf-8 -*-
"""
Created on Tue Jun 19 17:09:35 2018

@author: shintaro
modified by hermann
"""
import logging
import numpy as np
from typing import List, Dict, Callable
from functools import partial
import time

import nidaqmx
from nidaqmx.constants import Edge
from nidaqmx.utils import flatten_channel_string
from nidaqmx.constants import (
    TerminalConfiguration, VoltageUnits, CurrentUnits,
    CurrentShuntResistorLocation, TemperatureUnits, RTDType,
    ResistanceConfiguration, ExcitationSource, ResistanceUnits, StrainUnits,
    StrainGageBridgeType, BridgeConfiguration)
from nidaqmx.stream_readers import (
    AnalogSingleChannelReader, AnalogMultiChannelReader)
from nidaqmx.stream_writers import (
    AnalogSingleChannelWriter, AnalogMultiChannelWriter)

from qcodes import Instrument, VisaInstrument, validators as vals
from qcodes.instrument.channel import InstrumentChannel
from qcodes.instrument.parameter import ArrayParameter, Parameter

log = logging.getLogger(__name__)

class TraceNotReady(Exception):
    pass

def getTerminalConfiguration(term_config_str: str) -> TerminalConfiguration:
    if term_config_str == 'default':
        return TerminalConfiguration.DEFAULT
    elif term_config_str == 'Differential':
        return TerminalConfiguration.DIFFERENTIAL
    elif term_config_str == 'NRSE':
        return TerminalConfiguration.NRSE
    elif term_config_str == 'Pseudodifferential':
        return TerminalConfiguration.PSEUDODIFFERENTIAL
    elif term_config_str == 'RSE':
        return TerminalConfiguration.RSE
    
def getVoltageRange(voltage_range_str:str) -> float:
    if voltage_range_str == '+-0.2V':
        return 0.2
    elif voltage_range_str == '+-1V':
        return 1.0
    elif voltage_range_str == '+-5V':
        return 5.0
    elif voltage_range_str == '+-10V':
        return 10.0
    
def getEdge(edge_str: str) -> Edge:
    if edge_str == 'rise':
        return Edge.RISING
    elif edge_str == 'fall':
        return Edge.FALLING

class NI6216_ai_voltage_trace(ArrayParameter):
    def __init__(self,
                 name: str,
                 instrument: InstrumentChannel,
                 channum: int,
                 **kwargs) -> None:
        """
        The voltage trace parameter is attached to a channel of the analog input.
        """
        super().__init__(name=name,
                         instrument=instrument, # HE
                         shape=(1,),
                         label='Voltage',
                         unit='V',
                         setpoint_names=('Time',),
                         setpoint_labels=('Time',),
                         setpoint_units=('s',),
                         setpoints = None,
                         docstring='Holds analog input trace',
                         **kwargs)
        self.channum = channum
        self._instrument = instrument
    
    def get_raw(self):
        """
        Get an array from the stored dictionary
        """
        if not self._instrument._parent.trace_ready:
            raise TraceNotReady('Please run prepare_array_measurement as well'
                                'as run_array_measurement to acquire an array.')
        return self._instrument._parent.array['ai{:d}'.format(self.channum)]

class NI6216_ai_voltage_channel(InstrumentChannel):
    """
    ANALOG INPUT VOLTAGE CHANNEL
    """
    def __init__(self, 
                 parent: Instrument,
                 name: str,
                 channum: int,
                 terminal_config: str='Differential',
                 voltage_range: float=[0.2, 1.0, 5.0, 10.0][3],
				 **kwargs) -> None:
        """
        Args:
            parent (Instrument): The instrument to which the channel is attached
            name (str): The name of the channel
            channum (int): The number of the channel in question. Must match
                           the actual number as used by the instrument (0 to 31 now)
            terminal_config (str): Setup of the GND for analogue input channel. Be careful to use other than Differential about GND configuration.
            volrage_range (float): read voltage range.
        """
        if channum not in list(range(32)):
            raise ValueError('Invalid channel number. Must be between 0 and 31.')
            
        self.channum = channum
        self._term_config = terminal_config
        self._volt_range = voltage_range
        
        super().__init__(parent, name,**kwargs)
        
        self.add_parameter('term_config',
                           label='Terminal Configuration',
                           get_cmd=self.get_term_config,
                           set_cmd=self.set_term_config,
                           vals= vals.Enum('default','Differential','NRSE',
                                         'Pseudodifferential','RSE'))
        self.add_parameter('volt_range',
                           label='Voltage range',
                           unit='V',
                           get_cmd=self.get_volt_range,
                           set_cmd=self.set_volt_range,
                           val_mapping={'+-0.2V':0.2,
                                        '+-1V':1.0,
                                        '+-5V':5.0,
                                        '+-10V':10.0})
        self.add_parameter('v',
                           unit='V',
                           label='ADC-AI-{:d}'.format(self.channum),
                           get_cmd=self.get_v,
                           snapshot_value=False,
                           get_parser=float)
        
        #########################
        # Trace
        self.add_parameter('trace',
                           channum=self.channum,
                           parameter_class=NI6216_ai_voltage_trace)
    
    # Functions associated with parameters
    def get_term_config(self):
        return self._term_config
    
    def set_term_config(self, val: 'str'):
        self._term_config = val
        
    def get_volt_range(self):
        return self._volt_range
    
    def set_volt_range(self, val: float):
        self._volt_range = val
        
    def get_v(self):
        """
        Get the data point for the channel from the stored point dictionary.
        """
        if not self._parent.point_ready:
            return -999999999
        return self._parent.point['ai{:d}'.format(self.channum)]

class NI6216_ao_voltage_channel(InstrumentChannel):
    """
    ANALOG OUTPUT VOLTAGE CHANNEL
    """
    def __init__(self,
                 parent: Instrument,
                 name: str,
                 channum: int,
                 value: float=0.0,
				 **kwargs) -> None:
        """
        Args:
            parent (Instrument): The instrument to which the channel is attached
            name (str): The name of the channel
            channum (int): The number of the channel in question. Must match
                           the actual number as used by the instrument (0 to 31 now)
            value (float): Voltage of the analog-output-channel
        """
        if channum not in list(range(2)):
            raise ValueError('Invalid channel number. Must be between 0 and 2.')
            
        self.channum = channum
        self._value = value
        
        super().__init__(parent, name,**kwargs)
        
        self.add_parameter('v',
                           label='ADC-AO-{:d}'.format(self.channum),
                           unit='V',
                           scale = 1.0,
                           step = 1e-3,
                           inter_delay = 1e-3,
                           get_cmd = self.get_value,
                           set_cmd = self.set_value,
                           get_parser = float,
                           set_parser = float,
                           initial_value = value)
 
    def get_value(self):
        return self._value
    
    def set_value(self, val: float=0.0):
        ch_name = '{}/ao{:d}'.format(self._parent.devices[0], self.channum)
        with nidaqmx.Task() as task:
            task.ao_channels.add_ao_voltage_chan(ch_name)
            task.write(val,auto_start=True)
        

class NI6216(Instrument):
    """
    This is the qcodes driver for NI6216 multi function data collection device.
    
    status: beta-version
    
    Args:
        name(str): Given name of ADC
        ai_chans(List[int]): List of analogue input channels to be used. For DIFFERENTIAL MODE up to 8.
        ao_chans(List[int]): List of analogue output channels to be used.
        ai_sample_rate(int): Total sample rate of ADC. When you use N channels, rate of each becomes ?/N.
                            - Technically the maximum is 500 kHz. However, we might get error for to fast sampling rate and
                            long averaging time. Buffer becomes full and return an error.
        trigger_source(str): PFI port to accept external trigger for triggered measurement.
        trigger_mode(str): data acquisition mode.
                            Normal detection (point by point): "free"
                            fast ramp (array): "ramp"
                            fast cycle (array): "start"
        trigger_edge(str): active edge for trigger (rise or fall[default])
        average_time(int): Average time for each data point (ms). Effective for "free" and "start" mode.
        acquire_points(int): Number of points to be acquired.
    
    """
    def __init__(self, name: str, ai_chans: List[int]=[0],  ao_chans: List[int]=[0],
                 ai_sample_rate: int=250000,
                 trigger_source: str=['PFI0', 'PFI1', 'PFI2'][1],
                 trigger_mode: str=['ramp', 'start', 'free'][2],
                 trigger_edge: str=['rise','fall'][0], average_time: float=100,
                 acquire_points: int=101,
				 terminal_config: str = 'Differential', # HE
                 voltage_range: str = ['+-0.2V', '+-1V', '+-5V', '+-10V'][3],  # HE
				 **kwargs):
        super().__init__(name, **kwargs)
        # Device name
        self.devices = ['Dev1']
        # Analog input trace boolean
        self.trace_ready = False
        # Analog input point boolean
        self.point_ready = False
        # Holding dictionary of data array
        self.array = None
        # Holding dictionary of data point
        self.point = None
        
        self.ai_chans = ai_chans
        self.ao_chans = ao_chans
        
        self._ai_sample_rate = ai_sample_rate
        self._trigger_source = trigger_source
        self._trigger_mode = trigger_mode
        self._trigger_edge = trigger_edge
        self._average_time = average_time
        self._acquire_points = acquire_points
        self._buffer_size = 1000000
        
        self.add_parameter('ai_sample_rate',
                           label='AI sampling rate',
                           unit='Sa/s',
                           get_cmd=self.get_ai_sample_rate,
                           set_cmd=self.set_ai_sample_rate,
                           vals = vals.Ints(1, 500000),
                           get_parser=int)
        
        self.add_parameter('trigger_source',
                           label='Trigger source',
                           get_cmd=self.get_trigger_source,
                           set_cmd=self.set_trigger_source,
                           vals=vals.Enum('PFI0','PFI1','PFI2'))
        
        self.add_parameter('trigger_mode',
                           label = 'Trigger mode',
                           get_cmd=self.get_trigger_mode,
                           set_cmd=self.set_trigger_mode,
                           vals=vals.Enum('ramp', 'start', 'free'))
        
        self.add_parameter('trigger_edge',
                           label = 'Trigger edge',
                           get_cmd=self.get_trigger_edge,
                           set_cmd=self.set_trigger_edge,
                           vals=vals.Enum('rise', 'fall'))
    
        self.add_parameter('average_time',
                           label='Average time',
                           unit='ms',
                           get_cmd=self.get_average_time,
                           set_cmd=self.set_average_time,
                           vals=vals.Numbers(0.0, 1e9),
                           get_parser=float)
        
        self.add_parameter('acquire_points',
                           label='sample points',
                           get_cmd=self.get_acquire_points,
                           set_cmd=self.set_acquire_points,
                           vals=vals.Ints(2, 8589934590))
        
        self.add_parameter('buffer_size',
                           label='Buffer size',
                           get_cmd=self.get_buf_size,
                           set_cmd=self.set_buf_size,
                           get_parser=int)
        
        #############################
        # Open task
        self.read_task = nidaqmx.Task()
        self.sample_clk_task = nidaqmx.Task()
        
        #################################
        # Add input channels to the instrument
        for ch in self.ai_chans:
            ch_name = 'ai{}'.format(ch) # HE
            chan = NI6216_ai_voltage_channel(self, ch_name, ch)
            self.add_submodule(ch_name, chan) # HE
            self.submodules[ch_name].term_config(terminal_config) # HE
            self.submodules[ch_name].volt_range(voltage_range) # HE

        #################################
        # Add output channels to the instrument
        for ch in self.ao_chans:
            ch_name = 'ao{}'.format(ch) # HE
            chan = NI6216_ao_voltage_channel(self, ch_name, ch)
            self.add_submodule(ch_name, chan)

            
    ##########################
    # Get and set functions
    def get_ai_sample_rate(self):
        return self._ai_sample_rate
    
    def set_ai_sample_rate(self, val: int):
        self.trace_ready = False
        self._ai_sample_rate = val
        
    def get_trigger_source(self):
        return self._trigger_source
    
    def set_trigger_source(self, val: str):
        self._trigger_source = val
        
    def get_trigger_mode(self):
        return self._trigger_mode
    
    def set_trigger_mode(self, val: str):
        self._trigger_mode = val
        
    def get_trigger_edge(self):
        return self._trigger_edge
    
    def set_trigger_edge(self, val:str='rise'):
        self._trigger_edge = val
            
    def get_average_time(self):
        return self._average_time
    
    def set_average_time(self, val: float):
        self._average_time = val
        
    def get_acquire_points(self):
        return self._acquire_points
    
    def set_acquire_points(self, val: int):
        self.trace_ready = False
        self._acquire_points = val
        
    def get_buf_size(self):
        return self._buffer_size
    
    def set_buf_size(self, val: int):
        self._buffer_size = val
        
    ##########################
    # Base functions
    def get_idn(self):
        system = nidaqmx.system.System.local()
        ver = system.driver_version
        idn = {'major_version': ver[0],
                'minor_version': ver[1],
                'update_version': ver[2]}
        
        device_list = list()
        for device in system.devices:
            device_list.append(device.name)    
        idn['devices'] = device_list
        
        return idn
        
    def close(self):
        self.read_task.close()
        self.sample_clk_task.close()
        
    def connect(self):
        self.read_task = nidaqmx.Task()
        self.sample_clk_task = nidaqmx.Task()
        
    def clear(self):
        self.close()
        self.connect()
        
    #################################
    # Functions for data acquisition
    def set_sample_clock(self, samples: int) -> None:
        """
        Prepare the sample clock for the measurement
        
        Args:
            samples (int): Number of trigger (points) for measurement
        """
        # Set constants
        device_name = self.devices[0]
        sample_rate = self._ai_sample_rate
        sample_rate_per_channel = sample_rate/len(self.ai_chans)
        sample_clk_task = self.sample_clk_task
        
        # Set sample clock condition
        sample_clk_task.co_channels.add_co_pulse_chan_freq(
                '{0}/ctr0'.format(device_name),
                units=nidaqmx.constants.FrequencyUnits.HZ,
                idle_state=nidaqmx.constants.Level.LOW,
                initial_delay=0.0,
                freq=sample_rate_per_channel,
                duty_cycle=0.5,
                )
        sample_clk_task.timing.cfg_implicit_timing(
                samps_per_chan=samples,
                sample_mode=nidaqmx.constants.AcquisitionType.FINITE)
    
    def set_start_trigger(self):
        """
        Set the starting trigger for the read task
        """
        self.sample_clk_task.triggers.start_trigger.cfg_dig_edge_start_trig(
                '/{}/{}'.format(self.devices[0], self._trigger_source),
                trigger_edge=getEdge(self._trigger_edge))
        # Make the task to be retriggerable
        self.sample_clk_task.triggers.start_trigger.retriggerable = True
        
    def prepare_measurement(self):
        """
        This function setup the condition for sample_clock task as well as
        read task and make it ready to run array measurements.
        """
        # Setup the read channels
        read_channels = self.ai_chans
        # Sample rate
        sample_rate = self._ai_sample_rate
        sample_rate_per_channel = sample_rate/len(read_channels)
        # Calculate sample_per_point
        sample_per_point = int(max(2, np.floor(sample_rate_per_channel*self._average_time/1000)))
        # Device name
        device_name = self.devices[0]
        
        
        # Clear task
        self.clear()
        
        # Setup the read channels
        for ch in read_channels:
            chan = getattr(self, 'ai{:d}'.format(ch))
            self.read_task.ai_channels.add_ai_voltage_chan(
                    '{}/ai{:d}'.format(device_name, ch),
                    terminal_config=getTerminalConfiguration(chan.term_config()),
                    min_val = - abs(getVoltageRange(chan.volt_range())), max_val=abs(getVoltageRange(chan.volt_range())))
        
        if not self._trigger_mode == 'free':
            self.read_task.timing.cfg_samp_clk_timing(
                    sample_rate_per_channel,
                    source='/{0}/Ctr0InternalOutput'.format(device_name),
                    active_edge=Edge.RISING,
                    sample_mode=nidaqmx.constants.AcquisitionType.CONTINUOUS)
        else:
            self.read_task.timing.cfg_samp_clk_timing(
                    sample_rate_per_channel,
                    active_edge=Edge.RISING, samps_per_chan=sample_per_point,
                    sample_mode=nidaqmx.constants.AcquisitionType.CONTINUOUS)
        
        # Configure buffer
        self.read_task.in_stream.input_buf_size = self._buffer_size
        self.read_task.in_stream.over_write = nidaqmx.constants.OverwriteMode.OVERWRITE_UNREAD_SAMPLES
        
        self.read_task.control(nidaqmx.constants.TaskMode.TASK_COMMIT)
        
        if not self._trigger_mode == 'free':
            # Set the sample clock
            self.set_sample_clock(samples=sample_per_point)
            # Set the trigger source for the triggered measurement
            self.set_start_trigger()
        
    def run_measurement(self):
        """
        Run measurements and get a point.
        Finally set point_ready to True.
        """
        # Setup the read channels
        read_channels = self.ai_chans
        # Sample rate
        sample_rate = self._ai_sample_rate
        sample_rate_per_channel = sample_rate/len(read_channels)
        # Calculate sample_per_point
        sample_per_point = int(max(2, np.floor(sample_rate/len(read_channels)*self._average_time/1000)))
        # Define reader
        reader = AnalogMultiChannelReader(self.read_task.in_stream)
        
        results = {}
        
        values_read = np.zeros(
                (len(read_channels), sample_per_point), dtype=np.float64)
        
        self.read_task.start()
        if not self._trigger_mode == 'free':
            self.sample_clk_task.start()
            
        # Read data from the buffer
        reader.read_many_sample(
                values_read, number_of_samples_per_channel=sample_per_point,
                timeout=int(sample_per_point/sample_rate_per_channel)+2)
        
        self.read_task.stop()
        
        for j, ch in enumerate(read_channels):
            results['ai{:d}'.format(ch)] = np.average(values_read[j,:])
            
        if not self._trigger_mode == 'free':
            self.sample_clk_task.stop()
                    
        # Store results to data
        self.point = results
        self.point_ready = True
    
    def measure(self,precision: int=None):
        """
        This functions performs a measurement and returns the corresponding
        values of the active input channels.
        """
        
        self.prepare_measurement()
        self.run_measurement()
        readout = list()
        
        for submodule in self.submodules:
            if submodule[:2] == 'ai':
                readout.append(self.submodules[submodule].get_v())
        readout = np.array(readout)
        
        if precision != None:
            readout = np.round(readout,int(precision))
            
        return readout
    
    def prepare_array_measurement(self):
        """
        This function setup the condition for sample_clock task as well as
        read task and make it ready to run array measurements.
        """
        # Set trace_ready to be False before the new array measurement.
        self.trace_ready = False
        # Setup the read channels
        read_channels = self.ai_chans
        # Sample rate
        sample_rate = self._ai_sample_rate
        sample_rate_per_channel = sample_rate/len(read_channels)
        # Calculate sample_per_point
        sample_per_point = int(max(2, np.floor(sample_rate_per_channel*self._average_time/1000)))
        # Compensation factor for ramp mode
        if self._trigger_mode == 'ramp':
            # - When we set points same amount as trigger interval, we miss some samples and gets error.
            sample_per_point = int(np.floor(sample_per_point * 0.88))
            
        # points
        points = self._acquire_points
        # Calculate the total points
        if self._trigger_mode == 'start':
            measurement_points = points * sample_per_point
        else:
            measurement_points = sample_per_point
        # Device name
        device_name = self.devices[0]
        
        # Clear task
        self.clear()
        
        # Make setpoints for read channels
        setpoints = tuple(np.arange(points, dtype=np.float64) * sample_per_point/sample_rate_per_channel)
        
        # Setup the read channels
        for ch in read_channels:
            chan = getattr(self, 'ai{:d}'.format(ch))
            chan.trace.shape = (points,)
            if chan.trace.setpoints == None:
                chan.trace.setpoints = (setpoints,)
            self.read_task.ai_channels.add_ai_voltage_chan(
                    '{}/ai{:d}'.format(device_name, ch),
                    terminal_config=getTerminalConfiguration(chan.term_config()),
                    min_val = - abs(getVoltageRange(chan.volt_range())), max_val=abs(getVoltageRange(chan.volt_range())),
                    units = nidaqmx.constants.VoltageUnits.VOLTS,
                    )
            
        if not self._trigger_mode == 'free':
            self.read_task.timing.cfg_samp_clk_timing(
                    sample_rate_per_channel,
                    source='/{0}/Ctr0InternalOutput'.format(device_name),
                    active_edge=Edge.RISING,
                    sample_mode=nidaqmx.constants.AcquisitionType.CONTINUOUS,
                    )
        else:
            self.read_task.timing.cfg_samp_clk_timing(
                    sample_rate_per_channel,
                    active_edge=Edge.RISING,
                    samps_per_chan=measurement_points,
                    sample_mode=nidaqmx.constants.AcquisitionType.CONTINUOUS,
                    )
        
        # Configure buffer
        self.read_task.in_stream.input_buf_size = self._buffer_size
        self.read_task.in_stream.over_write = nidaqmx.constants.OverwriteMode.OVERWRITE_UNREAD_SAMPLES
        
        # Start read_task
        self.read_task.control(nidaqmx.constants.TaskMode.TASK_COMMIT)
        self.read_task.start()
        
        if not self._trigger_mode == 'free':
            # Set the sample clock
            self.set_sample_clock(samples=measurement_points)
        
            # Set the trigger source for the triggered measurement
            self.set_start_trigger()
            
            self.sample_clk_task.start()
            
    def run_array_measurement(self):
        """
        Read array from buffer.
        Finally set trace_ready to True.
        """
        # Setup the read channels
        read_channels = self.ai_chans
        # Sample rate
        sample_rate = self._ai_sample_rate
        sample_rate_per_channel = sample_rate/len(read_channels)
        # Calculate sample_per_point
        sample_per_point = int(max(2, np.floor(sample_rate_per_channel*self._average_time/1000)))
        # Compensation factor for ramp mode
        if self._trigger_mode == 'ramp':
            # - When we set points same amount as trigger interval, we miss some samples and gets error.
            sample_per_point = int(np.floor(sample_per_point * 0.88))
        
        # points
        points = self.acquire_points()
        # Define reader
        reader = AnalogMultiChannelReader(self.read_task.in_stream)
        
        if self._trigger_mode == 'start':
            repetition = 1
            measurement_points = points * sample_per_point
        else:
            repetition = points
            measurement_points = sample_per_point
        
        results = {}
        for ch in read_channels:
            results['ai{:d}'.format(ch)] = np.zeros((points,), dtype=np.float64)
        
        values_read = np.zeros(
                    (len(read_channels), measurement_points), dtype=np.float64)
        for i in range(repetition):
            reader.read_many_sample(
                    values_read,
                    number_of_samples_per_channel = measurement_points,
                    timeout=int(measurement_points/sample_rate_per_channel)+2)
            
            for j, ch in enumerate(read_channels):
                if self._trigger_mode == 'start':
                    results['ai{:d}'.format(ch)][:] = np.average(
                            values_read[j,:].reshape(points, sample_per_point), axis=1)
                else:
                    results['ai{:d}'.format(ch)][i] = np.average(values_read[j,:])
                    
        # Store results to data
        self.array = results
        self.trace_ready = True
