from numpy import rad2deg, deg2rad
from qcodes import VisaInstrument, validators as vals


def parse_on_off(stat):
    if stat.startswith('0'):
        stat = 'Off'
    elif stat.startswith('1'):
        stat = 'On'
    return stat

def rad2deg_mod(rad):
    deg = rad2deg(float(rad))
    return deg

class Keysight_E8257D(VisaInstrument):
    """
    This is the qcodes driver for the Keysight_E8257D signal generator

    Status: beta-version.
        TODO:
        - Add all parameters that are in the manual

    This driver will most likely work for multiple Agilent sources.

    This driver does not contain all commands available for the E8527D but
    only the ones most commonly used.
    """

    def __init__(self, name:str, address:str, step_attenuator:bool=False,
                 pulse_option:bool=True, **kwargs):
        super().__init__(name, address, **kwargs)

        self.add_parameter(name='frequency',
                           label='Frequency',
                           unit='Hz',
                           get_cmd='FREQ:CW?',
                           set_cmd='FREQ:CW' + ' {:.8f}',
                           get_parser=float,
                           set_parser=float,
                           vals=vals.Numbers(2.5e5, 20e9))
        self.add_parameter(name='phase',
                           label='Phase',
                           unit='deg',
                           get_cmd='PHASE?',
                           set_cmd='PHASE' + ' {:.8f}',
                           get_parser=rad2deg_mod,
                           set_parser=deg2rad,
                           vals=vals.Numbers(-180, 180))
        self.add_parameter(name='power',
                           label='Power',
                           unit='dBm',
                           get_cmd='POW:AMPL?',
                           set_cmd='POW:AMPL' + ' {:.4f}',
                           get_parser=float,
                           set_parser=float,
                           vals=vals.Numbers(-130, 25))
        if pulse_option:
            self.add_parameter(name='pulse_delay',
                               label='Pulse_Delay',
                               unit='s',
                               get_cmd='PULM:INT:DEL?',
                               set_cmd='PULM:INT:DEL' + ' {:e}',
                               get_parser=float,
                               set_parser=float,
                               vals=vals.Numbers(-70e-9,42))
            self.add_parameter(name='pulse_period',
                               label='Pulse_period',
                               unit='s',
                               get_cmd='PULM:INT:PER?',
                               set_cmd='PULM:INT:PER' + ' {:e}',
                               get_parser=float,
                               set_parser=float,
                               vals=vals.Numbers(-70e-9, 42))
            self.add_parameter(name='pulse_width',
                               label='Pulse_width',
                               unit='s',
                               get_cmd='PULM:INT:PWID?',
                               set_cmd='PULM:INT:PWID' + ' {:e}',
                               get_parser=float,
                               set_parser=float,
                               vals=vals.Numbers(10e-9, 42))
            self.add_parameter('pulse_mod',
                               get_cmd='PULM:STAT?',
                               set_cmd='PULM:STAT' + ' {}',
                               get_parser=parse_on_off,
                               # Only listed most common spellings idealy want a
                               # .upper value for Enum or string
                               vals=vals.Enum('on', 'On', 'ON',
                                              'off', 'Off', 'OFF'))
            self.add_parameter('pulse_src',
                               get_cmd='PULM:SOUR?',
                               set_cmd='PULM:SOUR' + ' {}',
                               vals=vals.Enum('INT', 'EXT'))
            self.add_parameter('pulse_int_mode',
                               get_cmd='PULM:SOUR:INT?',
                               set_cmd='PULM:SOUR:INT' + ' {}',
                               vals=vals.Enum('FRUN', 'TRIG', 'GATE'))
            self.add_parameter('modulation',
                               get_cmd='OUTP:MOD?',
                               set_cmd='OUTP:MOD' + ' {}',
                               get_parser=parse_on_off,
                               # Only listed most common spellings idealy want a
                               # .upper value for Enum or string
                               vals=vals.Enum('on', 'On', 'ON',
                                              'off', 'Off', 'OFF'))
            
        self.add_parameter('status',
                           get_cmd='OUTP?',
                            set_cmd='OUTP' + ' {}',
                            get_parser=parse_on_off,
                            # Only listed most common spellings idealy want a
                            # .upper value for Enum or string
                            vals=vals.Enum('on', 'On', 'ON',
                                          'off', 'Off', 'OFF'))
        
        self.add_parameter('alc',
                            get_cmd='POW:ALC?',
                            set_cmd='POW:ALC' + ' {}',
                            get_parser=parse_on_off,
                            # Only listed most common spellings idealy want a
                            # .upper value for Enum or string
                            vals=vals.Enum('on', 'On', 'ON',
                                          'off', 'Off', 'OFF'))
        

        self.connect_message()

    def on(self):
        self.set('status', 'on')

    def off(self):
        self.set('status', 'off')
        
    def mod_on(self):
        self.set('modulation', 'on')
        
    def mod_off(self):
        self.set('modulation', 'off')
        
    def alc_on(self):
        self.set('alc', 'on')
        
    def alc_off(self):
        self.set('alc', 'off')
        
    def pulse_on(self):
        self.set('pulse_mod', 'on')
        
    def pulse_off(self):
        self.set('pulse_mod', 'off')
        
    def pulse_source_int(self):
        self.set('pulse_src', 'INT')
        
    def pulse_source_ext(self):
        self.set('pulse_src', 'EXT')
        
    def pulse_int_mode_frun(self):
        self.set('pulse_int_mode', 'FRUN')
        
    def pulse_int_mode_trig(self):
        self.set('pulse_int_mode', 'TRIG')
        
    def pulse_int_mode_gate(self):
        self.set('pulse_int_mode', 'GATE')
