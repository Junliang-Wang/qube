import re
from abc import ABC, abstractmethod
from copy import deepcopy
from dataclasses import dataclass, field
from typing import Dict, Optional
from typing import List, Tuple

import numpy as np
from cycler import cycler
from gdsii import types
from gdsii.record import Record
from matplotlib import pyplot as plt

from qube.layout.base import ConfigBase, ViewBase
from qube.measurement.content import ExpContent


# Imports for interactive wizard:
# import ipywidgets as ipyw
# import matplotlib
# from IPython.display import display
# from cycler import cycler


def default_rc_text():
    rc = {
        'color': 'black',
        'weight': 'normal',
        'size': 8,
        'horizontalalignment': 'center',
        'verticalalignment': 'center',
    }
    return rc


def default_rc_shape():
    rc = {
        'facecolor': 'grey',
        'alpha': 0.8,
        'edgecolor': 'grey',
    }
    return rc


@dataclass
class Element(ABC):
    """Class for an element for a view"""
    name: str
    points: List[Tuple[float, float]]
    id: Optional[int] = None
    metadata: Dict = field(default_factory=dict)

    @abstractmethod
    def get_x(self):
        """ Get list of x coordinates """

    @abstractmethod
    def get_y(self):
        """ Get list of y coordinates """


@dataclass
class Shape(Element):
    """Class for keeping track of a shape for a view"""
    rc: Dict = field(default_factory=dict)

    def get_x(self):
        return [p[0] for p in self.points]

    def get_y(self):
        return [p[1] for p in self.points]

    def get_xy(self):
        return self.get_x(), self.get_y()


@dataclass
class Text(Element):
    """Class for keeping track of a text for a view"""
    label: str = None
    rc: Dict = field(default_factory=dict)

    def get_x(self):
        return self.points[0][0]

    def get_y(self):
        return self.points[0][1]

    def get_xy(self):
        return self.points[0]


