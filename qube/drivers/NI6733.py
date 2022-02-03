# -*- coding: utf-8 -*-
"""
Created on Fri Aug 21 20:00:50 2020

@author: takada
"""
import logging
import numpy as np
import functools
import operator
from typing import List, Dict, Callable
import time

import nidaqmx
from nidaqmx.stream_writers import (
    DigitalSingleChannelWriter, AnalogMultiChannelWriter)

from qcodes import Instrument, VisaInstrument, validators as vals
from qcodes.instrument.channel import InstrumentChannel
from qcodes.instrument.parameter import ArrayParameter, Parameter
from qcodes.dataset.sqlite.database import connect
from qcodes.dataset.sqlite.queries import get_last_run
from qcodes.dataset.data_set import load_by_id

log = logging.getLogger(__name__)

class NI6733_ao_voltage_trace(ArrayParameter):
    def __init__(self, name:str, instrument: InstrumentChannel,
                 channum: int) -> None:
        """
        This voltage trace parameter is attached to a channel of the analog output.

        Parameters
        ----------
        name : str
            Name of the trace.
        instrument : InstrumentChannel
            Instrument channel, where the trace is attached.
        channum : int
            Integer number of the channel, where the trace is attached.
            
        Returns
        -------
        None
            DESCRIPTION.

        """
        super().__init__(name=name,
                         shape=(1,),
                         label = 'voltage',
                         unit='V',
                         setpoint_names=('Count',),
                         setpoint_labels=('Count',),
                         setpoint_units=('pts',),
                         setpoints = None,
                         docstring='Holds analog output trace')
        self.channum = channum
        self._instrument = instrument
        
    def get_raw(self):
        pass
    
class NI6733_ao_voltage_channel(InstrumentChannel):
    def __init__(self, parent: Instrument, name:str,
                 slot_num:int, channum: int, min_val:float=-10.0,
                 fast_sequence:bool=False, fast_sequence_delta:float = -0.1,
                 max_val:float= 10.0) -> None:
        """
        

        Parameters
        ----------
        parent : Instrument
            Host instrument handler
        name : str
            Given name of the channel
        slot_num : int
            Slot number of the channel
        channum : int
            Channel number
        min_val : float, optional
            Minimum value of the channel voltage value. The default is -10.0.
        max_val : float, optional
            Maximum value of the channel voltage value. The default is 10.0.
        fast_sequence : bool, optional
            Whether this dac is used for fast sequence or not.
        fast_sequence_delta: float
            How far the voltage is moved by the fast sequence from its original position.

        Returns
        -------
        None
            DESCRIPTION.

        """
        super().__init__(parent, name)
        
        self.instrument = parent
        self.slot_num = slot_num
        self.channum = channum
        self._min_val = min_val
        self._max_val = max_val
        self._current_val = 0.0
        self._target_val = None
        self._fast_sequence = fast_sequence
        self._fast_sequence_delta = fast_sequence_delta
        
        self.add_parameter('min_val',
                           label = 'Minimum value',
                           unit = 'V',
                           get_cmd=self.get_min_val,
                           set_cmd=self.set_min_val,
                           vals = vals.Numbers(-10.0, 10.0)
                           )
        
        self.add_parameter('max_val',
                           label = 'Maximum value',
                           unit = 'V',
                           get_cmd=self.get_max_val,
                           set_cmd=self.set_max_val,
                           vals = vals.Numbers(-10.0, 10.0)
                           )
        
        self.add_parameter('cv',
                           label = 'Current value',
                           unit = 'V',
                           get_cmd=self.get_current_val,
                           set_cmd=self.set_current_val,
                           vals = vals.Numbers(-5.0, 5.0)
                           )
        
        self.add_parameter('fs',
                           label='fast sequence',
                           get_cmd = self.get_fast_sequence,
                           set_cmd = self.set_fast_sequence,
                           )
        
        self.add_parameter('fs_delta',
                           label = 'fast sequence delta',
                           unit = 'V',
                           get_cmd = self.get_fast_sequence_delta,
                           set_cmd = self.set_fast_sequence_delta,
                           vals = vals.Numbers(-1.0, 1.0)
                           )
        
    def get_min_val(self):
        return self._min_val
    
    def set_min_val(self, val:float):
        self._min_val = val
        
    def get_max_val(self):
        return self._max_val
    
    def set_max_val(self, val:float):
        self._max_val = val
        
    def get_current_val(self):
        return self._current_val
    
    def set_current_val(self, val:float):
        self._target_val = val
        
    def get_fast_sequence(self):
        return self._fast_sequence
    
    def set_fast_sequence(self, val:bool):
        self._fast_sequence = val
        self.instrument._fs_ready = False
        
    def get_fast_sequence_delta(self):
        return self._fast_sequence_delta
    
    def set_fast_sequence_delta(self, val:float):
        self._fast_sequence_delta = val
        self.instrument._fs_ready = False

