"""
Created on Tue Nov 17 14:23:14 2020

@author: Giorgos Georgiou
@email: georgiougeor@gmail.com

QCodes implementation of Lockin Signal Recovery 7265 DSP
"""

from functools import partial
import numpy as np

from qcodes import VisaInstrument
from qcodes.instrument.parameter import ArrayParameter
from qcodes.utils.validators import Numbers, Ints, Enum, Strings
from qcodes.instrument.group_parameter import GroupParameter, Group


from typing import Tuple
from time import sleep, time





class SR7265(VisaInstrument):
    """
    This is the qcodes driver for the Signal Recovery 7265 DSP 
    Lock-in Amplifier
    """

    _VOLT_TO_N = {2e-9:    1, 5e-9:    2, 10e-9:  3,
                  20e-9:   4, 50e-9:   5, 100e-9: 6,
                  200e-9:  7, 500e-9:  8, 1e-6:   9,
                  2e-6:    10, 5e-6:   11, 10e-6:  12,
                  20e-6:  13, 50e-6:  14, 100e-6: 15,
                  200e-6: 16, 500e-6: 17, 1e-3:   18,
                  2e-3:   19, 5e-3:   20, 10e-3:  21,
                  20e-3:  22, 50e-3:  23, 100e-3: 24,
                  200e-3: 25, 500e-3: 26, 1:      27}
    _N_TO_VOLT = {v: k for k, v in _VOLT_TO_N.items()}

    _CURR_TO_N = {2e-15:    1, 5e-15:    2, 10e-15:  3,
                  20e-15:   4, 50e-15:   5, 100e-15: 6,
                  200e-15:  7, 500e-15:  8, 1e-12:   9,
                  2e-12:    10, 5e-12:   11, 10e-12:  12,
                  20e-12:  13, 50e-12:  14, 100e-12: 15,
                  200e-12: 16, 500e-12: 17, 1e-9:    18,
                  2e-9:    19, 5e-9:    20, 10e-9:   21,
                  20e-9:   22, 50e-9:   23, 100e-9:  24,
                  200e-9:  25, 500e-9:  26, 1e-6:    27}
    _N_TO_CURR = {v: k for k, v in _CURR_TO_N.items()}

    _TIMEC_TO_N = {10e-6:  0, 20e-6:  1,
                   40e-6: 2, 80e-6: 3,
                   160e-6: 4, 320e-6: 5,
                   640e-6: 6, 5e-3: 7,
                   10e-3:  8, 20e-3:  9,
                   50e-3:  10, 100e-3:  11,
                   200e-3:  12, 500e-3:  13,
                   1:  14, 2:  15,
                   5:  16, 10:  17,
                   20:  18, 50:  19,
                   100:  20, 200:  21,
                   500:  22, 1e3:  23,
                   2e3:  24, 5e3:  25,
                   10e3:  26, 20e3:  27,
                   50e3:  28, 100e3:  29}
    _N_TO_TIMEC = {v: k for k, v in _TIMEC_TO_N.items()}

    _VOLT_ENUM = Enum(*_VOLT_TO_N.keys())
    _CURR_ENUM = Enum(*_CURR_TO_N.keys())
    _TIMEC_ENUM = Enum(*_TIMEC_TO_N.keys())


    _INPUT_CONFIG_TO_N = {
        'V': 0,
        'I High Bandwidth': 1,
        'I Low Noise': 2,
    }
    _N_TO_INPUT_CONFIG = {v: k for k, v in _INPUT_CONFIG_TO_N.items()}


    _INPUT_CONFIG_VOLTAGE_TO_N = {
        'GND': 0,
        'A': 1,
        '-B': 2,
        'A-B': 3,
    }
    _N_TO_INPUT_CONFIG_VOLTAGE = {v: k for k, v in _INPUT_CONFIG_VOLTAGE_TO_N.items()}
    
    

    def __init__(self, name, address, **kwargs):
        super().__init__(name, address, **kwargs)

        
        # Lock-in amplifier Mode: Single, Dual Reference, Dual Harmonic
        self.add_parameter('refmode',
                           label='Reference Mode (Single Reference, Dual Reference, Dual Harmonic)',
                           get_cmd='REFMODE?',
                           set_cmd=self._set_ref_mode,
                           val_mapping={
                               'Single Reference': 0,
                               'Dual Harmonic': 1,
                               'Dual Reference': 2,
                           },
                           vals=Enum('Single Reference', 'Dual Harmonic', 'Dual Reference'))
        
        # Initialise a Dual Mode variable (True or False) 
        self.dualMode = False if self.refmode()=='Single Reference' else True

        # Initialise the parameters that depend on single or dual mode
        self._parameters_single_dual_mode()

        # Input and filter
        self.add_parameter('input_config',
                           label='Input configuration',
                           get_cmd='IMODE?',
                           get_parser=self._get_input_config,
                           set_cmd='IMODE {}',
                           set_parser=self._set_input_config,
                           vals=Enum(*self._INPUT_CONFIG_TO_N.keys()))
        
        self.add_parameter('input_config_voltage',
                           label='Input configuration Voltage Mode',
                           get_cmd='VMODE?',
                           set_cmd='VMODE {}',
                           val_mapping={
                               'GND': 0,
                               'A': 1,
                               '-B': 2,
                               'A-B': 3,
                           })

        self.add_parameter('input_shield',
                           label='Input shield',
                           get_cmd='FLOAT?',
                           set_cmd='FLOAT {}',
                           val_mapping={
                               'Ground': 0,
                               'Float': 1,          # Connected to GND through a 10k resistor
                           })
        
        self.add_parameter('FET',
                           label='Voltage Input Device Control',
                           get_cmd='FET?',
                           set_cmd='FET {}',
                           val_mapping={
                               'Bipolar': 0,        # 10K input impedance and 2nV/sqrtHz noise @ 1KHz
                               'FET': 1,            # 10M input impedance and 5nV/sqrtHz noise @ 1KHz
                           })

        self.add_parameter('input_coupling',
                           label='Input coupling',
                           get_cmd='CP?',
                           set_cmd='CP {}',
                           val_mapping={
                               'AC': 0,
                               'DC': 1,
                           })

        self.add_parameter('grid_frequency',
                           label='Grid Frequency',
                           val_mapping={
                               '60': 0,
                               '50': 1,
                           },
                           parameter_class=GroupParameter) #initial_value=1,             # Change this to 0 if you have 60Hz

        self.add_parameter('notch_filter',
                           label='Notch filter',
                           val_mapping={
                               'off': 0,
                               'line in': 1,
                               '2x line in': 2,
                               'both': 3,
                           },
                           parameter_class=GroupParameter)
        
        self.output_group = Group([self.notch_filter, self.grid_frequency],
                                  get_cmd='LF?',
                                  set_cmd='LF {notch_filter} {grid_frequency}'
                                  )

        # Reference and phase
        self.add_parameter('reference_source',
                           label='Reference source',
                           get_cmd='IE?',
                           set_cmd='IE {}',
                           val_mapping={
                               'internal': 0,
                               'external rear': 1,
                               'external front': 2,
                           },
                           vals=Enum('internal', 'external rear', 'external front'))


              



        self.add_parameter('frequency',
                           label='Frequency',
                           get_cmd='FRQ.?',
                           get_parser=float,
                           set_cmd='OF. {:.4f}',
                           unit='Hz',
                           vals=Numbers(min_value=1e-3, max_value=2.5e5))


        self.add_parameter('amplitude',
                           label='Amplitude',
                           get_cmd='OA.?',
                           get_parser=float,
                           set_cmd='OA. {:.6f}',
                           unit='V',
                           vals=Numbers(min_value=1e-6, max_value=5.000000))


        
        self.add_parameter('sync_filter',
                           label='Sync filter',
                           get_cmd='SYNC?',
                           set_cmd='SYNC {}',
                           val_mapping={
                               'off': 0,
                               'on': 1,
                           })    
        
        
        
        # Data transfer
        # All the parameters that are single-dual mode dependent are defined in _parameters_single_dual_mode()
        self.add_parameter('N',
                           label='Noise',
                           get_cmd='NHZ.?',
                           get_parser=self._check_float,
                           unit='V/sqrtHz')
        
        self.add_parameter('EN',
                           label='Equivalent Noise Bandwidth',
                           get_cmd='ENBW.?',
                           get_parser=self._check_float,
                           unit='Hz')
        
        self.add_parameter('NN',
                           label='Noise: Mean absolute value of Y channel',
                           get_cmd='NN.?',
                           get_parser=self._check_float,
                           unit='V')       
        

        # Aux input/output
        for i in [1, 2]:
            self.add_parameter('aux_in{}'.format(i),
                               label='Aux input {}'.format(i),
                               get_cmd='ADC. {}?'.format(i),
                               get_parser=self._check_float,
                               unit='V')
        # In SR7265 the ADC3 is an integrating converter and the input depends
        # on the ADC3TIME command
        self.add_parameter('ADC3_time',
                           label='ADC 3 Integrating converter sample time',
                           set_cmd='ADC3TIME {}',
                           set_parser=float,
                           initial_value=10,
                           vals=Numbers(min_value=10, max_value=2000),
                           unit='ms')
        
        def parser_auxin3(x):
            t = self.ADC3_time()
            voltage = int(x)/(t*1000*20)
            return voltage
        
        self.add_parameter('aux_in3',
                               label='Aux input 3',
                               get_cmd='ADC 3?', #fixed point mode only
                               get_parser=parser_auxin3,
                               unit='V')
         
            
        for i in [1, 2, 3, 4]:
            self.add_parameter('aux_out{}'.format(i),
                               label='Aux output {}'.format(i),
                               get_cmd='DAC. {}?'.format(i),
                               set_cmd='DAC {} {}'.format(i, ':.3f'),
                               get_parser=self._check_float,
                               unit='V')


        
        # Data buffer settings
        self.add_parameter('buffer_SR',
                           label='Buffer sample rate',
                           get_cmd='STR?',
                           set_cmd='STR {}',
                           unit='ms',
                           vals=Numbers(min_value=0, max_value=1000000),
                           get_parser=int
                           )

        #self.add_parameter('buffer_trig_mode',
                           #label='Buffer trigger start mode',
                           #get_cmd='TDT?',
                           #set_cmd='TDT {}',
                           #val_mapping={'OFF': 0, 'ON': 1},
                           #get_parser=int)

        self.add_parameter('buffer_npts',
                           label='Buffer number of stored points',
                           get_cmd='LEN ?',
                           set_cmd='LEN {}',
                           get_parser=int)

        # Auto functions
        self.add_function('ac_gain', call_cmd='ACGAIN {0}',
                          args=[Enum(0, 10, 20, 30, 40, 50, 60, 70, 80, 90)])
        self.add_function('auto_gain', call_cmd='AUTOMATIC {0}',
                          args=[Enum(0, 1)])
        self.add_function('auto_sensitivity', call_cmd='AS')
        self.add_function('auto_measure', call_cmd='ASM')
        self.add_function('auto_phase', call_cmd='AQN')
        self.add_function('auto_offset', call_cmd='AXO')

        # Interface
        self.add_function('reset', call_cmd='ADF 1')

        self.add_function('remote_on', call_cmd='REMOTE 1')
        self.add_function('remote_off', call_cmd='REMOTE 0')


        self.add_function('buffer_start', call_cmd='TD',
                          docstring=("The buffer_start command starts or "
                                     "resumes data storage. buffer_start"
                                     " is ignored if storage is already in"
                                     " progress. Acquisition will contunue"
                                     " until the buffer is full"))
        
        self.add_function('buffer_start_continuous', call_cmd='TDC',
                          docstring=("The buffer_start command starts or "
                                     "resumes data storage. buffer_start"
                                     " is ignored if storage is already in"
                                     " progress. Acquisition will contunue"
                                     " and when is full it will start overwriting"
                                     " previous values"))

        self.add_function('buffer_pause', call_cmd='HC',
                          docstring=("The buffer_pause command pauses data "
                                     "storage."))

        self.add_function('buffer_reset', call_cmd='NC',
                          docstring=("The buffer_reset command resets the data"
                                     " buffers. The buffer_reset command can "
                                     "be sent at any time - any storage in "
                                     "progress, paused or not, will be reset."
                                     " This command will erase the data "
                                     "buffer."))

        

        # Initialize the proper units of the outputs and sensitivities
        self.input_config()

        self.connect_message()
    
    
    def _set_ref_mode(self, x: int):
        snt = f'REFMODE {x}'
        print('Changing Reference mode...')
        self.write(snt)
        sleep(10)
        self.dualMode = False if self.refmode()=='Single Reference' else True
        print('Lockin in ', self.refmode())
        self._parameters_single_dual_mode()

    def increment_sensitivity(self):
        """
        Increment the sensitivity setting of the lock-in. This is equivalent
        to pushing the sensitivity up button on the front panel. This has no
        effect if the sensitivity is already at the maximum.

        Returns:
            Whether or not the sensitivity was actually changed.
        """
        return self._change_sensitivity(1)

    def decrement_sensitivity(self):
        """
        Decrement the sensitivity setting of the lock-in. This is equivalent
        to pushing the sensitivity down button on the front panel. This has no
        effect if the sensitivity is already at the minimum.

        Returns:
            Whether or not the sensitivity was actually changed.
        """
        return self._change_sensitivity(-1)

    def _change_sensitivity(self, dn):
        if self.input_config() in ['V']:
            n_to = self._N_TO_VOLT
            to_n = self._VOLT_TO_N
        else:
            n_to = self._N_TO_CURR
            to_n = self._CURR_TO_N

        n = to_n[self.sensitivity()]

        if n + dn > max(n_to.keys()) or n + dn < min(n_to.keys()):
            return False

        self.sensitivity.set(n_to[n + dn])
        return True


    def _set_units(self, unit):
        # TODO:
        # make a public parameter function that allows to change the units
        if self.dualMode==False:
            for param in [self.X, self.Y, self.R, self.sensitivity]:
                param.unit = unit
        else:
            for param in [self.X1,self.X2, self.Y1, self.Y2, self.R1, self.R2, self.sensitivity1, self.sensitivity2]:
                param.unit = unit

    def _get_input_config(self, s):
        mode = self._N_TO_INPUT_CONFIG[int(s)]

        if mode in ['V']:
            if self.dualMode==False:
                self.sensitivity.vals = self._VOLT_ENUM
            else:
                self.sensitivity1.vals = self._VOLT_ENUM
                self.sensitivity2.vals = self._VOLT_ENUM
            self._set_units('V')
        else:
            if self.dualMode==False:
                self.sensitivity.vals = self._CURR_ENUM
            else:
                self.sensitivity1.vals = self._CURR_ENUM
                self.sensitivity2.vals = self._CURR_ENUM
            self._set_units('A')

        return mode

    def _set_input_config(self, s):
        if s in ['V']:
            if self.dualMode==False:
                self.sensitivity.vals = self._VOLT_ENUM
            else:
                self.sensitivity1.vals = self._VOLT_ENUM
                self.sensitivity2.vals = self._VOLT_ENUM
            self._set_units('V')
        else:
            if self.dualMode==False:
                self.sensitivity.vals = self._VOLT_ENUM
            else:
                self.sensitivity1.vals = self._VOLT_ENUM
                self.sensitivity2.vals = self._VOLT_ENUM
            self._set_units('A')

        return self._INPUT_CONFIG_TO_N[s]
    

    def _get_sensitivity(self, s):
        if self.input_config() in ['V']:
            return self._N_TO_VOLT[int(s)]
        else:
            return self._N_TO_CURR[int(s)]

    def _set_sensitivity(self, s):
        if self.input_config() in ['V']:
            return self._VOLT_TO_N[s]
        else:
            return self._CURR_TO_N[s]

    def _check_float(self, x):
        try:
            float(x)
        except:
            return float(0)
        else:
            return float(x)

    def parse_offset_get(device,values):
        parts = values.split(',')
        return int(parts[0]), int(parts[1])
    
    def _parameters_single_dual_mode(self):
        list_single = ['X', 'Y', 'R', 'P', 'sensitivity', 'filter_slope', 'time_constant', 'X_offset', 'Y_offset','phase','harmonic']
        list_double = ['X1', 'Y1', 'R1', 'P1', 'sensitivity1', 'filter_slope1', 'time_constant1', 'X_offset1', 'Y_offset1', 
                           'X2', 'Y2', 'R2', 'P2', 'sensitivity2', 'filter_slope2', 'time_constant2', 'X_offset2', 'Y_offset2','phase1','phase2','harmonic1','harmonic2']
        # Clear all relevant parameters so there is no problem
        for i in list_double:    
            if i in self.parameters: del self.parameters[i]
        for i in list_single:    
            if i in self.parameters: del self.parameters[i]
        
        if self.dualMode==False:
            self.add_parameter('harmonic',
                           label='Harmonic',
                           get_cmd='REFN?',
                           get_parser=int,
                           set_cmd='REFN {:d}',
                           vals=Numbers(min_value=1, max_value=65535))

            self.add_parameter('phase',
                           label='Phase',
                           get_cmd='REFP.?',
                           get_parser=float,
                           set_cmd='REFP. {:.2f}',
                           unit='deg',
                           vals=Numbers(min_value=-360, max_value=360))
            self.add_parameter('X',
                           get_cmd='X.?',
                           get_parser=self._check_float,
                           unit='V')

            self.add_parameter('Y',
                           get_cmd='Y.?',
                           get_parser=self._check_float,
                           unit='V')

            self.add_parameter('R',
                           get_cmd='MAG.?',
                           get_parser=self._check_float,
                           unit='V')

            self.add_parameter('P',
                           get_cmd='PHA.?',
                           get_parser=self._check_float,
                           unit='deg')
        
            self.add_parameter(name='sensitivity',
                           label='Sensitivity',
                           get_cmd='SEN?',
                           set_cmd='SEN {:d}',
                           get_parser=self._get_sensitivity,
                           set_parser=self._set_sensitivity
                           )  
         
            # Gain and time constant
            self.add_parameter('filter_slope',
                           label='Filter slope',
                           get_cmd='SLOPE?',
                           set_cmd='SLOPE {}',
                           unit='dB/oct',
                           val_mapping={
                               6: 0,
                               12: 1,
                               18: 2,
                               24: 3,
                           })        
            
            self.add_parameter('time_constant',
                           label='Time constant',
                           get_cmd='TC?',
                           set_cmd='TC {}',
                           unit='s',
                           get_parser=lambda i: self._N_TO_TIMEC[int(i)],
                           set_parser=lambda i: self._TIMEC_TO_N[i],
                           vals=Enum(*self._TIMEC_TO_N.keys()) )
            
            self.add_parameter('X_offset',
                           get_cmd='XOF?',
                           get_parser=self.parse_offset_get)

            self.add_parameter('Y_offset',
                           get_cmd='YOF?',
                           get_parser=self.parse_offset_get)
            
        else:
            self.add_parameter('harmonic1',
                           label='Harmonic1',
                           get_cmd='REFN1?',
                           get_parser=int,
                           set_cmd='REFN1 {:d}',
                           vals=Numbers(min_value=1, max_value=65535))
            self.add_parameter('harmonic2',
                           label='Harmonic2',
                           get_cmd='REFN2?',
                           get_parser=int,
                           set_cmd='REFN2 {:d}',
                           vals=Numbers(min_value=1, max_value=65535))
            self.add_parameter('phase1',
                           label='Phase1',
                           get_cmd='REFP1.?',
                           get_parser=float,
                           set_cmd='REFP1. {:.2f}',
                           unit='deg',
                           vals=Numbers(min_value=-360, max_value=360))
            self.add_parameter('phase2',
                           label='Phase2',
                           get_cmd='REFP2.?',
                           get_parser=float,
                           set_cmd='REFP2. {:.2f}',
                           unit='deg',
                           vals=Numbers(min_value=-360, max_value=360))                
            self.add_parameter('X1',
                           get_cmd='X1.?',
                           get_parser=self._check_float,
                           unit='V')
            self.add_parameter('X2',
                           get_cmd='X2.?',
                           get_parser=self._check_float,
                           unit='V')
            
            self.add_parameter('Y1',
                           get_cmd='Y1.?',
                           get_parser=self._check_float,
                           unit='V')
            self.add_parameter('Y2',
                           get_cmd='Y2.?',
                           get_parser=self._check_float,
                           unit='V')

            self.add_parameter('R1',
                           get_cmd='MAG1.?',
                           get_parser=self._check_float,
                           unit='V')
            self.add_parameter('R2',
                           get_cmd='MAG2.?',
                           get_parser=self._check_float,
                           unit='V')

            self.add_parameter('P1',
                           get_cmd='PHA1.?',
                           get_parser=self._check_float,
                           unit='deg')
            self.add_parameter('P2',
                           get_cmd='PHA2.?',
                           get_parser=self._check_float,
                           unit='deg')
        
            self.add_parameter(name='sensitivity1',
                           label='Sensitivity',
                           get_cmd='SEN1?',
                           set_cmd='SEN1 {:d}',
                           get_parser=self._get_sensitivity,
                           set_parser=self._set_sensitivity
                           )
            self.add_parameter(name='sensitivity2',
                           label='Sensitivity',
                           get_cmd='SEN2?',
                           set_cmd='SEN2 {:d}',
                           get_parser=self._get_sensitivity,
                           set_parser=self._set_sensitivity
                           )
         
            # Gain and time constant
            self.add_parameter('filter_slope1',
                           label='Filter slope 1',
                           get_cmd='SLOPE1?',
                           set_cmd='SLOPE1 {}',
                           unit='dB/oct',
                           val_mapping={
                               6: 0,
                               12: 1,
                               18: 2,
                               24: 3,
                           })     
            self.add_parameter('filter_slope2',
                           label='Filter slope 2',
                           get_cmd='SLOPE2?',
                           set_cmd='SLOPE2 {}',
                           unit='dB/oct',
                           val_mapping={
                               6: 0,
                               12: 1,
                               18: 2,
                               24: 3,
                           })
            
            self.add_parameter('time_constant1',
                           label='Time constant 1',
                           get_cmd='TC1?',
                           set_cmd='TC1 {}',
                           unit='s',
                           get_parser=lambda i: self._N_TO_TIMEC[int(i)],
                           set_parser=lambda i: self._TIMEC_TO_N[i],
                           vals=Enum(*self._TIMEC_TO_N.keys()) )
                           
            self.add_parameter('time_constant2',
                           label='Time constant 2',
                           get_cmd='TC2?',
                           set_cmd='TC2 {}',
                           unit='s',
                           get_parser=lambda i: self._N_TO_TIMEC[int(i)],
                           set_parser=lambda i: self._TIMEC_TO_N[i],
                           vals=Enum(*self._TIMEC_TO_N.keys()) )
            

            self.add_parameter('X_offset1',
                           get_cmd='XOF1?',
                           get_parser=self.parse_offset_get)
            self.add_parameter('X_offset2',
                           get_cmd='XOF2?',
                           get_parser=self.parse_offset_get)

            self.add_parameter('Y_offset1',
                           get_cmd='YOF1?',
                           get_parser=self.parse_offset_get)
            self.add_parameter('Y_offset2',
                           get_cmd='YOF2?',
                           get_parser=self.parse_offset_get)
            
    def freq_sweep_XY(self, freq_start: float, freq_stop: float, freq_step: float):
        freq = np.arange(freq_start, freq_stop, freq_step)
        X = []
        Y = []
        for f in freq:
            self.frequency(f)
            t_wait = 4*self.time_constant()
            sleep(t_wait)
            X.append(self.X())
            Y.append(self.Y())
            
        return freq, X, Y

    def freq_sweep_noise(self, freq_start: float, freq_stop: float, freq_step: float):
        freq = np.arange(freq_start, freq_stop, freq_step)
        N = []
        
        self.auto_measure()
        sleep(2)
        self.auto_gain(1)
        sleep(2)
        self.auto_measure()
        sleep(2)
        self.auto_measure()
        sleep(10)
        
        self.time_constant(10e-3)
        t_wait = 10*self.time_constant()
        for f in freq:
            if f < 100:
                t = min(self._TIMEC_TO_N, key=lambda x: abs(x-1/f))
                self.time_constant(t)
                t_wait = 10*self.time_constant()
            
            self.frequency(f)
            sleep(t_wait)
            N.append(self.NN())
        
        self.auto_gain(0)
        self.ac_gain(0)
        return freq, N