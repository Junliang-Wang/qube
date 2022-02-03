# from time import sleep, time
# import collections
# import numpy as np
# import qcodes as qc
#from qcodes import Instrument
from qcodes.instrument.base import InstrumentBase
from qcodes.instrument.parameter import (Parameter,DelegateParameter)
from qcodes.instrument.function import Function
from qcodes.dataset.measurements import Measurement
from qcodes import validators as vals
# from .sweep.Sweep import Sweep # CONSTRUCTION SITE
from qube.measurement.sweep import Sweep

from IPython.display import display, Markdown, clear_output
# from tools.plot.layout import GDS_layout
# from tools.plot.layout.datafile_gates_qcodes import LayoutContent

# Imports for interactive wizard:
import ipywidgets as ipyw

import numpy as np
import matplotlib
import matplotlib.pyplot as plt
import time
import os

import operator
import functools

import datetime

from typing import List, Union

str_mv_cmd_id = 'move_command_id'
str_offs_link = '_offset_dim'
str_sw_cntrlr = 'sweep_controller'

val_pos_int = vals.Lists(vals.Ints(min_value = 1))

class Controls(InstrumentBase):
    """
    This is a controller class that handles the control parameters of
    your experiment. Your control parameters are added as instances of the
    DelegateParameter class from qcodes.
    
    EXAMPLE:
    
    # In ../tools/startup.ipynb define the controls instance:
    
    from tools.drivers.Controls import *
    controls = Controls()
    
    # In ../configurations/c0_your_config.ipynb add your controls:
    # Add some control parameter (cp0) as DelegateParameter with the
    # corresponding instrument parameter -- let's call it instr.ch.par.v --
    # as source:
    cp0 = controls.add_control('cp0',
                       source=instr.ch.par.v,
                       move_command = inst.move,
                       # Adapt the parameter according to your exp. setup:
                       label = r'Reasonable label $r_{\rm L}$',
                       unit  =  'arb. units',
                       scale = 500,
                       # ...
                       )
    """

    def __init__(self, name:str, **kwargs) -> None:
        super().__init__( name, **kwargs)

        self._move_commands = list()
                     
        # Add submodule to perform sweeps of controls:
        self.add_submodule(
            name      = str_sw_cntrlr,
            submodule = Sweep(str_sw_cntrlr)
        )
                         
        self.metadata['comments'] = 'Abstract instrument handling experiment controls.'
                
    def _add_delegate_parameter(self,
            name: str,                         # Name of the control
            source: Parameter,                 # Controlled instrument parameter
            move_command: Function = None,     # Command to move the control
            **kwargs                           # Any delegating properties ... see DelegateParameter class
           ):
        """
        This function adds a parameter delegating to an instrument parameter
        and adds the corresponding move command if not already present.
        """
        self.add_parameter(name, parameter_class = DelegateParameter, source=source, **kwargs)
        if (move_command != None):
            if (move_command not in self._move_commands):
                self._move_commands.append(move_command)
            self.parameters[name].metadata[str_mv_cmd_id] = self._move_commands.index(move_command)
        else:
            self.parameters[name].metadata[str_mv_cmd_id] = None
        return self.parameters[name]

    def add_control(self,
            name: str,                         # Name of the control
            source: Parameter,                 # Controlled instrument parameter
            move_command: Function = None,     # Command to move the control
            **kwargs                           # Any delegating properties ... see DelegateParameter class
           ):
        """
        This function adds a delegate parameter (with move command) that is a readout.
        """
        par = self._add_delegate_parameter(name,source,move_command,**kwargs)
        self.parameters[name].metadata['readout'] = False
        return par
    
    def add_readout(self,
            name: str,                         # Name of the control
            source: Parameter,                 # Controlled instrument parameter
            move_command: Function = None,     # Command to move the control
            **kwargs                           # Any delegating properties ... see DelegateParameter class
           ):
        """
        This function adds a delegate parameter (with move command) that is a readout.
        """
        par = self._add_delegate_parameter(name,source,move_command,**kwargs)
        self.parameters[name].metadata['readout'] = True
        return par

    def _turn_key_to_instance(self, key):
        """
        This function transforms key, that is either the name
        (String) or the instance (DelegateParameter) of a parameter,
        into an instance of the parameter object.
        
        The usage of this function brings more flexibility for the
        user: He can provide parameter names or instances.
        """
        if type(key) == str:
            parameter = self.parameters[key]
        elif type(key) == DelegateParameter:
            parameter = self.parameters[key.name]
        elif key == None:
            parameter = None
        else:
            raise ValueError('The provided key {:s} is neighter of type String nor DelegateParameter.'.format(str(key)))
        return parameter

    def _turn_keys_to_instances(self, keys):
        """
        Same as _turn_key_to_instance, but for a list or tuple of keys.
        """
        parameters = list()
        if (type(keys) == tuple) or (type(keys) == list):          # Multiple keys in a list
            for key in keys:
                parameters.append(self._turn_key_to_instance(key))
        else:                                                      # Single key
            parameters.append(self._turn_key_to_instance(keys))
        return parameters

    def _is_readout(self, key):
        """
        This function checks if a delegate parameter is a readout or not.
        key ... name (str) or instance (DelegateParameter) of the parameter.
        """
        parameter = self._turn_key_to_instance(key)
        return parameter.metadata['readout'] 

    def apply(self, values):
        """
        This function applies the values of some control parameters
        and physically moves the corresponding instruments.
        
        values ... Can be either:
                    - dictionary of the form:
                      {'name_of_control1':value1, ...}
                      or
                      {instance_of_control1:value1, ...}
                    - a list of tuples of the form:
                      [('name_of_control1',value1), ...]
                      or
                      {(instance_of_control1,value1), ...}
        """
        
        if type(values) == dict:
            values = values.items()
            
        list_of_move_cmd_ids = list()
            
        # Collect move commands and set values    
        for key,value in values:
            control = self._turn_key_to_instance(key)
            if self._is_readout(control) == False: # Check that the paramter is not a readout
                move_cmd_id = control.metadata[str_mv_cmd_id]
                if (move_cmd_id != None) and (not move_cmd_id in list_of_move_cmd_ids):
                    list_of_move_cmd_ids.append(move_cmd_id)      # Memorize move command
                control(value)                                    # Set value

        for cmd_id in list_of_move_cmd_ids:
            self._move_commands[cmd_id]()

    def _get_delegate_parameters(self, 
                                 only_controls:bool = False,
                                 only_readouts:bool = False,
                                 as_instance:bool=False,
                                ):
        """
        This function returns a list of names (string) or a list instances
        (DelegateParameter; as_instance = True) for the controls (only_controls), 
        the readouts (only_readouts) or both (only_controls=only_readouts=False).
        """
        list_of_delegates = list()
        for parameter in self.parameters.values():
            if as_instance:
                list_item = parameter
            else:
                list_item = parameter.name
            
            if self._is_readout(parameter) and only_readouts:
                list_of_delegates.append(list_item)
            elif ( not self._is_readout(parameter) ) and only_controls:
                list_of_delegates.append(list_item)
            elif ( not only_controls ) and ( not only_readouts ):
                list_of_delegates.append(list_item)
                        
        return list_of_delegates

    def get_controls(self, as_instance:bool=False):
        """
        This function returns a list of the control names (string) or a list
        of the control instances (DelegateParameter; as_instance = True).
        """
        return self._get_delegate_parameters(only_controls = True,as_instance=as_instance)
    
    def get_readouts(self, as_instance:bool=False):
        """
        This function returns a list of the readout names (string) or a list
        of the readout instances (DelegateParameter; as_instance = True).
        """
        return self._get_delegate_parameters(only_readouts = True,as_instance=as_instance)
    
    def dictionary(self):
        """
        This function returns a dictionary containing all controls with their corresponding values.
        """
        output = dict()
        for control in self.get_controls(as_instance=True):
            value = control()
            output[control.name] = value
        return output
    
    def readout_dict(self, controls:list=None, key_as_instance:bool=False):
        """
        This function performs the readout operations and provides
        a dictionary of the updated measurement values of the form:
          {'name_of_readout1':value1, ...}
        If key_as_instance is set to True, the keys are instances:
          {instance_of_readout1:value1, ...}
        """
        
        if controls == None:
            controls = self.get_readouts()

        # Go through readouts and note move commands:
        readout_controls = list()
        list_of_move_cmd_ids = list()
        for key in controls:
            control = self._turn_key_to_instance(key)
            if self._is_readout(control):
                move_cmd_id = control.metadata[str_mv_cmd_id]
                if move_cmd_id != None:
                    list_of_move_cmd_ids.append(move_cmd_id)
                    
            readout_controls.append(control)

        # Update readout instruments:
        for cmd_id in list_of_move_cmd_ids:
            self._move_commands[cmd_id]()
            
        # Fill dictionary with updated values:
        readouts_dict = dict()
        for key in readout_controls:
            control = self._turn_key_to_instance(key)
            if key_as_instance:
                outkey = control
            else:
                outkey = control.name
            readouts_dict[outkey] = control()
                         
        return readouts_dict
        
    def readout(self, controls:list=None):
        """
        This function performs the readout operations and provides
        a list of tuples with the updated measurement values:
        [
          (instance_of_readout1,value1),
          (instance_of_readout2,value2),
          ...
        ]
        """
        readouts_dict = self.readout_dict(controls, key_as_instance=True)    
        return list(readouts_dict.items())
        
    def trace(self,
              controls:list=None,
              update_interval:float=0.1,
              figwidth:float=7.2,
              subplotheight:float=2.75,
             ):
        """
        This function traces the values of all (or certain) readouts
        as function of time and displays the values via a live plot.
        
        Functionality:
        A thread is used to update a hidden slider-object, which then
        triggers the update of the figure.
        """
        
        # If only one control is passed, transform to list:
        if not type(controls) in (list,tuple):
            controls = (controls,)
        
        # Initialise plots:
        readout_tuples = self.readout(controls=controls)
        N_rows = len(readout_tuples)        
        fig, axs = plt.subplots(N_rows)
        fig.set_figwidth(figwidth)
        fig.set_figheight(subplotheight*N_rows)
        lines = list()
        initial_time = time.time()
        if N_rows == 1:
            axs = (axs,)
        for idx, readout_tuple in enumerate(readout_tuples):
            print(axs)
            temp_line, = axs[idx].plot([0], [readout_tuple[1]])
            lines.append(temp_line)
            axs[idx].grid(True)
            label = readout_tuple[0].label
            unit =  readout_tuple[0].unit
            axs[idx].set_ylabel(r'{:s} ({:s})'.format(label,unit))
            if idx == N_rows-1:
                axs[idx].set_xlabel(r'Time $t$ (sec)')
        plt.tight_layout()

        def update(change):
            readout_tuples = self.readout(controls = controls)
            for idx, readout_tuple in enumerate(readout_tuples):
                xdata,ydata = lines[idx].get_data()
                xdata = np.append(xdata,time.time()-initial_time)
                ydata = np.append(ydata,readout_tuple[1])
                lines[idx].set_data(xdata,ydata)
                axs[idx].set_xlim([xdata[0],xdata[-1]])
                axs[idx].set_ylim([np.min(ydata)-1e-12,np.max(ydata)+1e-12])
            fig.canvas.draw()
  
        counter = ipyw.Label(value='None',continuous_update=True)
        counter.observe(update, 'value')

        button = ipyw.Button(description="Stop")
        output = ipyw.Output()

        thread_stopped = False

        import threading
        def work():
            i = 0
            while True:
                i += 1
                time.sleep(update_interval)
                counter.value = str(i)
                if button.disabled:
                    break

        thread = threading.Thread(target=work)

        def on_button_clicked(b):
            b.disabled=True

        button.on_click(on_button_clicked)
        display(button)
        thread.start()
        
        return fig

    def sweep(self, 
              instructions:List,
              **kwargs
             ):
        """
        This function feeds Sweep.execute_sweep with input arguments that
        are adjusted for usage with the Controls class.
        
        Example of usage:
        
            run_id = controls.sweep(
                [
                    [ 1, qpc,     values1 ],
                    [ 1, barrier, values2 ], # parallel sweep to qpc
                    [ 2, qpc,     offset2 ], # offset in 2nd dimension
                    [ 3, qpc,     offset3 ], # offset in 3rd dimension
                    [ 4, None,    2       ], # repeat twice in 4th dimension
                ]
            )      
        
        Additional functionality to Sweep.execute_sweeps:
        
          - Apply and readout commands launch move commands of the controls
          
          - Control and readout parameters can be provided also as string (name within controls) 
          
          - By default all readouts of the Controls instance are used
          
          - By default the current settings the Controls instance are
            used for the configuration applied before and after the measurement
        
        For input arguments see:
          help(tools.sweep.Sweep.execute_sweep)
          
        Returns:
          run_id ... integer indicating index of the qcodes measurement
        """

        # Names of arguments that are transformed before being passed to
        # the Sweep:
        var_str_instr     = 'instructions'
        var_str_readouts  = 'readouts'
        var_str_init_conf = 'initial_config'
        var_str_apply     = 'function_apply'
        var_str_readout   = 'function_readout'
        
        # If any control of the instruction is passed as string (control name),
        # then turn it into the qcodes-parameter instance of the control:
        for k in np.arange(len(instructions)):
            instructions[k][1] = self._turn_key_to_instance(instructions[k][1])
        kwargs[var_str_instr] = instructions
        
        # If no readouts are provided, use readouts of Controls object.
        if var_str_readouts not in kwargs.keys():
            kwargs[var_str_readouts] = self.get_readouts(as_instance=True)
        else:
            # If any readout of the is passed as string (control name),
            # turn it into the corresponding qcodes-parameter instance:
            kwargs[var_str_readouts] = self._turn_keys_to_instances(kwargs[var_str_readouts])
            
        # By default use current settings of controls for initial config:
        if var_str_init_conf not in kwargs.keys():
            kwargs[var_str_init_conf] = self.dictionary()
        else:
            temp_dict = kwargs[var_str_init_conf]
            kwargs[var_str_init_conf] = self.dictionary()
            for key, value in temp_dict.items():
                kwargs[var_str_init_conf][key] = value
            
        # Use apply and readout functions of Controls class:
        kwargs[var_str_apply] = self.apply
        kwargs[var_str_readout] = self.readout
        
        # Execute sweep via Sweep submodule:
        run_id = self.submodules[str_sw_cntrlr].execute_sweep(**kwargs)
        
        return run_id
                         
    def markdown(self):
        """
        This procedure displays the control parameters of your experiment in
        form of a Marktown table showing column-wise:
            - name of reference variable
            - instrument parameter
            - current value
            - type of control
        """
        output     =  'Your working environment is now enriched with the reference variables:  \n\n'\
                    +  '| Variable |   Reference   |   Value   |   Type   |   \n'  \
                    +  '| :------: |   :-------:   | :-------: | :-------: |  \n'
        for control in self.parameters:
            if type(self.parameters[control]) == DelegateParameter:
                source = self.parameters[control].source.full_name
                value = self.parameters[control]()
                unit = self.parameters[control].unit
                if type(value)==float:
                    value = "{:.3e}".format(value)+" "+str(unit)
                else:
                    value = str(value)+" "+str(unit)
                if self._is_readout(self.parameters[control]):
                    ctype = 'Readout'
                else:
                    ctype = 'Control'
                output += '|   {:s}   |     {:s}      |    {:s}   |    {:s}   | \n'.format(control, source, value,ctype)
        display(Markdown(output))

    
# def list_readouts(station:qc.Station):
#     """
#     This procedure displays the basic readouts of your station.
#     It is saved as metadata.
#     The output is a Marktown table showing for each readout the variable and qcodes-parameter reference and it's value.
#     """
#     output     =  'Your working environment is now enriched with the readouts:  \n\n'\
#                +  '| Variable |   Reference   |   Value   |   \n'  \
#                +  '| :------: |   :-------:   | :-------: |  \n'
#     for control in station.metadata['readouts']:
#         control_name = [k for k, v in globals().items() if v == control][0] 
#         ref_class = control.full_name
#         control_value = str(control())
#         output += '|   {:s}   |     {:s}      |    {:s}   | \n'.format(control_name, ref_class,control_value)
#     display(Markdown(output))

def display_with_source(parameter:DelegateParameter):
    """
    This procedure displays the value of a certain control parameter in
    its user-defined units with it's raw instrument value (source).
    """
    display(Markdown(
        'The value of **{:s}** is **{:.2e} {:s}**,  whereas its source **{:s}** is **{:.2f} {:s}**'.format(
        parameter.name,
        parameter(),
        parameter.unit,
        parameter.source.full_name,
        parameter.source(),
        parameter.source.unit,
    )))