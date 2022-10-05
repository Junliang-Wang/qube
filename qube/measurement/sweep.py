# from time import sleep, time
# import collections
# import numpy as np
# import qcodes as qc
# from qcodes import Instrument
from qcodes.instrument.base import InstrumentBase
from qcodes.instrument.parameter import (Parameter, DelegateParameter)
from qcodes.instrument.function import Function
from qcodes.dataset.measurements import Measurement
from qcodes import validators as vals

from IPython.display import display, Markdown

from tqdm.notebook import tqdm as progress_bar

import numpy as np
import matplotlib
import time
import os

import datetime

from typing import List, Union

str_mv_cmd_id = 'move_command_id'
str_sw_cntrlr = 'sweep_controller'
str_offset = 'offset'
str_counter = 'counter'
str_dim = 'dim'

str_fmt_offset = str_offset + '_{:s}_' + str_dim + '{:d}'  # with sweep name (str) and dimension (int) as format-arguments
str_fmt_counter = str_counter + '_' + str_dim + '{:d}'  # with dimension (int) as format-argument

val_pos_int = vals.Lists(vals.Ints(min_value=1))

""" GENERAL PURPOSE FUNCTIONS """


def apply_default(values=None):
    """
    This is the most basic function to apply values to 
    a set of Parameters within qcodes.

    Arguments:
     values ... List of tuples of the form:
                 [(instance_of_control1,value1), ...]
    """
    if values != None:
        for parameter, value in values:  # Go through each parameter ...
            parameter(value)  # ... and set it to its value.


def readout_default(parameters=None):
    """
    This is the most basic function to read values from
    a set of Parameters within qcodes.

    Arguments:
     values ... List of tuples of the form:
                 [(instance_of_control1,value1), ...]
    """
    if parameters != None:
        list_of_results = list()
        for parameter in parameters:  # Go through parameters ...
            value = parameter.get()
            par_val_tuple = (parameter, value)
            list_of_results.append(par_val_tuple)
        return list_of_results


def register_pre_and_post_process(
        meas: Measurement,
        pre_process: List = None,
        post_process: List = None,
):
    """
    This function registers a set of processes that are executed
    before or after a qcodes measurement. Here we call these processes
    pre- and post-processes.

    Arguments:
     measurement  ... instance of qcodes Measurement object
     pre_process  ... list of tuples containing:
                       ( function, (arguments_for_function) )
                      If the function takes no arguments, an empty tuple
                      must be provided:
                       ( function, () )
     post_process ... same structure as pre_process.
    """
    if pre_process != None:
        if (type(pre_process) == list or type(pre_process) == tuple):
            for p in pre_process:
                meas.add_before_run(p[0], args=p[1])
        else:
            meas.add_before_run(pre_process[0], args=pre_process[1])

    if post_process != None:
        if (type(post_process) == list or type(post_process) == tuple):
            for p in post_process:
                meas.add_after_run(p[0], args=p[1])
        else:
            meas.add_after_run(post_process[0], args=post_process[1])

import time

