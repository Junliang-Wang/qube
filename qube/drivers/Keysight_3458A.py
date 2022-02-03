# -*- coding: utf-8 -*-
"""
Created on Tue Sep  8 17:53:02 2020

@author: Daiki Matsumaru
"""

from qcodes import VisaInstrument, validators as vals
from typing import Union, List

class Keysight_3458A(VisaInstrument):
    """
    This is the qcodes driver for the Keysight 3458A digital multimeter

    Status: beta-version.
        TODO:
        - Add all parameters that are in the manual

    This driver will most likely work for multiple Agilent sources.

    This driver does not contain all commands available for the 3458A but
    only the ones most commonly used.
    """

    def __init__(self, name:str, address:int=10, NPLC:int=10,
                 NDIG:int=8, RANGE:Union[float, int, str]='AUTO',
                 AZERO:Union[int, str]='on', TARM:str='AUTO',
                 reset:bool=True, **kwargs):
        super().__init__(name, 'GPIB0::{:d}::INSTR'.format(address), **kwargs)
        # Initialize the instrument
        if reset:
            self.write('RESET')
            
        self._NPLC = NPLC
        self._NDIG = NDIG
        self._RANGE = RANGE
        self._AZERO = AZERO
        self._TARM = TARM
        
        self.add_parameter(name='NPLC',
                           label='NPLC',
                           initial_value = NPLC,
                           get_cmd=self.get_NPLC,
                           set_cmd=self.set_NPLC,
                           set_parser=float,
                           vals=vals.Numbers(0.01, 1000),
                           )
        self.add_parameter(name='NDIG',
                           label='Number of digits',
                           initial_value = NDIG,
                           get_cmd=self.get_NDIG,
                           set_cmd=self.set_NDIG,
                           set_parser=int,
                           vals=vals.Numbers(1, 8),
                           )
        self.add_parameter(name='RANGE',
                           label='RANGE',
                           initial_value = RANGE,
                           get_cmd=self.get_RANGE,
                           set_cmd=self.set_RANGE,
                           set_parser=str,
                           vals=vals.Enum(1, 10, 0.1, 'AUTO'),
                           )
        self.add_parameter(name='AZERO',
                           label='Auto Zero',
                           initial_value = AZERO,
                           get_cmd = self.get_AZERO,
                           set_cmd = self.set_AZERO,
                           set_parser=str,
                           vals=vals.Enum(0, 1, 'On', 'ON', 'on',
                                          'OFF', 'Off', 'off'),
                           )
        self.add_parameter(name='TARM',
                           label='TARM',
                           initial_value = TARM,
                           get_cmd=self.get_TARM,
                           set_cmd=self.set_TARM,
                           set_parser=str,
                           vals=vals.Enum('HOLD', 'AUTO'),
                           )
        self.add_parameter(name='v',
                           label='Input voltage',
                           unit='V',
                           get_cmd=self.get_value,
                           get_parser=float,
                           snapshot_get = False,
                           snapshot_value = False,
                           snapshot_exclude = True,
                           )
        # self.add_parameter(name='TRIG',
        #                    label='TRIG',
        #                    set_cmd='TRIG' + ' {}',
        #                    set_parser=str,
        #                    )
        # self.add_parameter(name='NRDGS',
        #                    label='NRDGS',
        #                    set_cmd='NRDGS' + ' {:d}',
        #                    set_parser=int,
        #                    )
        print('Load Keysight 3458A digital multimeter.')
        
        
    def get_NPLC(self):
        return self._NPLC
    
    def set_NPLC(self, val:float):
        self.write('NPLC {:.3f}'.format(val))
        self._NPLC = val
        
    def get_NDIG(self):
        return self._NDIG
    
    def set_NDIG(self, val:int):
        self.write('NDIG {:d}'.format(val))
        self._NDIG = val
        
    def get_RANGE(self):
        return self._RANGE
    
    def set_RANGE(self, val:str):
        self.write('RANGE {}'.format(val))
        self._RANGE = val
        
    def get_AZERO(self):
        return self._AZERO
    
    def set_AZERO(self, val:str):
        self.write('AZERO {}'.format(val))
        self._AZERO = val
        
    def get_TARM(self):
        return self._TARM
    
    def set_TARM(self, val:str):
        self.write('TARM {}'.format(val))
        self._TARM = val
        
    ###############################################
    # Core functions
    ###############################################
    def get_value(self):
        """
        This function performs single voltage measurement.
        """
        self.write('TARM SGL')
        self._TARM = 'HOLD'
        v = self.visa_handle.read_bytes(count=18)
        v = float(v)
        
        return v
        
    def reset_dmm(self):
        """
        Reset digital multi-meter to factory default.
        """
        self.write('RESET')