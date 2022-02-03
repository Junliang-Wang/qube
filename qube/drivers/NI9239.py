# -*- coding: utf-8 -*-
"""
Created on Tue Aug 25 21:13:53 2020

@author: takada
"""
import logging
import numpy as np
from typing import List, Dict, Callable, Tuple
import time

import nidaqmx
from nidaqmx.constants import Edge
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

    
def getEdge(edge_str: str) -> Edge:
    if edge_str == 'rise':
        return Edge.RISING
    elif edge_str == 'fall':
        return Edge.FALLING

class NI9239_ai_voltage_trace(ArrayParameter):
    def __init__(self, name: str, instrument: InstrumentChannel,
                 channum: int) -> None:
        """
        The voltage trace parameter is attached to a channel of the analog input.
        """
        super().__init__(name=name,
                         shape=(1,),
                         label='Voltage',
                         unit='V',
                         setpoint_names=('Time',),
                         setpoint_labels=('Time',),
                         setpoint_units=('s',),
                         setpoints = None,
                         docstring='Holds analog input trace')
        self.channum = channum
        self._instrument = instrument
    
    def get_raw(self):
        """
        Get an array from the stored dictionary
        """
        if not self._instrument._parent.trace_ready:
            raise TraceNotReady('Please run prepare_array_measurement as well'
                                'as run_array_measurement to acquire an array.')
        return self._instrument._parent.array['ai{:d}c{:d}'.format(self.channum[0], self.channum[1])]

class NI9239_ai_voltage_channel(InstrumentChannel):
    def __init__(self, parent: Instrument, name: str,
                 channum: Tuple[int],
                 ) -> None:
        """
        Args:
            parent (Instrument): The instrument to which the channel is attached
            name (str): The name of the channel
            channum (List[int]): A pair of module number and channel number.
        """
        self.channum = channum
        
        super().__init__(parent, name)
        
        self.add_parameter('v',
                           unit='V',
                           get_cmd=self.get_v,
                           snapshot_value=False,
                           get_parser=float)
        
        #########################
        # Trace
        self.add_parameter('trace',
                           channum=self.channum,
                           parameter_class=NI9239_ai_voltage_trace)
        
    def get_v(self):
        """
        Get the data point for the channel from the stored point dictionary.
        """
        if not self._parent.point_ready:
            return -999999999
        return self._parent.point['ai{:d}c{:d}'.format(self.channum[0],self.channum[1])]

