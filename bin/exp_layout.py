import os
import matplotlib.pyplot as plt
from cycler import cycler
import numpy as np
from copy import copy
import Utility.SHARED_variables as sv
from QuAnalysis.LayoutLibrary.layout_config import Layout_config
from QuAnalysis.LayoutLibrary.GDS_layout import Layout
from QuAnalysis.LayoutLibrary.datafile_gates import Datafile_gates

def get_exp_layout(datafile,FastRampMode=False):
    sample_gds = sv.PATH_Sample_gds
    exp_layout = Layout(sample_gds)

    configfile = sv.PATH_Sample_layout_config
    exp_layout.load_layout_config(configfile)

    exp_path = sv.PATH_experiments_and_data
    datapath = os.path.join(exp_path,datafile)

    gates = Datafile_gates(datapath,FastRampMode=FastRampMode)
    gates.set_to_layout(layout=exp_layout)
    return exp_layout

if __name__ == '__main__':
    datafile = 'DC0_framp_1d_14.h5'
    FastRampMode = True
    exp_layout = get_exp_layout(datafile, FastRampMode)
    fig, ax = exp_layout.plot_layout()
    plt.show()
