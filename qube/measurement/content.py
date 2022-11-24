from abc import ABC, abstractmethod
from typing import Dict, List, Any

import numpy as np
from qcodes import load_by_id
from qcodes.dataset.data_set import DataSetProtocol

from qube.postprocess.datafile import Datafile
from qube.postprocess.dataset import Dataset, Axis, Static


def qcodes_to_datafile(ds: DataSetProtocol = None) -> Datafile:
    expc_class = _find_loader(ds)
    expc = expc_class(ds)
    return expc.to_datafile()


def run_id_to_datafile(run_id: int) -> Datafile:
    qc_ds = load_by_id(run_id)
    return qcodes_to_datafile(qc_ds)


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

    def __init__(self, ds: DataSetProtocol = None):
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
    def readouts(self) -> List[Dataset]:
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

    def load(self, ds: DataSetProtocol):
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

    def _validate_qcodes_data(self, ds: DataSetProtocol):
        """
        Check if the qcodes dataset contains sweep information (from Controls.sweep)
        Comments:
            - This should be updated accordingly when Sweep class is improved
        """
        if not isinstance(ds, DataSetProtocol):
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

    def _extract_sweep_info(self) -> Dict[str, Any]:
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

    def to_datafile(self) -> Datafile:
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

    def _extract_statics(self) -> List[Static]:
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

    def _controls_snapshot(self) -> Dict:
        return self.qc_ds.snapshot['station']['components']['controls']

    def _controls_parameters(self):
        d = self._controls_snapshot()
        return d['parameters']


