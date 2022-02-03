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

######################################################
#
# MODEL DEPENDENT SETTINGS
#

_fg_path_val_map = {'M8190A': {}}

# number of markers per channel
_num_of_markers_map = {'M8190A': 2}

# channel resolution
_chan_resolutions = {'M8190A': [12]}

# Default waveform and seequence folder
awgFileFolder = "D:\\Shintaro\\Programs\\AWG"

#class  AWGTrace(ArrayParameter):
#    """
#    Class to store trace information of the AWG
#    """
#    def __init__(self, name: str, instrument: InstrumentChannel,
#                 segID: int, channel: int,
#                 trace = np.zeros((1,), dtype=np.int16),
#                 advance = ['AUTO', 'COND', 'REP', 'SING'][0],
#                 count = 1, offset = 0) -> None:
#        """
#        Args:
#            name: The name used in the Dataset
#            parent: The instrument channel instance to which the trace is
#                to be attached.
#            segID: The segment ID used to communicate with AWG
#            channel: The channel number, either 1 or 2
#        """
#        super().__init__(name=name,
#                         shape=(320,),
#                         label='Waveform',
#                         unit='',
#                         setpoint_names=('Time',),
#                         setpoint_labels=('Time',),
#                         setpoint_units=('ns',),
#                         docstring='Holds AWG trace data')
#        self.segID = segID
#        self.channel = channel
#        self._instrument = instrument
#        
#        self.trace = trace
#        self.advance = advance
#        self.count = count
#        self.offset = offset
#        
#    def get_raw(self):
#        return self.trace
#    
#    def set_raw(self, val: np.array):
#        # Update trace to the given val
#        self.trace = val
#        # Cast array type to be 16 bit integer to make sure
#        self.trace = self.trace.astype(np.int16)
#        N = self.trace.size
#        # update setpoints
#        self.setpoints = 1e9/self._instrument.root_instrument.sample_rate()*np.arange(N, dtype=np.float64)
#        # Send data to AWG (N*2 is 16 bit = 2 bytes)
#        cmd = 'TRACe{:d}:DATA {:d},{:d},#{:d}{:d}'.format(self.channel, self.segID, 0, len(str(N*2)), N*2)
#        cmd = cmd.encode()
#        cmd+= self.trace.tobytes()
#        self._instrument.root_instrument.visa_handle.write_raw(cmd)
#        # Update meta data
        

