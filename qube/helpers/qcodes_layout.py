import os
from copy import deepcopy

import h5py
import matplotlib.pyplot as plt
import numpy as np
import qcodes as qc

import qube
# from qube.helpers.qufox_layout import LayoutContent
from qube.layout.gds import LayoutGDS

controls_name = 'controls'
sweep_info_keys = ['fast_sweep', 'note', 'return2initial', 'shape', 'sweep_dims', 'sweep_names']


class LayoutContent(object):
    def __init__(self,
                 snapshot_controls: dict = None,  # snapshot of controls class
                 data: qc.dataset.data_set.DataSet = None,  # snapshot of measurement class
                 FastRampMode=True):
        self.snapshot_controls = snapshot_controls

        if data != None:
            self.data_provided = True
            data_dict = dict()
            data_dict_raw = data.get_parameter_data()
            for key in sweep_info_keys:
                data_dict[key] = data_dict_raw[key][key]
                if key == 'note':
                    print(data_dict[key])
            self.data_dict = data_dict
        else:
            self.data_provided = False

        self.gates = self.get_gates_from_datafile()

    #         # if FastRampMode:
    #         if False: # Deactivated by now
    #             self.fast_ramp_gates = self.get_fast_ramp_gates(gate_prefix='dV_')
    #             self.update_gates(self.fast_ramp_gates)

    def get_gates_from_datafile(self):
        # Qcodes dataset
        gates = {}
        gates['full_name'] = []
        gates['name'] = []
        gates['values'] = []
        gates['units'] = []
        gates['static'] = []
        #         gates['readout'] = []
        gates['sweep_dim'] = []

        if self.data_provided:  # if with measurement
            sweep_names = list(self.data_dict['sweep_names'])
            sweep_dims = list(self.data_dict['sweep_dims'].astype(int))
            shape = list(self.data_dict['shape'].astype(int))

        for control_name, control_snapshot in self.snapshot_controls.items():

            static = True  # No sweep per default
            readout = False  # No readout per default
            sweep_dim = -1
            if self.data_provided:  # if with measurement
                #                 control_full_name = control_snapshot['full_name']
                if control_name in sweep_names:
                    static = False
                    sweep_dim = sweep_dims[sweep_names.index(control_name)]
            #                 if control_full_name in readouts:
            #                     readout = True

            gates['full_name'].append(control_snapshot['full_name'])
            gates['name'].append(control_snapshot['name'])
            gates['values'].append(control_snapshot['value'])
            gates['units'].append(control_snapshot['unit'])
            gates['static'].append(static)
            #             gates['readout'].append(readout)
            gates['sweep_dim'].append(sweep_dim)

        return gates

    def get_fast_ramp_gates(self, gate_prefix='dV_'):
        gates = {}
        gates['full_name'] = []
        gates['values'] = []
        gates['static'] = []
        gates['sweep_dim'] = []
        prefix_len = len(gate_prefix)
        with h5py.File(self.fullpath, 'r') as datafile:
            labview = datafile['DRIVERS']['labview']
            fs = labview['fast_sequence']
            instructions = fs['instructions'].attrs.items()
            fast_ramp_gates = []
            for order, instruction in instructions:
                if gate_prefix in instruction and instruction not in fast_ramp_gates:
                    fast_ramp_gates.append(instruction)
        nb_gates = len(fast_ramp_gates)
        gates['full_name'] = [gate[prefix_len:] for gate in fast_ramp_gates]
        gates['values'] = [0] * nb_gates
        gates['static'] = [False] * nb_gates
        gates['sweep_dim'] = [0] * nb_gates
        return gates

    def update_gates(self, gates):
        nb_gates = len(gates['full_name'])
        for i in range(nb_gates):
            name = gates['full_name'][i]
            values = gates['values'][i]
            static = gates['static'][i]
            sweep_dim = gates['sweep_dim'][i]
            if name in self.gates['full_name']:
                index = self.gates['full_name'].index(name)
                self.gates['values'][index] = values
                self.gates['static'][index] = static
                self.gates['sweep_dim'][index] = sweep_dim
            else:
                self.gates['full_name'].append(name)
                self.gates['values'].append(values)
                self.gates['static'].append(static)
                self.gates['sweep_dim'].append(sweep_dim)

    def get_filtered_with_names(self, name_list):
        gates = deepcopy(self.gates)
        nb = len(gates['full_name'])
        pop_indexes = []
        for i in range(nb):
            if gates['full_name'][i] not in name_list:
                pop_indexes.append(i)
        pop_indexes.sort(reverse=True)
        for index in pop_indexes:
            for values in gates.values():
                values.pop(index)
        return gates

    def add_default_labels(self):
        gates = self.gates
        gates['label'] = []
        nb = len(gates['full_name'])
        for i in range(nb):
            if gates['static'][i]:
                label = '{:s}={:.3f} {:s}'.format(gates['name'][i], gates['values'][i], gates['units'][i])
            #                 label = '{0}={1}{2}'.format(gates['name'][i],gates['values'][i],gates['units'][i])
            else:
                label = '{}_dim_{}'.format(gates['name'][i], gates['sweep_dim'][i])
            gates['label'].append(label)

    def set_gates_color(self):
        gates = self.gates
        gates['color'] = []
        #         colormap = plt.cm.rainbow
        nb_sweep_gates = self.count_non_static()
        #         if nb_sweep_gates > 0:
        #             max_dim = max(gates['sweep_dim'])
        #             color_points = max_dim + 1
        #             colors = [colormap(i) for i in np.linspace(0, 1, color_points)]
        nb = len(gates['full_name'])
        for i in range(nb):
            if gates['static'][i]:
                gates['color'].append('default')
            else:
                sweep_dim = gates['sweep_dim'][i]
                print('sweep_dim', sweep_dim)
                #                 gates['color'].append(colors[sweep_dim])
                gates['color'].append(plt.cm.Set1(int(sweep_dim)))

    def count_non_static(self):
        gates = self.gates
        static_count = np.count_nonzero(gates['static'])
        total_gates = len(gates['static'])
        non_static_count = total_gates - static_count
        return non_static_count

    def set_to_layout(self, layout):
        """
        This function applies the color scheme and labels of a certain setting of gates.
        """
        valid_gates = layout.elements['name']
        self.gates = self.get_filtered_with_names(valid_gates)
        self.add_default_labels()
        self.set_gates_color()
        gates = self.gates
        #         # Go through gates and allocate accordingly colors and labels:
        #         for gate_name in self.gates['full_name']:

        for idx, element_id in enumerate(layout.elements['id']):
            element_type = layout.get_elements_property_value(element_id, 'type')
            rc = layout.get_elements_property_value(element_id, 'rc')
            name = layout.get_elements_property_value(element_id, 'name')
            if name == None or name not in gates['full_name']:
                continue
            gate_index = gates['full_name'].index(name)
            # gate_indexes = [index for index, gate in enumerate(gates['full_name']) if gate == name]
            # for gate_index in gate_indexes:
            if not gates['static'][gate_index]:
                if element_type == 'string':
                    rc['color'] = gates['color'][gate_index]
                elif element_type == 'shape':
                    rc['facecolor'] = gates['color'][gate_index]
                layout.set_elements_property_value(element_id, 'rc', rc)

            label = gates['label'][gate_index]
            layout.set_elements_property_value(idx, 'label', label)