class NI6733(Instrument):
    def __init__(self, name:str, device_name:str = 'PXI2',
                 slots:List[int]=[3,4,], ms2wait:float = 2.0,
                 fast_sequence_divider:float = 2.0, fs_pts:int = 101,
                 **kwargs):
        """
        This is the qcodes driver for NI6733 16 bit Analog Output.
        
        Args:
            name (str): Given name of the DAC
            device_name (str): Name of the PXI device. Default value is 'PXI2'.
            slots(List[int]): List of DAC slots. Each slot has 8 DAC channels.
            ms2wait (float): Wait time between minimum resolution DAC movement in [ms].
            fast_sequence_divider (float): Time between fast sequence movement in [ms].
            fs_pts (int): Length of the fast sequence.
        """
        super().__init__(name, **kwargs)
        
        self.device_name = device_name
        self.slots = slots
        self._ms2wait = ms2wait
        self._fast_sequence_divider = fast_sequence_divider
        self._fs_pts = fs_pts
        self._fs_ready = False
        self._fast_move_slot_list = list()
        self._fast_move_channel_list = dict()
        self._fast_move_list = dict()
        self._move_points = None
        
        self.write_task = dict()
        self.fast_seq_task = dict()
        for slot in self.slots:
            self.write_task[slot] = nidaqmx.Task()
            self.write_task['{:d}'.format(slot)] = False
            self.fast_seq_task[slot] = nidaqmx.Task()
            self.fast_seq_task['{:d}'.format(slot)] = False
        self.ctr_task = nidaqmx.Task()
        self.ctr_task_isClosed = False
        self.do_task = nidaqmx.Task()
        self.do_task_isClosed = False
        
        self.add_parameter('ms2wait',
                           label = 'ms to wait',
                           unit = 'ms',
                           get_cmd = self.get_ms2wait,
                           set_cmd = self.set_ms2wait,
                           vals = vals.Numbers(0.0, 100.0))
        
        self.add_parameter('fs_div',
                           label = 'fast sequence divider',
                           unit = 'ms',
                           get_cmd = self.get_fast_sequence_divider,
                           set_cmd = self.set_fast_sequence_divider,
                           vals = vals.Numbers(0.0, 100.0))
        
        self.add_parameter('fs_pts',
                           label = 'fast sequence size',
                           unit = 'pts',
                           get_cmd = self.get_fs_pts,
                           set_cmd = self.set_fs_pts,
                           vals = vals.Ints(2, 100000)
                           )
        
        ######################
        # Add channels to the instrument
        for slot in self.slots:
            for i in range(8):
                chan = NI6733_ao_voltage_channel(self,
                                                 'analog_output_s{:d}c{:d}'.format(slot, i),
                                                 slot_num = slot,
                                                 channum = i)
                self.add_submodule('s{:d}c{:d}'.format(slot, i), chan)
        
    ###########################
    # Function for parameters
    ###########################
    def get_ms2wait(self):
        return self._ms2wait
    
    def set_ms2wait(self, val:float):
        self._ms2wait = val
        
    def get_fast_sequence_divider(self):
        return self._fast_sequence_divider
    
    def set_fast_sequence_divider(self, val:float):
        self._fast_sequence_divider = val
        self._fs_ready = False
        
    def get_fs_pts(self):
        return self._fs_pts
    
    def set_fs_pts(self, val:int):
        self._fs_pts = val
        self._fs_ready = False
        
    ###########################
    # Utility functions
    ###########################
    def move_all_dac(self, v:float = 0.0):
        """
        Move all the dac to the given value.
        Scaling factor for each dac is not applied in this operation.

        Parameters
        ----------
        v : float, optional
            Target voltage in volt. The default is 0.0.

        Returns
        -------
        None.

        """
        for s in self.slots:
            for i in range(8):
                chan = getattr(self, 's{:d}c{:d}'.format(s, i))
                chan._target_val = v
        self.DAC_move()
        
    def init2zero(self):
        """
        Initialise all the DAC values to be 0.0 V after moving once to -10 mV.
        """
        self.move_all_dac()(-0.01)
        self.move_all_dac()(0.0)
        
    def load_current_values_from_database(self,
                                          db_path:str = './experiments.db',
                                          run_id:int = None,
                                          ):
        """
        Load current DAC values from the specified database and run_id.
        If run_id is not given, we load from the latest run_id.
        
        Args:
            db_path (str): Path to the database.
            run_id (int): run_id of the recovered run.
        """
        # Connect to the database
        conn = connect(db_path)
        if run_id == None:
            # Get last run id
            run_id = get_last_run(conn)
            
        # Load dataset
        dataset = load_by_id(run_id)
        # Whether return to initial sweep position after the measurment or not
        return2initial = dataset.snapshot['station']['instruments']['measurement_information']['parameters']['return2initial']['value']
        
        # Collect information from sweeping parameters
        data = dataset.get_parameter_data()
        data_dict = dict()
        for key in data.keys():
            d = data[key]
            for k in d.keys():
                if not k in data_dict.keys():
                    data_dict[k] = d[k]
        # Check whether measurement was complelted or not from data size
        ar_size = d[k].size
        fast_sweep = dataset.snapshot['station']['instruments']['measurement_information']['parameters']['fast_sweep']['value']
        sweep_dims = dataset.snapshot['station']['instruments']['measurement_information']['parameters']['sweep_dims']['value']
        if fast_sweep:
            first_dim_size = dataset.snapshot['station']['instruments'][self.name]['parameters']['fs_pts']['value']
        else:
            first_dim_size = 1
        total_pts = int(functools.reduce(operator.mul, sweep_dims, 1) * first_dim_size)
        
        if not ar_size == total_pts:
            completed = False
        else:
            completed = True
                    
        # Set current value of each dac from static values
        for sm in dataset.snapshot['station']['instruments'][self.name]['submodules'].keys():
            # Get raw value of each dac
            cv = dataset.snapshot['station']['instruments'][self.name]['submodules'][sm]['parameters']['cv']['raw_value']
            chan = getattr(self, sm)
            sm_fullname = dataset.snapshot['station']['instruments'][self.name]['submodules'][sm]['parameters']['cv']['full_name']
            if sm_fullname in data_dict.keys():
                if return2initial and completed:
                    cv = data_dict[sm_fullname][0]
                else:
                    cv = data_dict[sm_fullname][-1]
                
            chan._current_val = cv
            
        conn.close()
        
    def init_tasks(self):
        """
        Close all the task, which is opend. Then open it again.
        """
        if not self.do_task_isClosed:
            self.do_task.close()
            self.do_task = nidaqmx.Task()
            
        if not self.ctr_task_isClosed:
            self.ctr_task.close()
            self.ctr_task = nidaqmx.Task()
            
        for slot in self.slots:
            if not self.write_task['{:d}'.format(slot)]:
                self.write_task[slot].close()
                self.write_task[slot] = nidaqmx.Task()
                
            if not self.fast_seq_task['{:d}'.format(slot)]:
                self.fast_seq_task[slot].close()
                self.fast_seq_task[slot] = nidaqmx.Task()

    ###################################
    # Base functions for voltage output
    ###################################
    def ctr_setup(self,
                  task:nidaqmx.Task = None,
                  slot_num:int = 3,
                  no_of_samples:int = None,
                  trigger_delay:int = 0.0,
                  ):
        """
        This function setup a counter output for the counter 0 for the given slot.
        
        Args:
            task(nidaqmx.Task): Task counter is set.
            slot_num(int): Slot number of the trigger out
            no_of_samples (int): Number of trigger generated. If it is None, a trigger is generated continuously.
            trigger_delay (int): Delay of the counter in seconds.
        """
        # Create counter output channel
        task.co_channels.add_co_pulse_chan_freq('{}Slot{:d}/ctr0'.format(self.device_name, slot_num),
                                                            units = nidaqmx.constants.FrequencyUnits.HZ,
                                                            idle_state = nidaqmx.constants.Level.LOW,
                                                            initial_delay = trigger_delay,
                                                            freq = 1000.0/self._fast_sequence_divider,
                                                            duty_cycle = 0.5,
                                                            )
        # Set sample generation mode and number of samples to be generated.
        # Comment: Incrase 'samps_per_chan' by 3 since some trigger is missed by analog output.
        task.timing.cfg_implicit_timing(samps_per_chan = no_of_samples+3,
                                                 sample_mode = nidaqmx.constants.AcquisitionType.FINITE)
        
    def do_setup(self,
                 task:nidaqmx.Task = None,
                 slot_num:int = 3,
                 port_num:int = 0,
                 line_num:int = 0,
                 initial_delay:int = 1,
                 trigger_length:int = 2,
                 sample_clk_src:str = '/PXI2Slot3/Ctr0InternalOutput',
                 ):
        """
        This function setup digital output task used to trigger ADC.

        Parameters
        ----------
        task : nidaqmx.Task, optional
            task, where the digital output channel is set.
        slot_num : int, optional
            Slot number. The default is 3.
        port_num : int, optional
            Port number of digital output. The default is 0.
        line_num : int, optional
            Line number of digital output. The default is 0.
        initial_delay : int, optional
            Initial delay of the generated start trigger in a unit of a clock. The default is 1.
        trigger_length : int, optional
            Length of the trigger in a unit of a clock sample. The default is 2.
        sample_clk_src : str, optional
            Sample clock source. The default is '/PXI2Slot3/Ctr0InternalOutput'.
         : TYPE
            DESCRIPTION.

        Returns
        -------
        None.

        """
        # Calculate number of points for the trigger
        points = initial_delay + trigger_length + 10
        # Create digital output channel
        task.do_channels.add_do_chan(lines = '{}Slot{:d}/port{:d}/line{:d}'.format(self.device_name, slot_num, port_num, line_num))
        # Setup timing
        task.timing.cfg_samp_clk_timing(rate = 100000,
                                        source = sample_clk_src,
                                        active_edge=nidaqmx.constants.Edge.RISING,
                                        sample_mode=nidaqmx.constants.AcquisitionType.FINITE,
                                        samps_per_chan = points
                                        )
        # Write array information of the pulse
        writer = DigitalSingleChannelWriter(task.out_stream)
        ar = np.zeros((points,), dtype=np.uint8)
        ar[initial_delay:initial_delay+trigger_length] = 2 ** line_num
        writer.write_many_sample_port_byte(ar)
    
    def set_sample_clock(self,
                         task:nidaqmx.Task = None,
                         no_of_samples:int=None,
                         sample_rate:float=500.0,
                         sample_clk_src:str=None,
                         ):
        """
        This function setup the sample clock timing.

        Parameters
        ----------
        task : nidaqmx.Task, optional
            task, where the sample clock to be set.
        no_of_samples : int, optional
            Number of samples (data points) to be generated. If it is None, clock mode becomes
            continuous.
        sample_rate : float, optional
            Sampling rate in Hz. The default is 500.0 Hz.
        samle_clk_src : str, optional
            Sample clock source. We can set extra source. If it is None,
            we use a default onboard clock.

        Returns
        -------
        None.

        """
        if sample_clk_src == None:
            sample_clk_src = 'OnboardClock'
        
        task.timing.cfg_samp_clk_timing(sample_rate,
                                        source = sample_clk_src,
                                        active_edge=nidaqmx.constants.Edge.RISING,
                                        sample_mode=nidaqmx.constants.AcquisitionType.FINITE,
                                        samps_per_chan = no_of_samples)
    
    def DAC_move(self,
                 task_preparation:bool=True,
                 clear_task:bool=True):
        """
        This function moves the DAC values, whose target value is changed.
        
        Args:
            task_preparation (bool): Whether prepare analog output and sample clock to the task.
            clear_task (bool): Whether we clear the task after the movement or not.
        """
        move_slot_list = list()
        move_channel_list = dict()
        move_list = dict()
        largest_move = 0.0
        
        for slot in self.slots:
            move_channel_list[slot] = list()
            move_list[slot] = list()
            for i in range(8):
                chan = getattr(self, 's{:d}c{:d}'.format(slot, i))
                if not chan._target_val == None:
                    move_channel_list[slot].append(chan)
                    move_slot_list.append(slot)
                    
                    cv = chan._current_val  # Current DAC value
                    tv = chan._target_val # Target DAC value
                    move_list[slot].append((cv, tv)) # Keep the value
                    
                    delta = abs(tv - cv) # Size of the movement
                    if delta > largest_move:
                        # Check largest movement to determine number of points.
                        largest_move = delta
        # Convert move_slot_list to set
        move_slot_list = set(move_slot_list)
        
        # Calculate points
        points = max(2, int((largest_move/(20/2.0**16)//2.0)*2.0))
        # Keep points and re-define task when it changes
        if not self._move_points == points:
            self._move_points = points
            task_preparation = True
        
        # Create array for movement
        ar = dict()
        for slot in move_slot_list:
            ar_list = list()
            for v in move_list[slot]:
                ar_list.append(np.linspace(v[0],v[1], self._move_points,dtype=float))
            ar[slot] = np.vstack(tuple(ar_list))
        
        if task_preparation:
            # Clear task (It takes a few ms.)
            for slot in move_slot_list:
                if not self.write_task['{:d}'.format(slot)]:
                    self.write_task[slot].close()
                self.write_task[slot] = nidaqmx.Task()
                self.write_task['{:d}'.format(slot)] = False
            
                # Create analog output channel in the task
                for chan in move_channel_list[slot]:
                    self.write_task[slot].ao_channels.add_ao_voltage_chan(physical_channel = '{}Slot{:d}/ao{:d}'.format(self.device_name, chan.slot_num, chan.channum),
                                                                    min_val = chan.min_val(),
                                                                    max_val = chan.max_val(),
                                                                    units = nidaqmx.constants.VoltageUnits.VOLTS)
                # Setup sample clock
                self.set_sample_clock(task = self.write_task[slot],
                                      no_of_samples = self._move_points,
                                      sample_rate = 1000.0/self.ms2wait(),
                                      sample_clk_src = None,)
        
        writer = dict()
        for slot in move_slot_list:
            # Output voltage
            writer[slot] = AnalogMultiChannelWriter(self.write_task[slot].out_stream)
            writer[slot].write_many_sample(ar[slot])
        for slot in move_slot_list:
            self.write_task[slot].start()
        for slot in move_slot_list:
            self.write_task[slot].wait_until_done(timeout=nidaqmx.constants.WAIT_INFINITELY)
            self.write_task[slot].stop()
        
        if clear_task:
            # Clear task (It takes a few ms.)
            for slot in move_slot_list:
                self.write_task[slot].close()
                self.write_task['{:d}'.format(slot)] = True
                
        # Update information for the moved channels
        for slot in move_slot_list:
            for chan in move_channel_list[slot]:
                chan._current_val = chan._target_val
                chan._target_val = None
                            
    def prepare_fast_move(self):
        """
        This function prepare the task for fast movement.
        """
        self._fast_move_slot_list = list()
        self._fast_move_channel_list = dict()
        self._fast_move_list = dict()
        
        for slot in self.slots:
             self._fast_move_channel_list[slot] = list()
             self._fast_move_list[slot] = list()
             for i in range(8):
                 chan = getattr(self, 's{:d}c{:d}'.format(slot, i))
                 if chan.fs():
                     self._fast_move_slot_list.append(slot)
                     self._fast_move_channel_list[slot].append(chan)
                     
                     v0 = chan._current_val
                     v1 = chan._current_val + chan._fast_sequence_delta
                     self._fast_move_list[slot].append((v0, v1))
        # Convert fast_move_slot_list to set.
        self._fast_move_slot_list = set(self._fast_move_slot_list)
        
        
        # Clear the counter task
        if not self.ctr_task_isClosed:
            self.ctr_task.close()
        self.ctr_task = nidaqmx.Task()
        self.ctr_task_isClosed = False
        # Setup counter
        self.ctr_setup(task = self.ctr_task,
                       slot_num = self.slots[0],
                       no_of_samples = self.fs_pts(),
                       trigger_delay = 0.0,
                       )
        
        # Clear the digital out task
        if not self.do_task_isClosed:
            self.do_task.close()
        self.do_task = nidaqmx.Task()
        self.do_task_isClosed = False
        # Setup digital output
        self.do_setup(task = self.do_task,
                      slot_num = self.slots[0],
                      port_num = 0,
                      line_num = 0,
                      initial_delay = 0,
                      trigger_length = 1,
                      sample_clk_src = '/{}Slot{:d}/Ctr0InternalOutput'.format(self.device_name, self.slots[0]),
                      )
        
        self._fs_ready = True
    
    def DAC_fast_move(self):
        """
        This function makes fast sequence of the DAC.
        
        --> This function gets a problem when we use in a QuCoDeS. It is not possible
        to use DAC_move task and DAC_fast move task at the same time.
        """
        if not self._fs_ready:
            raise ValueError('Fase sequence is not ready. Please perform "prepare_fast_move".')
        
        # Number of array points has to be even. I adjust for that.
        if int(self.fs_pts()%2) == 0:
            points = self.fs_pts()+1
        else:
            points = self.fs_pts()
        
        # Set up channels
        for slot in self._fast_move_slot_list:
            # Define fast sequence task
            if not self.fast_seq_task['{:d}'.format(slot)]:
                self.fast_seq_task[slot].close()
            self.fast_seq_task[slot] = nidaqmx.Task()
            self.fast_seq_task['{:d}'.format(slot)] = False
            
            # Create analog output channel in the task
            for chan in self._fast_move_channel_list[slot]:
                self.fast_seq_task[slot].ao_channels.add_ao_voltage_chan(physical_channel = '{}Slot{:d}/ao{:d}'.format(self.device_name, chan.slot_num, chan.channum),
                                                                   min_val = chan.min_val(),
                                                                   max_val = chan.max_val(),
                                                                   units = nidaqmx.constants.VoltageUnits.VOLTS)
            
            # Setup sample clock
            self.set_sample_clock(task = self.fast_seq_task[slot],
                                  no_of_samples=points+1,
                                  sample_rate=1000.0/self._fast_sequence_divider,
                                  sample_clk_src='/{}Slot{:d}/Ctr0InternalOutput'.format(self.device_name, self.slots[0]),)
        
        ar_dict = dict()
        writer = dict()
        for slot in self._fast_move_slot_list:
            # Create array for fast movement
            ar_list = list()
            for chan in self._fast_move_channel_list[slot]:
                v0 = chan._current_val
                v1 = chan._current_val + chan._fast_sequence_delta
                ar = np.empty((points+1,), dtype=float)
                ar[0:self.fs_pts()] = np.linspace(v0, v1, self.fs_pts(), dtype=float)
                ar[self.fs_pts()] = v0
                if int(self.fs_pts()%2) == 0:
                    ar[self.fs_pts()+1] = v0
                ar_list.append(ar)
            ar_dict[slot] = np.vstack(tuple(ar_list))
            
            # Output voltage
            writer[slot] = AnalogMultiChannelWriter(self.fast_seq_task[slot].out_stream)
            writer[slot].write_many_sample(ar_dict[slot])
            
        for slot in self._fast_move_slot_list:
            self.fast_seq_task[slot].start()
        self.do_task.start()
        self.ctr_task.start()
            
        for slot in self._fast_move_slot_list:
            self.fast_seq_task[slot].wait_until_done(timeout=nidaqmx.constants.WAIT_INFINITELY)
            self.fast_seq_task[slot].stop()
            self.fast_seq_task[slot].close()
            self.fast_seq_task['{:d}'.format(slot)] = True
        self.do_task.wait_until_done(timeout=nidaqmx.constants.WAIT_INFINITELY)
        self.do_task.stop()
        self.ctr_task.wait_until_done(timeout=nidaqmx.constants.WAIT_INFINITELY)
        self.ctr_task.stop()
                
if __name__ == '__main__':
    t = time.time()
    dac = NI6733(name = 'dac',
                 device_name = 'PXI2',
                 slots=[3,4,],
                 ms2wait = 2.0,
                 fast_sequence_divider = 2.0,
                 fs_pts = 201,
                 )
    
    # # DAC movement test
    # dac.s3c0.cv(-0.1)
    # dac.s4c0.cv(-0.3)
    # dac.DAC_move(task_preparation = True,
    #              clear_task = False)
    # dac.s3c0.cv(-0.3)
    # dac.s4c0.cv(-0.5)
    # dac.DAC_move(task_preparation = False,
    #              clear_task = False)
    # dac.s3c0.cv(-0.5)
    # dac.s4c0.cv(-0.7)
    # dac.DAC_move(task_preparation = False,
    #              clear_task = False)
    # dac.s3c0.cv(0.0)
    # dac.s4c0.cv(0.0)
    # dac.DAC_move(task_preparation = False,
    #              clear_task = True)
    
    # # Trigger test
    # dac.ctr_setup(slot_num = 3,
    #                   no_of_samples = 20,
    #                   trigger_delay = 0.1)
    # dac.ctr_task.start()
    # dac.ctr_task.wait_until_done()
    # # time.sleep(5)
    # dac.ctr_task.stop()
    
    # Fast sequence test
    dac.fs_pts(201)
    dac.fs_div(2.0)
    dac.s3c0.fs(True)
    dac.s3c0.fs_delta(-1.0)
    dac.prepare_fast_move()
    dac.DAC_fast_move()
    
    print('Execution time {:f}'.format(time.time() - t))