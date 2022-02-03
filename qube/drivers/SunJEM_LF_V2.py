# -*- coding: utf-8 -*-
"""
Created on Tue Sep  8 17:53:02 2020

@author: Daiki Matsumaru
"""

from qcodes import Instrument, VisaInstrument, validators as vals
from qcodes.instrument.channel import InstrumentChannel
from typing import Union, List
import numpy as np

carriage_return='\r'

class SunJEM_LF_V2_ch(InstrumentChannel):
    def __init__(self, parent:Instrument, name:str,
                 ch_no:int, Dxy:float=0.0, **kwargs):
        """
        This class is a channel of SunJEM_LF_V2 to control bias current for each channel.
        
        Args:
            parent (Instrument): Parent instrument
            name (str): Given name of the channel
            ch_no (int): Channel number
        """
        super().__init__(parent, name, **kwargs)
        
        self.instrument = parent
        self.ch_no = ch_no
        
        self._Dxy = Dxy
        
        self.add_parameter(name='BiasCurrent',
                           label='Input the current value in each channel',
                           initial_value = Dxy,
                           unit='mA',
                           get_cmd=self.get_Dxy,
                           set_cmd=self.set_Dxy,
                           set_parser=float,
                           vals=vals.Numbers(0.0, 20.0),
                           )
        
    def get_Dxy(self):
        return self._Dxy
    
    def set_Dxy(self, val:float):
        val = int(val*200)
        s = '{:012d}'.format(int(bin(val)[2:]))
        if self.ch_no < 5:
            c = self.ch_no-1
            s = 'DA{:04d}'.format(int(bin(c)[2:])) + s
        elif self.ch_no < 9:
            c = self.ch_no-5
            s = 'DB{:04d}'.format(int(bin(c)[2:])) + s
        elif self.ch_no < 13:
            c = self.ch_no-9
            s = 'DC{:04d}'.format(int(bin(c)[2:])) + s
        elif self.ch_no < 17:
            c = self.ch_no-13
            s = 'DD{:04d}'.format(int(bin(c)[2:])) + s
        elif self.ch_no < 21:
            c = self.ch_no-17
            s = 'DE{:04d}'.format(int(bin(c)[2:])) + s
        elif self.ch_no < 25:
            c = self.ch_no-21
            s = 'DF{:04d}'.format(int(bin(c)[2:])) + s
        
        self.instrument.write(s)
        # Read buffer to make it empty
        s = self.instrument.visa_handle.read_bytes(count=3)
        # print('ch{:d},{}'.format(self.ch_no, s))
        self._Dxy = val

