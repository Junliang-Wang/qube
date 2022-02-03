# -*- coding: utf-8 -*-
"""
Created on Tue Jul  9 21:06:57 2018

@author: Shintaro
"""

import numpy as np

from qcodes import Instrument
from qcodes.instrument.visa import VisaInstrument
from qcodes.instrument.channel import InstrumentChannel
from qcodes.instrument.parameter import ArrayParameter
from qcodes import validators as vals

from typing import Union, List

def parse_frequency(freq):
#    if freq[-1]=='\n':
#        freq = freq[:-1]
    freq = freq.strip()
    return float(freq)

class sTrace(ArrayParameter):
    
    def __init__(self, name: str, instrument: InstrumentChannel,
                 channum: int, s_param_choice: str) -> None:
        """
        
        """
        super().__init__(name=name,
                         shape=(1,),
                         label=s_param_choice,
                         unit='dB',
                         setpoint_names=('Frequency',),
                         setpoint_labels=('Frequency',),
                         setpoint_units=('Hz',),
                         docstring='Holds s-parameter trace')
        self.channum = channum
        self._instrument = instrument
        
    def prepare_trace(self) -> None:
        """
        Prepare to get trace
        """
        inst = self._instrument._parent
        
        f_start = inst.f_start()
        f_stop = inst.f_stop()
        pts = inst.sweep_pts()
        self.shape = (pts,)
        self.setpoints = (tuple(np.linspace(f_start, f_stop, pts, dtype=np.float)),)
        self._trace_ready = True
        # we must ensure that all this took effect before proceeding
        inst.opc()
        
    def get_raw(self):
        """
        Measure and get data.
        """
        if not self._trace_ready:
            raise ValueError('Trace not ready! Please call '
                             'prepare_trace().')
            
        inst = self._instrument._parent
        
        inst.write("CALCulate:PARameter:SELect 'ch1_{}'".format(inst.s_params[int(self.channum)-1]))
        data = np.array(inst.ask('CALCulate:DATA? SDATA').split(','), dtype=np.float)
        data = data.reshape((2,self.shape[0]), order='F')[0,:] + 1j*data.reshape((2,self.shape[0]), order='F')[1,:]
        
        inst.opc()
        return data
        
class display(InstrumentChannel):
    """
    Class to hold a s parameter info.
    Since each s parameter is assigned to each window,
    this class holds scale info for that window.
    """
    def __init__(self, parent: Instrument, name: str, channum: int) -> None:
        if channum not in [1, 2, 3, 4]:
            raise ValueError('Invalid diaplay number! Must be 1 ~ 4.')
        
        self.channum = channum
        
        super().__init__(parent, name)
        
        self.add_parameter('trace',
                           channum=self.channum,
                           s_param_choice=self._parent.s_params[self.channum-1],
                           parameter_class=sTrace)
        
        self._trace_ready = False
                
    def auto_scale(self):
        self.write('DISPlay:WINDow{}:TRACe:Y:AUTO'.format(self.channum))
        