class Sweep(InstrumentBase):
    """
    This is a controller class that allows to perform certain types of
    parameter sweeps using the qcodes environment.
                   
    For usage check:
      help(Sweep.execute_sweep)
                   
    Parameters:
    
      'dimensions'      ... list of integers indicating the sweep dimensions
      'sweeps'          ... dictionary holding swept parameter for each dimension.
                             key: dimension,  value:  list of parameter instances
      'readouts'        ... dictionary holding readout parameters
                             key: full_name,  value:  instance of readout parameter
      'values'          ... dictionary holding values for each sweep parameter for each dimension.
                             key: dimension,  value: list of values ordered according to 'sweeps'
      'shape_of_sweeps' ... list of integers indicating the number of points per sweeping dimensions
      'sweep_offsets'   ... dictionary holding offsets in higher dimensions for each sweep.
                             key: parameter name,  value: number indicating offset value
                             
                             
    """

    def __init__(self, name: str, **kwargs) -> None:
        super().__init__(name, **kwargs)

        # List of parameters of the Sweep object
        par_defs = [  # name,      validator,      initial_value
            ('dimensions', val_pos_int, []),
            ('sweeps', vals.Dict(), None),
            ('readouts', vals.Dict(), None),
            ('values', vals.Dict(), None),
            ('shape_of_sweep', val_pos_int, []),
            ('sweep_offsets', vals.Dict(), None),
        ]

        for name, val, init in par_defs:
            self.add_parameter(name=name, set_cmd=None, get_cmd=None, vals=val, initial_value=init)

        # List of supplementary information stored to the qcodes dataset
        sweep_info = {
            # name:                [  validator,       paramtype,                 
            'note': [vals.Strings(), 'text'],
            'return2initial': [vals.Numbers(), 'numeric'],
            'fast_sweep': [vals.Numbers(), 'numeric'],
            'shape': [val_pos_int, 'numeric'],
            'shape_dims': [val_pos_int, 'numeric'],
            'sweep_names': [vals.Strings(), 'text'],
            'sweep_full_names': [vals.Strings(), 'text'],
            'sweep_dims': [vals.Numbers(), 'numeric'],
            'readout_names': [vals.Strings(), 'text'],
            'readout_full_names': [vals.Strings(), 'text'], }

        self.add_parameter(name='sweep_info', set_cmd=None, get_cmd=None, vals=vals.Dict(), initial_value=sweep_info)
        self.apply_pre_readout = lambda: 0
        self.apply_post_readout = lambda: 0

    def execute_sweep(self,
                      instructions: List,
                      readouts: List,
                      name: str = None,
                      pre_process: List = None,
                      post_process: List = None,
                      pre_readout: List = None,
                      post_readout: List = None,
                      initial_config: dict = None,
                      return2initial: bool = True,
                      fast_sweep: bool = False,
                      note: str = '',
                      show_time_estimation: bool = True,
                      show_progress_bar: bool = True,
                      function_apply=apply_default,  # ?
                      function_readout=readout_default,  # ?
                      wait_pre_readout=0,  # in s
                      wait_post_readout=0,  # ins s
                      ):
        """
        This function sweeps qcodes parameters in arbitrary dimensions, measures the the values
        on some readouts and stores a corresponding dataset into the qcodes database.

        instructions    ... List of instructions to sweep.

            Each instruction is given in a list as a list as follows:
               [ sweep_dim, param_spec, values ] # sweep_dim starts from 1, not 0. values must be consistent.
            - Example of 2-dimensional square sweep with offset in higher dimension (vector sweep):
              [
               [ 1,         gate1,      np.linspace(0.0,-1.5,501)   ], # swept simultaneously with gate 2 in 1st dimension
               [ 1,         gate2,      np.linspace(0.0,-1.5,501)   ], # length of values must be consistent for each dim.
               [ 2,         bias,       np.linspace(-1e-3,-1e-3,11) ], # bias swept in 2nd dimension
               [ 2,         gate1,      np.linspace(0.0,-0.3,4)     ], # offsets for sweep of gate1 in 2nd dimension
               [ 3,         None,       3                           ], # repeat measurement in 3rd dimension
              ]

        readouts        ... List of qcodes parameters for readout: [readout1, readout2, ....]

        pre_process     ... Function performed before "run" with corresponding arguments

            - Example:                                (callable, arg[tuple])
            - Example with multiple functions       [ (callable, arg[tuple]), ... ]
            - If the callable has no arguments, pass () as arg[tuple].

        post_process    ... Function performed after "run" -- same structure as pre_process

        initial_config  ... Dictionary holding initial values for a set of qcodes parameters

            - Example:       { Parameter1: value1, Parameter2: value2, ...}

        return2initial  ... Boolean indicating if initial configuration should be applied when the measurement is finished.

        fast_sweep      ... Boolean indicating if an array measurement should be performed.

        note            ... String containing supplementary measurement information that should be stored to the dataset.

        show_time_estimation ... Boolean indicating if the estimated measurement time should be displayed

        apply           ... function that is used to apply the sweep values to the sweep parameters

            Arguments:       List of tuples of the form:     [ (instance_of_control1,value1), ... ]

        readout         ... function that is used to retrieve the measurement values from the readout parameters

        """

        meas = Measurement(name=name)
        self.measurement = meas
        self.register_sweep_info(instructions, readouts)  # Register sweep information
        self.register_pre_and_post_process(pre_process, post_process)  # Register pre- and post- processes
        self.register_pre_and_post_readout(pre_readout, post_readout)
        function_apply(initial_config)  # Apply initial values of the controls

        meas_time = 0
        save_time = 0
        apply_time = 0
        with meas.run() as datasaver:  # Start measurement

            self.write_sweep_info(datasaver, note, return2initial, fast_sweep)

            index_matrix = self.get_indices_for_sweep()
            # print(index_matrix.shape)
            for i, index_list in enumerate(index_matrix):
                # >> index_list << contains index pointers to each sweep-parameter value for each step.

                # Show progress of measurement:
                if show_progress_bar:
                    self.progress_update(i, index_matrix.shape[0], show_time_estimation, show_progress_bar)

                # Set sweep values:
                start = time.time()
                targets = self.get_target_values(index_list)  # Get target values for current indices
                function_apply(targets)  # Apply target values to sweep controls
                apply_time += time.time() - start

                # Perform measurement:
                self.apply_pre_readout()
                if wait_pre_readout:
                    time.sleep(float(wait_pre_readout))
                start = time.time()
                measures = function_readout(readouts)  # Measure data on readout devices
                meas_time += time.time() - start
                if wait_post_readout:
                    time.sleep(float(wait_pre_readout))
                self.apply_post_readout()
                start = time.time()
                datasaver.add_result(*tuple(measures))  # Store measurement to database
                save_time += time.time() - start

            if return2initial:
                function_apply(initial_config)
            print(f'Timing for {i+1} loops:')
            print(f'\t apply: {apply_time/(i+1)} s')
            print(f'\t readout: {meas_time/(i+1)} s')
            print(f'\t save: {save_time/(i+1)} s')
            return datasaver.run_id

    def register_sweep_info(self,
                            instructions: List,
                            readouts: List,
                            ):
        """
        This function interprets the instructions for a measurement and registers
        the corresponding sweep and readout parameters for execution.
        """
        meas = self.measurement
        dimensions = list()
        sweeps = dict()  # key: dimension; value: list of controls
        values = dict()  # key: dimension; value: list of value-arrays
        readouts_dict = dict()  # key: full_name; value: list of readouts
        shape_of_sweep = list()
        sweep_offsets = dict()

        # Check instructions, extract information and register sweep parameters:
        for instruction in instructions:

            dimension, sweep, value = instruction

            # Register sweep parameters:
            if sweep != None:
                # Sweep or offset
                if not sweep.full_name in meas.parameters.keys():  # Parameter not registered yet
                    # New sweep:
                    parameter_to_register = sweep
                    sweep_offsets[sweep.name] = []
                else:  # Parameter already registered
                    # New offset to existing sweep:
                    offset_name = str_fmt_offset.format(sweep.name, dimension)
                    parameter_to_register = Parameter(
                        name=offset_name,
                        vals=type(sweep.vals)(),
                        set_cmd=None,
                        get_cmd=None,
                    )
                    sweep_offsets[sweep.name].append(parameter_to_register)
            else:
                # New dummy parameter: counter
                if type(value) == int:
                    counter_name = str_fmt_counter.format(dimension)
                    parameter_to_register = Parameter(
                        name=counter_name,
                        vals=vals.Ints(min_value=0, max_value=value - 1),
                        set_cmd=None,
                        get_cmd=None,
                    )
                    value = list(range(value))
                else:
                    raise TypeError("Value of None-type (repetition) instruction is not of integer type!")

            meas.register_parameter(parameter_to_register, paramtype='array')

            # Extract information of dimension and array of values:
            if not dimension in dimensions:  # New dimension:
                dimensions.append(dimension)
                sweeps[dimension] = [parameter_to_register]
                values[dimension] = [value]
                shape_of_sweep.append(len(value))
            else:  # Already existing dimension:
                sweeps[dimension].append(parameter_to_register)
                if len(list(value)) == len(values[dimension][0]):
                    values[dimension].append(value)
                else:
                    raise ValueError('Sweeping values of {:s} and {:s} are inconsistent!'.format(sweep.name,
                                                                                                 sweeps[dimension][
                                                                                                     0].name))

                    # Check readouts, extract information and register readout parameters:
        for readout in readouts:
            meas.register_parameter(readout, setpoints=tuple())
            readouts_dict[readout.full_name] = readout

        # Update parameters
        self.parameters['dimensions'].set(dimensions)
        self.parameters['sweeps'].set(sweeps)
        self.parameters['values'].set(values)
        self.parameters['readouts'].set(readouts_dict)
        self.parameters['shape_of_sweep'].set(shape_of_sweep)
        self.parameters['sweep_offsets'].set(sweep_offsets)

        # Register supplementary information for the dataset
        for suppl_name, (suppl_val, suppl_typ) in self.parameters['sweep_info'].get().items():
            meas.register_parameter(
                Parameter(name=suppl_name, set_cmd=None, get_cmd=None, vals=suppl_val),
                paramtype=suppl_typ
            )

    @staticmethod
    def _build_process_function(processes: List = None):
        if isinstance(processes, (list, tuple)):
            def _func():
                for p in processes:
                    f, args = p
                    f(*args)
        else:
            _func = lambda: 0
        return _func

    def register_pre_and_post_process(self, pre_process: List = None, post_process: List = None):
        """
        This function registers a set of processes that are executed
        before or after a qcodes measurement. Here we call these processes
        pre- and post-processes.

        Arguments:
         measurement  ... instance of qcodes Measurement object
         pre_process  ... list of tuples containing:
                           ( function, (arguments_for_function) )
                          If the function takes no arguments, an empty tuple
                          must be provided:
                           ( function, () )
         post_process ... same structure as pre_process.
        """
        register_pre_and_post_process(self.measurement, pre_process, post_process)

    def register_pre_and_post_readout(self, pre_readout: List = None, post_readout: List = None):
        """
        This function registers a set of processes that are executed
        before or after the readout. Here we call these processes
        pre- and post-readouts.

        Arguments:
         measurement  ... instance of qcodes Measurement object
         pre_readout  ... list of tuples containing:
                           ( function, (arguments_for_function) )
                          If the function takes no arguments, an empty tuple
                          must be provided:
                           ( function, () )
         post_readout ... same structure as pre_readout.
        """
        self.apply_pre_readout = self._build_process_function(pre_readout)
        self.apply_post_readout = self._build_process_function(post_readout)

    def get_indices_for_sweep(self):
        """
        This function returns a 2D-NumpyArray of indices for executing
        a sweep with a certain shape (shape_of_sweep).
        
        Example:
            self.shape_of_sweep = (4,3,2)
          Results in:
            array([[0, 0, 0],
                   [1, 0, 0],
                   [2, 0, 0],
                   [3, 0, 0],
                   [0, 1, 0],
                   [1, 1, 0],
                   [2, 1, 0],
                   [3, 1, 0],
                   [0, 2, 0],
                   [1, 2, 0],
                   [2, 2, 0],
                   [3, 2, 0],
                   [0, 0, 1],
                   [... , 1],
                   [3, 2, 1]])
            
        """

        shape_of_sweep = self.parameters['shape_of_sweep'].get()

        list_of_index_vectors = [np.arange(i) for i in np.flipud(shape_of_sweep)]

        indices = np.meshgrid(*list_of_index_vectors, indexing='ij')

        for k, _ in enumerate(indices):
            indices[k] = _.flatten()

        return np.fliplr(np.array(indices).T)

    def make_info_tuples(self, note, return2initial, fast_sweep):

        sweep_info_tuples = list()

        dimensions = self.parameters['dimensions'].get()
        sweeps = self.parameters['sweeps'].get()
        readouts = self.parameters['readouts'].get()
        sweep_info = self.parameters['sweep_info'].get()

        for key in sweep_info.keys():

            if key == 'sweep_names':
                for dimension in dimensions:
                    for sweep_id, sweep in enumerate(sweeps[dimension]):
                        sweep_info_tuples.append(('sweep_names', sweep.name))
                        sweep_info_tuples.append(('sweep_full_names', sweep.full_name))
                        sweep_info_tuples.append(('sweep_dims', dimension))
            elif key == 'readout_names':
                for readout in readouts.values():
                    sweep_info_tuples.append(('readout_names', readout.name))
                    sweep_info_tuples.append(('readout_full_names', readout.full_name))
            elif key == 'shape':
                shape_reversed = np.flipud(np.array(self.parameters['shape_of_sweep'].get()))
                dimensions_reversed = np.flipud(dimensions)
                for dimension, pts_per_dim in zip(dimensions_reversed, shape_reversed):
                    sweep_info_tuples.append(('shape', pts_per_dim))
                    sweep_info_tuples.append(('shape_dims', dimension))
            elif key in ['sweep_full_names', 'sweep_dims', 'readout_full_names', 'shape_dims']:
                pass
            else:
                if key == 'note':
                    value = note
                elif key == 'return2initial':
                    value = int(return2initial)
                elif key == 'fast_sweep':
                    value = int(fast_sweep)
                sweep_info_tuples.append((key, value))

        return sweep_info_tuples

    def write_sweep_info(self, datasaver, note, return2initial, fast_sweep):

        # Save sweep values for each dimension to database:
        dimensions = self.parameters['dimensions'].get()
        sweeps = self.parameters['sweeps'].get()
        values = self.parameters['values'].get()
        for dimension in dimensions:
            for sweep, sweep_array in zip(sweeps[dimension], values[dimension]):
                datasaver.add_result((sweep, sweep_array))

        # Save supplementary sweep information to database:
        info_tuples = self.make_info_tuples(note, return2initial, fast_sweep)
        for info_tuple in info_tuples:
            datasaver.add_result(info_tuple)

    def get_target_values(self,
                          index_list,
                          ):

        # Some definitions for better readability:
        dimensions = self.parameters['dimensions'].get()
        sweeps = self.parameters['sweeps'].get()
        values = self.parameters['values'].get()
        sweep_offsets = self.parameters['sweep_offsets'].get()

        # For vector sweep -- initialise sweep offset values to zero:
        sweep_offset_values = dict()
        for sweep_name in sweep_offsets.keys():
            sweep_offset_values[sweep_name] = 0

        # Get sweep values for each dimension at current sweep index:               
        targets = dict()

        for dimension in dimensions:
            for sweep_id, sweep in enumerate(sweeps[dimension]):
                temp_name = sweep.name
                temp_values = values[dimension][sweep_id]
                temp_index = index_list[dimension - 1] % len(temp_values)
                temp_value = temp_values[temp_index]
                is_offset = temp_name.startswith(str_offset)
                is_counter = temp_name.startswith(str_counter)
                if is_offset:
                    #                     real_name = temp_name.split(str_offs_link)[0]
                    real_name = '_'.join(temp_name.split('_')[1:-1])
                    sweep_offset_values[real_name] += temp_value
                elif is_counter:
                    pass
                else:  # Set value
                    targets[sweep] = temp_value

        # For vector sweep -- add offsets to target values:
        for offset_name, offset_value in sweep_offset_values.items():
            for dimension in dimensions:
                for sweep_id, sweep in enumerate(sweeps[dimension]):
                    if offset_name == sweep.name:
                        targets[sweep] += offset_value

        return list(targets.items())

    def progress_update(self, i, N, show_time_estimation, show_progress_bar):

        # Estimation of measurement duration
        if show_time_estimation:
            if i == 2:
                self.temp_time = time.time()
            elif i == 3:
                self.temp_time = (time.time() - self.temp_time) * (N - 3)
                print('The measurement will take {:s}.'.format(str(datetime.timedelta(seconds=self.temp_time))))

        # Display progress bar
        if show_progress_bar:
            start_idx = 3
            if i == start_idx:
                self.temp_progress = progress_bar(total=N)
                self.temp_progress.update(start_idx + 1)
            elif i > start_idx:
                self.temp_progress.update(1)