class ViewShapes(ViewBase):

    def __init__(self,
                 rc_shape=None,
                 rc_text=None,
                 ):
        self.shapes = []
        self.texts = []

        self._default_rc_shape_generator = default_rc_shape
        self._default_rc_text_generator = default_rc_text

        if rc_shape is not None:
            self.default_rc_shape = rc_shape

        if rc_text is not None:
            self.default_rc_text = rc_text

    @property
    def default_rc_shape(self):
        """ Return a deep copied dictionary of rc parameters for shapes """
        return self._default_rc_shape_generator()

    @default_rc_shape.setter
    def default_rc_shape(self, rc):
        if isinstance(rc, dict):
            self._default_rc_shape_generator = lambda: deepcopy(rc)
        else:
            raise ValueError('rc is not a dictionary')

    @property
    def default_rc_text(self):
        """ Return a deep copied dictionary of rc parameters for texts """
        return self._default_rc_text_generator()

    @default_rc_text.setter
    def default_rc_text(self, rc):
        if isinstance(rc, dict):
            self._default_rc_text_generator = lambda: deepcopy(rc)
        else:
            raise ValueError('rc is not a dictionary')

    def clear_elements(self):
        self.shapes = []
        self.texts = []

    @property
    def elements(self):
        return self.shapes + self.texts

    def add_shape(self, name: str, points: List[Tuple[float, float]]):
        name = str(name)
        element = Shape(
            name=name,
            points=points,
            rc=self.default_rc_shape,
        )
        self.shapes.append(element)

    def add_text(self, name: str, x: float, y: float):
        name = str(name)
        element = Text(
            name=name,
            points=[(x, y)],
            label=name,
            rc=self.default_rc_text,
        )
        self.texts.append(element)

    def change_name(self, old_name, new_name):
        shapes = self.get_shapes_with_name(old_name)
        for si in shapes:
            si.name = new_name
        texts = self.get_texts_with_name(old_name)
        for ti in texts:
            ti.name = new_name
            ti.label = new_name

    def set_rc_to_shapes(self, name, rc, update=False):
        shapes = self.get_shapes_with_name(name)
        for si in shapes:
            si.rc.update(rc) if update else dict(rc)

    def set_rc_to_all_shapes(self, rc, update=False):
        for si in self.shapes:
            si.rc.update(rc) if update else dict(rc)

    def set_rc_to_texts(self, name, rc, update=False):
        texts = self.get_texts_with_name(name)
        for ti in texts:
            ti.rc.update(rc) if update else dict(rc)

    def set_rc_to_all_texts(self, rc, update=False):
        for ti in self.texts:
            ti.rc.update(rc) if update else dict(rc)

    def set_label_to_texts(self, name, label):
        texts = self.get_texts_with_name(name)
        for ti in texts:
            ti.label = label

    def set_label_to_all_texts(self, label):
        for ti in self.texts:
            ti.label = label

    def reset_label_texts(self, name):
        self.set_label_to_texts(name, label=name)

    def reset_label_to_all_texts(self):
        for ti in self.texts:
            ti.label = ti.name

    def reset_shapes(self):
        self.set_rc_to_all_shapes(self.default_rc_shape, update=False)

    def reset_texts(self):
        self.set_rc_to_all_texts(self.default_rc_text, update=False)
        self.reset_label_to_all_texts()

    # def set_content_to_shapes(self, name, rc=None):
    #     shapes = self.get_shapes_with_name(name)
    #     if rc is not None:
    #         for si in shapes:
    #             si.rc.update(rc)
    #
    # def set_content_to_texts(self, name, label=None, rc=None):
    #     texts = self.get_texts_with_name(name)
    #     for ti in texts:
    #         if rc is not None:
    #             ti.rc.update(rc)
    #         if label is not None:
    #             ti.label = label
    #
    # def set_content_to_all_shapes(self, rc=None):
    #     if rc is not None:
    #         for si in self.shapes:
    #             si.rc.update(rc)
    #
    # def set_content_to_all_texts(self, label=None, rc=None):
    #     for ti in self.texts:
    #         if rc is not None:
    #             ti.rc.update(rc)
    #         if label is not None:
    #             ti.label = label

    def reset(self):
        self.reset_shapes()
        self.reset_texts()

    def get_elements_with_name(self, name):
        shapes = self.get_shapes_with_name(name)
        texts = self.get_texts_with_name(name)
        return shapes + texts

    def get_shapes_with_name(self, name):
        return [s for s in self.shapes if s.name == name]

    def get_texts_with_name(self, name):
        return [t for t in self.texts if t.name == name]

    def plot(self, ax=None, figsize=(8, 4)):
        fig, ax = self._create_fig_ax(ax, figsize=figsize)
        self._add_shapes_to_ax(ax)
        self._add_texts_to_ax(ax)
        self._correct_ax_limits(ax)
        return fig, ax

    def _create_fig_ax(self, ax=None, **kwargs):
        if ax is None:
            fig, ax = plt.subplots(1, **kwargs)
        else:
            fig = ax.figure
        ax.axis('off')
        return fig, ax

    def _add_shapes_to_ax(self, ax):
        for si in self.shapes:
            x = si.get_x()
            y = si.get_y()
            ax.fill(x, y, **si.rc)

    def _add_texts_to_ax(self, ax):
        for ti in self.texts:
            x = ti.get_x()
            y = ti.get_y()
            ax.text(x, y, ti.label, **ti.rc)

    def _correct_ax_limits(self, ax):
        x_list = []
        y_list = []
        for si in self.shapes:
            x_list += list(si.get_x())
            y_list += list(si.get_y())
        x_list += [ti.get_x() for ti in self.texts]
        y_list += [ti.get_y() for ti in self.texts]
        xlim = (np.min(x_list), np.max(x_list))
        ylim = (np.min(y_list), np.max(y_list))
        ax.set_xlim(xlim)
        ax.set_ylim(ylim)

    def plot_elements(self, ax=None, figsize=(8, 4), cmap='hsv'):
        fig, ax = self._create_fig_ax(ax, figsize=figsize)
        cmap = plt.get_cmap(cmap)
        nb = len(self.elements)
        colors = [cmap(i) for i in np.linspace(0, 1, nb)]
        ax.set_prop_cycle(cycler('color', colors))
        for si in self.shapes:
            x = si.get_x()
            y = si.get_y()
            ax.fill(x, y)
            ax.text(x[0], y[0], f'[shape] {si.name}')
        for ti in self.texts:
            x = ti.get_x()
            y = ti.get_y()
            ax.text(x, y, f'[text] {ti.name}')
        self._correct_ax_limits(ax)
        return fig, ax


