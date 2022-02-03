from copy import deepcopy

import h5py
import matplotlib.pyplot as plt
import numpy as np


class LayoutContent(object):
    def __init__(self, fullpath, FastRampMode=True):
        # Problem to read the FastRampMode attribute in current h5py file
        # Temporary solution: FastRampMode argument
        # QuFox dafile: different version... No info for fast ramp gate...
        self.fullpath = fullpath
        self.gates = self.get_gates_from_datafile()
        # if FastRampMode:
        if False:  # Deactivated by now
            self.fast_ramp_gates = self.get_fast_ramp_gates(gate_prefix='dV_')
            self.update_gates(self.fast_ramp_gates)

    def get_gates_from_datafile(self):
        # QuFox datafile
        gates = {}
        gates['name'] = []
        gates['values'] = []
        gates['static'] = []
        gates['sweep_dim'] = []
        with h5py.File(self.fullpath, 'r') as datafile:
            labview = datafile['DRIVERS']['labview']
            for gate, info in labview.items():
                if gate == 'fast_sequence':
                    continue
                values = info['values']
                values = np.array(values)
                static = is_static(values)
                sweep_dim = get_sweep_dim(values)
                if static:
                    values = float(values)
                gates['name'].append(gate)
                gates['values'].append(values)
                gates['static'].append(static)
                gates['sweep_dim'].append(sweep_dim)
        return gates

    def get_fast_ramp_gates(self, gate_prefix='dV_'):
        gates = {}
        gates['name'] = []
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
        gates['name'] = [gate[prefix_len:] for gate in fast_ramp_gates]
        gates['values'] = [0] * nb_gates
        gates['static'] = [False] * nb_gates
        gates['sweep_dim'] = [0] * nb_gates
        return gates

    def update_gates(self, gates):
        nb_gates = len(gates['name'])
        for i in range(nb_gates):
            name = gates['name'][i]
            values = gates['values'][i]
            static = gates['static'][i]
            sweep_dim = gates['sweep_dim'][i]
            if name in self.gates['name']:
                index = self.gates['name'].index(name)
                self.gates['values'][index] = values
                self.gates['static'][index] = static
                self.gates['sweep_dim'][index] = sweep_dim
            else:
                self.gates['name'].append(name)
                self.gates['values'].append(values)
                self.gates['static'].append(static)
                self.gates['sweep_dim'].append(sweep_dim)

    def get_filtered_with_names(self, name_list):
        gates = deepcopy(self.gates)
        nb = len(gates['name'])
        pop_indexes = []
        for i in range(nb):
            if gates['name'][i] not in name_list:
                pop_indexes.append(i)
        pop_indexes.sort(reverse=True)
        for index in pop_indexes:
            for values in gates.values():
                values.pop(index)
        return gates

    def add_default_labels(self):
        gates = self.gates
        gates['label'] = []
        nb = len(gates['name'])
        for i in range(nb):
            if gates['static'][i]:
                # label = '{0}={1:.3f}'.format(gates['name'][i],gates['values'][i])
                label = '{0}={1}'.format(gates['name'][i], gates['values'][i])
            else:
                label = '{}_dim_{}'.format(gates['name'][i], gates['sweep_dim'][i])
            gates['label'].append(label)

    def set_gates_color(self):
        gates = self.gates
        gates['color'] = []
        colormap = plt.cm.rainbow
        nb_sweep_gates = self.count_non_static()
        if nb_sweep_gates > 0:
            max_dim = max(gates['sweep_dim'])
            color_points = max_dim + 1
            colors = [colormap(i) for i in np.linspace(0, 1, color_points)]
        nb = len(gates['name'])
        for i in range(nb):
            if gates['static'][i]:
                gates['color'].append('default')
            else:
                sweep_dim = gates['sweep_dim'][i]
                gates['color'].append(colors[sweep_dim])

    def count_non_static(self):
        gates = self.gates
        static_count = np.count_nonzero(gates['static'])
        total_gates = len(gates['static'])
        non_static_count = total_gates - static_count
        return non_static_count

    def set_to_layout(self, layout):
        valid_gates = layout.elements['name']
        self.gates = self.get_filtered_with_names(valid_gates)
        self.add_default_labels()
        self.set_gates_color()
        gates = self.gates
        for id in layout.elements['id']:
            type = layout.get_elements_property_value(id, 'type')
            rc = layout.get_elements_property_value(id, 'rc')
            name = layout.get_elements_property_value(id, 'name')
            if name == None or name not in gates['name']:
                continue
            gate_index = gates['name'].index(name)
            # gate_indexes = [index for index, gate in enumerate(gates['name']) if gate == name]
            # for gate_index in gate_indexes:
            if not gates['static'][gate_index]:
                if type == 'string':
                    rc['color'] = gates['color'][gate_index]
                elif type == 'shape':
                    rc['facecolor'] = gates['color'][gate_index]
                layout.set_elements_property_value(id, 'rc', rc)

            label = gates['label'][gate_index]
            layout.set_elements_property_value(id, 'label', label)


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


if __name__ == '__main__':
    import Utility.SHARED_variables as sv
    import os

    # datafile = 'BM_SB_Bap_5.h5'
    datafile = 'TestLD2_1.h5'
    exp_path = sv.PATH_experiments_and_data
    datapath = os.path.join(exp_path, datafile)

    gates = LayoutContent(datapath, FastRampMode=True)
    # with h5py.File(datapath,'r') as datafile:
    #     fs = datafile['DRIVERS']['labview']['fast_sequence']
    #     values = np.array(fs['values'])
    #     gate =  datafile['DRIVERS']['labview']['RH2']['values']
    #     gate= np.array(gate)