class NI9239(Instrument):
    def __init__(self,
                 name: str,
                 device_name:str = 'cDAQ1',
                 ai_chans: List[int]=[(1,0),(1,1),(1,2),(1,3)],
                 ai_sample_rate: int=50000,
                 trigger_source: str=['PFI0', 'PFI1'][0],
                 trigger_edge: str=['rise','fall'][0],
                 average_time: float=100,
                 acquire_points: int=101,
                 **kwargs):
        """
        This is the qcodes driver for NI9239 ADC. Whose sampling rate can be controlled
        between 1.613 kS/s and 50 kS/s independent for each channel. ADC resolution is 24 bits.
        Terminal configuration is 'Differential' and voltage range is +-10 V.
        
        status: beta-version
        
        Args:
            name(str): Given name of ADC
            device_name(str): Name of the device in DAQ system.
            ai_chans(List[int]): List of analogue input channels to be used. (module number, channel number)
                                One module has 4 analog input channels.
            ai_sample_rate(int): Total sample rate of ADC. This parameter can be set between
                                1.613 kHz and 50 kHz.
            trigger_source(str): PFI port to accept external trigger for triggered measurement.
            trigger_edge(str): active edge for trigger (rise or fall[default])
            average_time(int): Average time for each data point (ms). Effective for "free" and "start" mode.
            acquire_points(int): Number of points to be acquired for triggered array measurement.
        
        """
        super().__init__(name, **kwargs)
        # Device name
        self.device_name = device_name
        # Analog input trace boolean
        self.trace_ready = False
        # Analog input point boolean
        self.point_ready = False
        # Holding dictionary of data array
        self.array = None
        # Holding dictionary of data point
        self.point = None
        
        self.ai_chans = ai_chans
        self._ai_sample_rate = ai_sample_rate
        self._trigger_source = trigger_source
        self._trigger_edge = trigger_edge
        self._average_time = average_time
        self._acquire_points = acquire_points
        
        self.add_parameter('ai_sample_rate',
                           label='AI sampling rate',
                           unit='Sa/s',
                           get_cmd=self.get_ai_sample_rate,
                           set_cmd=self.set_ai_sample_rate,
                           vals = vals.Ints(1613, 50000),
                           get_parser=int)
        
        self.add_parameter('trigger_source',
                           label='Trigger source',
                           get_cmd=self.get_trigger_source,
                           set_cmd=self.set_trigger_source,
                           vals=vals.Enum('PFI0','PFI1'))
        
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
        
        #############################
        # Open task
        self.read_task = nidaqmx.Task()
        
        #################################
        # Add channels to the instrument
        for ch in self.ai_chans:
            chan = NI9239_ai_voltage_channel(self, 'analog_input{:d}_{:d}'.format(ch[0],ch[1]), ch)
            self.add_submodule('ai{:d}c{:d}'.format(ch[0],ch[1]), chan)
        
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
        
    def connect(self):
        self.read_task = nidaqmx.Task()
        
    def clear(self):
        self.close()
        self.connect()
        
    #################################
    # Functions for data acquisition
        
    def prepare_measurement(self):
        """
        This function setup the condition for sample_clock task as well as
        read task and make it ready to run array measurements.
        """
        # Clear task
        self.clear()
        
        # Calculate sample_per_point
        sample_per_point = int(max(2, np.floor(self._ai_sample_rate*self._average_time/1000)))
        
        # Setup the read channels
        for ch in self.ai_chans:
            self.read_task.ai_channels.add_ai_voltage_chan(
                    '{}Mod{:d}/ai{:d}'.format(self.device_name, ch[0], ch[1]),
                    terminal_config=nidaqmx.constants.TerminalConfiguration.DEFAULT,
                    min_val = - 10.0, max_val=10.0)
        
        self.read_task.timing.cfg_samp_clk_timing(
                rate = self._ai_sample_rate,
                active_edge=Edge.RISING,
                samps_per_chan = sample_per_point,
                sample_mode=nidaqmx.constants.AcquisitionType.FINITE)
        
        # Configure buffer
        self.read_task.in_stream.input_buf_size = sample_per_point
        self.read_task.in_stream.over_write = nidaqmx.constants.OverwriteMode.OVERWRITE_UNREAD_SAMPLES
        
        self.read_task.control(nidaqmx.constants.TaskMode.TASK_COMMIT)
        
    def run_measurement(self):
        """
        Run measurements and get a point.
        Finally set point_ready to True.
        """
        # Setup the read channels
        read_channels = self.ai_chans
        # Sample rate
        sample_rate = self._ai_sample_rate
        # Calculate sample_per_point
        sample_per_point = int(max(2, np.floor(sample_rate*self._average_time/1000)))
        # Define reader
        reader = AnalogMultiChannelReader(self.read_task.in_stream)
        
        results = {}
        
        values_read = np.zeros(
                (len(read_channels), sample_per_point), dtype=float)
        
        self.read_task.start()
            
        # Read data from the buffer
        reader.read_many_sample(
                values_read, number_of_samples_per_channel=sample_per_point,
                timeout=int(sample_per_point/sample_rate)+2)
        
        self.read_task.stop()
        for j, ch in enumerate(read_channels):
            results['ai{:d}c{:d}'.format(ch[0], ch[1])] = np.average(values_read[j,:])
                    
        # Store results to data
        self.point = results
        self.point_ready = True
    
    def prepare_array_measurement(self):
        """
        This function setup the condition for sample_clock task as well as
        read task and make it ready to run array measurements.
        
        For NI9239 it is not possible to set the property 'retriggerable'.
        Therefore, we can only measure all the points at once depending on
        the average time, sampling rate, acquire points.
        """
        # Set trace_ready to be False before the new array measurement.
        self.trace_ready = False
        # Calculate sample_per_point
        sample_per_point = int(max(2, np.floor(self._ai_sample_rate*self._average_time/1000)))
        total_samples = self._acquire_points * sample_per_point
        
        # Clear task
        self.clear()
        
        # Make setpoints for read channels
        setpoints = tuple(np.arange(self._acquire_points, dtype=float) * self._average_time/1000)
        
        # Setup the read channels
        for ch in self.ai_chans:
            chan = getattr(self, 'ai{:d}c{:d}'.format(ch[0], ch[1]))
            chan.trace.shape = (self._acquire_points,)
            chan.trace.setpoints = (setpoints,)
            self.read_task.ai_channels.add_ai_voltage_chan(
                    '{}Mod{:d}/ai{:d}'.format(self.device_name, ch[0], ch[1]),
                    terminal_config=nidaqmx.constants.TerminalConfiguration.DEFAULT,
                    min_val = -10.0, max_val = 10.0,
                    units = nidaqmx.constants.VoltageUnits.VOLTS,
                    )
            
        self.read_task.timing.cfg_samp_clk_timing(
                    rate = self._ai_sample_rate,
                    source = 'OnboardClock',
                    active_edge=Edge.RISING,
                    samps_per_chan = total_samples,
                    sample_mode=nidaqmx.constants.AcquisitionType.FINITE,
                    )
        
        # Configure buffer
        self.read_task.in_stream.input_buf_size = total_samples
        self.read_task.in_stream.over_write = nidaqmx.constants.OverwriteMode.OVERWRITE_UNREAD_SAMPLES
    
        # Set the digital start trigger
        self.read_task.triggers.start_trigger.cfg_dig_edge_start_trig(trigger_source = '/{}/{}'.format(self.device_name, self._trigger_source),
                                                                     trigger_edge = getEdge(self._trigger_edge)
                                                                     )
        
        self.read_task.control(nidaqmx.constants.TaskMode.TASK_COMMIT)
        self.read_task.start()
            
    def run_array_measurement(self):
        """
        Read array from buffer.
        Finally set trace_ready to True.
        """
        # Calculate sample_per_point
        sample_per_point = int(max(2, np.floor(self._ai_sample_rate*self._average_time/1000)))
        total_samples = sample_per_point * self._acquire_points

        # Define reader
        reader = AnalogMultiChannelReader(self.read_task.in_stream)
                
        results = {}
        for ch in self.ai_chans:
            results['ai{:d}c{:d}'.format(ch[0], ch[1])] = np.zeros((self._acquire_points,), dtype=float)
        
        values_read = np.zeros(
                    (len(self.ai_chans), total_samples), dtype=float)
        
        reader.read_many_sample(
                values_read,
                number_of_samples_per_channel = total_samples,
                timeout=int(total_samples/self._ai_sample_rate)+2)
        
        for i, ch in enumerate(self.ai_chans):
            results['ai{:d}c{:d}'.format(ch[0], ch[1])][:] = np.average(
                values_read[i,:].reshape(self._acquire_points, sample_per_point), axis=1)
                    
        # Store results to data
        self.array = results
        self.trace_ready = True
        
