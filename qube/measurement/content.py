import numpy as np
from typing import Dict, List
from qcodes import load_by_id
from qcodes.dataset.data_set import DataSet as qc_DataSet
from qube.postprocess.dataset import Dataset, Axis, Static
from qube.postprocess.datafile import Datafile
from abc import ABC, abstractmethod


def qcodes_to_datafile(ds: qc_DataSet = None) -> Datafile:
    expc = QcodesDatasetContent(ds)
    return expc.to_datafile()


def run_id_to_datafile(run_id: int) -> Datafile:
    qc_ds = load_by_id(run_id)
    return qcodes_to_datafile(qc_ds)


# class ExpContent(object):
#     def __init__(self):
#         pass
#
#     def load(self, v):
#         pass
#
#     def load_qcodes_dataset(self, qc_ds):
#         pass
#
#     def load_datafile(self, df):
#         pass
#
class ExpContent(ABC):

    @abstractmethod
    def load(self, *args, **kwargs):
        """ Method to load the content """

    @abstractmethod
    def get_datasets(self) -> List[Dataset]:
        """ List of :class: Dataset (i.e. readouts) """

    @abstractmethod
    def get_axes(self) -> List[Axis]:
        """ List of :class: Axis (i.e. swept parameter) """

    @abstractmethod
    def get_statics(self) -> List[Static]:
        """ List of :class: Static (i.e. static parameter) """


class DatafileContent(ExpContent):
    """ Class to extract from a Datafile the information of an experiment performed with Controls class """

    def __int__(self, fullpath):
        self.df = None
        if fullpath:
            self.load(fullpath)

    def load(self, fullpath):
        self.df = Datafile()
        self.df.load(fullpath)
        self.fullpath = fullpath

    def get_datasets(self) -> List[Dataset]:
        return self.df.datasets

    def get_axes(self) -> List[Axis]:
        return self.df.axes

    def get_statics(self) -> List[Static]:
        return self.df.statics