class SunJEM_LF_V2(VisaInstrument):
    """
    This is the qcodes driver for the SunJEM_LF_V2 PJVS Bias Circuit

    Status: beta-version.
        TODO:
        - Add all parameters that are in the manual

    This driver does not contain all commands available for the LF_V2 but
    only the ones most commonly used.
    """

    def __init__(self, name:str, com:int=3,
                 Zx:int=1,
                 CLK:int=1, Base_f:int=1,
                 Wxxxx:int=0, write_termination:str=carriage_return,
                 timeout=10.0,
                 **kwargs):
        super().__init__(name, 'ASRL{:d}::INSTR'.format(com), timeout=timeout, **kwargs)
        self.visa_handle.write_termination = write_termination
        
        self._Zx = Zx
        self._CLK = CLK
        self._Base_f = Base_f
        self._ba = 0.0
        """
        ↑This parameter's value is the original value plus 1.
        """
        self._Wxxxx = Wxxxx
        
        self.add_parameter(name='Set_relays',
                           label='Set output-short latching relays',
                           initial_value = Zx,
                           get_cmd=self.get_Zx,
                           set_cmd=self.set_Zx,
                           set_parser=int,
                           vals=vals.Enum(1, 2),
                           )
        self.add_parameter(name='Set_clock',
                           label='Determine Base frequency by the parameter NBasse',
                           initial_value = CLK,
                           get_cmd=self.get_CLK,
                           set_cmd=self.set_CLK,
                           set_parser=int,
                           vals=vals.Ints(1, 3),
                           )
        self.add_parameter(name='Base_f',
                           label='Determine Base frequency by the parameter NDev',
                           initial_value = Base_f,
                           get_cmd=self.get_Base_f,
                           set_cmd=self.set_Base_f,
                           set_parser=int,
                           vals=vals.Ints(0, 255),
                           )
        self.add_parameter(name='Set_wave',
                           label='Select the waveform pattern (32 variation) from EPROMs',
                           initial_value = Wxxxx,
                           get_cmd = self.get_Wxxxx,
                           set_cmd = self.set_Wxxxx,
                           set_parser=int,
                           vals=vals.Ints(0, 31),
                           )
        
        self.add_parameter(name='ba',
                           label='Bias all channels',
                           unit = 'mA',
                           set_cmd = self.bias_all_zero,
                           vals=vals.Numbers(0.0, 20.0),
                           snapshot_get = False,
                           snapshot_value = False,
                           snapshot_exclude = True,
                           )
        
        for ch in range(24):
            chan = SunJEM_LF_V2_ch(parent = self,
                                   name = 'ch{:d}'.format(ch+1),
                                   ch_no = ch+1,
                                   Dxy=0.0
                                   )
            self.add_submodule('ch{:d}'.format(ch+1), chan)
            
        print('Load SunJEM LF_V2 bias source.')
        
    def get_Zx(self):
        return self._Zx
    
    def set_Zx(self, val:int):
        self.write('Z{:d}'.format(val))
        # Read buffer to make it empty
        s = self.visa_handle.read_bytes(count=3)
        # print('z, {}'.format(s))
        self._Zx = val
        
    def get_CLK(self):
        return self._CLK
    
    def set_CLK(self, val:int):
        self.write('CLK{:d}'.format(val))
        # Read buffer to make it empty
        self.visa_handle.read_bytes(count=3)
        self._CLK = val
        
    def get_Base_f(self):
        return self._Base_f
    
    def set_Base_f(self, val:int):
        self.write('B{}'.format('{:08d}'.format(int(bin(val)[2:]))))
        # Read buffer to make it empty
        self.visa_handle.read_bytes(count=3)
        self._Base_f = val
        
    def get_Wxxxx(self):
        return self._Wxxxx
    
    def set_Wxxxx(self, val:int):
        self.write('W{}'.format('{:05d}'.format(int(bin(31-val)[2:]))))
        # Read buffer to make it empty
        s = self.visa_handle.read_bytes(count=3)
        # print('wave {}'.format(s))
        
        self.write('EXEC')
        # Read buffer to make it empty
        s = self.visa_handle.read_bytes(count=3)
        # print('EXEC, {}'.format(s))
        self._Wxxxx = val
        
    ###############################################
    # Core functions
    ###############################################
    def init_bias(self):
        """
        Initialize bias source.
        """
        self.Set_relays(2)
        self.Set_clock(1)
        self.set_Base_f(1)
        self.Set_wave(0)
        
    def bias_all_zero(self, val:float=0.0):
        """
        This function set bias current of all the channel to the given value.
        """
        for i in range(24):
            chan = getattr(self, 'ch{:d}'.format(i+1))
            chan.BiasCurrent(val)
            
    def set_all_bias(self, ar:np.array):
        """
        When you give an array whose size is larger than 24,
        this function set each element of the array to the corresponding channel.
        """
        # Check array size
        sz = ar.size
        if sz < 24:
            return ValueError('Please give an array larger than 24')
        # Reshpe array dimension to 1D
        ar = ar.reshape(-1)
        
        for i in range(24):
            chan = getattr(self, 'ch{:d}'.format(i+1))
            chan.BiasCurrent(ar[i])