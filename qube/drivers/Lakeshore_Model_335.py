from typing import ClassVar, Dict, Any
from qcodes import Instrument, VisaInstrument, validators as vals
from qcodes.instrument.channel import InstrumentChannel
import time

class Model_335_output_channel(InstrumentChannel):
    """
    
    """
    def __init__(self, parent:Instrument, name:str, ch_no:int, **kwargs) -> None:
        super().__init__(parent, name, **kwargs)
        self.ch_no = ch_no
        
        range_get_cmd = 'RANGE? {:d}'.format(self.ch_no)
        range_set_cmd = 'RANGE {:d}'.format(self.ch_no)
        setp_get_cmd = 'SETP? {:d}'.format(self.ch_no)
        setp_set_cmd = 'STEP {:d}'.format(self.ch_no)
        
        self.add_parameter('range',
                           label='Output range',
                           get_cmd=range_get_cmd,
                           set_cmd=range_set_cmd + ',{:d}',
                           get_parser = int,
                           val_mapping = {'off':0, 'low':1, 'medium':2, 'high':3},
                           )
        
        self.add_parameter('setp',
                           label='Temperature set point',
                           unit='K',
                           get_cmd = setp_get_cmd,
                           set_cmd = setp_set_cmd + ',{:f}',
                           get_parser = float,
                           set_parser  =float,
                           vals = vals.Numbers(0.0, 300.0),
                           )
        
class Model_335_output_sensor(InstrumentChannel):
    """
    
    """
    def __init__(self, parent:Instrument, name:str, sensor_name:str, **kwargs) -> None:
        super().__init__(parent, name, **kwargs)
        
        self.sensor_name = sensor_name
        krdg_cmd = 'KRDG? {}'.format(self.sensor_name)
        
        self.add_parameter('krdg',
                           label='Kelvin reading',
                           unit='K',
                           get_cmd = krdg_cmd,
                           get_parser=float)

class Model_335(VisaInstrument):
    """
    Lakeshore Model 335 Temperature Controller Driver
    """

    def __init__(self, name: str, address: str, **kwargs) -> None:
        super().__init__(name, address, **kwargs)
        
        self.add_parameter('time',
                           label='Elapsed time',
                           unit='s',
                           get_cmd = time.time,
                           get_parser = float,
                           )

        for ch in range(2):
            chan = Model_335_output_channel(self, 'ch{:d}'.format(ch+1), ch_no=(ch+1))
            self.add_submodule('ch{:d}'.format(ch+1), chan)
            
        for ch in range(2):
            chan = Model_335_output_sensor(self, ['A','B'][ch], ['A','B'][ch])
            self.add_submodule(['A','B'][ch], chan)
            
        self.connect_message()