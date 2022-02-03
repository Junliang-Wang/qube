import os
import re
from copy import copy

# Imports for interactive wizard:
import ipywidgets as ipyw
import matplotlib
import matplotlib.pyplot as plt
import numpy as np
from IPython.display import display
from cycler import cycler
from gdsii import types
from gdsii.record import Record

from qube.layout.config import LayoutConfig

default_rc_string = {
    'color': 'black',
    'weight': 'normal',
    'size': 8,
    'horizontalalignment': 'center',
    'verticalalignment': 'center',
}
default_rc_shape = {
    'facecolor': 'grey',
    'alpha': 0.8,
    'edgecolor': 'grey',
}
default_rc_figure = {
    'figsize_x': 8,
    'figsize_y': 4,
    'lim_factor': 1.0,
    'extra_left': 0.0,
    'extra_right': 0.0,
    'extra_top': 0.0,
    'extra_bottom': 0.0,
}


class LayoutGDS(object):
    elements = {
        'id': [],
        'xy': [],
        'name': [],
        'rc': [],
        'type': [],  # string or shape
        'label': [],
    }

    def __init__(self, fullpath):
        self.fullpath = fullpath
        self.load_GDS()
        self.read_elements()
        self.read_strings()
        self.read_shapes()
        self.set_default_rc()

    def load_GDS(self):
        self.structure = structurefromGDS(self.fullpath)

    def set_default_rc(self):
        global default_rc_figure
        global default_rc_string
        global default_rc_shape
        self.rc_figure = default_rc_figure
        self.rc_string = default_rc_string
        self.rc_shape = default_rc_shape

    def load_layout_config(self, fullpath):
        self.load_shapes_config(fullpath)
        self.load_strings_config(fullpath)

    #         self.load_rc_string_config(fullpath)
    #         self.load_rc_shape_config(fullpath)
    #         self.load_rc_figure_config(fullpath)

    def load_shapes_config(self, fullpath):
        config = LayoutConfig(fullpath)
        shapes_config = config.get_shapes_config()
        for name, ids in shapes_config.items():
            for id in ids:
                self.set_elements_property_value(id, 'name', name)
                self.set_elements_property_value(id, 'label', name)

    def load_strings_config(self, fullpath):
        config = LayoutConfig(fullpath)
        strings_config = config.get_strings_config()
        for name, ids in strings_config.items():
            for id in ids:
                self.set_elements_property_value(id, 'name', name)
                self.set_elements_property_value(id, 'label', name)

    def load_rc_string_config(self, fullpath):
        config = LayoutConfig(fullpath)
        section = 'RC_STRING'
        if section in config.sections:
            rc_string = config.get_section_config(section)
            rc_string['size'] = float(rc_string['size'])
            self.rc_string.update(rc_string)

    def load_rc_shape_config(self, fullpath):
        config = LayoutConfig(fullpath)
        section = 'RC_SHAPE'
        if section in config.sections:
            rc_shape = config.get_section_config(section)
            rc_shape['alpha'] = float(rc_shape['alpha'])
            self.rc_shape.update(rc_shape)

    def load_rc_figure_config(self, fullpath):
        config = LayoutConfig(fullpath)
        section = 'RC_FIGURE'
        if section in config.sections:
            rc_figure = config.get_section_config(section)
            for key, value in rc_figure.items():
                rc_figure[key] = float(rc_figure[key])

            self.rc_figure.update(rc_figure)

    def read_elements(self):
        elements_list = self.structure()
        self.elements['id'] = []
        self.elements['xy'] = []
        self.elements['name'] = []
        self.elements['label'] = []
        self.elements['rc'] = []
        self.elements['type'] = []
        for i, element in enumerate(elements_list):
            self.elements['id'].append(i)
            self.elements['xy'].append(element.transpose())  # For x,y = self.elements
            self.elements['name'].append(None)
            self.elements['label'].append(None)
            self.elements['rc'].append({})
            self.elements['type'].append('Undefined')
        self.elements_size = i + 1

    def read_strings(self):
        self.strings_ids = []
        for key, value in self.structure.string_infos.items():
            index = self.get_elements_index('id', key)
            self.strings_ids.append(key)
            self.elements['type'][index] = 'string'
            self.elements['name'][index] = value
            self.elements['label'][index] = value
            self.elements['rc'][index] = copy(default_rc_string)
        self.strings_size = len(self.strings_ids)

    def read_shapes(self):
        self.shapes_ids = []
        for i in range(self.elements_size):
            if self.elements['type'][i] != 'string':
                self.shapes_ids.append(self.elements['id'][i])
                self.elements['type'][i] = 'shape'
                self.elements['rc'][i] = copy(default_rc_shape)
        self.shapes_size = len(self.shapes_ids)

    def get_elements_index(self, key, target):
        index = self.elements[key].index(target)
        return index

    def set_elements_property_value(self, id, property, value):
        index = self.get_elements_index('id', id)
        self.elements[property][index] = value

    def get_elements_property_value(self, id, property):
        index = self.get_elements_index('id', id)
        value = self.elements[property][index]
        return value

    def get_ids_with_property_value(self, property, target_value):
        ids = []
        for i in range(self.elements_size):
            cur_value = self.elements[property][i]
            if cur_value == target_value:
                id = self.elements['id'][i]
                ids.append(id)
        return id

    def layout_limits(self, extra_factor=1.2):
        xlim = np.array([0, 0])
        ylim = np.array([0, 0])
        for xy in self.elements['xy']:
            x, y = xy
            xlim[0] = min(xlim[0], np.amin(x))
            xlim[1] = max(xlim[1], np.amax(x))
            ylim[0] = min(ylim[0], np.amin(y))
            ylim[1] = max(ylim[1], np.amax(y))
        xlim = xlim * extra_factor
        ylim = ylim * extra_factor
        return xlim, ylim

    def plot_elements(self):
        nb = self.elements_size
        fig, ax = plt.subplots()
        colormap = plt.cm.hsv
        colors = [colormap(i) for i in np.linspace(0, 1, nb)]
        ax.set_prop_cycle(cycler('color', colors))
        for i in range(nb):
            x, y = self.elements['xy'][i]
            ax.fill(x, y)
            ax.text(x[0], y[0], i)
        return fig, ax

    def plot_layout(self):
        rc_fig = self.rc_figure
        figsize = (rc_fig['figsize_x'], rc_fig['figsize_y'])
        fig, ax = plt.subplots(1, figsize=figsize)
        ax.axis('off')
        for id in self.shapes_ids:
            x, y = self.get_elements_property_value(id, 'xy')
            rc = self.get_elements_property_value(id, 'rc')
            rc_shape = copy(self.rc_shape)
            rc_shape.update(rc)
            # rc.update(self.rc_shape)
            ax.fill(x, y, **rc_shape)

        for id in self.strings_ids:
            x, y = self.get_elements_property_value(id, 'xy')
            label = self.get_elements_property_value(id, 'label')
            rc = self.get_elements_property_value(id, 'rc')
            rc_string = copy(self.rc_string)
            rc_string.update(rc)
            # rc.update(self.rc_string)
            # rc['horizontalalignment']='center'
            ax.text(x, y, label, **rc_string)
        lim_factor = rc_fig['lim_factor']
        xlim, ylim = self.layout_limits(extra_factor=lim_factor)
        xlim = (xlim[0] + rc_fig['extra_left'], xlim[1] + rc_fig['extra_right'])
        ylim = (ylim[0] + rc_fig['extra_bottom'], ylim[1] + rc_fig['extra_top'])
        ax.set_xlim(xlim)
        ax.set_ylim(ylim)
        return fig, ax

    def set_dummy_label(self, label):
        elems = self.elements
        n = len(elems['id'])
        for i in range(n):
            elems['label'][i] = label

    def config_wizard(self,
                      names: list,  # names of controls to allocate to the strings and shapes
                      export_file=None,  # location of the file to export the GDS configuration
                      default_file=None,  # location of reference file to import footer for GDS config
                      ):

        if not os.path.exists(default_file):
            raise Exception('File with format-defaults \"{:s}\" not found!'.format(default_file))

        shapes_data = list()
        strings_data = list()

        N_elements = len(self.elements['id'])

        shape_id = ipyw.IntSlider(
            value=0,
            min=0,
            max=N_elements,
            step=1,
        )
        shape_id.layout.visibility = 'hidden'

        textbox = ipyw.Label(value='Nothing')

        nothing = 'Nothing'
        temp_names = names + [nothing]
        dropdown_controls = ipyw.Dropdown(
            options=temp_names,
            description='Control:',
        )

        move_button = ipyw.Button(description='Choose')

        fig, ax = self.plot_layout()
        shapes = ax.get_children()[0:N_elements]

        def is_polygon(element_id):
            condition1 = element_id in self.shapes_ids
            condition2 = isinstance(shapes[element_id], matplotlib.patches.Polygon)
            return condition1 and condition2

        def is_text(element_id):
            condition1 = element_id in self.strings_ids
            condition2 = isinstance(shapes[element_id], matplotlib.text.Text)
            return condition1 and condition2

        def highlight_shape(element_id):
            if is_polygon(element_id):
                shapes[element_id].set_facecolor('red')
                shapes[element_id].set_edgecolor('black')
                textbox.value = 'Element #{:d}: Polygon'.format(element_id)
            if is_text(element_id):
                shapes[element_id].set_color('red')
                shapes[element_id].set_weight('bold')
                textbox.value = 'Element #{:d}: Text'.format(element_id)

        def hide_shape(element_id):
            if is_polygon(element_id):
                shapes[element_id].set_facecolor('grey')
                shapes[element_id].set_edgecolor('grey')
                shapes[element_id].set_alpha(0.3)
            if is_text(element_id):
                shapes[element_id].set_color('grey')
                shapes[element_id].set_weight('normal')
                shapes[element_id].set_alpha(0.8)

        def note_selection(element_id):

            if dropdown_controls.value != nothing:
                temp_str = '{:s} = {:d}'.format(dropdown_controls.value, element_id)
                if is_polygon(element_id):
                    shapes_data.append(temp_str)
                if is_text(element_id):
                    strings_data.append(temp_str)
                temp_options = list(dropdown_controls.options)
                temp_options.remove(dropdown_controls.value)
                dropdown_controls.options = temp_options

            # Display all options when string allocation starts:
            if element_id == self.shapes_ids[-1]:
                dropdown_controls.options = names + [nothing]

            dropdown_controls.value = dropdown_controls.options[0]

        #             if element_id == self.shapes_ids[-1]:
        #                 temp_names = names + [None]
        #                 dropdown_controls.options = temp_names

        def write_to_file(filename='../configurations/gds_config.ini',
                          default_file=None):
            with open(filename, 'a') as gds_config:
                gds_config.write('[SHAPES]\n')
                for shapes_entry in shapes_data:
                    gds_config.write(shapes_entry + "\n")
                gds_config.write('\n')
                gds_config.write('[STRINGS]\n')
                for strings_entry in strings_data:
                    gds_config.write(strings_entry + "\n")
                gds_config.write('\n')
                if default_file != None:
                    with open(default_file) as rc_default:
                        for rc_line in rc_default:
                            gds_config.write(rc_line)
            print('Wrote GDS-configuration file: \"{:s}\"'.format(filename))

        def close_widgets():
            textbox.close()
            dropdown_controls.close()
            move_button.close()

        def advance_wizard(button):
            note_selection(shape_id.value)  # NOTE SELECTION
            hide_shape(shape_id.value)  # HIDE CURRENT SHAPE
            shape_id.value = shape_id.value + 1  # GO TO NEXT SHAPE
            if shape_id.value < N_elements:
                highlight_shape(shape_id.value)  # HIGHLIGHT NEXT SHAPE
                fig.canvas.draw()  # UPDATE PLOT
            elif shape_id.value == N_elements:  # IF FINISH
                close_widgets();
                hide_shape(shape_id.value - 1)  # CLOSE WIDGETS AND
                write_to_file(export_file, default_file)  # SAVE SELECTIONS TO FILE

        move_button.on_click(advance_wizard)

        highlight_shape(shape_id.value)
        dropdown_controls.value = dropdown_controls.options[0]
        display(shape_id, textbox, dropdown_controls, move_button)