class AWGChannel(InstrumentChannel):
    """
    Class to hold a channel of the AWG
    """
    
    def __init__(self, parent: Instrument, name: str, channel: int) -> None:
        """
        Args:
            parent: The Instrument instance to which the channel is
                to be attached.
            name: The name used in the DataSet
            channel: The channel number, either 1 or 2.
        """
        
        super().__init__(parent, name)
        
        self.channel = channel
        
        num_channels = self.root_instrument.num_channels
        self.model = self.root_instrument.model
        self.traceFileList = dict()
        self.sequenceFileList = dict()
        self._skew = 0.0
                
        if channel not in list(range(1, num_channels+1)):
            raise ValueError('Illegal channel value.')
            
        self.add_parameter('state',
                           label='Channel {} state'.format(channel),
                           get_cmd='OUTPut{}:NORMal?'.format(channel),
                           set_cmd='OUTPut{}:NORMal {{}}'.format(channel),
                           vals = vals.Ints(0, 1),
                           get_parser = int)
        
        self.add_parameter('cstate',
                           label='Channel {} complement state'.format(channel),
                           get_cmd='OUTPut{}:COMPlement?'.format(channel),
                           set_cmd='OUTPut{}:COMPlement {{}}'.format(channel),
                           vals = vals.Ints(0, 1),
                           get_parser = int)
        
        ##########################################################
        # Mode of the channel
        
        # I'm not sure whether these modes are really independent
        # between channel 1 and 2. However since it could be chosen,
        # I set them as a channel parameter.
        self.add_parameter('func_mode',
                           label='Function mode channel {}'.format(channel),
                           get_cmd='FUNCtion{}:MODE?'.format(channel),
                           set_cmd='FUNCtion{}:MODE {{}}'.format(channel),
                           val_mapping={'ARBitrary':'ARB', 'STSequence':'STS', 'STSCenario':'STSC'})
        self.add_parameter('continuous',
                           label='Continuous state channel {}'.format(channel),
                           get_cmd='INITiate:CONTinuous{}?'.format(channel),
                           set_cmd='INITiate:CONTinuous{} {{}}'.format(channel),
                           vals=vals.Ints(0, 1),
                           get_parser=int)
        self.add_parameter('gate_state',
                           label='Gate state channel {}'.format(channel),
                           get_cmd='INITiate:GATE{}?'.format(channel),
                           set_cmd='INITiate:GATE{} {{}}'.format(channel),
                           vals=vals.Ints(0, 1),
                           get_parser=int)
        self.add_parameter('arm_mode',
                           label='Arm mode channel {}'.format(channel),
                           get_cmd='INITiate:CONTinuous{}:ENABle?'.format(channel),
                           set_cmd='INITiate:CONTinuous{}:ENABle {{}}'.format(channel),
                           val_mapping={'Self':'SELF', 'Armed':'ARM'})
        self.add_parameter('output_format',
                           label='Output format channel {}'.format(channel),
                           get_cmd='DAC{}:FORMat?'.format(channel),
                           set_cmd='DAC{}:FORMat {{}}',
                           val_mapping={'Return_to_Zero':'RZ', 'Double_NRZ':'DNRZ', 'Non_Return_to_Zero':'NRZ', 'Doublet':'DOUB'})
        
        ############################################
        # AWG PARAMETERS
        
        amp_cmd = 'DAC{}:VOLT'.format(channel)
        offset_cmd = 'DAC{}:VOLT:OFFS'.format(channel)
        fine_delay_cmd = 'ARM:DEL{}'.format(channel)
        coarse_delay_cmd = 'ARM:CDEL{}'.format(channel)
        current_trace_cmd = 'TRACe{}:SELect'.format(channel)
        current_sequence_cmd = 'STABle{}:SEQuence:SELect'.format(channel)
        
        # Set channel first to ensure sensible sorting of pars
        
        self.add_parameter('amp',
                           label='Amplitude channel {}'.format(channel),
                           unit='Vpp',
                           get_cmd=amp_cmd + '?',
                           set_cmd=amp_cmd + ' {:.6f}',
                           vals=vals.Numbers(0.35, 0.7),
                           get_parser=float)
        self.add_parameter('offset',
                           label='Offset channel {}'.format(channel),
                           unit='V',
                           get_cmd=offset_cmd + '?',
                           set_cmd=offset_cmd + ' {:.6f}',
                           vals=vals.Numbers(-0.02, 0.02),
                           get_parser=float)
        self.add_parameter('fd',
                           label='Fine delay channel {}'.format(channel),
                           unit='ps',
                           get_cmd=fine_delay_cmd + '?',
                           set_cmd=fine_delay_cmd + ' {:.3f}e-12',
                           vals=vals.Numbers(0.0, 150),
                           get_parser=float,
                           docstring = 'f_Sa >= 6.25 GSa/s: 0...30 ps, 2.5 GSa/s <= f_Sa < 6.25 GSa/s:0...60 ps, f_Sa < 2.5 GSa/s: 0...150 ps.',
                           )
        self.add_parameter('cd',
                           label='Coarse delay channel {}'.format(channel),
                           unit='ns',
                           get_cmd=coarse_delay_cmd + '?',
                           set_cmd=coarse_delay_cmd + ' {:.3f}e-9',
                           vals=vals.Numbers(0.0, 10),
                           get_parser=float,
                           docstring = 'f_Sa >= 6.25 GSa/s: 0...10 ns with 10 ps step, 2.5 GSa/s <= f_Sa < 6.25 GSa/s:0...10 ns with 20 ps step, f_Sa < 2.5 GSa/s: 0...10 ns with 50 ps step.',
                           )
        self.add_parameter('skew',
                           label = 'Skew of ch'.format(channel),
                           unit = 'ps',
                           get_cmd=self.get_skew,
                           set_cmd=self.set_skew,
                           vals=vals.Numbers(0.0, 10000.0),
                           docstring='This is a combined parameter of fine delay and coarase delay. We can smoothly change skew between 0 and 10 ns.',
                           )
        
        ##########################
        # Trace parameter
        self.add_parameter('current_trace',
                           label='Current trace channel {}'.format(channel),
                           get_cmd=current_trace_cmd + '?',
                           set_cmd=current_trace_cmd + ' {:d}',
                           vals=vals.Ints(1, 512000),
                           get_parser=int)
        
        ##########################
        # Sequence parameter
        self.add_parameter('current_sequence',
                           label='Current sequence channel {}'.format(channel),
                           get_cmd=current_sequence_cmd + '?',
                           set_cmd=current_sequence_cmd + ' {:d}',
                           vals=vals.Ints(0, 512000-2),
                           get_parser=int)
        
        ##########################
        # Markers
        mk_list = ['sample', 'sync']
        mk_cmd_list = ['SAMP', 'SYNC']
        for mrk in range(_num_of_markers_map[self.model]):
            self.add_parameter(mk_list[mrk]+'_mk_high',
                               label=mk_list[mrk]+' marker high channel {}'.format(channel),
                               unit='V',
                               get_cmd='MARK{}:{}:VOLT:HIGH?'.format(channel, mk_cmd_list[mrk]),
                               set_cmd='MARK{}:{}:VOLT:HIGH {{:.3f}}'.format(channel, mk_cmd_list[mrk]),
                               vals=vals.Numbers(0.5, 1.75),
                               get_parser=float)
            self.add_parameter(mk_list[mrk]+'_mk_low',
                               label=mk_list[mrk]+' marker low channel {}'.format(channel),
                               unit='V',
                               get_cmd='MARK{}:{}:VOLT:LOW?'.format(channel, mk_cmd_list[mrk]),
                               set_cmd='MARK{}:{}:VOLT:LOW {{:.3f}}'.format(channel, mk_cmd_list[mrk]),
                               vals=vals.Numbers(-0.5, 1.75),
                               get_parser=float)
    
    ################################
    # Functions related to parameter
    def get_skew(self):
        return self._skew
    
    def set_skew(self, val:float):
        sample_rate = self.root_instrument.sample_rate()
        
        if sample_rate > 6.25e9:
            fine_skew = val % 10.0
            coarse_skew = (val // 10.0)*0.01
        elif sample_rate > 2.5e9:
            fine_skew = val % 20.0
            coarse_skew = (val // 20.0)*0.02
        else:
            fine_skew = val % 50.0
            coarse_skew = (val // 50.0)*0.05
            
        self.fd(fine_skew)
        self.cd(coarse_skew)
        self._skew = val
    
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
        elif segID > 512000:
            raise ValueError('Segment ID has to be integer between 1 and 512k.')
            
        self.root_instrument.write(f'TRACe{self.channel}:DELete {segID}')
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
        elif segID > 512000:
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
        elif len(shape) == 2:
            N = shape[1]
            M = shape[0]
            wfm = data[0, :]
            if M > 2:
                sample_marker = data[1, :]
                # Cast the data to be either 0 or 1.
                sample_marker = (np.round(sample_marker) % 2).astype(np.short)
                sync_marker = data[2, :]
                # Cast the data to be either 0 or 1.
                sync_marker = (np.round(sync_marker) % 2).astype(np.short)
            elif M > 1:
                sample_marker = data[1, :]
                # Cast the data to be either 0 or 1.
                sample_marker = (np.round(sample_marker) % 2).astype(np.short)
        else:
            raise ValueError("Input data hs too many dimensions!")
            
        # Check the size of the data
        if N*2 > 999999999:
            raise ValueError('Data size is too large !!')
        elif N < 320:
            raise ValueError('Data size is too small !!')
        elif (N % 64) != 0:
            raise ValueError('Data size has to be multiple of 64 !!')
            
        # Cast wfm data to be below 1
        max_value = np.max(np.abs(wfm))
        if max_value > 1:
            wfm = wfm / max_value
            
        # Create data array
        ar = (2047 * wfm).astype(np.short)
        ar = ar << 4                    # shift 4 bit to left
        if M > 1:
            ar += sample_marker         # add sample marker to 1st bit
        if M > 2:
            ar += sync_marker << 1      # add sync marker to 2nd bit
            
        # Make command
        # N * 2 (16 bit integer is 2 byte, so we multiply 2)
        cmd = 'TRACe{:d}:DATA {:d},{:d},#{:d}{:d}'.format(self.channel, segID, offset, len(str(N*2)), N*2)
        cmd = cmd.encode()
        cmd+= ar.tobytes()
        
        self.root_instrument.visa_handle.write_raw(cmd)
        
        # OPC
        if opc:
            self.root_instrument.ask('*OPC?')
        
    ################################
    # Functions related to sequence
    @property
    def sequenceList(self):
        """
        Return the sequence list as a list of strings
        {'seqID':List[int], 'length':List[int]}
        """
        slist = {}
        sliststr = self.root_instrument.ask(f'SEQuence{self.channel}:CATalog?')
        sliststr = sliststr.split(',')
        slist['seqID'] = [int(n) for n in sliststr[::2]]
        slist['length'] = [int(n) for n in sliststr[1::2]]
        
        return slist
    
    def clearSequenceList(self):
        """
        Delete all sequences defined.
        """
        self.root_instrument.write(f'SEQuence{self.channel}:DELete:ALL')
        self.root_instrument.write(f'STABle{self.channel}:RESet')
        # Clear the list as well
        self.sequenceFileList = dict()
        
    def deleteSequence(self, seqID: int):
        """
        Delete the trace specified by the segment ID (int)
        """
        self.root_instrument.write(f'SEQuence{self.channel}:DELete {seqID}')
        del self.sequenceFileList[seqID]
        
    def defineSequence(self, length: int) -> int:
        """
        Define new sequence of "length"(int) with "sequence ID"(int).
        
        args:
            length: Number of sequence table entries.
            
        returns:
            seqID (int): sequence ID
        """
        return int(self.root_instrument.ask(f'SEQuence{self.channel}:DEFine:NEW? {length}'))
        
    def setSequenceAdvance(self, seqID: int, mode: str):
        """
        Set the advancement mode between iterations of a sequence.
        """
        # Check the validity of the values
        if not mode in ['AUTO', 'COND', 'REP', 'SING']:
            raise ValueError('Unknown mode is specified. Please check it again.')
            
        self.root_instrument.write(f'SEQuence{self.channel}:ADVance {seqID},{mode}')
        
    def setSequenceCount(self, seqID: int, count: int):
        """
        < sequence_id > 0…512K-2
        <count> 1...4G-1 number of times the sequence is executed.
        Set or query the number of iterations of a sequence.
        """
        # Check the validity of the values
        if count < 1:
            raise ValueError('Count has to be an integer between 1 and 4G-1.')
        elif count > 4e9-1:
            raise ValueError('Count has to be an integer between 1 and 4G-1.')
            
        self.root_instrument.write('SEQuence{self.channel}:COUNt {seqID},{count}')
        
    def setSeqData(self, seqID: int, step: int, data_array, opc: bool=True):
        """
        Set segment data to a sequence table element.
        
        Args:
            seqID: sequence ID to be set.
            step: sequence table entry in the sequence.
            data_array: numpy array of (N, 6) elements
                        Each element indicates
                        <segment_id>: segment id 
                        <loop_count>: no of segment loop iterations 1...4G-1
                        <advance_mode>:
                            0: AUTO, Execute until the end and proceed to the next element
                            1: CONDitional, Repeat the element until advancement event and then proceed
                            2: REPeat, Execute until the end and wait for advancement event to proceed
                            3: SINGle, Execute
                        <marker_enable>:
                            0: Marker disabled
                            1: Marker enabled
                        <start_addr>: Address of the first sample within the segment to inserted into the sequence.
                        <end_addr>: Address of the last sample within the segment to be inserted into the sequence.
                                    We can use 0xffffffff (16**8-1 = 4294967295) to specify the last sample of the segment.
            opc: Whether query OPC or not in the end.
        """
        data_str = data_array.tobytes()
        data_str_size = len(data_str)
        cmd = 'SEQuence{:d}:DATA {:d}, {:d},#{:d}{:d}'.format(self.channel, seqID, step, len(str(data_str_size)), data_str_size)
        cmd = cmd.encode()
        cmd+= data_str
        
        self.root_instrument.visa_handle.write_raw(cmd)
        
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
            dset = np.array(dset[Ellipsis], dtype=np.int16)
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
        
        tlist = self.traceList
        if segID == None:
            segID = max(tlist['segID'])+1
        else:
            if segID in tlist['segID']:
                self.deleteTrace(segID)
        N = dset.size
        self.defineTrace(segID, N+offset)
        
        cmd = 'TRACe{:d}:DATA {:d},{:d},#{:d}{:d}'.format(self.channel, segID, offset, len(str(N*2)), N*2)
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
    
    def loadSequenceFile(self, fileName: str, folderPath: str = None):
        """
        Load a sequence file.
        """
        # Setup folder path and file name
        if folderPath == None:
            folderPath = self.root_instrument.awgFileFolder
        param_list=['counts', 'advances', 'maker_enables', 'start_addrs', 'end_addrs']
        # Read data from the file
        with h5py.File(folderPath+'\\'+fileName+'.sq', 'r') as f:
            tlist = f['trace_list'][Ellipsis]
            meta = f['trace_list'].attrs['meta_data']
            meta = json.loads(meta)
            # Define trace while checking whether it is already in the memory
            segIDList = list()
            for t in tlist:
                segIDList.append(self.sendTraceFromFile(t.decode(), folderPath))
            ar = np.array(segIDList, dtype=np.uint32)
                    
            dsize = tlist.size
            for p in param_list:
                data = f[p][Ellipsis]
                if data.size == 1:
                    data = np.array((list(data)*dsize))
                if not data.size == dsize:
                    raise ValueError('Input parameter {} size does not match.'.format(p))
                ar = np.vstack((ar,data))
        ar = ar.astype(np.uint32).transpose()
        return ar, meta
    
    def sendSequenceFromFile(self, fileName: str, folderPath: str = None,
                             step: int = 0):
        # If the file has been already loaded, function simply returns sequence ID.
        if fileName in list(self.sequenceFileList.values()):
            return list(self.sequenceFileList.keys())[list(self.sequenceFileList.values()).index(fileName)]
        # Set default folder path if not given.
        if folderPath == None:
            folderPath = self.root_instrument.awgFileFolder
            
        ar, meta = self.loadSequenceFile(fileName, folderPath)
        shape = ar.shape
        seqID = self.defineSequence(shape[0])
        
        ar = ar.flatten().tobytes()
        dsize = len(ar)
        cmd = 'SEQuence{:d}:DATA {:d},{:d},#{:d}{:d}'.format(self.channel, seqID, step, len(str(dsize)), dsize)
        cmd = cmd.encode()
        cmd+= ar
        self.root_instrument.visa_handle.write_raw(cmd)
        self.root_instrument.ask('*OPC?')
        # Set conditions
        if not meta['advance']==None:
            self.setSequenceAdvance(seqID, meta['advance'])
        if not meta['count']==None:
            self.setSequenceCount(seqID, meta['count'])
        
        # Set file name to sequence file list
        self.sequenceFileList[seqID] = fileName
        
        return seqID

class Keysight_M8190A(VisaInstrument):
    """
    This is the QCoDes driver for the Keysight M8190A
    Arbitrary Waveform Generator.
    
    The driver makes some assumptions on the settings of the instrument:
        
        - The output channels are always in Amplitude/Offset mode
        - The output markers are always in High/Low mode
        - We use the AWG in 'sequence mode' with 2 channels. In this mode you
        can define as many traces (or waveforms) up to 512k and set them into
        the sequence table (up to 512k-1).
        
        Useful modes:
            1.  We repeat each waveform infinitely. When we send an advancement
                Event, the waveform switch to next. Finally it comes back to 
                func_mode: STSequence, 
                continuous: 1 (True),
                gate_state: 0 (False),
                arm_mode: 'Self'
        
    TODO:
        
        
    In the future, we should consider the following:
        
        
    """
    
    def __init__(self, name: str, address: str, timeout: float=180.0,
                 num_channels: int=2, **kwargs) -> None:
        """
        Initializes the Keysight M8190A
        
        Args:
            name (string): name of the instrument
            address (string): GPIB or ethernet address as used by VISA (practically 'TCPIP::localhost::hislip0::INSTR')
            timeout (float): visa timeout, in secs. long default (180)
                to accommodate large waveforms
            num_channels (int): number of channels on the device
            
        Returns:
            None
        """
        self.num_channels = num_channels
        
        super().__init__(name, address, timeout=timeout, terminator='\n',
                         **kwargs)
        
        # Basic functions
        self.add_function('reset', call_cmd='*RST')
        
        # Get the model value
        self.model = self.IDN()['model']
        
        if self.model not in ['M8190A']:
            raise ValueError('Unkown model type: {}. Are you using '
                             'the right driver for your instrument?'
                             ''.format(self.model))
            
        self.add_parameter('current_directory',
                           label='Current file system directory',
                           set_cmd='MMEMory:CDIRectory "{}"',
                           get_cmd='MMEMory:CDIRectory?',
                           vals=vals.Strings())
        
        ##########################################################
        # Clock parameters
        
        self.add_parameter('sample_rate',
                           label='Clock sample rate',
                           unit='Sa/s',
                           get_cmd='FREQ:RAST?',
                           set_cmd='FREQ:RAST' + ' {}',
                           vals=vals.Numbers(125.0e6, 12.0e9),
                           get_parser=float)
        
        self.add_parameter('clock_source',
                           label='Clock source',
                           get_cmd='ROSC:SOUR?',
                           set_cmd='ROSC:SOUR' + ' {}',
                           val_mapping={'Internal':'INT',
                                         'External':'EXT',
                                         'Auxiliary':'AXI'})
        
        self.add_parameter('clock_external_frequency',
                           unit='Hz',
                           label='External clock frequency',
                           get_cmd='ROSC:FREQ?',
                           set_cmd='ROSC:FREQ' + ' {}',
                           vals=vals.Numbers(1.0e6,100.0e6),
                           get_parser=float)
        
        ####################################
        # Trigger parameters
        
        self.add_parameter('trigger_level',
                           unit='V',
                           label='Trigger level',
                           get_cmd='ARM:TRIG:LEV?',
                           set_cmd='ARM:TRIG:LEV' + ' {:.3f}',
                           vals=vals.Numbers(0.0, 1.0),
                           get_parser=float)
        
        self.add_parameter('trigger_slope',
                           get_cmd='ARM:TRIG:SLOP?',
                           set_cmd='ARM:TRIG:SLOP' + ' {}',
                           val_mapping={'Positive':'POS',
                                        'Negative':'NEG',
                                        'Either':'EITH'})
        
        self.add_parameter('event_level',
                           unit='V',
                           label='Event level',
                           get_cmd='ARM:EVEN:LEV?',
                           set_cmd='ARM:EVEN:LEV' + ' {:.3f}',
                           vals=vals.Numbers(0.0, 1.0),
                           get_parser=float)
        
        self.add_parameter('event_slope',
                           get_cmd='ARM:EVEN:SLOP?',
                           set_cmd='ARM:EVEN:SLOP' + ' {}',
                           val_mapping={'Positive':'POS',
                                        'Negative':'NEG',
                                        'Either':'EITH'})
        
        
        # We deem 2 channels too few for a channel list
        if self.num_channels > 2:
            chanlist = ChannelList(self, 'Channels', AWGChannel,
                                   snapshotable=False)
        for ch_num in range(1, num_channels+1):
            ch_name = 'ch{}'.format(ch_num)
            channel = AWGChannel(self, ch_name, ch_num)
            self.add_submodule(ch_name, channel)
            if self.num_channels > 2:
                chanlist.append(channel)
                
        if self.num_channels > 2:
            chanlist.lock()
            self.add_submodule('channels', chanlist)
            
        # Folder, where waveform and sequence file will be saved.
        self.awgFileFolder = awgFileFolder
        
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
        
    def reset_trace_sequence(self):
        """
        Reset all defined trace and sequences for all channels
        """
        for ch_num in range(1, self.num_channels+1):
            ch_name = 'ch{}'.format(ch_num)
            channel = getattr(self, ch_name)
            channel.clearSequenceList()
            channel.clearTraceList()
        
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
        We can send the trace to AWG using thie file.
        
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
        elif len(shape) == 2:
            N = shape[1]
            M = shape[0]
            wfm = data[0, :]
            if M > 2:
                sample_marker = data[1, :]
                # Cast the data to be either 0 or 1.
                sample_marker = (np.round(sample_marker) % 2).astype(np.short)
                sync_marker = data[2, :]
                # Cast the data to be either 0 or 1.
                sync_marker = (np.round(sync_marker) % 2).astype(np.short)
            elif M > 1:
                sample_marker = data[1, :]
                # Cast the data to be either 0 or 1.
                sample_marker = (np.round(sample_marker) % 2).astype(np.short)
        else:
            raise ValueError("Input data has too many dimensions!")
            
        # Check the size of the data
        if N*2 > 999999999:
            raise ValueError('Data size is too large !!')
        elif N < 320:
            raise ValueError('Data size is too small !!')
        elif (N % 64) != 0:
            raise ValueError('Data size has to be multiple of 64 !!')
        
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
        ar = (2047 * wfm).astype(np.short)
        ar = ar << 4                    # shift 4 bit to left
        if M > 1:
            ar += sample_marker         # add sample marker to 1st bit
        if M > 2:
            ar += sync_marker << 1      # add sync marker to 2nd bit
        
        # Create file
        with h5py.File(folderPath+'/'+fileName+'.trc', mode='w') as f:
            dset = f.create_dataset('trace', data=ar, dtype='i2', chunks=True, compression='gzip', compression_opts=9)
            # Attach meta data
            if not advance in ['AUTO', 'COND', 'REP', 'SING', None]:
                advance = None
            meta = {'advance':advance, 'count':count, 'offset': offset,
                    'comments': comments}
            meta = json.dumps(meta)
            dset.attrs['meta_data'] = meta
            
        return fileName
    
    def convertTraceBinary2Array(self, data: np.ndarray):
        """
        Convert Binary block format trace data to (3, N) dimensional
        numpy array.
        
        Args:
            data: Binary block format data of trace as well as markers
            
        Returns:
            ar: numpy.ndarray containing the data
        """
        dshape = data.shape
        if len(dshape)>2:
            return ValueError('Data dimension is too large! Only 1d array can be accepted.')
        ar = np.zeros((3, data.size), dtype=np.float64)
        ar[1,:] = (data % 2)
        data = (data >> 1)
        ar[2,:] = (data % 2)
        data = (data >> 3)
        ar[0,:] = data/2047.0
        return ar
    
    def makeSequenceFile(self,
                         traceFileNameList: List[str],
                         fileName: str = None,
                         folderPath: str = None,
                         counts: List[int] = [1],
                         advances: List[int] = [0],
                         maker_enables: List[int] = [1],
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
                      ('advances', advances, uint), ('maker_enables', maker_enables, uint),
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