class SweeperContent(ExpContent):
    """ Class to extract from a qcodes.DataSet the information of an experiment performed with Sweeper class """

    def __init__(self, ds: DataSetProtocol = None):
        self.datasets = []
        self.axes = []
        self.statics = {}
        self.sweep_info = {}
        self.qc_ds = None
        self.qc_data = {}
        self.qc_params = []

        if ds is not None:
            self.load(ds)

    @property
    def readouts(self) -> List[Dataset]:
        """ Alias for datasets """
        return self.datasets

    def clear(self):
        self.datasets = []
        self.axes = []
        self.statics = {}
        self.sweep_info = {}
        self.qc_ds = None
        self.qc_data = {}
        self.qc_params = []

    def load(self, ds: DataSetProtocol):
        self._validate_qcodes_data(ds)
        self.clear()
        self.qc_ds = ds
        self.qc_data = self.qc_ds.get_parameter_data()
        self.qc_params = self.qc_ds.get_parameters()
        self.sweep_info = self._extract_sweep_info()
        self.sweep_info.update(self._extract_static_info())
        self.datasets = self._extract_datasets()
        self.statics = self._extract_statics()

    def load_by_id(self, run_id: int, *args, **kwargs):
        ds = load_by_id(run_id, *args, **kwargs)
        self.load(ds)

    def get_datasets(self) -> List[Dataset]:
        """ List of :class: Dataset (i.e. readouts) """
        return self.datasets

    def get_axes(self) -> List[Axis]:
        """ List of :class: Axis (i.e. swept parameter) """
        return self.axes

    def get_statics(self, key=None) -> List[Static]:
        """ List of :class: Static (i.e. static parameter) """
        key = key if key is not None else list(self.statics.keys())[0]
        return self.statics[key]

    def to_datafile(self) -> Datafile:
        # Add datasets to datafile
        df = Datafile()
        df.add_datasets(*self.datasets)
        # df.add_statics(*self.statics) #TODO
        # df.metadata(self.qc_ds.snapshot)
        return df

    def _extract_sweep_info(self) -> Dict[str, Any]:
        key_fmt = [
            ['sweep_shape', int],
            ['sweep_dims', int],
            ['sweep_axes_names', str],
            ['sweep_axes_full_names', str],
            ['sweep_axes_isbools', int],
            ['sweep_readouts_names', str],
            ['sweep_readouts_full_names', str],
            ['sweep_readouts_dim0s', int],
            ['sweep_note', str],
            ['static_labels', str],
            ['static_names', str],
            ['static_units', str],
            ['static_isbools', int],
        ]
        return self._fmt_qc_data(key_fmt)

    def _extract_static_info(self) -> Dict[str, Any]:
        key_fmt = []
        for label in self.sweep_info['static_labels']:
            # key_fmt.append([f'static_{label}_names', str])
            key_fmt.append([f'static_values_{label}', None])
            # key_fmt.append([f'static_{label}_units', str])
            # key_fmt.append([f'static_{label}_isbool', int])
        return self._fmt_qc_data(key_fmt)

    def _fmt_qc_data(self, key_fmt) -> Dict[str, Any]:
        d = {}
        for kf in key_fmt:
            key, fmt = kf
            arr = np.array(self.qc_data[key][key])
            if fmt is not None: arr = arr.astype(fmt)
            d[key] = list(arr)
        return d

    def _extract_axes(self) -> List[Axis]:
        qc_data = self.qc_data
        params_specs = self.qc_params
        sweep_info = self.sweep_info

        ax_fnames = sweep_info['sweep_axes_full_names']
        ax_names = sweep_info['sweep_axes_names']
        dims = sweep_info['sweep_dims']
        isbools = sweep_info['sweep_axes_isbools']
        params_names = [p.name for p in params_specs]

        axes = []
        for fname, name, dim, isbool in zip(ax_fnames, ax_names, dims, isbools):
            if fname not in params_names:
                continue
            param_spec = params_specs[params_names.index(fname)]
            fname = param_spec.name
            unit = param_spec.unit
            value = np.array(qc_data[fname][fname])
            if isbool == 1: value = value.astype(bool)
            ax = Axis(
                name=name,
                unit=unit,
                value=value,
                dim=int(dim),
                metadata={},
            )
            axes.append(ax)
        return axes

    def _extract_datasets(self) -> List[Dataset]:
        qc_data = self.qc_data
        params_specs = self.qc_params
        sweep_info = self.sweep_info

        rd_fnames = sweep_info['sweep_readouts_full_names']
        rd_names = sweep_info['sweep_readouts_names']
        dim0s = sweep_info['sweep_readouts_dim0s']
        sweep_shape = sweep_info['sweep_shape']
        params_names = [p.name for p in params_specs]

        axes = self._extract_axes()
        datasets = []
        for fname, name, dim0 in zip(rd_fnames, rd_names, dim0s):
            if fname not in params_names:
                continue
            param_spec = params_specs[params_names.index(fname)]
            fname = param_spec.name
            unit = param_spec.unit
            if dim0 == 1:
                shape = list(sweep_shape)
                ds_axes = []
                for ax in axes:
                    axi = ax.copy()
                    axi.dim = axi.dim - 1
                    ds_axes.append(axi)
            else:
                shape = [dim0] + list(sweep_shape)
                ds_axes = [ax.copy() for ax in axes]

            shape = tuple(shape)
            value = np.array(qc_data[fname][fname]).reshape(shape, order='F')
            ds = Dataset(
                name=name,
                unit=unit,
                value=value,
                axes=ds_axes,
                metadata={},
            )

            datasets.append(ds)
        return datasets

    def _extract_statics(self) -> Dict[str, List[Static]]:
        sweep_info = self.sweep_info
        statics = {}
        for label in sweep_info['static_labels']:
            statics[label] = self._extract_static_config(label)
        return statics

    def _extract_static_config(self, key: str) -> List[Static]:
        sweep_info = self.sweep_info
        names = sweep_info[f'static_names']
        units = sweep_info[f'static_units']
        isbools = sweep_info[f'static_isbools']
        values = sweep_info[f'static_values_{key}']

        statics = []
        for name, unit, value, isbool in zip(names, units, values, isbools):
            value = np.array(value)
            if isbool == 1: value = value.astype(bool)
            st = Static(
                name=name,
                unit=unit,
                value=value,
                metadata={},
            )
            statics.append(st)
        return statics

    def _validate_qcodes_data(self, ds: DataSetProtocol):
        """
        Check if the qcodes dataset contains sweep information (from Controls.sweep)
        Comments:
            - This should be updated accordingly when Sweep class is improved
        """
        if not isinstance(ds, DataSetProtocol):
            raise TypeError(f'Input has be a qcodes dataset')
        data = ds.get_parameter_data()
        valid = 'sweep_dims' in data.keys()
        if not valid:
            raise ValueError(f'Invalid qcodes dataset. It does not contain sweep information.')


def _find_loader(ds: DataSetProtocol = None):
    qc_data = ds.get_parameter_data()
    if 'return2initial' in qc_data.keys():
        return QcodesDatasetContent
    elif 'sweep_readouts_names' in qc_data.keys():
        return SweeperContent
    else:
        raise ValueError('Not found a valid loading protocol')
