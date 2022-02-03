import configparser
import os


class LayoutConfig(object):
    def __init__(self, fullpath=''):
        self.config = configparser.ConfigParser()
        self.config.optionxform = str
        if fullpath:
            self.read(fullpath)

    def read(self, fullpath):
        self.config.read(fullpath)

    def write(self, fullpath):
        with open(fullpath, 'w') as configfile:
            self.config.write(configfile)

    def get_shapes_config(self):
        config = self.config['SHAPES']
        config = format_dict(config, key_fmt=str, value_fmt=int)
        return config

    def get_strings_config(self):
        config = self.config['STRINGS']
        config = format_dict(config, key_fmt=str, value_fmt=int)
        return config

    def get_section_config(self, section, key_fmt=None, value_fmt=None):
        config = self.config[str(section)]
        config = format_dict(config, key_fmt=key_fmt, value_fmt=value_fmt)
        return config

    @property
    def sections(self):
        return list(self.config.keys())


# Util functions
def format_dict(target_dict, key_fmt=None, value_fmt=None, value_sep=','):
    new_dict = {}
    for key, value in target_dict.items():
        if callable(key_fmt):
            new_key = key_fmt(key)
        else:
            new_key = key
        if callable(value_fmt):
            values = value.split(value_sep)
            new_value = [value_fmt(value) for value in values]
        else:
            new_value = value
        new_dict[new_key] = new_value
    return new_dict


if __name__ == '__main__':
    path = r"E:\Junliang\ownCloud\Scripts\LoadGDS"
    configfile = 'BM2_layout_config.ini'
    fullpath = os.path.join(path, configfile)
    #
    # config = layout_config()
    # config.read(fullpath)
    # shapes_config = config.get_shapes_config()
    # strings_config = config.get_strings_config()

    if True:
        config = configparser.ConfigParser()
        config.optionxform = str

        config['SHAPES'] = {
            'LH1': 10,
            'LH2': 2,
            'LH3': 0,
            'LV1': 15,
            'LV2': 1,
            'LD1': 6,
            'LD2': 8,
            'RH1': 4,
            'RH2': 12,
            'RH3': 13,
            'RV1': 7,
            'RV2': 14,
            'RD1': 5,
            'RD2': 9,
            'TC': 11,
            'BC': 3,
        }

        config['STRINGS'] = {
            'LH1': 19,
            'LH2': 24,
            'LH3': 23,
            'LV1': 18,
            'LV2': 22,
            'LD1': 17,
            'LD2': 16,
            'RH1': 25,
            'RH2': 26,
            'RH3': 27,
            'RV1': 28,
            'RV2': 29,
            'RD1': 30,
            'RD2': 31,
            'TC': 20,
            'BC': 21,
        }

        with open('BM2_layout_config.ini', 'w') as configfile:
            config.write(configfile)
