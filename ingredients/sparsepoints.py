"""
This class overlays points on top of the image stacks. 
TODO: once this is working, pull out the general purpose stuff and set up an ingredient class that this inherits
"""

from __future__ import division
import numpy as np
import os
import pyqtgraph as pg
from  lasagna_ingredient import lasagna_ingredient 

class sparsepoints(lasagna_ingredient):
    def __init__(self, data=None, fnameAbsPath='', enable=True, objectName=''):
        super(sparsepoints,self).__init__(data, fnameAbsPath, enable, objectName,
                                        pgObject='PlotDataItem'
                                        )


    def data(self,axisToPlot=0):
        """
        Sparse point data are an n by 3 array where each row defines the location
        of a single point in x, y, and z
        """
        data = np.delete(self._data,axisToPlot,1)
        if axisToPlot==2:
            data = np.fliplr(data)

        return data


    
    # TODO: farm out preceeding stuff to a general-purpose ingredient class 
    # Methods that follow are specific to the imagestack class. Methods that preceed this
    # are general-purpose and can be part of an "ingredient" class

    def plotIngredient(self,pyqtObject,axisToPlot=0,sliceToPlot=0):
        """
        Plots the ingredient onto pyqtObject along axisAxisToPlot,
        onto the object with which it is associated
        """
        z = self._data[:,axisToPlot]
        data = self.data(axisToPlot)
        data = data[z==sliceToPlot,:]


        pyqtObject.setData(x=data[:,0], y=data[:,1], symbol='t', pen=None, symbolSize=10, symbolBrush=(100, 100, 255, 150))
        