class ConfigShapes(ConfigBase):
    sections = ['SHAPES', 'TEXTS', 'RC_SHAPE', 'RC_TEXT']

    def __init__(self, fullpath=None):
        """
        fullpath: path to config.ini file

        This file has the following format:
        [SHAPES]
        new_name1 = id1
        new_name2 = id2.1, id2.2, ...

        [TEXTS]
        new_name3 = id3
        new_name4 = id4.1, id4.2, ...

        For example:
        [SHAPES]
        barrier_gate = 3
        side_gate = 1, 2

        [TEXTS]
        barrier_gate = 4
        side_gate = 5
        RF_power = 6
        """
        super().__init__(fullpath)

    def get_shapes(self) -> dict:
        return self.get_section_config('SHAPES', key_fmt=str, value_fmt=str, value_sep=',')

    def get_texts(self) -> dict:
        return self.get_section_config('TEXTS', key_fmt=str, value_fmt=str, value_sep=',')

    def get_rc_shape(self):
        return self.get_section_config('RC_SHAPE', key_fmt=str, value_fmt=(float, str), value_sep=None)

    def get_rc_text(self):
        return self.get_section_config('RC_TEXT', key_fmt=str, value_fmt=(float, str), value_sep=None)

    def set_shapes(self, dict_):
        self.set_section_config('SHAPES', dict_)

    def set_texts(self, dict_):
        self.set_section_config('TEXTS', dict_)

    def set_rc_shape(self, dict_):
        self.set_section_config('RC_SHAPE', dict_)

    def set_rc_text(self, dict_):
        self.set_section_config('RC_TEXT', dict_)