class Keysight_ENA(VisaInstrument):
    """
    This is the qcodes driver for the Keysight vecotr network analyzer (ENA)
    The driver is tested by E5080A.
    
    NOTE: Meanwhile I use this device by splitting the window to 4 and set
          each window to measure s11, s12, s21, s22, respectively.
    """
    def __init__(self, name: str, address: str,
                 timeout:float =180.0, s_params =['S11', 'S12', 'S21', 'S22'], csa_list = [''],
                 current_csa = 0, csa_folder_path = 'D:/Calibration/Picoprobe',
                 **kwargs):
        super().__init__(name, address, timeout, **kwargs)
        
        self.s_params = s_params
        self._csa_list = csa_list
        self._current_csa = current_csa
        self._csa_folder_path = csa_folder_path
        
        self.add_parameter('state',
                           label='Output state',
                           set_cmd='OUTPut {}',
                           get_cmd='OUTPut?',
                           val_mapping={'ON':1, 'OFF':0})
        
        self.add_parameter('f_start',
                           label='Start frequency',
                           unit='Hz',
                           set_cmd='SENSe:FREQuency:STARt {:e}',
                           get_cmd='SENSe:FREQuency:STARt?',
                           get_parser=parse_frequency,
                           vals=vals.Numbers(9.0e3, 9.0e9))
        
        self.add_parameter('f_stop',
                           label='Stop frequency',
                           unit='Hz',
                           set_cmd='SENSe:FREQuency:STOP {:e}',
                           get_cmd='SENSe:FREQuency:STOP?',
                           get_parser=parse_frequency,
                           vals=vals.Numbers(9.0e3, 9.0e9))
        
        self.add_parameter('f_center',
                           label='Center frequency',
                           unit='Hz',
                           set_cmd='SENSe:FREQuency:CENTer {:e}',
                           get_cmd='SENSe:FREQuency:CENTer?',
                           get_parser=parse_frequency,
                           vals=vals.Numbers(9.0e3, 9.0e9))
        
        self.add_parameter('sweep_pts',
                           label='Sweep points',
                           unit='pts',
                           set_cmd='SENSe:SWEep:POINts {:d}',
                           get_cmd='SENSe:SWEep:POINts?',
                           get_parser=int)
        
        self.add_parameter('power',
                           label='Source power port 1',
                           unit='dBm',
                           set_cmd='SOURce:POWer {:f}',
                           get_cmd='SOURce:POWer?',
                           get_parser=float,
                           vals=vals.Numbers(-120, 20))
        
        self.add_parameter('ifbw',
                           label='IF Bandwidth',
                           unit='Hz',
                           set_cmd='SENSe:BWID {:e}',
                           get_cmd='SENSe:BWID?',
                           get_parser=float,
                           vals=vals.Numbers(1.0, 1.5e6))
        
        self.add_parameter('average',
                           label='Average state',
                           set_cmd='SENSe:AVERage {}',
                           get_cmd='SENSe:AVERage?',
                           val_mapping = {'ON':1, 'OFF':0})
        
        self.add_parameter('avg_count',
                           label='Average counts',
                           set_cmd='SENSe:AVERage:COUNt {:d}',
                           get_cmd='SENSe:AVERage:COUNt?',
                           get_parser=int)
        
        self.add_parameter('avg_mode',
                           label='Average mode',
                           set_cmd='SENSe:AVERage:MODE {}',
                           get_cmd='SENSe:AVERage:MODE?',
                           val_mapping={'Sweep':'SWE\n', 'Point':'POIN\n'})
        
        self.add_parameter('trig_src',
                           label='Trigger source',
                           set_cmd='TRIGger:SOURce {}',
                           get_cmd='TRIGger:SOURce?',
                           val_mapping={'manual':'MAN\n','internal':'IMM\n','external':'EXT\n'})
        
        self.add_parameter('current_csa',
                           label = 'Currently setelcted csa file',
                           set_cmd = self.set_current_csa,
                           get_cmd = self.get_current_csa)
        
        self.add_parameter('csa_list',
                           label = 'CSA file list',
                           get_cmd = self.get_csa_list,
                           set_cmd = self.set_csa_list)
        
        # Initialize instrument
        self.initialize()
        
        # Add displays
        for i, s in enumerate(self.s_params):
            chan = display(self, s, i+1)
            self.add_submodule(s, chan)
        
        self.connect_message()
        
    def set_csa_list(self, val:List[str]):
        self._csa_list = val
        
    def get_csa_list(self):
        return self._csa_list
    
    def set_current_csa(self, val: Union[int, float]):
        if not int(val) < len(self._csa_list):
            raise ValueError('Please check the value of current_csa. It is larger than list size.')
            
        csa_name = self._csa_list[int(val)]
        self.loadCState(name = csa_name, folder = self._csa_folder_path)
        self.opc()
        
        self._current_csa = int(val)
        
    def get_current_csa(self):
        return int(self._current_csa)
    
    def run(self):
        self.write('INITiate:IMMediate')
        
    def run_continuous(self):
        self.write('INITiate:CONTinuous 1')
        
    def hold(self):
        self.write('INITiate:CONTinuous 0')
        
    def stop(self):
        self.write('ABORt')
        
    def clear_average(self):
        self.write('SENSe:AVERage:CLEar')
        
    def display_arrange(self, num=4):
        """
        Choose display arrangement
        """
        if num==1:
            cmd = 'OVERlay'
        elif num==2:
            cmd = 'STACk'
        elif num==3:
            cmd = 'SPLit'
        elif num==4:
            cmd = 'QUAD'
        else:
            cmd = 'TILE'
        self.write('DISPlay:ARRange '+cmd)
        
    def display_catalog(self):
        """
        Return catalog of the current display
        When there are 2 windows, [1,2] will be returned.
        """
        s = self.ask('DISPlay:CATalog?')
        return [int(i) if i != 'EMPTY' else None for i in s.strip().replace('"','').split(',')]
    
    def trace_catalog(self, wnum=1):
        """
        Return the list of the traces in the specified window.
        """
        s = self.ask('DISPlay:WINDow{:d}:CATalog?'.format(wnum))
        return [int(i) if i != 'EMPTY' else None for i in s.strip().replace('"','').split(',')]
    
    def del_trace(self, name=None):
        if name == None:
            self.write('CALCulate:PARameter:DELete:ALL')
        else:
            self.write("CALCulate:PARameter:DELete '{}'".format(name))
            
    def def_trace(self, name, parameter):
        self.write("CALCulate:PARameter:EXTended '{}', {}".format(name, parameter))
                
    def auto_scale_all(self):
        """
        Auto scale all the dispaly.
        """
        for i in self.display_catalog():
            self.write('DISPlay:WINDow{:d}:TRACe:Y:AUTO'.format(i))
            
    def loadCal(self, name:str, folder:str):
        """
        Load calibration file.
        
        Args:
            name (str): Name of the calibration file
            folder (str): Path to the folder containing the calibration file
        """
        path = folder + '/' + name + '.cal'
        self.write('MMEMory:LOAD:CORRection \'{}\''.format(path))
        self.opc()
        
    def loadState(self, name:str, folder:str):
        """
        Load state file.
        
        Args:
            name (str): Name of the calibration file
            folder (str): Path to the folder containing the calibration file
        """
        path = folder + '/' + name + '.sta'
        self.write('MMEMory:LOAD:STATe \'{}\''.format(path))
        self.opc()
        
    def loadCState(self, name:str, folder:str):
        """
        Load calibration and state file.
        
        Args:
            name (str): Name of the calibration file
            folder (str): Path to the folder containing the calibration file
        """
        path = folder + '/' + name + '.csa'
        self.write('MMEMory:LOAD:CSARchive \'{}\''.format(path))
        self.opc()
        
    def saveCState(self, name:str, folder:str):
        """
        Save calibration and state file.
        
        Args:
            name (str): Name of the calibration file
            folder (str): Path to the folder containing the calibration file
        """
        path = folder + '/' + name + '.csa'
        self.write('MMEMory:STORe:CSARchive \'{}\''.format(path))
        self.opc()
        
    def get_error_msg(self):
        """
        Get error message.
        """
        msg = self.ask('SYSTem:ERRor?')
        return msg
        
    def opc(self):
        ans = 0
        while not ans == 1:
            ans =int(self.ask('*OPC?'))
        return ans
        
    def initialize(self, reset=True):
        if reset:
            # Reset the instrument if requested.
            self.write('*RST')
        
        total_wnum = len(self.s_params)
        if total_wnum > 4:
            raise ValueError('Number of S-parameters to be measured'
                             ' should be less than 4.')
        # Split display to 4. Then set measurement parameter to s11, s12
        # s21, s22, respectively.
        self.display_arrange(num=total_wnum)
        
        # Clear all the traces before definition
        self.del_trace(name=None)
        # Define traces
        for i, s in enumerate(self.s_params):
            self.def_trace('ch1_{}'.format(s), s)
#            self.write("CALCulate:PARameter:EXTended 'ch1_{}', {}".format(s, s))
            self.write("DISPlay:WINDow{:d}:TRACe1:FEED 'ch1_{}'".format(i+1, s))
        
        # Set display data format
        for i, s in enumerate(self.s_params):
            self.write("CALCulate:PARameter:SELect 'ch1_{}'".format(s))
            self.write('CALCulate:FORMat MLOGarithmic')
        
        # Set data format to be ascii
        self.write('FORMat ASCii,0')
        
        self.opc()
        
    def measure(self):
        # Clear averaging
        self.clear_average()
        # Set to HOLD mode; wait
        self.hold()
        self.opc()
        # Trigger measurements
        for i in range(self.avg_count()):
            self.run()
            self.opc()
       
        f_start = self.f_start()
        f_stop = self.f_stop()
        pts = self.sweep_pts()
        for s in self.s_params:
            chan = getattr(self, s)
            chan.trace.shape = (pts,)
            chan.trace.setpoints = (tuple(np.linspace(f_start, f_stop, pts, dtype=np.float)),)
            chan.trace._trace_ready = True
            
if __name__=='__main__':
    ena = Keysight_ENA('ena',address='TCPIP0::192.168.0.80::hislip0::INSTR')