class QcodesDatasetContent(ExpContent):
    """ Class to extract from a qcodes.DataSet the information of an experiment performed with Controls class """

    def __init__(self, ds: qc_DataSet = None):
        self.datasets = []
        self.axes = []
        self.statics = []
        self._sweep_info = {}
        self.qc_ds = None
        self.qc_data = {}
        self.qc_params = []

        if ds is not None:
            self.load(ds)

    @property
    def readouts(self):
        """ Alias for datasets """
        return self.datasets

    def clear(self):
        self.datasets = []
        self.axes = []
        self.statics = []
        self._sweep_info = {}
        self.qc_ds = None
        self.qc_data = {}
        self.qc_params = []

    def load(self, ds: qc_DataSet):
        self._validate_qcodes_data(ds)
        self.clear()
        self.qc_ds = ds
        self.qc_data = self.qc_ds.get_parameter_data()
        self.qc_params = self.qc_ds.get_parameters()
        self._sweep_info = self._extract_sweep_info()
        self.datasets, self.axes = self._extract_datasets()
        self.statics = self._extract_statics()

    def load_by_id(self, run_id: int, *args, **kwargs):
        ds = load_by_id(run_id, *args, **kwargs)
        self.load(ds)

    def _validate_qcodes_data(self, ds: qc_DataSet):
        """
        Check if the qcodes dataset contains sweep information (from Controls.sweep)
        Comments:
            - This should be updated accordingly when Sweep class is improved
        """
        if not isinstance(ds, qc_DataSet):
            raise TypeError(f'Input has be a qcodes dataset')
        data = ds.get_parameter_data()
        valid = 'sweep_dims' in data.keys()
        if not valid:
            raise ValueError(f'Invalid qcodes dataset. It does not contain sweep information.')

    def get_datasets(self) -> List[Dataset]:
        """ List of :class: Dataset (i.e. readouts) """
        return self.datasets

    def get_axes(self) -> List[Axis]:
        """ List of :class: Axis (i.e. swept parameter) """
        return self.axes

    def get_statics(self) -> List[Static]:
        """ List of :class: Static (i.e. static parameter) """
        return self.statics

    def _extract_sweep_info(self) -> Dict:
        d = {}
        key_fmt = [
            ['sweep_dims', int],
            ['sweep_full_names', str],
            ['sweep_names', str],
            ['shape', int],
            ['readout_full_names', str],
            ['readout_names', str],
        ]
        for kf in key_fmt:
            key, fmt = kf
            d[key] = list(np.array(self.qc_data[key][key]).astype(fmt))
        return d

    def to_datafile(self):
        # Add datasets to datafile
        df = Datafile()
        df.add_datasets(*self.datasets)
        # df.add_statics(*self.statics) #TODO
        # df.metadata(self.qc_ds.snapshot)
        return df

    def _extract_datasets(self):
        qc_data = self.qc_data
        params_specs = self.qc_params
        sweep_info = self._sweep_info
        params_metadata = self._controls_parameters()

        readouts = sweep_info['readout_full_names']
        sweeps = sweep_info['sweep_full_names']
        prefix = 'controls_'
        axes = []
        datasets = []

        for pinfo in params_specs:
            full_name = pinfo.name
            unit = pinfo.unit
            if full_name[:len(prefix)] != prefix:
                # Ignore parameter if it has no 'control_' as prefix
                continue
            if full_name in readouts:
                # Create a Dataset if it is a readout parameter
                idx = readouts.index(full_name)
                name = sweep_info['readout_names'][idx]
                dsi = Dataset(
                    name=name,
                    unit=unit,
                    value=qc_data[full_name][full_name].reshape(*sweep_info['shape']).T,
                    metadata=params_metadata[name],
                )
                datasets.append(dsi)
            elif full_name in sweeps:
                # Create an Axis if it is a swept parameter
                idx = sweeps.index(full_name)
                name = sweep_info['sweep_names'][idx]
                ax = Axis(
                    name=name,
                    unit=unit,
                    value=np.squeeze(qc_data[full_name][full_name]),
                    dim=int(sweep_info['sweep_dims'][idx]) - 1,  # to be fixed in Sweep class?
                    metadata=params_metadata[name],
                )
                axes.append(ax)

        # Add axes to each dataset
        [dsi.add_axes(*axes) for dsi in datasets]
        return datasets, axes

    def _extract_statics(self):
        sweep_info = self._sweep_info
        params_metadata = self._controls_parameters()

        readouts = sweep_info['readout_names']
        sweeps = sweep_info['sweep_names']
        control_names = readouts + sweeps

        statics = []
        for pname, metadata in params_metadata.items():
            if pname in control_names:
                continue
            st = Static(
                name=pname,
                unit=metadata['unit'],
                value=metadata['value'],
                metadata=metadata,
            )
            statics.append(st)
        return statics

    def _controls_snapshot(self):
        return self.qc_ds.snapshot['station']['components']['controls']

    def _controls_parameters(self):
        d = self._controls_snapshot()
        return d['parameters']


