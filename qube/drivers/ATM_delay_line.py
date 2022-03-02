# -*- coding: utf-8 -*-
"""
Program to control the delay line ATM PNR P1608-SM24

Usage: 
if the device has been turned off at a position different from zero
        -With the power unplugged, screw counterclockwise all the way to the end
        -ATM_delay_line.init(0)            This command move the line slightly to the left (used to get away from the end reached while screwing)
        -ATM_delay_line.set_zero(0)         This command set the current position as zero reference for the system. 
When zero position has been correctly set        
        -ATM_delay_line.delay(float)       To safely set the delay in ps.
Before closing:
        -ATM_delay_line.delay(0)           Not mandatory but saves you to reset the position on start up again.

Parameters: acceleration, deceleration, maximum_velocity and initial velocity might be tweaked to reduce the movement time.

The delay is computed in picoseconds relatively to the zero position and it's not an absolute number.
Imporant notes:
    All parameters should be asked 3 times in order to clear the data in the comunication buffer. Unfortunately echo mode = 2 is necessary for the driver to work

    
"""

import time

import qcodes as qc
from qcodes import (Instrument, VisaInstrument,
                    ManualParameter, MultiParameter,
                    validators as vals)
from qcodes.instrument.channel import InstrumentChannel

import matplotlib.pyplot as plt
import numpy as np
     
""" CONSTANTS """

conv_steps_to_picoseconds = -17.9679e-5                                      #used to convert steps and picoseconds: unit ps/step 
letters2kill = ['\n','BD','=','A']

""" GENERAL PURPOSE FUNCTIONS """

def kill_letters(text:str,letters2kill=list):                               #to strip characters from the outputs
    for letter2kill in letters2kill:
        text = text.replace(letter2kill,'')
    return text

strip_newline_to_int = lambda text: int(kill_letters(text,letters2kill)) 
strip_A_to_int = lambda text: int(text.replace('\n',''))



class ATM_delay_line(VisaInstrument):
    

     
    def __init__(self, name, address, **kwargs):

        super().__init__(name, address, terminator="\r", **kwargs)
        
        self.add_parameter(
            name='echo_mode',                                   #useless parameter but must be set to 2 for the program to work
            set_cmd='EM {:d}',
            get_cmd=False, 
            set_parser=int,
            initial_value=2,                        
        )

        self.add_parameter(
            name="baud_rate1",                                 #unused parameter
            set_cmd='BD {:d}',
            get_cmd=False,
            set_parser=int,
            initial_value=9600,             
        )
   
        
        self.add_parameter(
            name="acceleration",                              #unused but can be useful to set it to different values.
            set_cmd='A {:d}',                                 # speed (steps/sec) starts at initial velocity
            get_cmd=self._get_acceleration,                   # "acceleration"  (steps/sec**2) until maximum velocity or half of the movement
            set_parser=int,                                   # decelerate to 0 at rate "deceleration" (step/sec**2)
            get_parser=strip_newline_to_int,
            vals=vals.Numbers(min_value=1e5,max_value=1e6),
            initial_value=3e5,
        )

        self.add_parameter(
            name="deceleration",
            set_cmd='D {:d}',
            get_cmd=self._get_deceleration,
            set_parser=int,
            get_parser=strip_newline_to_int,
            vals=vals.Numbers(min_value=1e5,max_value=1e6),
            initial_value=3e5,
        )

        self.add_parameter(
            name="initial_velocity",
            set_cmd='VI {:d}',
            get_cmd=self._get_initial_velocity,
            set_parser=int,
            get_parser=strip_newline_to_int,
            initial_value=1e5,
        )

        self.add_parameter(
            name="maximum_velocity",
            set_cmd='VM {:d}',
            get_cmd=self._get_maximum_velocity,
            set_parser=int,
            get_parser=strip_newline_to_int,
            initial_value=5e5,
        )
       
        self.add_parameter(                              # used to set the actual position as zero reference 
            name='set_zero',
            set_cmd='P {:d}',
            get_cmd=False, 
            set_parser=int
        )
                
        self.add_parameter(                             #used byt to functione _move_to to actually move (in steps)
            name="_move_step",
            unit='steps',
            set_cmd='MR {:d}',
            get_cmd=False
        )
        self.add_parameter(                             #used in the initialization to move away from the boundary. implemented with different name and fixed value for device safety
            name="init",
            unit='steps',
            set_cmd='MR -20000',
            get_cmd=False
        )

        self.add_parameter(
            name='_position',                           # Position parameter measured in steps. Ideally this is not used by the user
            unit='steps',
            set_cmd=self._move_to,
            get_cmd=self._get_position, 
            get_parser=strip_newline_to_int
        )
        
        self.add_parameter(                       #Line delay in picoseconds
            name='delay',
            unit='ps',
            set_cmd=self._move_to_time,
            get_cmd=self._position_to_delay,
            vals=vals.Numbers(min_value=0.0,max_value=230.0)
        )
        
        self.add_parameter(
            name='_moving_flag',                  #Flag for the moving state
            set_cmd=False,
            get_cmd = self._get_moving_flag,
            get_parser = strip_newline_to_int
        )
        
    def ask3x(self,cmd:str):                     #Function used to overcome the echos. Ask three times for a parameter
        for ind in np.arange(5):
            answer = self.ask(cmd)
        return answer

    def _check_range(self,position_to_check):                 #Check if the requested final position is achievable. Move to zero if it fails
        if position_to_check<-1300000 or position_to_check>0:
            print("Position out of range. \nMoving to the start of the line. \nRemember the allowed position are between -1.3E6 and 0 and the time position between 0 and 230")
            return(0)
        else:
            return position_to_check  
    


    def _move_to(self, position_in_steps:int):                 #move to the desired position measured in step
        target_position = self._check_range(position_in_steps) # if position is invalid, then target position is 0
        actual_position = self._position()
        steps_to_move   = target_position - actual_position    #compute the relative movement
        self._move_step(steps_to_move)                         #actual movement
        time.sleep(0.01)
        moving = self._moving_flag()                           #check every 0.01 seconds if the movement has finished
        print('Waiting for move to finish.')
        while moving:
            time.sleep(0.01)
            moving = self._moving_flag()
        print('Done.')


  
    
    def _position_to_delay(self):                          #converts the actual position in steps to delay in picoseconds
        position=self._position()
        delay=position*conv_steps_to_picoseconds
        return delay

    def _move_to_time(self, time :float):                 #move to required delay in picoseconds. Converts delay to a position in steps wich is input to _move_to
        position=int(time//conv_steps_to_picoseconds)
        self._move_to(position)
    
    def _get_position(self):                              # parameters get function repeated three times
         return self.ask3x("PR P")
        
    def _get_moving_flag(self):
         return self.ask3x("PR MV")
    
    def _get_acceleration(self):
        return self.ask3x('PR A')

    def _get_deceleration(self):
        return self.ask3x('PR D')

    def _get_initial_velocity(self):
         return self.ask3x("PR VI")

    def _get_maximum_velocity(self):
         return self.ask3x("PR VM")    

        
        
print('Connected to ATM delay line ... IMPORTANT: If initial position is not zero, follow the initialization procedure describe in the driver')

        

