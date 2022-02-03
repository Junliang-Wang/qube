# -*- coding: utf-8 -*-
"""
Created on Sat Jun  2 13:11:26 2018

@author: Shintaro Takada
""" 
import numpy as np
import logging
import h5py
import json

import time
from typing import List, Sequence, Union

from qcodes import Instrument, VisaInstrument, validators as vals
from qcodes.instrument.channel import InstrumentChannel, ChannelList
from qcodes.utils.validators import Validator

log = logging.getLogger(__name__)

# M8195 information
segment_max = 16777216
        

class AWGChannel(InstrumentChannel):
    """
    Class to hold a channel of the AWG
    """
    
    def __init__(self, parent:Instrument, name:str, channel:int, marker:bool, ext_mem:bool=False) -> None:
        """
        Args:
            parent: The Instrument instance to which the channel is
                to be attached.
            name: The name used in the DataSet
            channel: The channel number, 1 ~ 4.
            marker (bool): Whether it is marker or not.
            ext_mem (bool): Whether this channel extended memory or not.
        """
        
        super().__init__(parent, name)
        
        self.channel = channel
        self._mk = marker
        self._ext_mem = ext_mem
        
        self.model = self.root_instrument.model
        self.traceFileList = dict()
            
        self.add_parameter('state',
                           label='Channel {} state'.format(channel),
                           get_cmd=':OUTPut{}?'.format(channel),
                           set_cmd=':OUTPut{} {{}}'.format(channel),
                           vals = vals.Ints(0, 1),
                           get_parser = int)
        
        ############################################
        # AWG PARAMETERS
        
        amp_cmd = ':VOLTage{}'.format(channel)
        offset_cmd = 'VOLT{}:OFFS'.format(channel)
        chan_skew_cmd = 'ARM:SDEL{}'.format(channel)
        current_trace_cmd = 'TRACe{}:SELect'.format(channel)
        
        # Set channel first to ensure sensible sorting of pars
        
        self.add_parameter('amplitude',
                           label='Amplitude channel {}'.format(channel),
                           unit='Vpp',
                           get_cmd=amp_cmd + '?',
                           set_cmd=amp_cmd + ' {:.6f}',
                           vals=vals.Numbers(0.075, 1.0),
                           get_parser=float)
        self.add_parameter('offset',
                           label='Offset channel {}'.format(channel),
                           unit='V',
                           get_cmd=offset_cmd + '?',
                           set_cmd=offset_cmd + ' {:.6f}',
                           vals=vals.Numbers(-0.9625, 0.5375),
                           get_parser=float)
        self.add_parameter('channel_skew',
                           label='Channel skew of channel {}'.format(channel),
                           unit='sample clock periods',
                           get_cmd=chan_skew_cmd + '?',
                           set_cmd=chan_skew_cmd + ' {:d}',
                           vals=vals.Ints(0, 95),
                           get_parser=int)
        
        ##########################
        # Trace parameter
        
        self.add_parameter('current_trace',
                           label='Current trace channel {}'.format(channel),
                           get_cmd=current_trace_cmd + '?',
                           set_cmd=current_trace_cmd + ' {:d}',
                           vals=vals.Ints(1, segment_max),
                           get_parser=int)
        
        ##########################
        # Markers
        self.add_parameter('marker',
                           label='marker state channel {}'.format(channel),
                           get_cmd=':TRACe{}:MARK?'.format(channel),
                           set_cmd=':TRACe{}:MARK {{}}'.format(channel),
                           vals=vals.Ints(0,1),
                           get_parser=int)
            
    ################################
    # Functions related to trace
    
    @property
    def traceList(self):
        """
        Return the trace list as a list of strings
        {'segID':List[int], 'length':List[int]}
        """
        tlist = {}
        tliststr = self.root_instrument.ask(f'TRACe{self.channel}:CATalog?')
        tliststr = tliststr.split(',')
        tlist['segID'] = [int(n) for n in tliststr[::2]]
        tlist['length'] = [int(n) for n in tliststr[1::2]]
        
        return tlist       
    
    def clearTraceList(self):
        """
        Delete all traces defined.
        """
        self.root_instrument.write(f'TRACe{self.channel}:DELete:ALL')
        # Clear also the list
        self.traceFileList = dict()
        
    def deleteTrace(self, segID: int):
        """
        Delete the trace specified by the segment ID (int)
        
        Args:
            segID (int): Target segment IDT to be deleted.
        """
        # Check the validity of the values
        if segID < 1:
            raise ValueError('Segment ID has to be integer between 1 and 512k.')
        elif segID > segment_max:
            raise ValueError('Segment ID has to be integer between 1 and 512k.')
            
        self.root_instrument.write(f':TRACe{self.channel}:DELete {segID}')
        # Remove also from the list
        del self.traceFileList[segID]
        
    def defineTrace(self, segID: int, length: int):
        """
        Define trace of "length"(int) with "segment ID"(int).
        
        * Length of the segment has to be longer than 320.
            In addition, it has to be multiple of 64.
            
        Args:
            segID (int): Segment ID to be defined.
            length (int): Length of the trance
        """
        # Check the validity of the values
        if segID < 1:
            raise ValueError('Segment ID has to be integer between 1 and 512k.')
        elif segID > segment_max:
            raise ValueError('Segment ID has to be integer between 1 and 512k.')
            
        if length < 320:
            raise ValueError('Length of the segment has to be longer than 320.')
        
        if not (length % 64) == 0:
            raise ValueError('Length of the segment has to be multiple of 64.')
            
        self.root_instrument.write(f'TRACe{self.channel}:DEFine {segID},{length}')
        
    def setTraceAdvance(self, mode: str):
        """
        Set the advancement mode for the selected segment.
        
        Args:
            mode (str): Advanced mode of the trace.
        """
        # Check the validity of the values
        if not mode in ['AUTO', 'COND', 'REP', 'SING']:
            raise ValueError('Unknown mode is specified. Please check it again.')
            
        self.root_instrument.write(f'TRACe{self.channel}:ADVance {mode}')
        
    def setTraceCount(self, count: int):
        """
        Set the segment loop count for the selected segment.
        
        Args:
            count (int): Number of count of the segment loop.
        """
        # Check the validity of the values
        if count < 1:
            raise ValueError('Count has to be an integer between 1 and 4G-1.')
        elif count > 4e9-1:
            raise ValueError('Count has to be an integer between 1 and 4G-1.')
            
        self.root_instrument.write('TRACe{self.channel}:COUNt {count}')
        
    def sendTraceData(self, data: np.ndarray, segID: int, offset: int=0, opc: bool=True):
        """
        Send data presented by np.ndarray to the trace with "segID" at
        the position "offset".
        
        Args:
            data: A numpy array holding the data. Markers can be included.
            segID: Segment ID (int between 1 to 512k)
            offset: Position offset to insert the data
            opc (bool): Perform opc or not.
        """
        # Check the dimension of the data
        shape = np.shape(data)
        if len(shape) == 1:
            N = shape[0]
            M = 0
            wfm = data
            mk_state  = False
        elif len(shape) == 2:
            N = shape[1]
            M = shape[0]
            wfm = data[0, :]
            if M > 2:
                sample_marker = data[1, :]
                # Cast the data to be either 0 or 1.
                sample_marker = (np.round(sample_marker) % 2).astype(np.int8)
                sync_marker = data[2, :]
                # Cast the data to be either 0 or 1.
                sync_marker = (np.round(sync_marker) % 2).astype(np.int8)
                
                marker = sample_marker
                marker+= sync_marker << 1
                mk_state = True
            elif M > 1:
                sample_marker = data[1, :]
                # Cast the data to be either 0 or 1.
                sample_marker = (np.round(sample_marker) % 2).astype(np.int8)
                marker = sample_marker
                mk_state = True
        else:
            raise ValueError("Input data hs too many dimensions!")
            
        # Check existence of marker
        if self._mk:
            if not mk_state:
                raise ValueError('Please provide (3,N) dim array containing marker information.')
            
        # Check the size of the data
        if N*2 > 999999999:
            raise ValueError('Data size is too large !!')
        elif N < 320:
            raise ValueError('Data size is too small !!')
        elif (N % self.root_instrument._seg_granu) != 0:
            raise ValueError('Data size has to be multiple of {:d} !!'.format(self.root_instrument._seg_granu))
            
        # Cast wfm data to be below 1
        max_value = np.max(np.abs(wfm))
        if max_value > 1:
            wfm = wfm / max_value
            
        # Create data array
        ar = (127 * wfm).astype(np.int8)
        
        if M > 1:
            ar = np.column_stack((ar,marker))
            ar = ar.flatten()
        
        N = ar.size
            
        # Make command
        # N * 1 (8 bit integer is 1 byte, so we multiply 1)
        cmd = 'TRACe{:d}:DATA {:d},{:d},#{:d}{:d}'.format(self.channel, segID, offset, len(str(N*1)), N*1)
        cmd = cmd.encode()
        cmd+= ar.tobytes()
        
        self.root_instrument.visa_handle.write_raw(cmd)
        
        # OPC
        if opc:
            self.root_instrument.ask('*OPC?')
            
    ###########################################
    # Send data while making files to store the trace and the sequence data
    def loadTraceFile(self, fileName:str, folderPath: str=None):
        """
        Load trace data (Binary block format) and meta data from a trace file
        (.trc, HDF5).
        
        Args:
            fileName: name of the file
            folderPath: path to the folder containing the file
            
        Returns:
            dset: 1D array of data containing trace and marker information
            meta: Dictionary of the meta data of the trace
        """
        # Setup default folder path if it is None
        if folderPath == None:
            folderPath = self.root_instrument.awgFileFolder
        # Open file
        with h5py.File(folderPath+'\\'+fileName+'.trc', mode='r') as f:
            dset = f['trace']
            meta = dset.attrs['meta_data']
            meta = json.loads(meta)
            dset = np.array(dset[Ellipsis], dtype=np.int8)
        return dset, meta
    
    def sendTraceFromFile(self, fileName: str, folderPath: str = None, segID: int = None):
        """
        Load trace data from the file and send it to AWG.
        
        Args:
            fileName: Name of the trace file (without extension)
            folderPath: Path to the folder containing the trace file
            segID: Target segment ID. If it is None, generated automatically.
            
        Returns:
            segID: Segment ID used to send trace to AWG.
        """
        # Simply return segment ID if the trace has been already sent to the AWG
        if fileName in list(self.traceFileList.values()):
            return list(self.traceFileList.keys())[list(self.traceFileList.values()).index(fileName)]
        # Set default folder if not given.
        if folderPath == None:
            folderPath = self.root_instrument.awgFileFolder
        
        dset, meta = self.loadTraceFile(fileName, folderPath)
        advance = meta['advance']
        count = meta['count']
        offset = meta['offset']
        mk = meta['marker']
        
        N = dset.size
        
        # Segment size granurarity check
        if mk:
            factor = 2
        else:
            factor = 1
            
        if not ((N//factor) % self.root_instrument._seg_granu) == 0:
            raise ValueError('Loaded data size has to be multiple of {:d} !!'.format(self.root_instrument._seg_granu))
        
        # Check this channel has marker or not
        # When it has, we check the file has marker or not
        if self._mk:
            if not mk:
                raise ValueError('Channel{:d} has marker but loaded file does not.'.format(self.channel))
        
        tlist = self.traceList
        if self._ext_mem == False:
            segID = 1
            self.defineTrace(segID, N+offset)
        else:
            if segID == None:
                segID = max(tlist['segID'])+1
                self.defineTrace(segID, N+offset)
            else:
                if segID in tlist['segID']:
                    # self.deleteTrace(segID)
                    pass
                else:
                    self.defineTrace(segID, N+offset)
                    
        # self.defineTrace(segID, N+offset)
        
        cmd = 'TRACe{:d}:DATA {:d},{:d},#{:d}{:d}'.format(self.channel, segID, offset, len(str(N*1)), N*1)
        cmd = cmd.encode()
        cmd+= dset.tobytes()
        
        self.root_instrument.visa_handle.write_raw(cmd)
        self.root_instrument.ask('*OPC?')
        # Set modes
        self.current_trace(segID)
        if not advance == None:
            self.setTraceAdvance(advance)
        if not count == None:
            self.setTraceCount(count)
        
        # Set file name to trace file list
        self.traceFileList[segID] = fileName
        
        return segID

class Keysight_M8195A(VisaInstrument):
    """
    This is the QCoDes driver for the Keysight M8195A
    Arbitrary Waveform Generator.
    
    About Operation mode:
        This device has several different operation modes.
        
        All available choice:
            ['1-1-1','1-1-2','1-2-1','1-2-2','1-3-1','1-3-2','2-1','2-2','2-3',
            '3-1-1','3-1-2','3-2-1','3-2-2','3-2-3','3-2-4','3-3-1','3-3-2',
            '3-3-3','3-3-4','4','5-1','5-2-1','5-2-2','5-3-1','5-3-2','6-1-1',
            '6-1-2','6-2-1','6-2-2','6-2-3','6-2-4','6-3-1','6-3-2','6-3-3',
            '6-3-4','6-3-5','6-3-6','6-3-7','6-3-8','6-3-9','6-3-10','6-3-11',
            '6-3-12','6-3-13','6-3-14','6-3-15','6-3-16']
        
        1. Single channel (:INSTrument:DACMode SINGle)
            1. Sample rate divider: 1 (:INSTrument:MEMory:EXTended:RDIVider DIV1)
            (Waveform granurarity is 256 / sample clock range is 53.76e9 ~ 65.0e9)
                1. Ch1. Memory mode: internal
                2. Ch1. Memory mode: extended
            2. Sample rate divider: 2 (:INSTrument:MEMory:EXTended:RDIVider DIV2)
            (Waveform granurarity is 128 / sample clock range is 26.88e9 ~ 32.5e9)
                1. Ch1. Memory mode: internal
                2. Ch1. Memory mode: extended
            3. Sample rate divider: 4 (:INSTrument:MEMory:EXTended:RDIVider DIV4)
            (Waveform granurarity is 64 / sample clock range is 13.44e9/4.0 ~ 16.25e9)
                1. Ch1. Memory mode: internal
                2. Ch1. Memory mode: extended
        2. Single channel with markers
            - Memory is always 1: Extended, 2: None, 3: Extended, 4: Extended
            1. Sample rate divider: 1 (:INSTrument:MEMory:EXTended:RDIVider DIV1)
            2. Sample rate divider: 2 (:INSTrument:MEMory:EXTended:RDIVider DIV2)
            3. Sample rate divider: 4 (:INSTrument:MEMory:EXTended:RDIVider DIV4)
        3. Dual channel
            1. Sample rate divider: 1 (:INSTrument:MEMory:EXTended:RDIVider DIV1)
                - ch2, ch3 is always None (unused), ch4 automatically use internal memory.
                1. ch1. Memory internal
                2. ch1 memory extended
            2. Sample rate divider: 2 (:INSTrument:MEMory:EXTended:RDIVider DIV2)
                1. ch1, ch4 memory internal
                2. ch1 memory extended, ch4 memory internal
                3. ch1 memory internal, ch4 memory extended
                4. ch1 memory extended, ch4 memory extended
            3. Sample rate divider: 4 (:INSTrument:MEMory:EXTended:RDIVider DIV4)
                1. ch1, ch4 memory internal
                2. ch1 memory extended, ch4 memory internal
                3. ch1 memory internal, ch4 memory extended
                4. ch1 memory extended, ch4 memory extended
        4. Dual channel Duplicate
            - There is no choice about sample rate divider and memory.
            ch1, ch2: extended memory, ch3, ch4: None (unused), Sample rate divider is 2.
        5. Dual channel with markers
            - About memory: ch1, ch3, ch4 are always extended. When sample rate divider is
            more than 2, you can choose memory mode for ch2.
            1. Sample rate divider: 1 (:INSTrument:MEMory:EXTended:RDIVider DIV1)
            2. Sample rate divider: 2 (:INSTrument:MEMory:EXTended:RDIVider DIV2)
                1. ch2. Memory internal
                2. ch2 memory extended
            3. Sample rate divider: 4 (:INSTrument:MEMory:EXTended:RDIVider DIV4)
                1. ch2. Memory internal
                2. ch2 memory extended
        6. Four channel
            1. Sample rate divider: 1 (:INSTrument:MEMory:EXTended:RDIVider DIV1)
                1. ch1 memory internal, ch2, ch3, ch4 memory internal
                2. ch1 memory extended, ch2, ch3, ch4 memory internal
            2. Sample rate divider: 2 (:INSTrument:MEMory:EXTended:RDIVider DIV2)
                1. ch1, ch2 memory internal, ch3, ch4 memory internal
                2. ch1 extended, ch2 internal, ch3, ch4 internal
                3. ch1 internal, ch2 exended, ch3, ch4 internal
                4. ch1, ch2 extended, ch3, ch4 internal
            3. Sample rate divider: 4 (:INSTrument:MEMory:EXTended:RDIVider DIV4)
                internal: 0, extended: 1
                Avaiable number N is
                N = ch1 + 2*ch2 + 4*ch3 + 8*ch4 + 1 (1 ~ 16)
                
    About trigger mode:
        
        :INITiate:CONTinuous[:STATe][?] OFF|ON|0|1
        
        ON --> Continuous mode
        
        OFF --> :INITiate:GATE[:STATe][?] OFF|ON|0|1
                ON --> Gated
                OFF --> Triggered
                
        For details, please see 3.8 Sequencer Modes in the manual.
        
    About arm mode:
        
        We can choose either 'Armed' or 'self Armed'. This parameter is useful only when you are in sequence/senario
        mode and trigger mode is 'continuous'. In this case, after run the AWG, it repeats first segment until
        enable event is received. This function can be used when you would like to output specific waveform during the
        idle time.
    
    """
    
    def __init__(self, name: str, address: str, timeout: float=180.0,
                 op_mode: str='6-1-2', awgFileFolder:str='', reset = True,
                 **kwargs) -> None:
        """
        Initializes the Keysight M8195A
        
        Args:
            name (string): name of the instrument
            address (string): GPIB or ethernet address as used by VISA (practically 'TCPIP::localhost::hislip0::INSTR')
            timeout (float): visa timeout, in secs. long default (180)
                to accommodate large waveforms
            op_mode (str): Instrument operation mode. [SINGle, DUAL, FOUR, MARKer, DCDuplicate, DCMarker]
            awgFileFolder (str): Path to the directory (Folder), where generated AWG file will be stored.
            
        Returns:
            None
        """
        super().__init__(name, address, timeout=timeout, terminator='\n',
                         **kwargs)
        
        # Parameters
        self.available_mode = ['1-1-1','1-1-2','1-2-1','1-2-2','1-3-1','1-3-2','2-1','2-2','2-3',
            '3-1-1','3-1-2','3-2-1','3-2-2','3-2-3','3-2-4','3-3-1','3-3-2',
            '3-3-3','3-3-4','4','5-1','5-2-1','5-2-2','5-3-1','5-3-2','6-1-1',
            '6-1-2','6-2-1','6-2-2','6-2-3','6-2-4','6-3-1','6-3-2','6-3-3',
            '6-3-4','6-3-5','6-3-6','6-3-7','6-3-8','6-3-9','6-3-10','6-3-11',
            '6-3-12','6-3-13','6-3-14','6-3-15','6-3-16']
        self._op_mode = op_mode
        self._seg_granu = 256
        self._sample_frec_lim = (53.76e9, 65.0e9)
        self.awgFileFolder = awgFileFolder          # Folder, where waveform and sequence file will be saved.
        self.sequenceFileList = dict()
        
        # Basic functions
        self.add_function('reset', call_cmd='*RST')
        
        # Get the model value
        self.model = self.IDN()['model']
        
        if self.model not in ['M8195A']:
            raise ValueError('Unkown model type: {}. Are you using '
                             'the right driver for your instrument?'
                             ''.format(self.model))
            
        self.add_parameter('current_directory',
                           label='Current file system directory',
                           set_cmd=':MMEMory:CDIRectory "{}"',
                           get_cmd=':MMEMory:CDIRectory?',
                           vals=vals.Strings())
        
        ##########################################################
        # Clock parameters
        
        self.add_parameter('sample_rate',
                           label='Clock sample rate',
                           unit='Sa/s',
                           get_cmd=':FREQ:RAST?',
                           set_cmd=':FREQ:RAST' + ' {}',
                           vals=vals.Numbers(*self._sample_frec_lim),
                           get_parser=float)
        
        self.add_parameter('clock_source',
                           label='Clock source',
                           get_cmd=':ROSC:SOUR?',
                           set_cmd=':ROSC:SOUR' + ' {}',
                           val_mapping={'internal':'INT',
                                         'external':'EXT',
                                         'auxiliary':'AXI'})
        
        self.add_parameter('clock_external_frequency',
                           unit='Hz',
                           label='External clock frequency',
                           get_cmd=':ROSC:FREQ?',
                           set_cmd=self.set_ref_clk_freq,
                           vals=vals.Numbers(1.0e7,1.7e10),
                           get_parser=float)
        
        #########################################################
        # Operation mode
        
        self.add_parameter('op_mode',
                           label='Operation mode',
                           set_cmd=self.set_op_mode,
                           get_cmd=self.get_op_mode,
                           vals=vals.Enum(*self.available_mode)
                           )
        
        ###############################################
        # Fcunction mode for external memory channel(s)
        
        self.add_parameter('func_mode',
                           label='Function mode channel',
                           get_cmd='FUNCtion:MODE?',
                           set_cmd='FUNCtion:MODE {}',
                           val_mapping={'ARBitrary':'ARB', 'STSequence':'STS', 'STSCenario':'STSC'})
        
        #####################################
        # Delay (skew) control
        
        self.add_parameter('modu_delay',
                           label='Module delay',
                           get_cmd=':ARM:MDEL?',
                           set_cmd=':ARM:MDEL {:.3f}',
                           vals=vals.Numbers(0.0, 1.0e-8),
                           get_parser=float)
        
        ####################################
        # Trigger parameters
        
        self.add_parameter('continuous',
                           label='Continuous mode',
                           get_cmd=':INITiate:CONTinuous:STATe?',
                           set_cmd=':INITiate:CONTinuous:STATe {}',
                           val_mapping={'on':1,
                                        'off':0},
                           )
        
        self.add_parameter('gate',
                           label='Gate mode',
                           get_cmd=':INITiate:GATE:STATe?',
                           set_cmd=':INITiate:GATE:STATe {}',
                           val_mapping={'on':1,
                                        'off':0},
                           )
        
        self.add_parameter('arm',
                           label='Arm mode',
                           get_cmd=':INIT:CONT:ENAB?',
                           set_cmd=':INIT:CONT:ENAB {}',
                           val_mapping={'self':'SELF',
                                        'armed':'ARM'},
                           )
        
        self.add_parameter('trigger_level',
                           unit='V',
                           label='Trigger level',
                           get_cmd=':ARM:TRIG:LEV?',
                           set_cmd=':ARM:TRIG:LEV' + ' {:.3f}',
                           vals=vals.Numbers(-4.0, 4.0),
                           get_parser=float)
        
        self.add_parameter('trigger_slope',
                           label = 'Trigger slope',
                           get_cmd=':ARM:TRIG:SLOP?',
                           set_cmd=':ARM:TRIG:SLOP' + ' {}',
                           val_mapping={'Positive':'POS',
                                        'Negative':'NEG',
                                        'Either':'EITH'},
                           )
        
        self.add_parameter('trigger_source',
                           label = 'Trigger input source',
                           get_cmd=':ARM:TRIGger:SOURce?',
                           set_cmd=':ARM:TRIGger:SOURce {}',
                           val_mapping={'trigger':'TRIG',
                                        'event':'EVEN',
                                        'internal':'INT'},
                           )
        
        self.add_parameter('trigger_sync_mode',
                           label='Trigger operation mode',
                           get_cmd=':ARM:TRIGger:OPERation?',
                           set_cmd=':ARM:TRIGger:OPERation {}',
                           val_mapping={'sync':'SYNC',
                                        'async':'ASYN'},
                           )
        
        self.add_parameter('event_level',
                           unit='V',
                           label='Event level',
                           get_cmd=':ARM:EVEN:LEV?',
                           set_cmd=':ARM:EVEN:LEV' + ' {:.3f}',
                           vals=vals.Numbers(-4.0, 4.0),
                           get_parser=float)
        
        self.add_parameter('event_slope',
                           label='Event slope',
                           get_cmd=':ARM:EVEN:SLOP?',
                           set_cmd=':ARM:EVEN:SLOP' + ' {}',
                           val_mapping={'Positive':'POS',
                                        'Negative':'NEG',
                                        'Either':'EITH'},
                           )
        
        self.add_parameter('event_source',
                           label='Event input source',
                           get_cmd=':TRIGger:SOURce:ENABle?',
                           set_cmd=':TRIGger:SOURce:ENABle {}',
                           val_mapping={'trigger':'TRIG',
                                        'event':'EVEN'},
                           )
        
        self.add_parameter('advance_source',
                           label='Advancement event input source',
                           get_cmd=':TRIGger:SOURce:ADVance?',
                           set_cmd=':TRIGger:SOURce:ADVance {}',
                           val_mapping={'trigger':'TRIG',
                                        'event':'EVEN',
                                        'internal':'INT'},
                           )
        ###########################
        # Dynamic mode
        self.add_parameter('dynamic',
                           label = 'Dynamic mode',
                           get_cmd = ':STABle:DYNamic?',
                           set_cmd = ':STABle:DYNamic {}',
                           vals = vals.Enum(0,1,'OFF','ON'))
        
        self.add_parameter('dynamic_selec',
                           label = 'Dynamic Selection',
                           set_cmd = ':STABle:DYNamic:SELect {}')
        
        ##########################
        # Sequence parameter
        self.add_parameter('current_sequence',
                           label='Current sequence',
                           get_cmd=':STABle:SEQuence:SELect?',
                           set_cmd=':STABle:SEQuence:SELect {}',
                           vals=vals.Ints(0, segment_max-2),
                           get_parser=int,
                           set_parser=int,)
        
        # Reset instrument if required.
        if reset:
            self.reset()
        # Set up channels
        self.setup_channels()
        
        # Set up operation mode
        self.set_op_mode(op_mode)
        
        self.current_directory(self.awgFileFolder)
            
        self.connect_message()
        
    # Functions
    def start(self):
        """Convenience function, identical to self.run()"""
        return self.run()
    
    def run(self):
        """
        This command initiates the output of a waveform or a sequence.
        This is equivalent to pressing Run/Stop button on the front panel.
        The instrument can be put in the run state only when output waveforms
        are assigned to channels.
        """
        self.write('INIT:IMM')
        
    def stop(self):
        """This command stops the output of a waveform or a sequence."""
        self.write('ABOR')
        
    def setup_channels(self):
        """
        This function setup AWG channels during initialisation.
        """
        
        for i in range(4):
            chan = AWGChannel(parent=self, name='ch{:d}'.format(i+1), channel=i+1,
                              marker=False, ext_mem = False)
            self.add_submodule('ch{:d}'.format(i+1), chan)
                
        
    def set_op_mode(self, mode):
        """
        This function set the operation mode including DAC mode, Sample rate divide, Memory distribution.
        In total we have 47 possibilities about the operation mode.
        
        Default mode is '6-1-2', four channel, sample rate divide = 1, ch1 extended memory.
        """
        mode = [int(i) for i in mode.split('-')]
        # initialise external memory indicator to be False
        self.ch1._ext_mem = False
        self.ch2._ext_mem = False
        self.ch3._ext_mem = False
        self.ch4._ext_mem = False
        # Initialize marker state (marker will be associated only channel 1.)
        self.ch1._mk = False
        
        if mode[0] == 1:
            # Set mode
            self.write(':INSTrument:DACMode SINGle')
            # Set marker condition
            self.ch3.marker(0)
            self.ch4.marker(0)
            
            # Set sample rate divide
            if mode[1] == 1:
                self.write(':INSTrument:MEMory:EXTended:RDIVider DIV1')
                self._seg_granu = 256
                # self._sample_frec_lim=(53.76e9, 65.0e9)
                # self.sample_rate.vals = vals.Numbers(*self._sample_frec_lim)
                
                # Set memory mode
                if mode[2]  == 1:
                    self.write(':TRACe1:MMODe INTernal')
                elif mode[2] == 2:
                    self.write(':TRACe1:MMODe EXTended')
                    self.ch1._ext_mem = True
            elif mode[1] == 2:
                self.write(':INSTrument:MEMory:EXTended:RDIVider DIV2')
                self._seg_granu = 128
                # self._sample_frec_lim=(26.88e9, 32.5e9)
                # self.sample_rate.vals = vals.Numbers(*self._sample_frec_lim)
                if mode[2]  == 1:
                    self.write(':TRACe1:MMODe INTernal')
                elif mode[2] == 2:
                    self.write(':TRACe1:MMODe EXTended')
                    self.ch1._ext_mem = True
            elif mode[1] == 3:
                self.write(':INSTrument:MEMory:EXTended:RDIVider DIV4')
                self._seg_granu = 64
                # self._sample_frec_lim=(13.44e9, 16.25e9)
                # self.sample_rate.vals = vals.Numbers(*self._sample_frec_lim)
                if mode[2]  == 1:
                    self.write(':TRACe1:MMODe INTernal')
                elif mode[2] == 2:
                    self.write(':TRACe1:MMODe EXTended')
                    self.ch1._ext_mem = True
        elif mode[0] == 2:
            # Set mode
            self.write(':INSTrument:DACMode MARKer')
            # Set marker conditions
            self.ch1._mk = True
            self.ch3.marker(1)
            self.ch4.marker(1)
            if mode[1] == 1:
                self.write(':INSTrument:MEMory:EXTended:RDIVider DIV1')
                self._seg_granu = 256
                # self._sample_frec_lim=(53.76e9, 65.0e9)
                # self.sample_rate.vals = vals.Numbers(*self._sample_frec_lim)
            elif mode[1] == 2:
                self.write(':INSTrument:MEMory:EXTended:RDIVider DIV2')
                self._seg_granu = 128
                # self._sample_frec_lim=(26.88e9, 32.5e9)
                # self.sample_rate.vals = vals.Numbers(*self._sample_frec_lim)
            elif mode[1] == 3:
                self.write(':INSTrument:MEMory:EXTended:RDIVider DIV4')
                self._seg_granu = 64
                # self._sample_frec_lim=(13.44e9, 16.25e9)
                # self.sample_rate.vals = vals.Numbers(*self._sample_frec_lim)
        elif mode[0] == 3:
            # Set mode
            self.write(':INSTrument:DACMode DUAL')
            # Set marker condition
            self.ch3.marker(0)
            self.ch4.marker(0)
            if mode[1] == 1:
                self.write(':INSTrument:MEMory:EXTended:RDIVider DIV1')
                self._seg_granu = 256
                # self._sample_frec_lim=(53.76e9, 65.0e9)
                # self.sample_rate.vals = vals.Numbers(*self._sample_frec_lim)
                if mode[2]  == 1:
                    self.write(':TRACe1:MMODe INTernal')
                elif mode[2] == 2:
                    self.write(':TRACe1:MMODe EXTended')
                    self.ch1._ext_mem = True
            elif mode[1] == 2:
                self.write(':INSTrument:MEMory:EXTended:RDIVider DIV2')
                self._seg_granu = 128
                # self._sample_frec_lim=(26.88e9, 32.5e9)
                # self.sample_rate.vals = vals.Numbers(*self._sample_frec_lim)
                if mode[2]  == 1:
                    self.write(':TRACe1:MMODe INTernal')
                    self.write(':TRACe4:MMODe INTernal')
                elif mode[2] == 2:
                    self.write(':TRACe1:MMODe EXTended')
                    self.ch1._ext_mem = True
                    self.write(':TRACe4:MMODe INTernal')
                elif mode[2] == 3:
                    self.write(':TRACe1:MMODe INTernal')
                    self.write(':TRACe4:MMODe EXTended')
                    self.ch4._ext_mem = True
                elif mode[2] == 4:
                    self.write(':TRACe1:MMODe EXTended')
                    self.ch1._ext_mem = True
                    self.write(':TRACe4:MMODe EXTended')
                    self.ch4._ext_mem = True
            elif mode[1] == 3:
                self.write(':INSTrument:MEMory:EXTended:RDIVider DIV4')
                self._seg_granu = 64
                # self._sample_frec_lim=(13.44e9, 16.25e9)
                # self.sample_rate.vals = vals.Numbers(*self._sample_frec_lim)
                if mode[2]  == 1:
                    self.write(':TRACe1:MMODe INTernal')
                    self.write(':TRACe4:MMODe INTernal')
                    self.ch4._ext_mem = True
                elif mode[2] == 2:
                    self.write(':TRACe1:MMODe EXTended')
                    self.ch1._ext_mem = True
                    self.write(':TRACe4:MMODe INTernal')
                elif mode[2] == 3:
                    self.write(':TRACe1:MMODe INTernal')
                    self.write(':TRACe4:MMODe EXTended')
                    self.ch4._ext_mem = True
                elif mode[2] == 4:
                    self.write(':TRACe1:MMODe EXTended')
                    self.ch1._ext_mem = True
                    self.write(':TRACe4:MMODe EXTended')
                    self.ch4._ext_mem = True
        elif mode[0] == 4:
            # Set mode
            self.write(':INSTrument:DACMode DCDuplicate')
            # Set marker condition
            self.ch3.marker(0)
            self.ch4.marker(0)
        elif mode[0] == 5:
            # Set mode
            self.write(':INSTrument:DACMode DCMarker')
            # Set marker condition
            self.ch1._mk = True
            self.ch3.marker(1)
            self.ch4.marker(1)
            if mode[1] == 1:
                self.write(':INSTrument:MEMory:EXTended:RDIVider DIV1')
                self._seg_granu = 256
                # self._sample_frec_lim=(53.76e9, 65.0e9)
                # self.sample_rate.vals = vals.Numbers(*self._sample_frec_lim)
            elif mode[1] == 2:
                self.write(':INSTrument:MEMory:EXTended:RDIVider DIV2')
                self._seg_granu = 128
                # self._sample_frec_lim=(26.88e9, 32.5e9)
                # self.sample_rate.vals = vals.Numbers(*self._sample_frec_lim)
                if mode[2]  == 1:
                    self.write(':TRACe2:MMODe INTernal')
                elif mode[2] == 2:
                    self.write(':TRACe2:MMODe EXTended')
                    self.ch2._ext_mem = True
            elif mode[1] == 3:
                self.write(':INSTrument:MEMory:EXTended:RDIVider DIV4')
                self._seg_granu = 64
                # self._sample_frec_lim=(13.44e9, 16.25e9)
                # self.sample_rate.vals = vals.Numbers(*self._sample_frec_lim)
                if mode[2]  == 1:
                    self.write(':TRACe2:MMODe INTernal')
                elif mode[2] == 2:
                    self.write(':TRACe2:MMODe EXTended')
                    self.ch2._ext_mem = True
        elif mode[0] == 6:
            # Set mode
            self.write(':INSTrument:DACMode FOUR')
            # Set marker condition
            self.ch3.marker(0)
            self.ch4.marker(0)
            if mode[1] == 1:
                self.write(':INSTrument:MEMory:EXTended:RDIVider DIV1')
                self._seg_granu = 256
                # self._sample_frec_lim=(53.76e9, 65.0e9)
                # self.sample_rate.vals = vals.Numbers(*self._sample_frec_lim)
                if mode[2]  == 1:
                    self.write(':TRACe1:MMODe INTernal')
                elif mode[2] == 2:
                    self.write(':TRACe1:MMODe EXTended')
                    self.ch1._ext_mem = True
            elif mode[1] == 2:
                self.write(':INSTrument:MEMory:EXTended:RDIVider DIV2')
                self._seg_granu = 128
                # self._sample_frec_lim=(26.88e9, 32.5e9)
                # self.sample_rate.vals = vals.Numbers(*self._sample_frec_lim)
                if mode[2]  == 1:
                    self.write(':TRACe1:MMODe INTernal')
                    self.write(':TRACe2:MMODe INTernal')
                elif mode[2] == 2:
                    self.write(':TRACe1:MMODe EXTended')
                    self.ch1._ext_mem = True
                    self.write(':TRACe2:MMODe INTernal')
                elif mode[2] == 3:
                    self.write(':TRACe1:MMODe INTernal')
                    self.write(':TRACe2:MMODe EXTended')
                    self.ch2._ext_mem = True
                elif mode[2] == 4:
                    self.write(':TRACe1:MMODe EXTended')
                    self.ch1._ext_mem = True
                    self.write(':TRACe2:MMODe EXTended')
                    self.ch2._ext_mem = True
            elif mode[1] == 3:
                self.write(':INSTrument:MEMory:EXTended:RDIVider DIV4')
                self._seg_granu = 64
                # self._sample_frec_lim=(13.44e9, 16.25e9)
                # self.sample_rate.vals = vals.Numbers(*self._sample_frec_lim)
                if mode[2] == 1:
                    self.write(':TRACe1:MMODe INTernal')
                    self.write(':TRACe2:MMODe INTernal')
                    self.write(':TRACe3:MMODe INTernal')
                    self.write(':TRACe4:MMODe INTernal')
                elif mode[2] == 2:
                    self.write(':TRACe1:MMODe EXTended')
                    self.ch1._ext_mem = True
                    self.write(':TRACe2:MMODe INTernal')
                    self.write(':TRACe3:MMODe INTernal')
                    self.write(':TRACe4:MMODe INTernal')
                elif mode[2] == 3:
                    self.write(':TRACe1:MMODe INTernal')
                    self.write(':TRACe2:MMODe EXTended')
                    self.ch2._ext_mem = True
                    self.write(':TRACe3:MMODe INTernal')
                    self.write(':TRACe4:MMODe INTernal')
                elif mode[2] == 4:
                    self.write(':TRACe1:MMODe EXTended')
                    self.ch1._ext_mem = True
                    self.write(':TRACe2:MMODe EXTended')
                    self.ch2._ext_mem = True
                    self.write(':TRACe3:MMODe INTernal')
                    self.write(':TRACe4:MMODe INTernal')
                elif mode[2] == 5:
                    self.write(':TRACe1:MMODe INTernal')
                    self.write(':TRACe2:MMODe INTernal')
                    self.write(':TRACe3:MMODe EXTended')
                    self.ch3._ext_mem = True
                    self.write(':TRACe4:MMODe INTernal')
                elif mode[2] == 6:
                    self.write(':TRACe1:MMODe EXTended')
                    self.ch1._ext_mem = True
                    self.write(':TRACe2:MMODe INTernal')
                    self.write(':TRACe3:MMODe EXTended')
                    self.ch3._ext_mem = True
                    self.write(':TRACe4:MMODe INTernal')
                elif mode[2] == 7:
                    self.write(':TRACe1:MMODe INTernal')
                    self.write(':TRACe2:MMODe EXTended')
                    self.ch2._ext_mem = True
                    self.write(':TRACe3:MMODe EXTended')
                    self.ch3._ext_mem = True
                    self.write(':TRACe4:MMODe INTernal')
                elif mode[2] == 8:
                    self.write(':TRACe1:MMODe EXTended')
                    self.ch1._ext_mem = True
                    self.write(':TRACe2:MMODe EXTended')
                    self.ch2._ext_mem = True
                    self.write(':TRACe3:MMODe EXTended')
                    self.ch3._ext_mem = True
                    self.write(':TRACe4:MMODe INTernal')
                elif mode[2] == 9:
                    self.write(':TRACe1:MMODe INTernal')
                    self.write(':TRACe2:MMODe INTernal')
                    self.write(':TRACe3:MMODe INTernal')
                    self.write(':TRACe4:MMODe EXTended')
                    self.ch4._ext_mem = True
                elif mode[2] == 10:
                    self.write(':TRACe1:MMODe EXTended')
                    self.ch1._ext_mem = True
                    self.write(':TRACe2:MMODe INTernal')
                    self.write(':TRACe3:MMODe INTernal')
                    self.write(':TRACe4:MMODe EXTended')
                    self.ch4._ext_mem = True
                elif mode[2] == 11:
                    self.write(':TRACe1:MMODe INTernal')
                    self.write(':TRACe2:MMODe EXTended')
                    self.ch2._ext_mem = True
                    self.write(':TRACe3:MMODe INTernal')
                    self.write(':TRACe4:MMODe EXTended')
                    self.ch4._ext_mem = True
                elif mode[2] == 12:
                    self.write(':TRACe1:MMODe EXTended')
                    self.ch1._ext_mem = True
                    self.write(':TRACe2:MMODe EXTended')
                    self.ch2._ext_mem = True
                    self.write(':TRACe3:MMODe INTernal')
                    self.write(':TRACe4:MMODe EXTended')
                    self.ch4._ext_mem = True
                elif mode[2] == 13:
                    self.write(':TRACe1:MMODe INTernal')
                    self.write(':TRACe2:MMODe INTernal')
                    self.write(':TRACe3:MMODe EXTended')
                    self.ch3._ext_mem = True
                    self.write(':TRACe4:MMODe EXTended')
                    self.ch4._ext_mem = True
                elif mode[2] == 14:
                    self.write(':TRACe1:MMODe EXTended')
                    self.ch1._ext_mem = True
                    self.write(':TRACe2:MMODe INTernal')
                    self.write(':TRACe3:MMODe EXTended')
                    self.ch3._ext_mem = True
                    self.write(':TRACe4:MMODe EXTended')
                    self.ch4._ext_mem = True
                elif mode[2] == 15:
                    self.write(':TRACe1:MMODe INTernal')
                    self.write(':TRACe2:MMODe EXTended')
                    self.ch2._ext_mem = True
                    self.write(':TRACe3:MMODe EXTended')
                    self.ch3._ext_mem = True
                    self.write(':TRACe4:MMODe EXTended')
                    self.ch4._ext_mem = True
                elif mode[2] == 16:
                    self.write(':TRACe1:MMODe EXTended')
                    self.ch1._ext_mem = True
                    self.write(':TRACe2:MMODe EXTended')
                    self.ch2._ext_mem = True
                    self.write(':TRACe3:MMODe EXTended')
                    self.ch3._ext_mem = True
                    self.write(':TRACe4:MMODe EXTended')
                    self.ch4._ext_mem = True
            
        self._op_mode = mode
    
    def get_op_mode(self):            
        return self._op_mode
        
    def set_ref_clk_freq(self, f):
        """
        Set refrence clock frequency, if the external reference clock source is selected.
        """
        if f < 2.5e8:
            self.write(':ROSC:RANG RANG1')
            self.write(':ROSC:FREQ {:.3f}'.format(f))
        else:
            self.write(':ROSC:RANG RANG2')
            self.write(':ROSC:FREQ {:.3f}'.format(f))
        
    def send_begin_trigger(self):
        """
        This command generates a start event.
        """
        self.write('TRIGger:BEGin')
        
    def send_enable_event(self):
        """
        Send the enable event
        """
        self.write('TRIG:ENAB')
        
    def send_gate_open_event(self, state = 1):
        """
        Send the "gate open" (ON:1) or "gate close" (OFF:0)
        """
        self.write('TRIG:BEG:GATE' + ' {:d}'.format(state))
        
    def send_advance_event(self):
        """
        Send the advancement event
        """
        self.write('TRIG:ADV')
        
    ############################
    # Functions to create and load trace as well as sequence files
    def makeTraceFile(self, 
                      data: np.ndarray,
                      amplitude: float = 1.0,
                      advance: str = None,
                      count: int = None,
                      offset: int = 0,
                      comments: str = None,
                      fileName: str = None,
                      folderPath: str = None
                      )-> str:
        """
        This function creates a trace file (.trc [HDF5]) to store the trace
        data and meta data (advance, count, offset, comments).
        We can send the trace to AWG using this file.
        
        Args:
            data: (N, M) dimension array
                N: 0 - 2 depending on marker data
                M: size of the trace
            amplitude: relative amplitude to the channel amplitude 0.0 - 1.0
            advance: advance mode of the trace (AUTO, CONDitional, REPeat, SINGle)
            count: No of repetition of the trace
            offset: Where in the trace the data is to be inserted.
            comments: Some comments about the trace
            
        Returns:
            fileName (str): Name of the created trace file
        """
         # Check the dimension of the data
        shape = np.shape(data)
        if len(shape) == 1:
            N = shape[0]
            M = 0
            wfm = data
            mk_state = False
        elif len(shape) == 2:
            N = shape[1]
            M = shape[0]
            wfm = data[0, :]
            if M > 2:
                sample_marker = data[1, :]
                # Cast the data to be either 0 or 1.
                sample_marker = (np.round(sample_marker) % 2).astype(np.int8)
                sync_marker = data[2, :]
                # Cast the data to be either 0 or 1.
                sync_marker = (np.round(sync_marker) % 2).astype(np.int8)
                
                marker = sample_marker
                marker+= sync_marker << 1
                mk_state = True
            elif M > 1:
                sample_marker = data[1, :]
                # Cast the data to be either 0 or 1.
                sample_marker = (np.round(sample_marker) % 2).astype(np.int8)
                marker = sample_marker
                mk_state = True
        else:
            raise ValueError("Input data has too many dimensions!")
            
        # Check the size of the data
        if N*2 > 999999999:
            raise ValueError('Data size is too large !!')
        elif N < 320:
            raise ValueError('Data size is too small !!')
        elif (N % self._seg_granu) != 0:
            raise ValueError('Data size has to be multiple of {:d} !!'.format(self._seg_granu))
        
        # Setup folder path and file name
        if folderPath == None:
            folderPath = self.awgFileFolder
        if fileName == None:
            fileName = time.strftime('%Y%m%d%H%M%S')
        
        ## Convert data to proper style
        # Cast amplitude
        if amplitude > 1.0:
            amplitude = 1.0
        # Cast wfm data to be below 1
        max_value = np.max(np.abs(wfm))
        if max_value > 1:
            wfm = wfm / max_value
        wfm = wfm * amplitude
            
        # Create data array
        ar = (127 * wfm).astype(np.int8)
        # Add marker if exists
        if M > 1:
            ar = np.column_stack((ar,marker))
            ar = ar.flatten()
        
        # Create file
        with h5py.File(folderPath+'/'+fileName+'.trc', mode='w') as f:
            dset = f.create_dataset('trace', data=ar, dtype='i2', chunks=True, compression='gzip', compression_opts=9)
            # Attach meta data
            if not advance in ['AUTO', 'COND', 'REP', 'SING', None]:
                advance = None
            meta = {'advance':advance, 'count':count, 'offset': offset,
                    'comments': comments, 'marker':mk_state}
            meta = json.dumps(meta)
            dset.attrs['meta_data'] = meta
            
        return fileName
    
    def convertTraceBinary2Array(self, data: np.ndarray, marker:bool):
        """
        Convert Binary block format trace data to (1, N) dimensional
        numpy array without marker. ((3, N) dimensional numpy array with marker.)
        
        Args:
            data: Binary block format data of trace
            marker (bool): Whether data includes marker or not.
            
        Returns:
            ar: numpy.ndarray containing the data
        """
        dshape = data.shape
        if len(dshape)>2:
            return ValueError('Data dimension is too large! Only 1d array can be accepted.')
        if marker:
            data = data.reshape((-1,2))
            ar = np.zeros((3, data.size), dtype=np.float64)
            ar[0,:] = data[:,0]/127.0
            ar[1,:] = data[:,1] % 2
            data[:,1] = data[:,1] >> 1
            ar[2,:] = data[:,1] % 2
        else:
            data = data.reshape((-1,1))
            ar = np.zeros((3, data.size), dtype=np.float64)
            ar[0,:] = data[:,0]/127.0

        return ar
    
    def makeSequenceFile(self,
                         traceFileNameList: List[str],
                         fileName: str = None,
                         folderPath: str = None,
                         counts: List[int] = [1],
                         advances: List[int] = [0],
                         maker_enables: List[int] = [0],
                         start_addrs: List[int] = [0],
                         end_addrs: List[int] = [0xffffffff],
                         advance: str = None,
                         count: int = None,
                         comments: str = None) -> str:
        """
        Load trace data from the given trace files and send them to AWG.
        Then make a sequence using those traces.
        
        Args:
            traceFileNameList (List[str]): List of trance files to be used for this sequence.
            fileName (str): File name
            folderPath (str): Path to the folder, where sequence file is saved.
            counts (List[int]): List of loop count of each segment. (1...4G-1)
            advances (List[str]): List of advancement mode of each segment.
                                      0: AUTO, Execute until the end and proceed to the next element
                                      1: CONDtional, Repeat the element until advancement event and then proceed
                                      2: REPeat, Execute until the end (loop count) and wait for advancement event to proceed
                                      3: SINGle, Execute
            marker_enables (List[int]): List of marker condition (1: enable, 0: disable)
                                        0: Marker disabled
                                        1: Marker enabled
            start_addrs (List[int]): List of address of the first sample within the segment to inserted into the sequence.
            end_addrs (List[int]): List of address of the last sample within the segment to be inserted into the sequence.
                                    We can use 0xffffffff (16**8 - 1 = 4294967295) to specify the last sample of the segment.
                                    
            advance (str): Advancement mode of sequence, ('AUTO', 'COND', 'REP', 'SING')
            count (int): Loop count of the sequence, (1 ... 4G-1).
            comments (str): Comments about the sequence
            
        Returns:
            fileName (str): Name of the created file
        """
        # Setup folder path and file name
        if folderPath == None:
            folderPath = self.awgFileFolder
        if fileName == None:
            fileName = time.strftime('%Y%m%d%H%M%S')
        
        dt = h5py.special_dtype(vlen=bytes)
        uint = h5py.h5t.NATIVE_UINT32
        param_list = [('trace_list', traceFileNameList, dt), ('counts', counts, uint),
                      ('advances', advances, uint), ('marker_enables', maker_enables, uint),
                      ('start_addrs', start_addrs, uint), ('end_addrs', end_addrs, uint)]
        with h5py.File(folderPath+'/'+fileName+'.sq', 'w') as f:
            for p in param_list:
                if p[2] == dt:
                    dset = f.create_dataset(p[0], (len(p[1]),), dtype=p[2])
                    for i, item in enumerate(p[1]):
                        dset[i] = item
                elif p[2] == uint:
                    dset = f.create_dataset(p[0], data=p[1], dtype=p[2])
            dset = f['trace_list']
            meta = {'advance':advance, 'count':count, 'comments':comments}
            meta = json.dumps(meta)
            dset.attrs['meta_data'] = meta
        
        return fileName
    
    ################################
    # Functions related to sequence
    def clearSequenceList(self):
        """
        Delete all sequences defined.
        """
        self.write(':STABle:RESet')
        # Clear the list as well
        self.sequenceFileList = dict()
            
    def loadSequenceFile(self,
                         fileName: str,
                         folderPath: str = None,
                         channel:Union[List[int],int] = 1,):
        """
        Load a sequence file.
        """
        # Setup folder path and file name
        if folderPath == None:
            folderPath = self.awgFileFolder
        # Read data from the file
        with h5py.File(folderPath+'\\'+fileName+'.sq', 'r') as f:
            tlist = f['trace_list'][Ellipsis]
            dsize = tlist.size
            
            meta = f['trace_list'].attrs['meta_data']
            meta = json.loads(meta)
            # Define trace while checking whether it is already in the memory
            if type(channel) == int:
                channel = [channel,]
            for i, c in enumerate(channel):
                ch = getattr(self, 'ch{:d}'.format(c))
                segIDList = list()
                for t in tlist:
                    segIDList.append(ch.sendTraceFromFile(t.decode(), folderPath))
                if i == 0:
                    segID_ar = np.array(segIDList, dtype=np.uint32)
            
            # Sequence loop array
            seqLoop_ar = np.zeros((dsize,),dtype=np.uint32)
            if meta['count'] == None:
                seqLoop_ar[0] = 1
            else:
                seqLoop_ar[0] = meta['count']
                    
            # Control array
            control_ar = np.zeros((dsize,),dtype=np.uint32)
            ### Mark as a start of sequence
            control_ar[0] = 2**28
            ### Mark as a end of sequence
            control_ar[-1] = 2**30
            ### Sequence advance
            if meta['advance'] == 'COND':
                control_ar[0] = control_ar[0] + (1<<20)
            elif meta['advance'] == 'REP':
                control_ar[0] = control_ar[0] + (2<<20)
            elif meta['advance'] == 'SING':
                control_ar[0] = control_ar[0] + (3<<20)
            ### Take care markers
            ar = f['marker_enables'][Ellipsis]
            if ar.size == 1:
                ar = np.array((list(ar)*dsize))
            if not ar.size == dsize:
                raise ValueError('Input parameter {} size does not match.'.format('marker_enables'))
            control_ar = control_ar[:] + (ar[:]<<24)
            ### Take care segment advance mode
            ar = f['advances'][Ellipsis]
            if ar.size == 1:
                ar = np.array((list(ar)*dsize))
            if not ar.size == dsize:
                raise ValueError('Input parameter {} size does not match.'.format('advances'))
            control_ar = control_ar[:] + (ar[:]<<16)
            
            # Combine parameters and make array to write
            ar = np.vstack((control_ar, seqLoop_ar))
            
            param_list=['counts', 'seg_id', 'start_addrs', 'end_addrs']
            for i, p in enumerate(param_list):
                if i == 1:
                    ar = np.vstack((ar, segID_ar))
                else:
                    data = f[p][Ellipsis]
                    if data.size == 1:
                        data = np.array((list(data)*dsize))
                    if not data.size == dsize:
                        raise ValueError('Input parameter {} size does not match.'.format(p))
                    ar = np.vstack((ar,data))
        ar = ar.astype(np.uint32).transpose()
        return ar
    
    def sendSequenceFromFile(self,
                             fileName: str,
                             folderPath: str = None,
                             seqID: int = 0,
                             channel:Union[List[int],int] = 1,):
        """
        This function create sequence from sequence file created by 'MakeSequenceFile' function.
        
        Args:
            fileName (str): Name of the sequence file
            folderPath (str): Path to the folder of the file. If None, becomes default awg folder.
            seqID (int): From which sequence table ID we make a sequence.
        """
        # If the file has been already loaded, function simply returns sequence ID.
        if fileName in list(self.sequenceFileList.values()):
            return list(self.sequenceFileList.keys())[list(self.sequenceFileList.values()).index(fileName)]
        # Set default folder path if not given.
        if folderPath == None:
            folderPath = self.awgFileFolder
            
        ar = self.loadSequenceFile(fileName, folderPath, channel)
        
        ar = ar.flatten().tobytes()
        dsize = len(ar)
        cmd = 'STABle:DATA {:d},#{:d}{:d}'.format(seqID, len(str(dsize)), dsize)
        cmd = cmd.encode()
        cmd+= ar
        self.visa_handle.write_raw(cmd)
        self.ask('*OPC?')
        
        # Set file name to sequence file list
        self.sequenceFileList[seqID] = fileName
        
        return seqID
    
if __name__=='__main__':
    # Test this driver.
    awg = Keysight_M8195A(name = 'awg', 
                          address = 'TCPIP0::192.168.0.47::inst0::INSTR',
                          timeout = 10,
                          op_mode = '6-1-2',
                          awgFileFolder='D:/Users/Shintaro/Data/AWG',
                          reset=False)
    
#    sin = np.array(np.sin(2*np.pi*np.arange(2048)/512)*127, dtype=np.int8)
#    N = sin.size
#    
#    awg.ch1.defineTrace(1, N)
#    cmd = ':TRACe{:d}:DATA {:d},{:d},#{:d}{:d}'.format(1, 1, 0, len(str(N*1)), N*1)
#    cmd = cmd.encode()
#    cmd+= sin.tobytes()
#    awg.visa_handle.write_raw(cmd)
#    awg.ask('*OPC?')
##    
#    awg.ch2.defineTrace(1, N)
#    cmd = ':TRACe{:d}:DATA {:d},{:d},#{:d}{:d}'.format(2, 1, 0, len(str(N*1)), N*1)
#    cmd = cmd.encode()
#    cmd+= sin.tobytes()
#    awg.visa_handle.write_raw(cmd)
#    awg.ask('*OPC?')
    
    awg.ch1.sendTraceFromFile('test', segID=1)
    awg.ch2.sendTraceFromFile('test', segID=1)
    print(awg.ch1.traceFileList)
    awg.close()