#         return layout

def is_static(values):
    static = values.size == 1
    return static


def get_sweep_dim(values):
    shape = np.array(values.shape)
    sweep_dim = np.argwhere(shape != 1)
    sweep_dim = np.squeeze(sweep_dim)
    if sweep_dim.size == 0:
        sweep_dim = -1
    return sweep_dim


def display_layout(
        experiment: qube.Controls,
        run_id: int,
        # data: qc.dataset.data_set.DataSet = None,  # Optional: Extract information from a dataset
        gds_path='..\\configurations\\sample.GDS',
        gds_conf='..\\configurations\\gds_config.ini',
):
    """
    This function displays the controls of your experiment via a GDS layout.
    If no data is passed, the current values of your controls are shown.
    If data is passed, the control values and sweeps from the dataset are displayed.
    """

    # Extract information of controls and measurement (optional, if dataset is provided)
    # if data == None:
    #     snapshot_controls = controls.snapshot()['parameters']
    # else:
    data = qc.load_by_id(run_id)
    snapshot_controls = data.snapshot['station']['components']['controls']['parameters']

    # Make layout
    temp_layout = LayoutGDS(gds_path)

    if not os.path.exists(gds_conf):
        # Run wizard if layout config file is not existing
        print('GDS config file does not exist ... launching wizard ...')
        full_names_of_controls = [i['full_name'] for i in experiment.snapshot()['parameters'].values()]
        temp_layout.config_wizard(
            names=full_names_of_controls,
            export_file=gds_conf,
            default_file='..\\tools\\plot\\LayoutLibrary\\db\\default.ini'
        )

    else:

        # Load layout config file
        temp_layout.load_layout_config(gds_conf)

        # Extract informations on controls and measurement
        gates = LayoutContent(snapshot_controls, data)
        gates.set_to_layout(layout=temp_layout)

        # Plot
        fig, ax = temp_layout.plot_layout()
        plt.show()


if __name__ == '__main__':
    pass
#     import Utility.SHARED_variables as sv
#     import os

#     # datafile = 'BM_SB_Bap_5.h5'
#     datafile = 'TestLD2_1.h5'
#     exp_path = sv.PATH_experiments_and_data
#     datapath = os.path.join(exp_path,datafile)

#     gates = LayoutContent(datapath, FastRampMode=True)
#     # with h5py.File(datapath,'r') as datafile:
#     #     fs = datafile['DRIVERS']['labview']['fast_sequence']
#     #     values = np.array(fs['values'])
#     #     gate =  datafile['DRIVERS']['labview']['RH2']['values']
#     #     gate= np.array(gate)