class LayoutGDS(object):
    def __init__(self, gdspath: str, content: ExpContent, view: ViewShapes = None,
                 gdsconfig: Optional[ConfigShapes] = None):
        self.gdspath = gdspath
        self.content = content
        if view is None:
            self.view = ViewShapes()
        else:
            self.view = view
        self.gdsconfig = gdsconfig
        self.load_gds_elements()
        if self.gdsconfig:
            self.apply_config()

    def load_content(self, *args, **kwargs):
        self.content.load(*args, **kwargs)
        self.apply_content_to_view()

    def load_gds_elements(self):
        """
        open filename (if exists)
        read units
        get list of polygons
        """
        self.view.clear_elements()
        element_id = 0
        xy = {}
        string_info = {}
        with open(self.gdspath, 'rb') as a_file:
            for rec in Record.iterate(a_file):
                # if rec.tag_name == 'UNITS':
                #     unitstring = self._rec_to_string(rec)
                #     self.units = np.array(re.split(',', unitstring)).astype(float)
                if rec.tag_name == 'XY':
                    # XY of string or shape
                    data = self._get_vertexes_from_rec(rec)
                    xy[element_id] = data
                    element_id += 1
                elif rec.tag_name == 'STRING':
                    text = rec.data
                    text = text.decode("utf-8") if isinstance(text, bytes) else str(text)
                    string_info[element_id - 1] = text

        str_keys = string_info.keys()
        for el_id, xyi in xy.items():
            if el_id in str_keys:
                xi, yi = tuple(np.squeeze(xyi))  # [[x,y]] to [x,y]
                self.view.add_text(name=str(el_id), x=xi, y=yi)
            else:
                self.view.add_shape(name=str(el_id), points=xyi)

    def apply_config(self):
        config = self.gdsconfig
        shapes = config.get_shapes()
        rc_shape = config.get_rc_shape()
        rc_text = config.get_rc_text()
        for name, ids in shapes.items():
            for id_ in ids:
                self.view.change_name(old_name=id_, new_name=name)
                self.view.set_rc_to_shapes(name, rc=rc_shape)

        texts = config.get_texts()
        for name, ids in texts.items():
            for id_ in ids:
                self.view.change_name(old_name=id_, new_name=name)
                self.view.set_rc_to_texts(name, rc=rc_text)
                self.view.set_label_to_texts(name, label=name)

    def plot(self, *args, **kwargs):
        return self.view.plot(*args, **kwargs)

    def apply_content_to_view(self):
        """
        This function applies the color scheme and labels of a certain setting of gates.
        """
        self.reset_view_rc()
        self._apply_statics_info_to_view()
        self._apply_sweep_info_to_view()

    def _apply_sweep_info_to_view(self):
        axes = self.content.get_axes()
        for axi in axes:
            color = self.generate_rc_color(axi.dim)
            rc_shape = {'facecolor': color, 'edgecolor': color}
            self.view.set_rc_to_shapes(axi.name, rc=rc_shape, update=True)
            rc_text = {'color': color}
            label = f'{axi.name} (dim {axi.dim})'
            self.view.set_rc_to_texts(axi.name, rc=rc_text, update=True)
            self.view.set_label_to_texts(axi.name, label=label)

    def _apply_statics_info_to_view(self):
        statics = self.content.get_statics()
        for st in statics:
            label = f'{st.name} = {st.value} {st.unit}'
            self.view.set_label_to_texts(st.name, label=label)

    def reset_view_rc(self):
        self.view.reset()
        if self.gdsconfig:
            rc_shape = self.gdsconfig.get_rc_shape()
            rc_text = self.gdsconfig.get_rc_text()
            self.view.set_rc_to_all_shapes(rc_shape, update=True)
            self.view.set_rc_to_all_texts(rc_text, update=True)

    def generate_rc_color(self, dim):
        """
        Leave it hardcoded here for the moment.
        In the future, we should use a RCGenerator class
        """
        # base_colors = [
        #     (255, 0, 0),  # red
        #     (0, 0, 255),  # blue
        #     (0, 255, 0),  # green
        #     (255, 0, 255),  # purple
        #     (255, 255, 0),  # yellow
        #     (0, 255, 255),  # cyan
        # ]
        base_colors = ['r', 'b', 'g', 'orange', 'c', 'm', 'y', 'purple']

        nmax = len(base_colors)
        color = base_colors[dim % nmax]  # loop
        return color

    def _rec_to_string(self, rec):
        """Shows data in a human-readable format."""
        if rec.tag_type == types.ASCII:
            return '"%s"' % rec.data.decode()  # TODO escape
        elif rec.tag_type == types.BITARRAY:
            return str(rec.data)
        return ', '.join('{0}'.format(i) for i in rec.data)

    def _get_units_from_rec(self, rec):
        unitstring = self._rec_to_string(rec)
        units = np.array(re.split(',', unitstring)).astype(float)
        return units

    def _get_vertexes_from_rec(self, rec):
        datastring = self._rec_to_string(rec)
        # split string at , and convert to float
        data = np.array(re.split(',', datastring)).astype(float)
        # reshape into [[x1,y1],[x2,y2],...]
        if len(data) > 2:
            data = np.reshape(data, (int(len(data) / 2), 2))[:-1]
        else:
            data = np.reshape(data, (int(len(data) / 2), 2))
        return data

# def unique_color(n):
#     nmax = len(base_colors)
#     rgb = np.array(base_colors[n % nmax])
#     rgb = rgb / (n // nmax + 1)


