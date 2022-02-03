from qcodes import VisaInstrument
from qcodes import Instrument
from qcodes import validators as vals
from qcodes.instrument.channel import InstrumentChannel


def ms2nplc(ms:float):
    """
    Convert ms to nplc for 50 Hz.
    """
    nplc = ms/20.0
    
    return nplc

def nplc2ms(nplc:str):
    """
    Convert nplc for 50 Hz to ms.
    """
    ms = float(nplc) * 20
    
    return ms

class B2901AChannel(InstrumentChannel):
    """

    """
    def __init__(self, parent: Instrument, name: str, chan: int) -> None:
        """
        Args:
            parent (Instrument): The instrument to which the channel is
            attached.
            name (str): The name of the channel
            channum (int): The number of the channel in question (1-2)
        """
        # Sanity Check inputs
        if name not in ['ch1']:
            raise ValueError("Invalid Channel: {}, expected 'ch1' or 'ch2'"
                             .format(name))
        if chan not in [1]:
            raise ValueError("Invalid Channel: {}, expected '1' or '2'"
                             .format(chan))

        super().__init__(parent, name)

        self.add_parameter('source_voltage',
                           label="Channel {} Voltage".format(chan),
                           get_cmd='SOURCE{:d}:VOLT?'.format(chan),
                           get_parser=float,
                           set_cmd='SOURCE{:d}:VOLT {{:.8G}}'.format(chan),
                           unit='V')

        self.add_parameter('source_current',
                           label="Channel {} Current".format(chan),
                           get_cmd='SOURCE{:d}:CURR?'.format(chan),
                           get_parser=float,
                           set_cmd='SOURCE{:d}:CURR {{:.8G}}'.format(chan),
                           unit='A')
        
        self.add_parameter('src_volt_range',
                           label = 'Channel {} Voltage range'.format(chan),
                           get_cmd = 'SOURCE{:d}:VOLT:RANGe?'.format(chan),
                           get_parser=float,
                           set_cmd='SOURCE{:d}:VOLT:RANGe {{:.8G}}'.format(chan),
                           unit='V',
                           val_mapping={1:0.2, 2:2, 3:20, 4:200})
        
        self.add_parameter('src_curr_range',
                           label = 'Channel {} Current range'.format(chan),
                           get_cmd = 'SOURCE{:d}:CURR:RANGe?'.format(chan),
                           get_parser=float,
                           set_cmd='SOURCE{:d}:CURR:RANGe {{:.8G}}'.format(chan),
                           unit='V',
                           val_mapping={1:10.0e-9, 2:100.0e-9, 3:1.0e-6, 4:10.0e-6,
                                        5:100.0e-6, 6:1.0e-3, 7: 10.0e-3, 8:100.0e-3,
                                        9:1.0, 10:1.5, 11:3, 12:10})
        
        self.add_parameter('volt_avg_time',
                           label='Channel {} voltage averaging time'.format(chan),
                           get_cmd = 'SENSe{:d}:VOLT:NPLC?'.format(chan),
                           get_parser = nplc2ms,
                           set_cmd = 'SENSe{:d}:VOLT:NPLC {{:.8G}}'.format(chan),
                           set_parser = ms2nplc,
                           unit='ms',
                           vals = vals.Numbers(8.0e-3, 2000)
                           )
        
        self.add_parameter('curr_avg_time',
                           label='Channel {} current averaging time'.format(chan),
                           get_cmd = 'SENSe{:d}:CURR:NPLC?'.format(chan),
                           get_parser = nplc2ms,
                           set_cmd = 'SENSe{:d}:CURR:NPLC {{:.8G}}'.format(chan),
                           set_parser = ms2nplc,
                           unit='ms',
                           vals = vals.Numbers(8.0e-3, 2000)
                           )

        self.add_parameter('voltage',
                           get_cmd='MEAS:VOLT? (@{:d})'.format(chan),
                           get_parser=float,
                           label='Channel {} Voltage'.format(chan),
                           unit='V')

        self.add_parameter('current',
                           get_cmd='MEAS:CURR? (@{:d})'.format(chan),
                           get_parser=float,
                           label='Channel {} Current'.format(chan),
                           unit='A')

        self.add_parameter('resistance',
                           get_cmd='MEAS:RES? (@{:d})'.format(chan),
                           get_parser=float,
                           label='Channel {} Resistance'.format(chan),
                           unit='ohm')

        self.add_parameter('voltage_limit',
                           get_cmd='SENS{:d}:VOLT:PROT?'.format(chan),
                           get_parser=float,
                           set_cmd='SENS{:d}:VOLT:PROT {{:.8G}}'.format(chan),
                           label='Channel {} Voltage Limit'.format(chan),
                           unit='V')

        self.add_parameter('current_limit',
                           get_cmd='SENS{:d}:CURR:PROT?'.format(chan),
                           get_parser=float,
                           set_cmd='SENS{:d}:CURR:PROT {{:.8G}}'.format(chan),
                           label='Channel {} Current Limit',
                           unit='A')

        self.add_parameter('enable',
                           get_cmd='OUTP{:d}?'.format(chan),
                           set_cmd='OUTP{:d} {{:d}}'.format(chan),
                           val_mapping={'on':  1, 'off': 0})

        self.add_parameter('source_mode',
                           get_cmd=':SOUR{:d}:FUNC:MODE?'.format(chan),
                           set_cmd=':SOUR{:d}:FUNC:MODE {{:s}}'.format(chan),
                           val_mapping={'current': 'CURR', 'voltage': 'VOLT'})

        self.channel = chan


class B2901A(VisaInstrument):
    """
    This is the qcodes driver for the Keysight B2901A.

    Status: alpha-version.
    TODO:
        - Implement any remaining parameters supported by the device
        - Similar drivers have special handlers to map return values of
          9.9e+37 to inf, is this needed?
    """
    def __init__(self, name, address, **kwargs):
        super().__init__(name, address, terminator='\n', **kwargs)

        # The B2962A supports two channels
        for ch_num in [1]:
            ch_name = "ch{:d}".format(ch_num)
            channel = B2901AChannel(self, ch_name, ch_num)
            self.add_submodule(ch_name, channel)

        self.connect_message()

    def get_idn(self):
        IDN = self.ask_raw('*IDN?')
        vendor, model, serial, firmware = map(str.strip, IDN.split(','))
        IDN = {'vendor': vendor, 'model': model,
               'serial': serial, 'firmware': firmware}
        return IDN
