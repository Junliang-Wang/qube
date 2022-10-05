from typing import List, Dict, Callable, Any
import configparser
import re
from abc import ABC, abstractmethod
from collections.abc import Iterable


class ViewBase(ABC):
    """ Base class for layout View """

    @abstractmethod
    def plot(self):
        """ Abstract method for showing the view """


class ConfigBase(ABC):
    """ Base clase for Configuration file for a View """
    sections: List = None

    def __init__(self, fullpath: str = None):
        self.config = configparser.ConfigParser()
        self.config.optionxform = str
        self.fullpath = fullpath

        if not self.sections:
            self.sections = []
        for sec in self.sections:
            self.config[sec] = {}

        if fullpath:
            self.read(fullpath)

    def read(self, fullpath):
        self.config.read(fullpath)
        self.fullpath = fullpath

    def write(self, fullpath):
        with open(fullpath, 'w') as configfile:
            self.config.write(configfile)

    def get_section_config(self, section, key_fmt=None, value_fmt=None, value_sep=None) -> Dict:
        if self.has_section(section):
            config = self.config[str(section)]
            config = format_dict(config, key_fmt=key_fmt, value_fmt=value_fmt, value_sep=value_sep)
        else:
            config = {}
        return config

    def has_section(self, section):
        return section in self.get_sections()

    def get_sections(self) -> List:
        return self.sections

    def set_section_config(self, section, dict_):
        """
        dict_: config for shapes like {'key1': '1', 'key2': '2,3'}
        """
        self.config[section] = dict_


class ContentBase(ABC):
    """ Base class for the content of a view """


# class RCGenerator(ABC):
#     """ Base class to generate rc parameters with a given sweep information """
#
#     @abstractmethod
#     def get_rc(self) -> Dict:
#         """ Dictionary of rc parameters where key is the sweeping dimension """


def format_dict(target_dict, key_fmt=None, value_fmt=None, value_sep=None) -> Dict:
    key_fmt = fmt_func(key_fmt)
    value_fmt = fmt_func(value_fmt)
    new_dict = {}
    for key, value in target_dict.items():
        new_key = key_fmt(key)
        if value_sep is not None:
            value = remove_all_space(value)
            values = value.split(value_sep)
            new_value = [value_fmt(value) for value in values]
            new_value = remove_empty_in_list(new_value)
        else:
            new_value = value_fmt(value)
        new_dict[new_key] = new_value
    return new_dict


def iterable(var: Any) -> bool:
    return isinstance(var, Iterable)


def fmt_func(var: Any) -> Callable[[Any], Any]:
    if callable(var):
        return var
    elif iterable(var):
        flist = [fmt_func(v) for v in var]
        return try_fmts(*flist)
    else:
        return lambda x: x


def try_fmts(*funcs: Callable) -> Callable:
    def _f(value):
        v = value
        for f in funcs:
            try:
                v = f(value)
                break
            except:
                continue
        return v

    return _f


def remove_all_space(string: str) -> str:
    return re.sub(r"\s+", "", string, flags=re.UNICODE)


def remove_empty_in_list(l: List) -> List:
    return [li for li in l if li != '']


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

if __name__ == '__main__':
    c = ConfigGDS()

    c.config['SHAPES'] = {
        'gate1': '0',
        'gate2': '1,2',
    }

    c.config['TEXTS'] = {
        'gate1': '3, 4',
        'gate2': '5',
    }