# class ControlsContent(ExpContent):
#     """ Class to extract the experiment information from a Controls class """
#
#     def __init__(self, ds: qc_DataSet = None):
#         self.datasets = []
#         self.axes = []
#         self.statics = []
#         self._sweep_info = {}
#         self.qc_ds = None
#         self.qc_data = {}
#         self.qc_params = []
#
#         if ds is not None:
#             self.load(ds)
#
#     @property
#     def readouts(self):
#         """ Alias for datasets """
#         return self.datasets
#
#     def clear(self):
#         self.datasets = []
#         self.axes = []
#         self.statics = []
#         self._sweep_info = {}
#         self.qc_ds = None
#         self.qc_data = {}
#         self.qc_params = []
#
#     def load(self, ds: qc_DataSet):
#         self._validate_qcodes_data(ds)
#         self.clear()
#         self.qc_ds = ds
#         self.qc_data = self.qc_ds.get_parameter_data()
#         self.qc_params = self.qc_ds.get_parameters()
#         self._sweep_info = self._extract_sweep_info()
#         self.datasets, self.axes = self._extract_datasets()
#         self.statics = self._extract_statics()
#
#     def load_by_id(self, run_id: int, *args, **kwargs):
#         ds = load_by_id(run_id, *args, **kwargs)
#         self.load(ds)
#
#     def _validate_qcodes_data(self, ds: qc_DataSet):
#         """
#         Check if the qcodes dataset contains sweep information (from Controls.sweep)
#         Comments:
#             - This should be updated accordingly when Sweep class is improved
#         """
#         if not isinstance(ds, qc_DataSet):
#             raise TypeError(f'Input has be a qcodes dataset')
#         data = ds.get_parameter_data()
#         valid = 'sweep_dims' in data.keys()
#         if not valid:
#             raise ValueError(f'Invalid qcodes dataset. It does not contain sweep information.')
#
#     def get_datasets(self) -> List[Dataset]:
#         """ List of :class: Dataset (i.e. readouts) """
#         return self.datasets
#
#     def get_axes(self) -> List[Axis]:
#         """ List of :class: Axis (i.e. swept parameter) """
#         return self.axes
#
#     def get_statics(self) -> List[Static]:
#         """ List of :class: Static (i.e. static parameter) """
#         return self.statics
#
#     def _extract_sweep_info(self) -> Dict:
#         d = {}
#         key_fmt = [
#             ['sweep_dims', int],
#             ['sweep_full_names', str],
#             ['sweep_names', str],
#             ['shape', int],
#             ['readout_full_names', str],
#             ['readout_names', str],
#         ]
#         for kf in key_fmt:
#             key, fmt = kf
#             d[key] = list(np.array(self.qc_data[key][key]).astype(fmt))
#         return d
#
#     def to_datafile(self):
#         # Add datasets to datafile
#         df = Datafile()
#         df.add_datasets(*self.datasets)
#         # df.add_statics(*self.statics) #TODO
#         # df.metadata(self.qc_ds.snapshot)
#         return df
#
#     def _extract_datasets(self):
#         qc_data = self.qc_data
#         params_specs = self.qc_params
#         sweep_info = self._sweep_info
#         params_metadata = self._controls_parameters()
#
#         readouts = sweep_info['readout_full_names']
#         sweeps = sweep_info['sweep_full_names']
#         prefix = 'controls_'
#         axes = []
#         datasets = []
#
#         for pinfo in params_specs:
#             full_name = pinfo.name
#             unit = pinfo.unit
#             if full_name[:len(prefix)] != prefix:
#                 # Ignore parameter if it has no 'control_' as prefix
#                 continue
#             if full_name in readouts:
#                 # Create a Dataset if it is a readout parameter
#                 idx = readouts.index(full_name)
#                 name = sweep_info['readout_names'][idx]
#                 dsi = Dataset(
#                     name=name,
#                     unit=unit,
#                     value=qc_data[full_name][full_name].reshape(*sweep_info['shape']).T,
#                     metadata=params_metadata[name],
#                 )
#                 datasets.append(dsi)
#             elif full_name in sweeps:
#                 # Create an Axis if it is a swept parameter
#                 idx = sweeps.index(full_name)
#                 name = sweep_info['sweep_names'][idx]
#                 ax = Axis(
#                     name=name,
#                     unit=unit,
#                     value=np.squeeze(qc_data[full_name][full_name]),
#                     dim=int(sweep_info['sweep_dims'][idx]) - 1,  # to be fixed in Sweep class?
#                     metadata=params_metadata[name],
#                 )
#                 axes.append(ax)
#
#         # Add axes to each dataset
#         [dsi.add_axes(*axes) for dsi in datasets]
#         return datasets, axes
#
#     def _extract_statics(self):
#         sweep_info = self._sweep_info
#         params_metadata = self._controls_parameters()
#
#         readouts = sweep_info['readout_names']
#         sweeps = sweep_info['sweep_names']
#         control_names = readouts + sweeps
#
#         statics = []
#         for pname, metadata in params_metadata.items():
#             if pname in control_names:
#                 continue
#             st = Static(
#                 name=pname,
#                 unit=metadata['unit'],
#                 value=metadata['value'],
#                 metadata=metadata,
#             )
#             statics.append(st)
#         return statics
#
#     def _controls_snapshot(self):
#         return self.qc_ds.snapshot['station']['components']['controls']
#
#     def _controls_parameters(self):
#         d = self._controls_snapshot()
#         return d['parameters']