if __name__=='__main__':
    t = time.time()
    from NI6733 import NI6733
    dac = NI6733(name = 'dac',
                 device_name = 'PXI2',
                 slots=[3,4,],
                 ms2wait = 2.0,
                 )
    adc = NI9239(name = 'adc',
                 ai_sample_rate = 50000,
                 trigger_source = 'PFI0',
                 trigger_edge = ['rise','fall'][1],
                 average_time = 100,
                 acquire_points = 101)
    
    # # Normal measurement test
    # adc.prepare_measurement()
    
    # # DAC movement test
    # dac.s3c0.cv(-0.2)
    # # dac.s4c3.cv(-0.1)
    # dac.DAC_move(task_preparation = True,
    #               clear_task = False)
    # adc.run_measurement()
    # # print(adc.ai1c0.v())
    # print(adc.ai1c3.v())
    
    # dac.s3c0.cv(-0.4)
    # # dac.s4c3.cv(-0.3)
    # dac.DAC_move(task_preparation = False,
    #               clear_task = False)
    # adc.run_measurement()
    # # print(adc.ai1c0.v())
    # print(adc.ai1c3.v())
    
    # dac.s3c0.cv(-0.6)
    # # dac.s4c3.cv(-0.5)
    # dac.DAC_move(task_preparation = False,
    #               clear_task = False)
    # adc.run_measurement()
    # # print(adc.ai1c0.v())
    # print(adc.ai1c3.v())
    
    # dac.s3c0.cv(-0.0)
    # # dac.s4c3.cv(-0.0)
    # dac.DAC_move(task_preparation = True,
    #               clear_task = True)
    # adc.run_measurement()
    # # print(adc.ai1c0.v())
    # print(adc.ai1c3.v())
    
    
    
    # # Sweep test
    # adc.prepare_measurement()
    
    # ar = np.linspace(0.0, -0.5, 101)
    # for i in range(101):
    #     print(i, ar[i])
    #     dac.s3c0.cv(ar[i])
    #     dac.DAC_move(task_preparation=True,
    #                  clear_task = True)
    
    
    
    # Fast sequence test
    for i in range(1):
        t = time.time()
        points = 1001
        average_time = 2.0
        
        dac.fs_pts(points)
        dac.fs_div(average_time)
        dac.s3c0.fs(True)
        dac.s3c0.fs_delta(-0.5)
        dac.s4c0.fs(True)
        dac.s4c0.fs_delta(-1.0)
        dac.prepare_fast_move()
        
        dac.s3c0.cv(-0.1)
        dac.DAC_move(task_preparation=True,
                      clear_task=True)
        
        adc.average_time(average_time)
        adc.acquire_points(points)
        adc.prepare_array_measurement()
        
        dac.DAC_fast_move()
        adc.run_array_measurement()
    
        data = adc.ai1c0.trace()
        data = adc.ai1c1.trace()
        
        dac.s3c0.cv(-0.1)
        dac.DAC_move(task_preparation=True,
                      clear_task=True)
        
        print(i)
        print('Execution time {:f}'.format(time.time() - t))
        
    print(data)