# default_colors = ['r', 'b', 'g', 'orange']
# class structurefromGDS(object):
#     """
#     Interface to convert the polygons from GDS files into point lists that
#     can be used to calculate the potential landscapes.
#     Reads gds file
#     outputs pointlist when called
#     """
#
#     def __init__(self, fname):
#         self.fname = fname
#         self.units = []
#         self.pointlists = []
#         self.string_infos = {}
#
#     def show_data(self, rec):
#         """Shows data in a human-readable format."""
#         if rec.tag_type == types.ASCII:
#             return '"%s"' % rec.data.decode()  # TODO escape
#         elif rec.tag_type == types.BITARRAY:
#             return str(rec.data)
#         return ', '.join('{0}'.format(i) for i in rec.data)
#
#     def main(self):
#         """
#         open filename (if exists)
#         read units
#         get list of polygons
#         """
#         #        test = []
#         no_of_Structures = 0
#         string_position = []
#         strings = []
#
#         with open(self.fname, 'rb') as a_file:
#             for rec in Record.iterate(a_file):
#                 #                test.append([rec.tag_name, rec.data, rec.tag_type])
#                 if rec.tag_type == types.NODATA:
#                     pass
#                 else:
#                     #                    print('%s: %s' % (rec.tag_name, show_data(rec)))
#                     #                    print('%s:' % (rec.tag_name))
#                     if rec.tag_name == 'UNITS':
#                         """
#                         get units
#                         """
#                         unitstring = self.show_data(rec)
#                         self.units = np.array(re.split(',', unitstring)).astype(float)
#
#                     elif rec.tag_name == 'XY':
#                         no_of_Structures += 1
#                         """
#                         get pointlist
#                         """
#                         # get data
#                         datastring = self.show_data(rec)
#                         # split string at , and convert to float
#                         data = np.array(re.split(',', datastring)).astype(float)
#                         # reshape into [[x1,y1],[x2,y2],...]
#                         # print((len(data)/2, 2))
#                         if len(data) > 2:
#                             data = np.reshape(data, (int(len(data) / 2), 2))[:-1]
#                         else:
#                             data = np.reshape(data, (int(len(data) / 2), 2))
#                         self.pointlists.append(data)
#                     elif rec.tag_name == 'STRING':
#                         string_position.append(no_of_Structures - 1)
#                         strings.append(rec.data)
#         self.string_infos = dict(zip(string_position, strings))
#
#     def __call__(self):
#         """
#         execute main
#         return list of polygons with correct SI-units (scaled by units)
#         """
#         self.main()
#         #        return np.array(self.pointlists) * self.units[1]
#         #        return np.multiply(np.array(self.pointlists), self.units[1])
#         return np.array(self.pointlists, dtype=list)

