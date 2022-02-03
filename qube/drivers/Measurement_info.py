# -*- coding: utf-8 -*-
"""
Created on Fri Nov 29 13:57:28 2019

@author: Shintaro
"""
from qcodes.instrument.base import InstrumentBase

class measurement_info(InstrumentBase):
    """
    This is meta instrument holding meta information of measurement.
    
    """
    
    def __init__(self,
                 name = '',
                 sweeps = ('',),
                 return2initial = True,
                 measures = ('',),
                 sweep_dims = (1,),
                 measurement_type = '',
                 device_name = '',
                 note = '',
                 fast_sweep = False,
                 **kwargs
                 ) -> None:
        super().__init__(name, **kwargs)
        self._sweeps = sweeps
        self._return2initial = return2initial
        self._measures = measures
        self._sweep_dims = sweep_dims
        self._measurement_type = measurement_type
        self._device_name = device_name
        self._note = note
        self._fast_sweep = fast_sweep
        
        self.add_parameter('sweeps',
                           label='Sweep parameters',
                           get_cmd = self.get_sweeps,
                           set_cmd = self.set_sweeps,
                           )
        
        self.add_parameter('return2initial',
                           label = 'Return to initial position',
                           get_cmd = self.get_return2initial,
                           set_cmd = self.set_return2initial,
                           )
        
        self.add_parameter('measures',
                           label='Measurement parameters',
                           get_cmd = self.get_measures,
                           set_cmd = self.set_measures)
        
        self.add_parameter('sweep_dims',
                           label='Sweep dimensions',
                           get_cmd = self.get_sweep_dims,
                           set_cmd = self.set_sweep_dims)
        
        self.add_parameter('measurement_type',
                           label='Type of measurement',
                           get_cmd = self.get_measurement_type,
                           set_cmd = self.set_measurement_type)
        
        self.add_parameter('device_name',
                           label = 'Name of the measured device',
                           get_cmd = self.get_device_name,
                           set_cmd = self.set_device_name)
        
        self.add_parameter('note',
                           label = 'note',
                           get_cmd = self.get_note,
                           set_cmd = self.set_note)
        
        self.add_parameter('fast_sweep',
                           label = 'fast sweep',
                           get_cmd = self.get_fast_sweep,
                           set_cmd = self.set_fast_sweep)
        
    def set_sweeps(self, val:tuple):
        self._sweeps = val
        
    def get_sweeps(self):
        return self._sweeps
    
    def set_return2initial(self, val:bool):
        self._return2initial = val
        
    def get_return2initial(self):
        return self._return2initial
    
    def set_measures(self, val:tuple):
        self._measures = val
        
    def get_measures(self):
        return self._measures
    
    def set_sweep_dims(self, val:tuple):
        self._sweep_dims = val
        
    def get_sweep_dims(self):
        return self._sweep_dims
    
    def set_measurement_type(self, val:str):
        self._measurement_type = val
        
    def get_measurement_type(self):
        return self._measurement_type
    
    def set_device_name(self, val:str):
        self._device_name = val
        
    def get_device_name(self):
        return self._device_name
    
    def set_note(self, val:str):
        self._note = val
        
    def get_note(self):
        return self._note
    
    def set_fast_sweep(self, val:bool):
        self._fast_sweep = val
        
    def get_fast_sweep(self):
        return self._fast_sweep