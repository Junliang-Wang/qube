# qube
Useful tools for experiments performed by the group of Dr. Christopher Bauerle (CNRS Neel Institute, Grenoble)

_______________________________________
# How to install QCoDeS?

Open your Anaconda/Miniconda prompt and install qcodes:

```sh
conda create -n qcodes python=3.9
conda activate qcodes
pip install qcodes
```

Open your Anaconda/Miniconda prompt and install additional packages:

```sh
activate qcodes
pip install python-gdsii
pip install style
conda install -c conda-forge scipy
conda install -c conda-forge gdspy
conda install -c conda-forge jupyterlab
conda install -c conda-forge ipympl
conda install -c conda-forge nidaqmx-python
pip install nifpga
```


_______________________________________
# How to start an experiment with QCoDeS?

____
COPY the "YYYYMMDD__experiment__sample" folder into "E:/your_name/" and rename it the following way:

YYYYMMDD   ... starting date of the experiment
experiment ... name of your experiment -- for instance "ABL" for Aharanov-Bohm oscillations with Levitons
sample     ... name of your sample -- for instance "v0_b3" for first version of design and 2nd column (B) and 3rd row (3) of your chip

Note: For automatic recognition, is important to keep TWO subsequent underscores "__" between the keywords of the folder name.

The folder has the following content:

./configurations/ 
  This folder holds Jupyter Notebooks to setup different configurations of your experiment.
  As a starting point you can check the default configuration of your fridge -- for instance "default_wodan.ipynb".
  Setup your configurations accordingly with reasonable file names -- such as "c0_lock_in.ipynb",  "m1_pinch_off_dc.ipynb", ... .
  A configuration notebook contains the instruments that are used on your experimental setup.
  If you make a modification, always modify a copy of a previously used configuration.


./measurements/
  This folder will contain the database for your experiment "experiments.db" with all the measurements.
  Additionally, there should be all the code for the measurements that are executed during your experiment.
  The measurement template "tutorial.ipynb" contains all the imports to perform sweeps and basic plotting operations.
  Use it for your measurements that should be always saved with reasonable names such as "m0_lockin_test", "m1_pinch_off_at_4K", ... .
  

./notes/
  Here one should find only notes that are prepared in a presentable way.
  We propose to use jupyter notebook with markdown language since it is flexible.
  You can make your notes however in any format you like (OneNote, PowerPoint, ...)


./tools/
  This folder contains tools and instrument drivers that go beyond the standard qcodes functionality.
  Feel free to adapt them for your application and to add custom functions that you can use in your measurements.
  After implemententing a new feature that is working well, one can discuss an update of the driver in the template folder.
  
./QCoDeS - Jupyter Notebook
  Windows shortcut to open qcodes via Miniconda3 locally or on a network drive.


_____
# SETUP your configuration file:

_____
# MEASURE:

_____
# ANALYSE:


