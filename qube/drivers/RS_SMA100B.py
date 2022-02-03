#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Wed Jan 22 11:50:13 2020

@author: shintarotakada
"""
from qcodes import VisaInstrument, validators as vals

class RS_SMA100B(VisaInstrument):
    """
    This is a qcodes driver for Rohde Schwarz SMA100B signal generator
    
    
    """
    
    def __init__(self, name, address, **kwargs):
        super().__init__(name, address, **kwargs)
        
        self.add_parameter(name = 'frequency',
                           label = 'Frequency',
                           unit = 'Hz',
                           get_cmd = ':FREQ:CW?',
                           set_cmd = ':FREQ:CW {:.4f}',
                           get_parser = float,
                           set_parser = float,
                           vals = vals.Numbers(8.0e3,20.0e9))
        self.add_parameter(name = 'phase',
                           label = 'Phase',
                           unit = 'Deg',
                           get_cmd = ':PHASe?',
                           set_cmd = ':PHASe {:.8f}',
                           get_parser = float,
                           set_parser = float,
                           vals = vals.Numbers(-36000, 36000))
        self.add_parameter(name = 'power',
                           label = 'Power',
                           unit = 'dBm',
                           get_cmd = ':POW:POW?',
                           set_cmd = ':POW:POW {:.2f}',
                           get_parser = float,
                           set_parser = float,
                           vals = vals.Numbers(-145, 30))
        self.add_parameter(name='pulse_delay',
                           label='Pulse_Delay',
                           unit='s',
                           get_cmd=':PULM:DEL?',
                           set_cmd=':PULM:DEL' + ' {:e}',
                           get_parser=float,
                           set_parser=float)
        self.add_parameter(name='pulse_period',
                           label='Pulse_period',
                           unit='s',
                           get_cmd=':PULM:PER?',
                           set_cmd=':PULM:PER' + ' {:e}',
                           get_parser=float,
                           set_parser=float,
                           vals = vals.Numbers(20.0e-9, 100))
        self.add_parameter(name='pulse_width',
                           label='Pulse_width',
                           unit='s',
                           get_cmd=':PULM:WIDT?',
                           set_cmd=':PULM:WIDT' + ' {:e}',
                           get_parser=float,
                           set_parser=float,
                           vals=vals.Numbers(20.0e-9, 100))
        self.add_parameter('status',
                           get_cmd=':OUTP:ALL?',
                           set_cmd=':OUTP:ALL' + ' {}',
                           vals=vals.Enum(0,1,'OFF','ON'))
        self.add_parameter('modulation',
                           get_cmd=':MOD?',
                           set_cmd=':MOD' + ' {}',
                           vals=vals.Enum(0,1,'OFF','ON'))
        self.add_parameter('alc',
                           get_cmd=':POW:ALC?',
                           set_cmd=':POW:ALC' + ' {}',
                           vals=vals.Enum(1, 'ON', 'AUTO',
                                          'OFFTable','OFF',0,
                                          'ONTable'))
        self.add_parameter('pulse_mod',
                           get_cmd=':PULM:STAT?',
                           set_cmd=':PULM:STAT' + ' {}',
                           vals=vals.Enum(0,1,'OFF','ON'))
        self.add_parameter('pulse_src',
                           get_cmd=':PULM:SOUR?',
                           set_cmd=':PULM:SOUR' + ' {}',
                           vals=vals.Enum('INT', 'EXT'))
        self.add_parameter('pulse_mode',
                           get_cmd=':PULM:MODE?',
                           set_cmd=':PULM:MODE' + ' {}',
                           vals=vals.Enum('SING', 'DOUB', 'PTR'))
        self.add_parameter('pulse_ttype',
                           label = 'Pulse transition type',
                           get_cmd = ':PULM:TTYP?',
                           set_cmd = ':PULM:TTYP {}',
                           vals = vals.Enum('SMO','FAST'),
                           docstring = """SMOothed
                                          flattens the slew rate, resulting in longer rise/fall times.
                                          FAST
                                          enables fast transitions with shortest rise and fall times.""",
                           )
        self.add_parameter(name = 'pulse_trig_mode',
                           label = 'Pulse Trigger Mode',
                           get_cmd = ':PULM:TRIG:MODE?',
                           set_cmd = ':PULM:TRIG:MODE {}',
                           vals = vals.Enum('AUTO','EXT','EGAT','SING','ESIN'))
        self.add_parameter(name = 'pulse_trig_pol',
                           label = 'External pulse trigger polarity',
                           get_cmd = ':PULM:POL?',
                           set_cmd = ':PULM:POL {}',
                           vals = vals.Enum('NORM', 'INV'))
        self.add_parameter(name = 'pulse_trig_thre',
                           label = 'External pulse trigger threshold',
                           unit = 'V',
                           get_cmd = ':PULM:THR?',
                           set_cmd = ':PULM:THR {:.1f}',
                           vals = vals.Numbers(0,2))
        self.add_parameter(name = 'pgen_output_pol',
                           label = 'Pulse generator output polatity',
                           get_cmd = ':PGEN:OUTP:POL?',
                           set_cmd = ':PGEN:OUTP:POL {}',
                           vals = vals.Enum('NORM','INV'),
                           docstring = """NORMal
                                          Outputs the pulse signal during the pulse width, that means during the high state.
                                          INVerted
                                          Inverts the pulse output signal polarity. The pulse output signal is
                                          suppressed during the pulse width, but provided during the low
                                          state.""",
                           )
        self.add_parameter(name = 'pgen_output',
                           label = 'Pulse generator output state',
                           get_cmd = ':PGEN:OUTP?',
                           set_cmd = ':PGEN:OUTP {}',
                           vals = vals.Enum(0,1,'OFF','ON'),
                           )
        self.add_parameter(name = 'pgen_state',
                           label = 'Pulse generator state',
                           get_cmd = ':PGEN:STAT?',
                           set_cmd = ':PGEN:STAT {}',
                           vals = vals.Enum(0,1,'OFF','ON'),
                           docstring = """
                           Enables the output of the video/sync signal.
                            If the pulse generator is the current modulation source, activating the pulse modulation
                            automatically activates the signal output and the pulse generator.
                           """,
                           )
        

        self.connect_message()
        
    def trig_pulse(self):
        self.write(':PULM:TRIG:IMM')
        
    def on(self):
        self.set('status','ON')
        
    def off(self):
        self.set('status','OFF')
        
    def pulse_on(self):
        self.set('pulse_mod', 'ON')
        
    def pulse_off(self):
        self.set('pulse_mod', 'OFF')