# if __name__ == '__main__':
#     # sample_gds = sv.PATH_Sample_gds
#     sample_gds = './GDS/'
#     layout_1 = LayoutGDS(sample_gds)

#     # layout_1.plot_elements()
#     # layout_1.plot_layout()
#     # plt.show()

#     configfile = sv.PATH_Sample_layout_config
#     layout_1.load_layout_config(configfile)

#     datafile = 'DC1_SD_TR_3.h5'
#     # datafile = 'pinch_4K_LD2_LV2_1.h5'
#     exp_path = sv.PATH_experiments_and_data
#     datapath = os.path.join(exp_path,datafile)

#     gates = LayoutContent(datapath,FastRampMode=False)
#     gates.set_to_layout(layout=layout_1)
#     layout_1.plot_layout()
#     plt.show()
class structurefromGDS(object):
    """
    Interface to convert the polygons from GDS files into point lists that
    can be used to calculate the potential landscapes.
    Reads gds file
    outputs pointlist when called
    """

    def __init__(self, fname):
        self.fname = fname
        self.units = []
        self.pointlists = []
        self.string_infos = {}

    def show_data(self, rec):
        """Shows data in a human-readable format."""
        if rec.tag_type == types.ASCII:
            return '"%s"' % rec.data.decode()  # TODO escape
        elif rec.tag_type == types.BITARRAY:
            return str(rec.data)
        return ', '.join('{0}'.format(i) for i in rec.data)

    def main(self):
        """
        open filename (if exists)
        read units
        get list of polygons
        """
        #        test = []
        no_of_Structures = 0
        string_position = []
        strings = []

        with open(self.fname, 'rb') as a_file:
            for rec in Record.iterate(a_file):
                #                test.append([rec.tag_name, rec.data, rec.tag_type])
                if rec.tag_type == types.NODATA:
                    pass
                else:
                    #                    print('%s: %s' % (rec.tag_name, show_data(rec)))
                    #                    print('%s:' % (rec.tag_name))
                    if rec.tag_name == 'UNITS':
                        """
                        get units
                        """
                        unitstring = self.show_data(rec)
                        self.units = np.array(re.split(',', unitstring)).astype(float)

                    elif rec.tag_name == 'XY':
                        no_of_Structures += 1
                        """
                        get pointlist
                        """
                        # get data
                        datastring = self.show_data(rec)
                        # split string at , and convert to float
                        data = np.array(re.split(',', datastring)).astype(float)
                        # reshape into [[x1,y1],[x2,y2],...]
                        # print((len(data)/2, 2))
                        if len(data) > 2:
                            data = np.reshape(data, (int(len(data) / 2), 2))[:-1]
                        else:
                            data = np.reshape(data, (int(len(data) / 2), 2))
                        self.pointlists.append(data)
                    elif rec.tag_name == 'STRING':
                        string_position.append(no_of_Structures - 1)
                        strings.append(rec.data)
        self.string_infos = dict(zip(string_position, strings))

    def __call__(self):
        """
        execute main
        return list of polygons with correct SI-units (scaled by units)
        """
        self.main()
        #        return np.array(self.pointlists) * self.units[1]
        #        return np.multiply(np.array(self.pointlists), self.units[1])
        return np.array(self.pointlists, dtype=list)
