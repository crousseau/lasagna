"""
this file describes a class that handles the axis behavior for the lasagna viewer
"""

import pyqtgraph as pg


from lasagna.ingredients.imagestack import imagestack as lasagna_imagestack
from lasagna.utils.lasagna_qt_helper_functions import find_pyqt_graph_object_name_in_plot_widget
from lasagna.utils import preferences


class projection2D():

    def __init__(self, thisPlotWidget, lasagna_serving, axisName='', minMax=(0, 1500), axisRatio=1, axisToPlot=0):
        """
        thisPlotWidget - the PlotWidget to which we will add the axes
        minMax - the minimum and maximum values of the plotted image. 
        axisRatio - the voxel size ratio along the x and y axes. 1 means square voxels.
        axisToPlot - the dimension along which we are slicing the data.
        """

        # Create properties
        self.axisToPlot = axisToPlot  # the axis in 3D space that this view correponds to
        self.axisName = axisName
        # We can link this projection to two others
        self.linkedXprojection = None
        self.linkedYprojection = None

        print("Creating axis at " + str(thisPlotWidget.objectName()))
        self.view = thisPlotWidget  # This should target the axes to a particular plot widget

        if preferences.readPreference('hideZoomResetButtonOnImageAxes'):
            self.view.hideButtons()

        if preferences.readPreference('hideAxes'):
            self.view.hideAxis('left')
            self.view.hideAxis('bottom')               

        self.view.setAspectLocked(True, axisRatio)

        # Loop through the ingredients list and add them to the ViewBox
        self.lasagna = lasagna_serving
        self.items = []  # a list of added plot items TODO: check if we really need this
        self.addItemsToPlotWidget(self.lasagna.ingredientList)

        # The currently plotted slice
        self.currentSlice = None

        # Link the progressLayer signal to a slot that will move through image layers as the wheel is turned
        self.view.getViewBox().progressLayer.connect(self.wheel_layer_slot)

    def addItemToPlotWidget(self, ingredient):
        """
        Adds an ingredient to the PlotWidget as an item (i.e. the ingredient manages the process of 
        producing an item using information in the ingredient properties.
        """
        verbose = False

        _item = (getattr(pg, ingredient.pgObject)(**ingredient.pgObjectConstructionArgs))
        _item.objectName = ingredient.objectName

        if verbose:
            print("\nlasagna_axis.addItemToPlotWidget adds item " + ingredient.objectName + " as: " + str(_item))

        self.view.addItem(_item)
        self.items.append(_item)

    def removeItemFromPlotWidget(self, item):
        """
        Removes an item from the PlotWidget and also from the list of items.
        This function is used for when want to delete or wipe an item from the list
        because it is no longer needed. Use hideIngredient if you want to temporarily
        make something invisible

        "item" is either a string defining an objectName or the object itself
        """
        items = list(self.view.items())
        n_items_before = len(items)  # to determine if an item was removed
        if isinstance(item, str):
            removed = False
            for this_item in items:
                if hasattr(this_item, 'objectName') and this_item.objectName == item:
                        self.view.removeItem(this_item)
                        removed = True
            if not removed:
                print("lasagna_axis.removeItemFromPlotWidget failed to remove item defined by string " + item)
        else:  # it should be an image item
            self.view.removeItem(item)

        # Optionally return True of False depending on whether the removal was successful
        n_items_after = len(list(self.view.items()))

        if n_items_after < n_items_before:
            return True
        elif n_items_after == n_items_before:
            return False
        else:
            print('** removeItemFromPlotWidget: %d items before removal and %d after removal **' % (n_items_before,
                                                                                                    n_items_after))
            return False

    def addItemsToPlotWidget(self, ingredients):
        """
        Add all ingredients in list to the PlotWidget as items
        """
        if not ingredients:
            return
        [self.addItemToPlotWidget(ingredient) for ingredient in ingredients]

    def removeAllItemsFromPlotWidget(self, items):
        """
        Remove all items (i.e. delete them) from the PlotWidget
        items is a list of strings or plot items
        """
        if not items:
            return
        [self.removeItemFromPlotWidget(item) for item in items]

    def listNamedItemsInPlotWidget(self):
        """
        Print a list of all named items actually *added* in the PlotWidget
        """
        n = 1
        for item in list(self.view.items()):
            if hasattr(item, 'objectName') and isinstance(item.objectName, str):
                print("object %s: %s" % (n, item.objectName))
            n += 1


    def getPlotItemByName(self, objName):
        """
        returns the first plot item in the list bearing the objectName 'objName'
        because of the way we generally add objects, there *should* never be 
        multiple objects with the same name
        """
        for item in list(self.view.items()):
            if hasattr(item, 'objectName') and isinstance(item.objectName, str):
                if item.objectName == objName:
                    return item

    def getPlotItemByType(self, itemType):
        """
        returns all plot items of the defined type. 
        itemType should be a string that defines a pyqtgraph item type. 
        Examples include: ImageItem, ViewBox, PlotItem, AxisItem and LabelItem
        """
        item_list = []
        for item in list(self.view.items()):
            if item.__module__.endswith(itemType):
                item_list.append(item)

        return item_list

    def hideItem(self, item):
        """
        Hides an item from the PlotWidget. If you want to delete an item
        outright then use removeItemFromPlotWidget.
        """
        print("NEED TO WRITE lasagna.axis.hideItem()")
        return

    def updatePlotItems_2D(self, ingredientsList, sliceToPlot=None, resetToMiddleLayer=False):
        """
        Update all plot items on axis, redrawing so everything associated with a specified 
        slice (sliceToPlot) is shown. This is done based upon a list of ingredients
        """
        verbose = False

        # loop through all plot items searching for imagestack items (these need to be plotted first)
        for ingredient in ingredientsList:
            if isinstance(ingredient, lasagna_imagestack):
                # * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * *
                #TODO: AXIS need some way of linking the ingredient to the plot item but keeping in mind 
                #      that this same object needs to be plotted in different axes, each of which has its own
                #      plot items. So I can't assign a single plot item to the ingredient. Options?
                #      a list of items and axes in the ingredient? I don't like that.

                # Got to the middle of the stack
                if sliceToPlot is None or resetToMiddleLayer:
                    stacks = self.lasagna.returnIngredientByType('imagestack')
                    num_slices = []
                    [num_slices.append(stack.data(self.axisToPlot).shape[0]) for stack in stacks]
                    num_slices = max(num_slices)
                    sliceToPlot = num_slices // 2

                self.currentSlice = sliceToPlot

                if verbose:
                    print("lasagna_axis.updatePlotItems_2D - plotting ingredient " + ingredient.objectName)

                ingredient.plotIngredient(
                    pyqtObject=find_pyqt_graph_object_name_in_plot_widget(self.view,
                                                                          ingredient.objectName,
                                                                          verbose=verbose),
                    axisToPlot=self.axisToPlot,
                    sliceToPlot=self.currentSlice
                )
                # * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * *

        # the image is now displayed

        # loop through all plot items searching for non-image items (these need to be overlaid on top of the image)
        for ingredient in ingredientsList:
            if not isinstance(ingredient, lasagna_imagestack):
                if verbose:
                    print("lasagna_axis.updatePlotItems_2D - plotting ingredient " + ingredient.objectName)

                ingredient.plotIngredient(
                    pyqtObject=find_pyqt_graph_object_name_in_plot_widget(self.view,
                                                                          ingredient.objectName,
                                                                          verbose=verbose),
                    axisToPlot=self.axisToPlot,
                    sliceToPlot=self.currentSlice
                )

    def updateDisplayedSlices_2D(self, ingredients, slicesToPlot):
        """
        Update the image planes shown in each of the axes
        ingredients - lasagna.ingredients
        slicesToPlot - a tuple of length 2 that defines which slices to plot for the Y and X linked axes
        """
        # self.updatePlotItems_2D(ingredients)  # TODO: Not have this here. This should be set when the mouse enters the axis and then not changed.
                                               # Like this it doesn't work if we are to change the displayed slice in the current axis using the mouse wheel.
        self.linkedYprojection.updatePlotItems_2D(ingredients, slicesToPlot[0])
        self.linkedXprojection.updatePlotItems_2D(ingredients, slicesToPlot[1])

    def getMousePositionInCurrentView(self, pos):
        # TODO: figure out what pos is and where best to put it. Then can integrate this call into updateDisplayedSlices
        # TODO: Consider not returning x or y values that fall outside of the image space.
        mouse_point = self.view.getPlotItem().vb.mapSceneToView(pos)
        x = int(mouse_point.x())
        y = int(mouse_point.y())
        return x, y

    def resetAxes(self):
        """
        Set the X and Y limits of the axis to nicely frame the data 
        """
        self.view.autoRange()

    # ------------------------------------------------------
    # slots
    def wheel_layer_slot(self):
        """
        Handle the wheel action that allows the user to move through stack layers
        """
        self.updatePlotItems_2D(self.lasagna.ingredientList,
                                sliceToPlot=round(self.currentSlice + self.view.getViewBox().progressBy))  # round creates an int that supresses a warning in p3
