#!/usr/bin/python
"""
This function accepts a csv file produced by aratools.utils.exportMaSIVPoints2Lasagna.m
Each row of the csv file produced by that function is in this format:
nodeId,parentID,z position,x position,y position

This module imports this file and turns it into a format suitable
for plotting in lasagna. i.e. into a line series format:
line series #, z, x, y
Where each line series is one segment from the tree. This is 
produced using tree.find_segments, which returns all unique segments
such that only nodes at the end of each segment are duplicated. 

Processed text is dumped to standard output by default unless
the user specifies otherwise with -q

Example:
1. Plot and don't dump data to screen
exportedGoggleTree2LasagnaLines.py -pqf ./ingredients/exampleTreeDump.csv 

2. Dump data to text file and don't plot
exportedGoggleTree2LasagnaLines.py -f ./ingredients/exampleTreeDump.csv  > /tmp/dumpedTree.csv

"""


import sys
import os
import argparse

from lasagna.tree.tree_parser import parse_file


def get_parser():
    # Parse command-line input arguments
    parser = argparse.ArgumentParser()
    parser.add_argument('-f', '--file-name', dest='file_name', type=str,
                        help='File name to load')
    parser.add_argument('-p', '--plot', action='store_true',
                        help='Optionally plot tree')
    parser.add_argument('-q', '--quiet', action='store_true',
                        help='Quiet - do not dump processed tree to standard output')
    return parser


def data_from_path(tree, path):
    """
    Get the data from the tree given a path.
    """
    x = []
    y = []
    z = []
    for node in path:
        if node == 0:
            continue
        z.append(tree.nodes[node].data['z'])
        x.append(tree.nodes[node].data['x'])
        y.append(tree.nodes[node].data['y'])
    return z, x, y


def main():
    args = get_parser().parse_args()
    fname = args.file_name
    check_file_name(fname)

    # Get the data out of the tree
    data_tree = parse_file(fname, header_line=['id', 'parent', 'z', 'x', 'y'])

    # Get the unique segments of each tree
    paths = [segment for segment in data_tree.find_segments()]

    # Show paths in standard output
    if not args.quiet:
        for i, path in enumerate(paths):
            data = data_from_path(data_tree, path)
            for j in range(len(data[0])):  # FIXME: len(data[1]) ?)
                print("%d,%d,%d,%d" % (i, data[0][j], data[1][j], data[2][j]))

    if args.plot:
        plot_points(data_tree, paths)


def plot_points(data_tree, paths):
    from pyqtgraph.Qt import QtGui
    import pyqtgraph as pg
    # Set up the window
    app = QtGui.QApplication([])
    main_window = QtGui.QMainWindow()
    main_window.resize(800, 800)
    view = pg.GraphicsLayoutWidget()  # GraphicsView with GraphicsLayout inserted by default
    main_window.setCentralWidget(view)
    main_window.show()
    main_window.setWindowTitle('Neurite Tree')
    # view 1
    w1 = view.addPlot()
    path_item = []
    for path in paths:
        path_item.append(pg.PlotDataItem(size=10, pen='w', symbol='o',
                                         symbolSize=2, brush=pg.mkBrush(255, 255, 255, 120)))  # FIXME: extract
        data = data_from_path(data_tree, path)
        path_item[-1].setData(x=data[0], y=data[1])  # Only different line
        w1.addItem(path_item[-1])

    # view 2
    w2 = view.addPlot()
    path_item = []
    for path in paths:
        path_item.append(pg.PlotDataItem(size=10, pen='w', symbol='o',
                                         symbolSize=2, brush=pg.mkBrush(255, 255, 255, 120)))
        data = data_from_path(data_tree, path)
        path_item[-1].setData(x=data[0], y=data[2])  # Only different line
        w2.addItem(path_item[-1])

    # view 3
    view.nextRow()
    w3 = view.addPlot()
    path_item = []
    for path in paths:
        path_item.append(pg.PlotDataItem(size=10, pen='w', symbol='o',
                                         symbolSize=2, brush=pg.mkBrush(255, 255, 255, 120)))
        data = data_from_path(data_tree, path)
        path_item[-1].setData(x=data[1], y=data[2])  # Only different line
        w3.addItem(path_item[-1])


def check_file_name(fname):
    if fname is None:
        print("Please supply a file name to convert. e.g.:\n"
              "exported_goggle_tree_to_lasagna_lines.py -f myFile.csv\n")
        sys.exit(0)
    if not os.path.exists(fname):
        print('Can not find {}'.format(fname))
        sys.exit(0)


# Start Qt event loop unless running in interactive mode.
if __name__ == '__main__':
    import sys
    from pyqtgraph.Qt import QtGui, QtCore
    main()
    if sys.flags.interactive != 1 or not hasattr(QtCore, 'PYQT_VERSION'):
        QtGui.QApplication.instance().exec_()
