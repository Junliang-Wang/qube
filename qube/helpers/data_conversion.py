from qcodes.dataset.data_set import DataSet
from qube.postprocess.datafile import Datafile
from qube.postprocess.dataset import Axis, Dataset

import numpy as np


def qcodes_to_datafile(ds: DataSet = None) -> Datafile:
    """
    parameters:
    ds: qcodes dataset

    return:
    Datafile
    """
    qc_ds = ds
    id_ = qc_ds.run_id
    data = qc_ds.get_parameter_data()
    # A bit complicated to extract information
    data_sweep_dims = list(np.array(data['sweep_dims']['sweep_dims']).astype(int))
    data_sweep_names = list(np.array(data['sweep_names']['sweep_names']))
    data_shape = list(np.array(data['shape']['shape']).astype(int))
    data_measured_name = []  # ???
    prefixe = 'controls_'

    parameters = qc_ds.get_parameters()
    df = Datafile()
    for measured in parameters:  # create Dataset with values for measured parameters
        # redundant check?
        if measured.name[:len(prefixe)] == prefixe and measured.name[len(prefixe):] not in data_sweep_names:
            dsi = Dataset(
                name=str(id_) + '_' + measured.name,
                unit=measured.unit,
                value=data[measured.name][measured.name].reshape(*data_shape).T)
            for swept in parameters:  # for each Dataset add the axes
                # redundant check?
                if swept.name[:len(prefixe)] == 'controls_' and swept.name[len(prefixe):] in data_sweep_names:
                    dim = data_sweep_dims[data_sweep_names.index(swept.name[9:])]
                    value = data[swept.name][swept.name][0]
                    ax = Axis(
                        name=swept.name,
                        unit=swept.unit,
                        value=value,
                        dim=int(dim) - 1,
                    )
                    dsi.add_axis(ax)
            df.add_dataset(dsi)
    return df


""" Alias for qcodes_to_datafile """
qc2df = qcodes_to_datafile
