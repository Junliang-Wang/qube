import matplotlib.pyplot as plt
#import Utility.SHARED_variables as sv
# from QuAnalysis.layout.GDS_layout import LayoutGDS
from qube.layout.gds import LayoutGDS

def preview_GDS_layout(fullpath):
    # sample_gds = sv.PATH_Sample_gds
    sample_gds = './GDS/'
    layout_1 = LayoutGDS(fullpath)
    layout_1.plot_elements()
    plt.show()

def preview_current_layout():
    # sample_gds = sv.PATH_Sample_gds
    sample_gds = './GDS/'
    preview_GDS_layout(sample_gds)

if __name__ == '__main__':
    import os
    plt.ion()
    # preview_current_layout()
    path = r'C:\Users\manip.batm\Desktop\QuFox_prod\Python\QuAnalysis\LayoutLibrary\GDS'
    gds = 'HBT9_d3_40um_3_cd1.GDS'
    fullpath = os.path.join(path,gds)
    # preview_GDS_layout(fullpath)
    layout = LayoutGDS(fullpath)
    if True:
        layout.set_dummy_label('ABC = 0.000V')
        layout.rc_figure = {
            'figsize_x': 8,
            'figsize_y': 4,
            'lim_factor': 1.0,
            'extra_left': 0.0,
            'extra_right': 0.0,
            'extra_top': 0.0,
            'extra_bottom': 0.0,
            }
        layout.plot_elements()
        # layout.plot_layout()
    else:
        conf_path = r'C:\Users\manip.batm\Desktop\QuFox_prod\Python\QuAnalysis\LayoutLibrary\db'
        conf = 'HBT9_d3_40um_3_cd1.ini'
        layout.load_layout_config(os.path.join(conf_path,conf))
        layout.plot_layout()