# class LayoutGDS(object):
#     elements = {
#         'id': [],
#         'xy': [],
#         'name': [],
#         'rc': [],
#         'type': [],  # string or shape
#         'label': [],
#     }
#
#     def __init__(self, fullpath):
#         self.fullpath = fullpath
#         self.load_GDS()
#         self.read_elements()
#         self.read_strings()
#         self.read_shapes()
#         self.set_default_rc()
#
#     def load_GDS(self):
#         self.structure = structurefromGDS(self.fullpath)
#
#     def set_default_rc(self):
#         global default_rc_figure
#         global default_rc_text
#         global default_rc_shape
#         self.rc_figure = default_rc_figure
#         self.rc_string = default_rc_text
#         self.rc_shape = default_rc_shape
#
#     def load_layout_config(self, fullpath):
#         self.load_shapes_config(fullpath)
#         self.load_strings_config(fullpath)
#
#     #         self.load_rc_string_config(fullpath)
#     #         self.load_rc_shape_config(fullpath)
#     #         self.load_rc_figure_config(fullpath)
#
#     def load_shapes_config(self, fullpath):
#         config = LayoutConfig(fullpath)
#         shapes_config = config.get_shapes_config()
#         for name, ids in shapes_config.items():
#             for id in ids:
#                 self.set_elements_property_value(id, 'name', name)
#                 self.set_elements_property_value(id, 'label', name)
#
#     def load_strings_config(self, fullpath):
#         config = LayoutConfig(fullpath)
#         strings_config = config.get_strings_config()
#         for name, ids in strings_config.items():
#             for id in ids:
#                 self.set_elements_property_value(id, 'name', name)
#                 self.set_elements_property_value(id, 'label', name)
#
#     def load_rc_string_config(self, fullpath):
#         config = LayoutConfig(fullpath)
#         section = 'RC_STRING'
#         if section in config.sections:
#             rc_string = config.get_section_config(section)
#             rc_string['size'] = float(rc_string['size'])
#             self.rc_string.update(rc_string)
#
#     def load_rc_shape_config(self, fullpath):
#         config = LayoutConfig(fullpath)
#         section = 'RC_SHAPE'
#         if section in config.sections:
#             rc_shape = config.get_section_config(section)
#             rc_shape['alpha'] = float(rc_shape['alpha'])
#             self.rc_shape.update(rc_shape)
#
#     def load_rc_figure_config(self, fullpath):
#         config = LayoutConfig(fullpath)
#         section = 'RC_FIGURE'
#         if section in config.sections:
#             rc_figure = config.get_section_config(section)
#             for key, value in rc_figure.items():
#                 rc_figure[key] = float(rc_figure[key])
#
#             self.rc_figure.update(rc_figure)
#
#     def read_elements(self):
#         elements_list = self.structure()
#         self.elements['id'] = []
#         self.elements['xy'] = []
#         self.elements['name'] = []
#         self.elements['label'] = []
#         self.elements['rc'] = []
#         self.elements['type'] = []
#         for i, element in enumerate(elements_list):
#             self.elements['id'].append(i)
#             self.elements['xy'].append(element.transpose())  # For x,y = self.elements
#             self.elements['name'].append(None)
#             self.elements['label'].append(None)
#             self.elements['rc'].append({})
#             self.elements['type'].append('Undefined')
#         self.elements_size = i + 1
#
#     def read_strings(self):
#         self.strings_ids = []
#         for key, value in self.structure.string_infos.items():
#             index = self.get_elements_index('id', key)
#             self.strings_ids.append(key)
#             self.elements['type'][index] = 'string'
#             self.elements['name'][index] = value
#             self.elements['label'][index] = value
#             self.elements['rc'][index] = copy(default_rc_text)
#         self.strings_size = len(self.strings_ids)
#
#     def read_shapes(self):
#         self.shapes_ids = []
#         for i in range(self.elements_size):
#             if self.elements['type'][i] != 'string':
#                 self.shapes_ids.append(self.elements['id'][i])
#                 self.elements['type'][i] = 'shape'
#                 self.elements['rc'][i] = copy(default_rc_shape)
#         self.shapes_size = len(self.shapes_ids)
#
#     def get_elements_index(self, key, target):
#         index = self.elements[key].index(target)
#         return index
#
#     def set_elements_property_value(self, id, property, value):
#         index = self.get_elements_index('id', id)
#         self.elements[property][index] = value
#
#     def get_elements_property_value(self, id, property):
#         index = self.get_elements_index('id', id)
#         value = self.elements[property][index]
#         return value
#
#     def get_ids_with_property_value(self, property, target_value):
#         ids = []
#         for i in range(self.elements_size):
#             cur_value = self.elements[property][i]
#             if cur_value == target_value:
#                 id = self.elements['id'][i]
#                 ids.append(id)
#         return id
#
#     def layout_limits(self, extra_factor=1.2):
#         xlim = np.array([0, 0])
#         ylim = np.array([0, 0])
#         for xy in self.elements['xy']:
#             x, y = xy
#             xlim[0] = min(xlim[0], np.amin(x))
#             xlim[1] = max(xlim[1], np.amax(x))
#             ylim[0] = min(ylim[0], np.amin(y))
#             ylim[1] = max(ylim[1], np.amax(y))
#         xlim = xlim * extra_factor
#         ylim = ylim * extra_factor
#         return xlim, ylim
#
#     def plot_elements(self):
#         nb = self.elements_size
#         fig, ax = plt.subplots()
#         colormap = plt.cm.hsv
#         colors = [colormap(i) for i in np.linspace(0, 1, nb)]
#         ax.set_prop_cycle(cycler('color', colors))
#         for i in range(nb):
#             x, y = self.elements['xy'][i]
#             ax.fill(x, y)
#             ax.text(x[0], y[0], i)
#         return fig, ax
#
#     def plot_layout(self):
#         rc_fig = self.rc_figure
#         figsize = (rc_fig['figsize_x'], rc_fig['figsize_y'])
#         fig, ax = plt.subplots(1, figsize=figsize)
#         ax.axis('off')
#         for id in self.shapes_ids:
#             x, y = self.get_elements_property_value(id, 'xy')
#             rc = self.get_elements_property_value(id, 'rc')
#             rc_shape = copy(self.rc_shape)
#             rc_shape.update(rc)
#             # rc.update(self.rc_shape)
#             ax.fill(x, y, **rc_shape)
#
#         for id in self.strings_ids:
#             x, y = self.get_elements_property_value(id, 'xy')
#             label = self.get_elements_property_value(id, 'label')
#             rc = self.get_elements_property_value(id, 'rc')
#             rc_string = copy(self.rc_string)
#             rc_string.update(rc)
#             # rc.update(self.rc_string)
#             # rc['horizontalalignment']='center'
#             ax.text(x, y, label, **rc_string)
#         lim_factor = rc_fig['lim_factor']
#         xlim, ylim = self.layout_limits(extra_factor=lim_factor)
#         xlim = (xlim[0] + rc_fig['extra_left'], xlim[1] + rc_fig['extra_right'])
#         ylim = (ylim[0] + rc_fig['extra_bottom'], ylim[1] + rc_fig['extra_top'])
#         ax.set_xlim(xlim)
#         ax.set_ylim(ylim)
#         return fig, ax
#
#     def set_dummy_label(self, label):
#         elems = self.elements
#         n = len(elems['id'])
#         for i in range(n):
#             elems['label'][i] = label
#
#     def config_wizard(self,
#                       names: list,  # names of controls to allocate to the strings and shapes
#                       export_file=None,  # location of the file to export the GDS configuration
#                       default_file=None,  # location of reference file to import footer for GDS config
#                       ):
#
#         if not os.path.exists(default_file):
#             raise Exception('File with format-defaults \"{:s}\" not found!'.format(default_file))
#
#         shapes_data = list()
#         strings_data = list()
#
#         N_elements = len(self.elements['id'])
#
#         shape_id = ipyw.IntSlider(
#             value=0,
#             min=0,
#             max=N_elements,
#             step=1,
#         )
#         shape_id.layout.visibility = 'hidden'
#
#         textbox = ipyw.Label(value='Nothing')
#
#         nothing = 'Nothing'
#         temp_names = names + [nothing]
#         dropdown_controls = ipyw.Dropdown(
#             options=temp_names,
#             description='Control:',
#         )
#
#         move_button = ipyw.Button(description='Choose')
#
#         fig, ax = self.plot_layout()
#         shapes = ax.get_children()[0:N_elements]
#
#         def is_polygon(element_id):
#             condition1 = element_id in self.shapes_ids
#             condition2 = isinstance(shapes[element_id], matplotlib.patches.Polygon)
#             return condition1 and condition2
#
#         def is_text(element_id):
#             condition1 = element_id in self.strings_ids
#             condition2 = isinstance(shapes[element_id], matplotlib.text.Text)
#             return condition1 and condition2
#
#         def highlight_shape(element_id):
#             if is_polygon(element_id):
#                 shapes[element_id].set_facecolor('red')
#                 shapes[element_id].set_edgecolor('black')
#                 textbox.value = 'Element #{:d}: Polygon'.format(element_id)
#             if is_text(element_id):
#                 shapes[element_id].set_color('red')
#                 shapes[element_id].set_weight('bold')
#                 textbox.value = 'Element #{:d}: Text'.format(element_id)
#
#         def hide_shape(element_id):
#             if is_polygon(element_id):
#                 shapes[element_id].set_facecolor('grey')
#                 shapes[element_id].set_edgecolor('grey')
#                 shapes[element_id].set_alpha(0.3)
#             if is_text(element_id):
#                 shapes[element_id].set_color('grey')
#                 shapes[element_id].set_weight('normal')
#                 shapes[element_id].set_alpha(0.8)
#
#         def note_selection(element_id):
#
#             if dropdown_controls.value != nothing:
#                 temp_str = '{:s} = {:d}'.format(dropdown_controls.value, element_id)
#                 if is_polygon(element_id):
#                     shapes_data.append(temp_str)
#                 if is_text(element_id):
#                     strings_data.append(temp_str)
#                 temp_options = list(dropdown_controls.options)
#                 temp_options.remove(dropdown_controls.value)
#                 dropdown_controls.options = temp_options
#
#             # Display all options when string allocation starts:
#             if element_id == self.shapes_ids[-1]:
#                 dropdown_controls.options = names + [nothing]
#
#             dropdown_controls.value = dropdown_controls.options[0]
#
#         #             if element_id == self.shapes_ids[-1]:
#         #                 temp_names = names + [None]
#         #                 dropdown_controls.options = temp_names
#
#         def write_to_file(filename='../configurations/gds_config.ini',
#                           default_file=None):
#             with open(filename, 'a') as gds_config:
#                 gds_config.write('[SHAPES]\n')
#                 for shapes_entry in shapes_data:
#                     gds_config.write(shapes_entry + "\n")
#                 gds_config.write('\n')
#                 gds_config.write('[STRINGS]\n')
#                 for strings_entry in strings_data:
#                     gds_config.write(strings_entry + "\n")
#                 gds_config.write('\n')
#                 if default_file != None:
#                     with open(default_file) as rc_default:
#                         for rc_line in rc_default:
#                             gds_config.write(rc_line)
#             print('Wrote GDS-configuration file: \"{:s}\"'.format(filename))
#
#         def close_widgets():
#             textbox.close()
#             dropdown_controls.close()
#             move_button.close()
#
#         def advance_wizard(button):
#             note_selection(shape_id.value)  # NOTE SELECTION
#             hide_shape(shape_id.value)  # HIDE CURRENT SHAPE
#             shape_id.value = shape_id.value + 1  # GO TO NEXT SHAPE
#             if shape_id.value < N_elements:
#                 highlight_shape(shape_id.value)  # HIGHLIGHT NEXT SHAPE
#                 fig.canvas.draw()  # UPDATE PLOT
#             elif shape_id.value == N_elements:  # IF FINISH
#                 close_widgets();
#                 hide_shape(shape_id.value - 1)  # CLOSE WIDGETS AND
#                 write_to_file(export_file, default_file)  # SAVE SELECTIONS TO FILE
#
#         move_button.on_click(advance_wizard)
#
#         highlight_shape(shape_id.value)
#         dropdown_controls.value = dropdown_controls.options[0]
#         display(shape_id, textbox, dropdown_controls, move_button)


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

