import json
import os
import numpy as np
import qcodes as qc
from IPython.core.display import Markdown, Latex
from IPython.core.display_functions import display

from qube.postprocess.figures import Plot1D, Plot2D
from qube.postprocess.dataset import Dataset, Axis
from qube.postprocess.datafile import Datafile

from qcodes import load_by_id


"""-----------------------------
QuCoDes related function
------------------------------"""
def get_db_location():
    """
    This function gives easy access to the experiments.db location.
    """
    return qc.config['core']['db_location']


def set_db_location(path:str,
                    name:str='experiments.db'):
    """
    Set the database location.

    Args:
        path:
            path to the database
        name:
            name of the database. Default is 'experiments.db'.
    """
    qc.config['core']['db_location'] = path + '/' + name

"""------------------------------
Measurement note function
--------------------------------"""
def mnote(run_id:int,
          note_str:str,
          overwrite:bool = False,
          output:str = 'markdown'):
    """
    This function read snapshot from the database of 'run_id'.
    Then add measurement note as 'note' in parallel with 'station'.

    Args:
        run_id (int): run_id
        note_str (str): measurement note
        overwrite (bool): In case 'note' already exists whether overwrite or not
        output (str): 'markdown': output given note string as markdown.
                      'latex': output given note string as latex.
                  else: do not output string.
    """
    if output == 'markdown':
        line_break = '<br>'
    elif output == 'latex':
        line_break = '\\\\'

    dataset = qc.load_by_id(run_id)
    snap = dataset.snapshot
    if 'note' in snap.keys():
        if overwrite:
            print('"note" already exists for the specified run. However, the note is overwritten.\n --------')
        else:
            s = snap['note']
            note_str = s + line_break + note_str
            print('"note" already exists for the specified run. Note string is added after existing note.\n --------')
    snap['note'] = note_str
    dataset.add_snapshot(json.dumps(snap), True)

    if output == 'markdown':
        display(Markdown(note_str))
    elif output == 'latex':
        display(Latex(note_str))


def get_exp_and_sample():
    """
    This function returns the name of the experiment and sample of the current qcodes measurement.
    The experiment name and the sample name are defined via the main folder having the form 'YYYYMMDD__experiment_name__sample_name'.
    Returns:
     - Dictionary of the form:
        { 'experiment_name':experiment_name, 'sample_name':sample_name }
    """
    folder_name = os.path.basename(os.path.split(os.getcwd())[0]) # Name of the base folder with format YYYYMMDD__experiment__sample
    folder_split = folder_name.split('__')                        # Array containing [date,experiment,sample]
    output = dict()
    output['experiment_name'] = folder_split[1]
    output['sample_name'] = folder_split[2]
    return output


def set_config(config:list = None):
    """
    This function applies a bunch of values on a set of qcodes paramters.
    The configuration mustw be provided in the form of a nested list having the following shape:
    [
        [ reference_to_qcodes_parameter_1 , value_1 ], # item 0
        [ reference_to_qcodes_parameter_2 , value_2 ], # item 1
        ...                                            # item ...
    ]
    """
    if not config is None:
        for item in config:
            item[0](item[1])
    else:
        raise('No config provided!')


def list_instruments(station:qc.Station):
    """
    This procedure displays the names of the instrument instances and their classes in form of a markdown table
    """
    output     =  'The qcodes station contains now the components:  \n\n'\
               +  '| Variable |   Class   |   Comments   |  \n'  \
               +  '| :------: | :-------: | :----------- |  \n'
    for instrument in station.components:
        inst_class = station.components[instrument].__class__.__name__
        try:
            comment = station.components[instrument].metadata['comments']
        except:
            comment = '-'
        output += '|   {:s}   |    {:s}   |      {:s}    |  \n'.format(instrument, inst_class,comment)
    display(Markdown(output))


"""------------------------------
Plotter and data conversion
--------------------------------"""

def convert_for_plotter(ID):
    """
    parameters:
    ID: id in the qcodes database

    return:
    dictionary of Dataset

    """
    dataset = load_by_id(ID)
    data = dataset.get_parameter_data()
    data_sweep_dims = list(np.array(data['sweep_dims']['sweep_dims']).astype(int))
    data_sweep_names = list(np.array(data['sweep_names']['sweep_names']))
    data_shape = list(np.array(data['shape']['shape']).astype(int))
    data_measured_name = []
    prefixe = 'controls_'

    parameters = dataset.get_parameters()
    ds_dict = {}
    for measured in parameters:  # create Dataset with values for measured parameters
        if measured.name[:len(prefixe)] == prefixe and measured.name[len(prefixe):] not in data_sweep_names:
            ds_dict[str(ID) + ' ds_' + measured.name] = Dataset(
                name=str(ID) + '_' + measured.name,
                unit=measured.unit,
                value=data[measured.name][measured.name].reshape(*data_shape).T)
            for swept in parameters:  # for each Dataset add the axes

                if swept.name[:len(prefixe)] == 'controls_' and swept.name[len(prefixe):] in data_sweep_names:
                    dim = data_sweep_dims[data_sweep_names.index(swept.name[9:])]
                    value = data[swept.name][swept.name][0]
                    ax = Axis(
                        name=swept.name,
                        unit=swept.unit,
                        value=value,
                        dim=int(dim) - 1,
                    )

                    ds_dict[str(ID) + ' ds_' + measured.name].add_axis(ax)
    return ds_dict