# class structurefromGDS(object):
#     """
#     Interface to convert the polygons from GDS files into point lists that
#     can be used to calculate the potential landscapes.
#     Reads gds file
#     outputs pointlist when called
#     """
#
#     def __init__(self, fname):
#         self.fname = fname
#         self.units = []
#         self.pointlists = []
#         self.string_infos = {}
#
#     def show_data(self, rec):
#         """Shows data in a human-readable format."""
#         if rec.tag_type == types.ASCII:
#             return '"%s"' % rec.data.decode()  # TODO escape
#         elif rec.tag_type == types.BITARRAY:
#             return str(rec.data)
#         return ', '.join('{0}'.format(i) for i in rec.data)
#
#     def main(self):
#         """
#         open filename (if exists)
#         read units
#         get list of polygons
#         """
#         #        test = []
#         no_of_Structures = 0
#         string_position = []
#         strings = []
#
#         with open(self.fname, 'rb') as a_file:
#             for rec in Record.iterate(a_file):
#                 #                test.append([rec.tag_name, rec.data, rec.tag_type])
#                 if rec.tag_type == types.NODATA:
#                     pass
#                 else:
#                     #                    print('%s: %s' % (rec.tag_name, show_data(rec)))
#                     #                    print('%s:' % (rec.tag_name))
#                     if rec.tag_name == 'UNITS':
#                         """
#                         get units
#                         """
#                         unitstring = self.show_data(rec)
#                         self.units = np.array(re.split(',', unitstring)).astype(float)
#
#                     elif rec.tag_name == 'XY':
#                         no_of_Structures += 1
#                         """
#                         get pointlist
#                         """
#                         # get data
#                         datastring = self.show_data(rec)
#                         # split string at , and convert to float
#                         data = np.array(re.split(',', datastring)).astype(float)
#                         # reshape into [[x1,y1],[x2,y2],...]
#                         # print((len(data)/2, 2))
#                         if len(data) > 2:
#                             data = np.reshape(data, (int(len(data) / 2), 2))[:-1]
#                         else:
#                             data = np.reshape(data, (int(len(data) / 2), 2))
#                         self.pointlists.append(data)
#                     elif rec.tag_name == 'STRING':
#                         string_position.append(no_of_Structures - 1)
#                         strings.append(rec.data)
#         self.string_infos = dict(zip(string_position, strings))
#
#     def __call__(self):
#         """
#         execute main
#         return list of polygons with correct SI-units (scaled by units)
#         """
#         self.main()
#         #        return np.array(self.pointlists) * self.units[1]
#         #        return np.multiply(np.array(self.pointlists), self.units[1])
#         return np.array(self.pointlists, dtype=list)