def extract_by_id(ids, title_prefix='Exp', save_datafile=False, save_name='datafile'):
    """
    This function extracts qcodes data via its run_id from the database and transforms it
    in dataset objects that are suitable for analysis and postprocessing.
    """
    ds_list = []

    # convert to Dataset
    if type(ids) == int:
        ds_dict = convert_for_plotter(ids)

        for key in ds_dict.keys():
            ds_list.append(ds_dict[key])

    else:
        for ID in ids:
            ds_dict = convert_for_plotter(ID)

            for key in ds_dict.keys():
                ds_list.append(ds_dict[key])
    if save_datafile:  # save as datafile
        df = Datafile()
        for ds in ds_list:
            df.add_dataset(ds)
        df.save(
            fullpath=os.path.join('datafile', save_name + '.json'),
            overwrite=True)
    if len(ds_list) > 1:
        return ds_list
    elif len(ds_list) == 1:
        return ds_list[0]


# def plot_jupyter(ids,dim_plot=1,title_prefix='Exp',save_options=None,save_datafile=False,save_name='datafile'):
#     ds_list=[]
#     if save_options==None:
#         save_options = {
#         'folder': '',
#         'extension': 'png',
#         'kwargs': {'dpi': 100, 'bbox_inches': 'tight'},
#         }
#     #convert to Dataset
#     if type(ids)==int:
#         ds_dict=convert_for_plotter(ids)

#         for key in ds_dict.keys():
#             ds_list.append(ds_dict[key])

#     else:
#         for ID in ids:
#             ds_dict=convert_for_plotter(ID)

#             for key in ds_dict.keys():
#                 ds_list.append(ds_dict[key])
#     #plot
#     if dim_plot==1:
#         p1 = Plot1D(ds_list, save_options=save_options, title_prefix=title_prefix)
#     else:
#         p1 = Plot2D(ds_list, save_options=save_options, title_prefix=title_prefix)

#     if save_datafile: #save as datafile
#         df = Datafile()
#         for ds in ds_list:
#             df.add_dataset(ds)
#         df.save(
#             fullpath=os.path.join('datafile',save_name+'.json'),
#             overwrite=True)

#     return(p1)

def exploreNd(input_arg, dim_plot=1, title_prefix='Exp', save_options=None, save_datafile=False, save_name='datafile'):
    """
    This function allows to explore one or multiple datasets via an interactive wizard within a jupyter notebook.

    input_arg ... Can be either:
                    - single instance or list of dataset objects (tools.datasets.dataset.Dataset)
                    - single instance or list of run-ids from qcodes database
    """

    ds_list = []
    if save_options == None:
        save_options = {
            'folder': '',
            'extension': 'png',
            'kwargs': {'dpi': 100, 'bbox_inches': 'tight'},
        }

    # Check if the input argument is a list or not
    if not type(input_arg) == list:
        input_arg = [input_arg]

    # Check if data needs to be loaded from qcodes database or if it is already a Dataset
    if type(input_arg[0]) == int:
        load_from_database = True
    else:
        load_from_database = False

    # Fill list of datasets:
    if load_from_database:
        for run_id in input_arg:
            ds_dict = convert_for_plotter(run_id)
            for key in ds_dict.keys():
                ds_list.append(ds_dict[key])
    else:
        for dataset in input_arg:
            ds_list.append(dataset)

    # Plot
    if dim_plot == 1:
        p1 = Plot1D(ds_list, save_options=save_options, title_prefix=title_prefix)
    else:
        p1 = Plot2D(ds_list, save_options=save_options, title_prefix=title_prefix)

    if save_datafile:  # save as datafile
        df = Datafile()
        for ds in ds_list:
            df.add_dataset(ds)
        df.save(
            fullpath=os.path.join('datafile', save_name + '.json'),
            overwrite=True)

    return (p1)


def explore1d(input_arg, **kwargs):
    _ = exploreNd(input_arg, dim_plot=1, **kwargs)
    return _


def explore2d(input_arg: int, **kwargs):
    _ = exploreNd(input_arg, dim_plot=2, **kwargs)
    return _