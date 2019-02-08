import os
import sys

import numpy as np
import pyqtgraph as pg
from PyQt5 import QtGui, QtCore
from PyQt5.QtWidgets import qApp

# lasagna modules

# The following imports are made here in order to ensure Lasagna builds as a standlone
# application on the Mac with py2app
# import tifffile  # Used to load tiff and LSM files
# import nrrd

from lasagna import lasagna_mainWindow, lasagna_axis, ingredients
from lasagna.io_libs import image_stack_loader
from lasagna.plugins import plugin_handler
from lasagna.utils import preferences, path_utils
from lasagna.utils.lasagna_qt_helper_functions import find_pyqt_graph_object_name_in_plot_widget


class Lasagna(QtGui.QMainWindow, lasagna_mainWindow.Ui_lasagna_mainWindow):
    def __init__(self, parent=None):
        """
        Create default values for properties then call initialiseUI to set up main window
        """
        super(Lasagna, self).__init__(parent)

        # Create widgets defined in the designer file
        # self.win = QtGui.QMainWindow()
        self.setupUi(self)
        self.show()
        self.app = None  # The QApplication handle kept here

        # Misc. window set up
        self.setWindowTitle("Lasagna - 3D sectioning volume visualiser")
        self.recentLoadActions = []
        self.updateRecentlyOpenedFiles()

        # We will maintain a list of classes of loaded items that can be added to plots
        self.ingredientList = []

        # Set up GUI based on preferences
        self.view1Z_spinBox.setValue(preferences.readPreference('defaultPointZSpread')[0])
        self.view2Z_spinBox.setValue(preferences.readPreference('defaultPointZSpread')[1])
        self.view3Z_spinBox.setValue(preferences.readPreference('defaultPointZSpread')[2])
        self.markerSize_spinBox.setValue(preferences.readPreference('defaultSymbolSize'))
        self.lineWidth_spinBox.setValue(preferences.readPreference('defaultLineWidth'))
        self.markerAlpha_spinBox.setValue(preferences.readPreference('defaultSymbolOpacity'))

        # Set up axes
        # Turn axisRatioLineEdit_x elements into a list to allow functions to iterate across them
        self.axisRatioLineEdits = [self.axisRatioLineEdit_1, self.axisRatioLineEdit_2, self.axisRatioLineEdit_3]

        self.graphicsViews = [self.graphicsView_1, self.graphicsView_2, self.graphicsView_3]  # These are the graphics_views from the UI file
        self.axes2D = []
        print("")
        for i in range(len(self.graphicsViews)):
            self.axes2D.append(lasagna_axis.projection2D(self.graphicsViews[i],
                                                         self,
                                                         axisRatio=float(self.axisRatioLineEdits[i].text()),
                                                         axisToPlot=i))
        print("")

        # Establish links between projections for panning and zooming using lasagna_viewBox.linkedAxis
        self.axes2D[0].view.getViewBox().linkedAxis = {
                    self.axes2D[1].view.getViewBox(): {'linkX': None, 'linkY': 'y', 'linkZoom': True},
                    self.axes2D[2].view.getViewBox(): {'linkX': 'x', 'linkY': None, 'linkZoom': True}
                 }

        self.axes2D[1].view.getViewBox().linkedAxis = {
                    self.axes2D[0].view.getViewBox(): {'linkX': None, 'linkY': 'y', 'linkZoom': True},
                    self.axes2D[2].view.getViewBox(): {'linkX': 'y', 'linkY': None, 'linkZoom': True}
                 }

        self.axes2D[2].view.getViewBox().linkedAxis = {
                    self.axes2D[0].view.getViewBox(): {'linkX': 'x', 'linkY': None, 'linkZoom': True},
                    self.axes2D[1].view.getViewBox(): {'linkX': None, 'linkY': 'x', 'linkZoom': True}
                 }

        # Establish links between projections for scrolling through slices [implemented by signals in main() after the GUI is instantiated]
        self.axes2D[0].linkedXprojection = self.axes2D[2]
        self.axes2D[0].linkedYprojection = self.axes2D[1]

        self.axes2D[2].linkedXprojection = self.axes2D[0]
        self.axes2D[2].linkedYprojection = self.axes2D[1]

        self.axes2D[1].linkedXprojection = self.axes2D[2]
        self.axes2D[1].linkedYprojection = self.axes2D[0]

        # UI elements updated during mouse moves over an axis
        self.crossHairVLine = None
        self.crossHairHLine = None
        self.showCrossHairs = preferences.readPreference('showCrossHairs')
        self.mouseX = None
        self.mouseY = None
        self.inAxis = 0  # The axis the mouse is currently in [see mouseMoved()]
        self.mousePositionInStack = []  # A list defining voxel (Z,X,Y) in which the mouse cursor is currently positioned [see mouseMoved()]
        self.statusBarText = None

        # Ensure that the menu on OS X appears the same as in Linux and Windows
        self.menuBar.setNativeMenuBar(False)

        # Lists of functions that are used as hooks for plugins to modify the behavior of built-in methods.
        # Hooks are named using the following convention: <lasagnaMethodName_[Start|End]>
        # So:
        # 1. It's obvious which method will call a given hook list.
        # 2. _Start indicates the hook will run at the top of the method, potentially modifying all
        #    subsequent behavior of the method.
        # 3. _End indicates that the hook will run at the end of the method, appending its functionality
        #    to whatever the method normally does.
        self.hooks = {  # FIXME: use default dict
            'updateStatusBar_End'           :   [],
            'loadImageStack_Start'          :   [],
            'loadImageStack_End'            :   [],
            'showStackLoadDialog_Start'     :   [],
            'showStackLoadDialog_End'       :   [],
            'removeCrossHairs_Start'        :   [],
            'showFileLoadDialog_Start'      :   [],
            'showFileLoadDialog_End'        :   [],
            'loadRecentFileSlot_Start'      :   [],
            'updateMainWindowOnMouseMove_Start': [],
            'updateMainWindowOnMouseMove_End': [],
            'changeImageStackColorMap_Slot_End': [],
            'deleteLayerStack_Slot_End'     :   [],
            'axisClicked'                   :   [],
        }

        # Handle IO plugins. For instance these are the loaders that handle different data types
        # and different loading actions.
        lasagna_path = os.path.dirname(os.path.realpath(sys.argv[0]))
        built_in_io_path = os.path.join(lasagna_path, 'io_libs')
        io_paths = preferences.readPreference('IO_modulePaths')  # directories containing IO modules
        io_paths.append(built_in_io_path)
        io_paths = list(set(io_paths))  # remove duplicate paths

        print("Adding IO module paths to Python path")
        io_plugins, _ = plugin_handler.find_plugins(io_paths)
        for p in io_paths:
            sys.path.append(p)  # append to system path
            print(p)

        # Add *load actions* to the Load ingredients sub-menu and add loader modules here
        # TODO: currently we only have code to handle load actions as no save actions are available
        self.loadActions = {}  # actions must be attached to the lasagna object or they won't function
        for io_module in io_plugins:
            io_class, io_name = plugin_handler.get_plugin_instance_from_file_name(io_module,
                                                                                  attribute_to_import='loaderClass')
            if io_class is None:
                continue
            this_instance = io_class(self)
            self.loadActions[this_instance.objectName] = this_instance
            print(("Added %s to load menu as object name %s" % (io_module, this_instance.objectName)))
        print("")

        # Link other menu signals to slots
        self.actionOpen.triggered.connect(self.showStackLoadDialog)
        self.actionQuit.triggered.connect(self.quitLasagna)
        self.actionAbout.triggered.connect(self.about_slot)

        # Link toolbar signals to slots
        self.actionResetAxes.triggered.connect(self.resetAxes)

        # Link tabbed view items to slots

        # Image tab stuff
        # ImageStack QTreeView (see lasagna_ingredient.addToList for where the model is updated on ingredient addition)
        self.logYcheckBox.clicked.connect(self.plotImageStackHistogram)
        self.imageAlpha_horizontalSlider.valueChanged.connect(self.imageAlpha_horizontalSlider_slot)
        self.imageStackLayers_Model = QtGui.QStandardItemModel(self.imageStackLayers_TreeView)
        self.imageStackLayers_Model.setHorizontalHeaderLabels(["Name"])
        self.imageStackLayers_TreeView.setModel(self.imageStackLayers_Model)
        self.imageStackLayers_TreeView.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.imageStackLayers_TreeView.customContextMenuRequested.connect(self.layersMenuStacks)
        # self.imageStackLayers_TreeView.setColumnWidth(0,200)

        self.imageStackLayers_TreeView.selectionModel().selectionChanged[QtCore.QItemSelection, QtCore.QItemSelection].connect(self.imageStackLayers_TreeView_slot)

        # Points tab stuff. (The points tab deals with sparse data types like points, lines, and trees)
        # Points QTreeView (see lasagna_ingredient.addToList for where the model is updated upon ingredient addition)
        self.points_Model = QtGui.QStandardItemModel(self.points_TreeView)
        self.points_Model.setHorizontalHeaderLabels(["Name"])
        self.points_TreeView.setModel(self.points_Model)
        self.points_TreeView.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.points_TreeView.customContextMenuRequested.connect(self.layersMenuPoints)
        self.points_TreeView.selectionModel().selectionChanged[QtCore.QItemSelection, QtCore.QItemSelection].connect(self.pointsLayers_TreeView_slot)

        # Settings boxes, etc, for the points (sparse data) ingredients
        [self.markerSymbol_comboBox.addItem(pointType) for pointType in preferences.readPreference('symbolOrder')]  # populate with markers
        self.markerSymbol_comboBox.activated.connect(self.markerSymbol_comboBox_slot)
        self.markerSize_spinBox.valueChanged.connect(self.markerSize_spinBox_slot)
        self.markerAlpha_spinBox.valueChanged.connect(self.markerAlpha_spinBox_slot)
        self.markerAlpha_spinBox.valueChanged.connect(self.markerAlpha_spinBox_slot)
        self.markerColor_pushButton.released.connect(self.markerColor_pushButton_slot)
        self.lineWidth_spinBox.valueChanged.connect(self.lineWidth_spinBox_slot)

        # add the z-points spinboxes to a list to make them indexable
        self.viewZ_spinBoxes = [self.view1Z_spinBox, self.view2Z_spinBox, self.view3Z_spinBox]

        # create a slot to force a re-draw of the screen when the spinbox value changes
        self.view1Z_spinBox.valueChanged.connect(self.viewZ_spinBoxes_slot)
        self.view2Z_spinBox.valueChanged.connect(self.viewZ_spinBoxes_slot)
        self.view3Z_spinBox.valueChanged.connect(self.viewZ_spinBoxes_slot)

        # Axis tab stuff
        # TODO: set up as one slot that receives an argument telling it which axis ratio was changed
        self.axisRatioLineEdit_1.textChanged.connect(self.axisRatio1Slot)
        self.axisRatioLineEdit_2.textChanged.connect(self.axisRatio2Slot)
        self.axisRatioLineEdit_3.textChanged.connect(self.axisRatio3Slot)

        # Flip axis
        self.pushButton_FlipView1.released.connect(lambda: self.flipAxis_Slot(0))
        self.pushButton_FlipView2.released.connect(lambda: self.flipAxis_Slot(1))
        self.pushButton_FlipView3.released.connect(lambda: self.flipAxis_Slot(2))

        # Plugins menu and initialisation
        # 1. Get a list of all plugins in the plugins path and add their directories to the Python path
        plugin_paths = preferences.readPreference('pluginPaths')

        plugins, plugin_paths = plugin_handler.find_plugins(plugin_paths)
        print("Adding plugin paths to Python path:")
        self.pluginSubMenus = {}
        for p in plugin_paths:  # print plugin paths to screen, add to path, add as sub-dir names in Plugins menu
            print(p)
            sys.path.append(p)
            dir_name = p.split(os.path.sep)[-1]
            self.pluginSubMenus[dir_name] = QtGui.QMenu(self.menuPlugins)
            self.pluginSubMenus[dir_name].setObjectName(dir_name)
            self.pluginSubMenus[dir_name].setTitle(dir_name)
            self.menuPlugins.addAction(self.pluginSubMenus[dir_name].menuAction())

        # 2. Add each plugin to a dictionary where the keys are plugin name and values are instances of the plugin.
        print("")
        self.plugins = {}  # A dictionary where keys are plugin names and values are plugin classes or plugin instances
        self.pluginActions = {}  # A dictionary where keys are plugin names and values are QActions associated with a plugin
        for plugin in plugins:
            # Get the module name and class
            plugin_class, plugin_name = plugin_handler.get_plugin_instance_from_file_name(plugin, None)
            if plugin_class is None:
                continue

            # Get the name of the directory in which the plugin resides so we can add it to the right sub-menu
            dir_name = os.path.dirname(plugin_class.__file__).split(os.path.sep)[-1]

            # create instance of the plugin object and add to the self.plugins dictionary
            print(("Creating reference to class " + plugin_name + ".plugin"))
            self.plugins[plugin_name] = plugin_class.plugin

            # create an action associated with the plugin and add to the self.pluginActions dictionary
            print(("Creating menu QAction for " + plugin_name))
            self.pluginActions[plugin_name] = QtGui.QAction(plugin_name, self)
            self.pluginActions[plugin_name].setObjectName(plugin_name)
            self.pluginActions[plugin_name].setCheckable(True)  # so we have a checkbox next to the menu entry

            self.pluginSubMenus[dir_name].addAction(self.pluginActions[plugin_name])  # add action to the correct plugins sub-menu
            self.pluginActions[plugin_name].triggered.connect(self.startStopPlugin)  # Connect this action's signal to the slot
        print("")

        self.statusBar.showMessage("Initialised")

    # -  -  -  -  -  -  -  -  -  -  -  -  -  -  -  -  -  -
    def about_slot(self):
        """
        A simple about box
        """
        msg = "Lasagna - Rob Campbell<br>Basel - 2015"
        reply = QtGui.QMessageBox.question(self, 'Message', msg)

    # - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
    # Plugin-related methods
    def startStopPlugin(self):
        plugin_name = str(self.sender().objectName())  # Get the name of the action that sent this signal

        if self.pluginActions[plugin_name].isChecked():
           self.startPlugin(plugin_name)
        else:
            self.stopPlugin(plugin_name)

    def startPlugin(self, pluginName):
        print(("Starting " + pluginName))
        self.plugins[pluginName] = self.plugins[pluginName](self)  # Create an instance of the plugin object

    def stopPlugin(self, pluginName):
        print(("Stopping " + pluginName))
        try:
            self.plugins[pluginName].closePlugin()  # tidy up the plugin
        except Exception as err:  # FIXME: too broad exception
            print("failed to properly close plugin {}; main error: {}".format(pluginName, err))

        # delete the plugin instance and replace it in the dictionary with a reference (that what it is?) to the class
        # NOTE: plugins with a window do not run the following code when the window is closed. They should, however,
        # detach hooks (unless the plugin author forgot to do this)
        del(self.plugins[pluginName])
        plugin_class, pluginName = plugin_handler.get_plugin_instance_from_file_name(pluginName + ".py", None)
        if plugin_class is None:
            return
        self.plugins[pluginName] = plugin_class.plugin

    def runHook(self, hookArray, *args):
        """
        loops through list of functions and runs them
        """
        if len(hookArray) == 0:
            return

        for hook in hookArray:
            try:
                if hook is None:
                    print("Skipping empty hook in hook list")
                    continue
                else:
                    hook(*args)
            except Exception as err:
                print("Error running plugin method {}; main error {}".format(hook, err))
                raise

    # - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
    # File menu and methods associated with loading the base image stack.
    def loadImageStack(self, fnameToLoad):
        """
        Loads an image image stack.
        """
        self.runHook(self.hooks['loadImageStack_Start'])

        if not os.path.isfile(fnameToLoad):
            msg = 'Unable to find ' + fnameToLoad
            print(msg)
            self.statusBar.showMessage(msg)
            return False

        print(("Loading image stack " + fnameToLoad))

        # TODO: The axis swap likely shouldn't be hard-coded here
        loaded_image_stack = image_stack_loader.load_stack(fnameToLoad)

        if len(loaded_image_stack) == 0 and not loaded_image_stack:
            return False

        # Set up default values in tabs
        # It's ok to load images of different sizes but their voxel sizes need to be the same
        ax_ratio = image_stack_loader.get_voxel_spacing(fnameToLoad)
        for i in range(len(ax_ratio)):
            self.axisRatioLineEdits[i].setText(str(ax_ratio[i]))

        # Add to the ingredients list
        obj_name = fnameToLoad.split(os.path.sep)[-1]
        self.addIngredient(objectName=obj_name,
                           kind='imagestack',
                           data=loaded_image_stack,
                           fname=fnameToLoad)

        self.returnIngredientByName(obj_name).addToPlots()  # Add item to all three 2D plots

        # If only one stack is present, we will display it as gray (see imagestack class)
        # if more than one stack has been added, we will colour successive stacks according
        # to the colorOrder preference in the parameter file
        stacks = self.stacksInTreeList()
        color_order = preferences.readPreference('colorOrder')

        if len(stacks) == 2:
            self.returnIngredientByName(stacks[0]).lut = color_order[0]
            self.returnIngredientByName(stacks[1]).lut = color_order[1]
        elif len(stacks) > 2:
            self.returnIngredientByName(stacks[len(stacks)-1]).lut = color_order[len(stacks)-1]

        # remove any existing range highlighter on the histogram. We do this because different images
        # will likely have different default ranges
        if hasattr(self, 'plottedIntensityRegionObj'):
            del self.plottedIntensityRegionObj

        self.runHook(self.hooks['loadImageStack_End'])

    def showStackLoadDialog(self, triggered=None, fileFilter=image_stack_loader.image_filter()):
        """
        This slot brings up the file load dialog and gets the file name.
        If the file name is valid, it loads the base stack using the loadImageStack method.
        We split things up so that the base stack can be loaded from the command line,
        or from a plugin without going via the load dialog.

        triggered - just catches the input from the signal so we can set fileFilter
        """

        self.runHook(self.hooks['showStackLoadDialog_Start'])

        fname = self.showFileLoadDialog(fileFilter=fileFilter)  # TODO: this way the recently loaded files are updated before we succesfully loaded
        if fname is None:
            return

        if os.path.isfile(fname):
            self.loadImageStack(str(fname))
            self.initialiseAxes()
        else:
            self.statusBar.showMessage("Unable to find " + str(fname))

        self.runHook(self.hooks['showStackLoadDialog_End'])

    # -  -  -  -  -  -  -  -  -  -  -  -  -  -  -  -  -  -  -  -  -
    # Code to handle generic file loading, dialogs, etc
    def showFileLoadDialog(self, fileFilter="All files (*)"):
        """
        Bring up the file load dialog. Return the file name. Update the last used path.
        """
        self.runHook(self.hooks['showFileLoadDialog_Start'])
        fname = QtGui.QFileDialog.getOpenFileName(self, 'Open file',
                                                  preferences.readPreference('lastLoadDir'),
                                                  fileFilter)[0]
        fname = str(fname)
        if len(fname) == 0:
            return None

        # Update last loaded directory
        preferences.preferenceWriter('lastLoadDir', path_utils.stripTrailingFileFromPath(fname))

        # Keep a track of the last loaded files
        recently_loaded = preferences.readPreference('recentlyLoadedFiles')
        n = preferences.readPreference('numRecentFiles')

        # Add to start of list
        recently_loaded.reverse()
        recently_loaded.append(fname)
        recently_loaded.reverse()

        while len(recently_loaded) > n:
            recently_loaded.pop(-1)

        # TODO: list will no longer have the most recent item first
        recently_loaded = list(set(recently_loaded))  # get remove repeats (i.e. keep only unique values)

        preferences.preferenceWriter('recentlyLoadedFiles', recently_loaded)
        self.updateRecentlyOpenedFiles()

        self.runHook(self.hooks['showFileLoadDialog_End'])

        return fname

    def updateRecentlyOpenedFiles(self):
        """
        Updates the list of recently opened files
        """
        recently_loaded_files = preferences.readPreference('recentlyLoadedFiles')

        # Remove existing actions if present
        if len(self.recentLoadActions) > 0 and len(recently_loaded_files) > 0:
            for thisAction in self.recentLoadActions:
                self.menuOpen_recent.removeAction(thisAction)
            self.recentLoadActions = []

        for thisFile in recently_loaded_files:
            self.recentLoadActions.append(self.menuOpen_recent.addAction(thisFile))  # add action to list
            self.recentLoadActions[-1].triggered.connect(self.loadRecentFileSlot)  # link it to a slot
            # NOTE: tried the lambda approach but it always assigns the last file name to the list to all signals
            #      http://stackoverflow.com/questions/940555/pyqt-sending-parameter-to-slot-when-connecting-to-a-signal

    def loadRecentFileSlot(self):
        """
        load a file from recently opened list
        """
        self.runHook(self.hooks['loadRecentFileSlot_Start'])
        fname = str(self.sender().text())
        self.loadImageStack(fname)
        self.initialiseAxes()

    def quitLasagna(self):
        """
        Neatly shut down the GUI
        """
        # Loop through and shut plugins.
        for thisPlugin in list(self.pluginActions.keys()):
            if self.pluginActions[thisPlugin].isChecked():
                if not self.plugins[thisPlugin].confirmOnClose:  # TODO: handle cases where plugins want confirmation to close
                    self.stopPlugin(thisPlugin)

        qApp.quit()
        sys.exit(0)  # without this we get a big horrible error report on the Mac

    def closeEvent(self, event):
        self.quitLasagna()

    # ------------------------------------------------------------------------
    # Ingredient handling methods
    def addIngredient(self, kind='', objectName='', data=None, fname=''):
        """
        Adds an ingredient to the list of ingredients.
        Scans the list of ingredients to see if an ingredient is already present.
        If so, it removes it before adding a new one with the same name.
        ingredients are classes that are defined in the ingredients package
        """

        print(("\nlasanga.addIngredient - Adding %s ingredient: %s" % (kind, objectName)))

        if not kind:
            print("ERROR: no ingredient kind {} is defined by Lasagna".format(kind))
            return

        # Do not attempt to add an ingredient if it's class is not defined
        if not hasattr(ingredients, kind):
            print("ERROR: ingredients module has no class '{}'".format(kind))
            return

        # If an ingredient with this object name is already present we delete it
        self.removeIngredientByName(objectName)

        # Get ingredient of this class from the ingredients package
        ingredient_class_obj = getattr(getattr(ingredients, kind), kind)  # make an ingredient of type "kind"
        self.ingredientList.append(ingredient_class_obj(
                            parent=self,
                            fnameAbsPath=fname,
                            data=data,
                            objectName=objectName
                            )
                        )

    def removeIngredient(self, ingredientInstance):
        """
        Removes the ingredient "ingredientInstance" from self.ingredientList
        This method is called by the two following methods that remove based on
        ingredient name or type
        """
        ingredientInstance.removePlotItem()  # remove from axes
        self.ingredientList.remove(ingredientInstance)  # Remove ingredient from the list of ingredients
        ingredientInstance.removeFromList()  # remove ingredient from the list with which it is associated
        self.selectedStackName()  # Ensures something is highlighted

        # TODO: The following two lines fail to clear the image data from RAM. Somehow there are other references to the object...
        ingredientInstance._data = None
        del(ingredientInstance)

        self.initialiseAxes()

    def removeIngredientByName(self, objectName):
        """
        Finds ingredient by name and removes it from the list
        """

        verbose = False
        if not self.ingredientList:
            if verbose:
                print("lasagna.removeIngredientByType finds no ingredients in list!")
            return

        removed_ingredient = False
        for thisIngredient in self.ingredientList[:]:
            if thisIngredient.objectName == objectName:
                if verbose:
                    print(('Removing ingredient ' + objectName))
                self.removeIngredient(thisIngredient)
                self.selectedStackName()  # Ensures something is highlighted
                removed_ingredient = True

        if not removed_ingredient and verbose:
            print(("** Failed to remove ingredient %s **" % objectName))
            return False
        return True

    def removeIngredientByType(self, ingredientType):
        """
        Finds ingredients of one type (e.g. all imagestacks) and removes them all
        """
        verbose = False
        if not self.ingredientList:
            if verbose:
                print("removeIngredientByType finds no ingredients in list!")
            return

        for thisIngredient in self.ingredientList[:]:
            if thisIngredient.__module__.endswith(ingredientType):  # TODO: fix this so we look for it by instance not name
                if verbose:
                    print(('Removing ingredient ' + thisIngredient.objectName))
                self.selectedStackName() # Ensures something is highlighted
                self.removeIngredient(thisIngredient)

    def listIngredients(self):
        """
        Return a list of ingredient objectNames
        """
        ingredient_names = []
        for thisIngredient in self.ingredientList:
            ingredient_names.append(thisIngredient.objectName)

        return ingredient_names

    def returnIngredientByType(self, ingredientType):
        """
        Return a list of ingredients based upon their type. e.g. imagestack, sparsepoints, etc
        """
        verbose = False
        if not self.ingredientList:
            if verbose:
                print("returnIngredientByType finds no ingredients in list!")
            return False

        returned_ingredients = []
        for thisIngredient in self.ingredientList:
            if thisIngredient.__module__.endswith(ingredientType):  # TODO: fix this so we look for it by instance not name
                returned_ingredients.append(thisIngredient)

        if verbose and not returned_ingredients:
            print(("returnIngredientByType finds no ingredients with type " + ingredientType))
            return False
        else:
            return returned_ingredients

    def returnIngredientByName(self, objectName):
        """
        Return a specific ingredient object based upon its object name.
        Returns False if the ingredient was not found
        """
        verbose = False
        if not self.ingredientList:
            if verbose:
                print("returnIngredientByName finds no ingredients in list!")
            return False

        for ingredient in self.ingredientList:
            if ingredient.objectName == objectName:
                return ingredient

        if verbose:
            print(("returnIngredientByName finds no ingredient called " + objectName))
        return False

    # -  -  -  -  -  -  -  -  -  -  -  -  -  -  -  -  -  -  -  -  -
    # Functions involved in the display of plots on the screen
    def resetAxes(self):
        """
        Set X and Y limit of each axes to fit the data
        """
        if not self.stacksInTreeList():
            return
        [axis.resetAxes() for axis in self.axes2D]

    def initialiseAxes(self, resetAxes=False):
        """
        Initial display of images in axes and also update other parts of the GUI.
        """
        if not self.stacksInTreeList():
            self.plotImageStackHistogram()  # wipes the histogram
            return

        # show default images (snap to middle layer of each axis)
        [axis.updatePlotItems_2D(self.ingredientList, sliceToPlot=axis.currentSlice, resetToMiddleLayer=resetAxes) for axis in self.axes2D]

        # initialize cross hair
        if self.showCrossHairs:
            if self.crossHairVLine is None:
                self.crossHairVLine = pg.InfiniteLine(pen=(220, 200, 0, 180), angle=90, movable=False)
                self.crossHairVLine.objectName = 'crossHairVLine'
            if self.crossHairHLine is None:
                self.crossHairHLine = pg.InfiniteLine(pen=(220, 200, 0, 180), angle=0, movable=False)
                self.crossHairHLine.objectName = 'crossHairHLine'

        self.plotImageStackHistogram()

        for i in range(len(self.axisRatioLineEdits)):
            self.axes2D[i].view.setAspectLocked(True, float(self.axisRatioLineEdits[i].text()))

        if resetAxes:
            self.resetAxes()

    # - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
    # Slots for image stack tab
    # In each case, we set the values of the currently selected ingredient using the spinbox value
    # TODO: this is an example of code that is not flexible. These UI elements should be created by the ingredient
    def imageAlpha_horizontalSlider_slot(self,value):
        """
        Get the value of the slider and assign it to the currently selected imagestack ingredient.
        This is read back, and the slider assigned to the currently selected imagestack value in
        the slot: imageStackLayers_TreeView_slot
        """
        ingredient = self.selectedStackName()
        if not ingredient:
            return
        self.returnIngredientByName(ingredient).alpha = int(value)
        self.initialiseAxes()

    # - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
    # Slots for points tab
    # In each case, we set the values of the currently selected ingredient using the spinbox value
    # TODO: this is an example of code that is not flexible. These UI elements should be created by the ingredient
    def viewZ_spinBoxes_slot(self):
        self.initialiseAxes()

    def markerSymbol_comboBox_slot(self, index):
        symbol = str(self.markerSymbol_comboBox.currentText())
        ingredient = self.returnIngredientByName(self.selectedPointsName())
        if not ingredient:
            return
        ingredient.symbol = symbol
        self.initialiseAxes()

    def markerSize_spinBox_slot(self, spinBoxValue):
        ingredient = self.returnIngredientByName(self.selectedPointsName())
        if not ingredient:
            return
        ingredient.symbolSize = spinBoxValue
        self.initialiseAxes()

    def markerAlpha_spinBox_slot(self, spinBoxValue):
        ingredient = self.returnIngredientByName(self.selectedPointsName())
        if not ingredient:
            return
        ingredient.alpha = spinBoxValue
        self.initialiseAxes()

    def lineWidth_spinBox_slot(self, spinBoxValue):
        ingredient = self.returnIngredientByName(self.selectedPointsName())
        if not ingredient:
            return
        ingredient.lineWidth = spinBoxValue
        self.initialiseAxes()

    def markerColor_pushButton_slot(self):
        ingredient = self.returnIngredientByName(self.selectedPointsName())
        if not ingredient:
            return

        col = QtGui.QColorDialog.getColor()
        rgb = [col.toRgb().red(), col.toRgb().green(), col.toRgb().blue()]
        ingredient.color = rgb
        self.initialiseAxes()

    def selectedPointsName(self):
        """
        Return the name of the selected points ingredient. If none are selected, returns the first in the list
        """
        if self.points_Model.rowCount() == 0:
            print("lasagna.selectedPointsName finds no image stacks in list")
            return False

        # Highlight the first row if nothing is selected (which shouldn't ever happen)
        if not self.points_TreeView.selectedIndexes():
            first_item = self.points_Model.index(0, 0)
            self.points_TreeView.setCurrentIndex(first_item)
            print("lasagna.selectedStackName forced highlighting of first image stack")

        return self.points_TreeView.selectedIndexes()[0].data()

    # The remaining methods for this tab are involved in building a context menu on right-click
    def layersMenuPoints(self, position):
        """
        Defines a pop-up menu that appears when the user right-clicks on a points ingredient
        in the points QTreeView
        """
        menu = QtGui.QMenu()

        action = QtGui.QAction("Delete", self)
        action.triggered.connect(self.deleteLayerPoints_Slot)
        menu.addAction(action)
        action = QtGui.QAction("Save", self)
        action.triggered.connect(self.saveLayerPoints_Slot)
        menu.addAction(action)
        menu.exec_(self.points_TreeView.viewport().mapToGlobal(position))

    def saveLayerPoints_Slot(self):
        """call ingredient save method if any"""
        obj_name = self.selectedPointsName()
        ingredient = self.returnIngredientByName(obj_name)
        if hasattr(ingredient, 'save'):
            ingredient.save()
        else:
            print('no save method for "{}"'.format(obj_name))

    def deleteLayerPoints_Slot(self):
        """
        Remove a points ingredient and list item
        """
        obj_name = self.selectedPointsName()
        self.removeIngredientByName(obj_name)
        print(("removed " + obj_name))

    def pointsLayers_TreeView_slot(self):
        """
        Runs when the user selects one of the points ingredients in the list.
        """
        if not self.ingredientList:
            return

        name = self.selectedPointsName()
        ingredient = self.returnIngredientByName(name)
        if not ingredient:
            return

        # Assign GUI values based on what is stored in the ingredient
        if isinstance(ingredient.symbolSize, int):
            self.markerSize_spinBox.setValue(ingredient.symbolSize)
        if isinstance(ingredient.alpha, int):
            self.markerAlpha_spinBox.setValue(ingredient.alpha)
        if isinstance(ingredient.lineWidth, int):
            self.lineWidth_spinBox.setValue(ingredient.lineWidth)

    # - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
    # Slots for axis tab
    # TODO: incorporate these three slots into one
    def axisRatio1Slot(self):
        """
        Set axis ratio on plot 1
        """
        self.axes2D[0].view.setAspectLocked(True, float(self.axisRatioLineEdit_1.text()))

    def axisRatio2Slot(self):
        """
        Set axis ratio on plot 2
        """
        self.axes2D[1].view.setAspectLocked(True, float(self.axisRatioLineEdit_2.text()))

    def axisRatio3Slot(self):
        """
        Set axis ratio on plot 3
        """
        self.axes2D[2].view.setAspectLocked(True, float(self.axisRatioLineEdit_3.text()))

    def flipAxis_Slot(self, axisToFlip):
        """
        Loops through all displayed image stacks and flips the axes
        """
        image_stacks = self.returnIngredientByType('imagestack')
        if not image_stacks:
            return

        for thisStack in image_stacks:
            thisStack.flipAlongAxis(axisToFlip)

        self.initialiseAxes()

    # - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
    # Methods that are run during navigation
    def removeCrossHairs(self):
        """
        Remove the cross hairs from all plots
        """
        # NOTE: I'm a little unhappy about this as I don't understand what's going on.
        # I've noticed that removing the cross hairs from any one plot is sufficient to remove
        # them from the other two. However, if all three axes are not explicitly removed I've
        # seen peculiar behavior with plugins that query the PlotWidgets. RAAC 21/07/2015

        self.runHook(self.hooks['removeCrossHairs_Start'])  # This will be run each time a plot is updated

        if not self.showCrossHairs:
            return

        [axis.removeItemFromPlotWidget(self.crossHairVLine) for axis in self.axes2D]
        [axis.removeItemFromPlotWidget(self.crossHairHLine) for axis in self.axes2D]

    def updateCrossHairs(self, highlightCrossHairs=False):
        """
        Update the drawn cross hairs on the current image.
        Highlight cross hairs in red if caller says so
        """
        if not self.showCrossHairs:
            return

        # make cross hairs red if control key is pressed
        if QtGui.QApplication.keyboardModifiers() == QtCore.Qt.ControlModifier and highlightCrossHairs:
            self.crossHairVLine.setPen(240, 0, 0, 200)
            self.crossHairHLine.setPen(240, 0, 0, 200)
        else:
            self.crossHairVLine.setPen(220, 200, 0, 180)
            self.crossHairHLine.setPen(220, 200, 0, 180)

        self.crossHairVLine.setPos(self.mouseX+0.5)  # Add 0.5 to add line to middle of pixel
        self.crossHairHLine.setPos(self.mouseY+0.5)

    def updateStatusBar(self):
        """
        Update the text on the status bar based on the current mouse position
        """

        x = self.mouseX
        y = self.mouseY

        # get pixels under image
        image_items = self.axes2D[self.inAxis].getPlotItemByType('ImageItem')
        pixel_values = []

        # Get the pixel intensity of all displayed image layers under the mouse
        # The following assumes that images have their origin at (0,0)
        for thisImageItem in image_items:
            im_shape = thisImageItem.image.shape

            if x < 0 or y < 0:
                pixel_values.append(0)
            elif x >= im_shape[0] or y >= im_shape[1]:
                pixel_values.append(0)
            else:
                pixel_values.append(thisImageItem.image[x, y])

        # Build a text string to house these values
        value_str = ''
        while pixel_values:
            value_str += '%d,' % pixel_values.pop()

        value_str = value_str[:-1]  # Chop off the last character

        self.statusBarText = "X=%d, Y=%d, val=[%s]" % (x, y, value_str)

        self.runHook(self.hooks['updateStatusBar_End'])  # Hook goes here to modify or append message

        self.statusBar.showMessage(self.statusBarText)

    def axisClicked(self, event):
        axis_id = self.sender().axisID
        self.runHook(self.hooks['axisClicked'], self.axes2D[axis_id])

    def updateMainWindowOnMouseMove(self, axis):
        """
        Update UI elements on the screen (but not the plotted images) as the user moves the mouse across an axis
        """
        self.runHook(self.hooks['updateMainWindowOnMouseMove_Start'])  # Runs each time the views are updated

        self.updateCrossHairs(axis.view.getViewBox().controlDrag)  # highlight cross hairs is axis says to do so
        self.updateStatusBar()

        self.runHook(self.hooks['updateMainWindowOnMouseMove_End'])  # Runs each time the views are updated

    # - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
    # Image Tab methods and slots
    # These methods are involved with the tabs to the left of the three view axes

    def plotImageStackHistogram(self):
        """
        Plot the image stack histogram in a PlotWidget to the left of the three image views.
        This function is called when the plot is first set up and also when the log Y
        checkbox is checked or unchecked

        also see: self.initialiseAxes
        """
        ingredient = self.returnIngredientByName(self.selectedStackName())
        if not ingredient:  # TODO: when the last image stack is deleted there is an error that is caught by this if statement a more elegant solution would be nice
            self.intensityHistogram.clear()
            return

        x = ingredient.histogram['x']
        y = ingredient.histogram['y']

        # Plot the histogram
        if self.logYcheckBox.isChecked():
            y = np.log10(y+0.1)
            y[y < 0] = 0

        self.intensityHistogram.clear()
        ingredient = self.returnIngredientByName(self.selectedStackName())  # Get colour of the layer

        brush_color = ingredient.histBrushColor()
        pen_color = ingredient.histPenColor()

        # Using stepMode=True causes the plot to draw two lines for each sample but it needs X to be longer than Y by 1
        self.intensityHistogram.plot(x, y, stepMode=False, fillLevel=0, pen=pen_color, brush=brush_color, yMin=0, xMin=0)
        self.intensityHistogram.showGrid(x=True, y=True, alpha=0.33)

        # The object that represents the plotted intensity range is only set up the first time the
        # plot is made or following a new base image being loaded (any existing plottedIntensityRegionObj
        # is deleted at base image load time.)
        if not hasattr(self, 'plottedIntensityRegionObj'):
            self.plottedIntensityRegionObj = pg.LinearRegionItem()
            self.plottedIntensityRegionObj.setZValue(10)
            self.plottedIntensityRegionObj.sigRegionChanged.connect(self.updateAxisLevels)  # link signal slot

        # Get the plotted range and apply to the region object
        min_max = self.returnIngredientByName(self.selectedStackName()).minMax
        self.setIntensityRange(min_max)

        # Add to the ViewBox but exclude it from auto-range calculations.
        self.intensityHistogram.addItem(self.plottedIntensityRegionObj, ignoreBounds=True)

    def setIntensityRange(self, intRange=(0, 2**12)):
        """
        Set the intensity range of the images and update the axis labels.
        This is really just a convenience function with an easy to remember name.
        intRange is a tuple that is (minX,maxX)
        """
        self.plottedIntensityRegionObj.setRegion(intRange)
        self.updateAxisLevels()

    # -  -  -  -  -
    # The following methods and slots coordinate updating of the GUI
    # as imagestack ingredients are added or removed. These methods also
    # handle modifying the stack ingredients.
    """
    TODO: ingredients can only be handled if they are in the ingredients module
    ingredients defined in plugin directories, etc, can not be handled by this
    module. This potentially makes plugin creation awkward as it couples it too
    strongly to the core code (new ingredients must be added to the ingredients
    module). This may turn out to not be a problem in practice, so we leave
    things for now and play it by ear.
    """
    def layersMenuStacks(self, position):
        """
        Defines a pop-up menu that appears when the user right-clicks on an
        imagestack-related item in the image stack layers QTreeView
        """
        menu = QtGui.QMenu()

        change_color_menu = QtGui.QMenu("Change color", self)

        # action.triggered.connect(self.changeImageStackColorMap_Slot)

        for thisColor in preferences.readPreference('colorOrder'):
            action = QtGui.QAction(thisColor, self)
            # action.triggered.connect(lambda: self.changeImageStackColorMap_Slot(thisColor))
            action.triggered.connect(self.changeImageStackColorMap_Slot)
            change_color_menu.addAction(action)

        menu.addAction(change_color_menu.menuAction())

        action = QtGui.QAction("Delete", self)
        action.triggered.connect(self.deleteLayerStack_Slot)
        menu.addAction(action)
        action = QtGui.QAction("Save", self)
        action.triggered.connect(self.saveLayerStack_Slot)
        menu.addAction(action)
        menu.exec_(self.imageStackLayers_TreeView.viewport().mapToGlobal(position))


    def changeImageStackColorMap_Slot(self):
        """
        Change the color map of an image stack using methods in the imagestack ingredient
        """
        color = str(self.sender().text())
        obj_name = self.selectedStackName()
        self.returnIngredientByName(obj_name).lut = color
        self.initialiseAxes()
        self.runHook(self.hooks['changeImageStackColorMap_Slot_End'])


    def deleteLayerStack_Slot(self):
        """
        Remove an imagestack ingredient and list item
        """
        obj_name = self.selectedStackName()
        self.removeIngredientByName(obj_name)
        print(("removed " + obj_name))
        self.runHook(self.hooks['deleteLayerStack_Slot_End'])

    def saveLayerStack_Slot(self):
        """call stack save method"""
        obj_name = self.selectedStackName()
        ingredient = self.returnIngredientByName(obj_name)
        if hasattr(ingredient, 'save'):
            ingredient.save()
        else:
            print('no save method for {}'.format(obj_name))

    def stacksInTreeList(self):
        """
        Goes through the list of image stack layers in the QTreeView list
        and pull out the names.
        """
        stacks = []
        for i in range(self.imageStackLayers_Model.rowCount()):
            stack_name = self.imageStackLayers_Model.index(i, 0).data()
            stacks.append(stack_name)

        if stacks:
            return stacks
        else:
            return False

    def selectedStackName(self):
        """
        Return the name of the selected image stack. If no stack selected, returns the first stack in the list.
        """
        if self.imageStackLayers_Model.rowCount() == 0:
            print("lasagna.selectedStackName finds no image stacks in list")
            return False

        # Highlight the first row if nothing is selected (which shouldn't ever happen)
        if not self.imageStackLayers_TreeView.selectedIndexes():
            first_item = self.imageStackLayers_Model.index(0, 0)
            self.imageStackLayers_TreeView.setCurrentIndex(first_item)
            print("lasagna.selectedStackName forced highlighting of first image stack")

        return self.imageStackLayers_TreeView.selectedIndexes()[0].data()

    def imageStackLayers_TreeView_slot(self):
        """
        Runs when the user selects one of the stacks on the list
        """

        if not self.ingredientList:
            return

        name = self.selectedStackName()
        ingredient = self.returnIngredientByName(name)
        if not ingredient:
            return

        self.imageAlpha_horizontalSlider.setValue(ingredient._alpha)  # see also: imageAlpha_horizontalSlider_slot

        self.plotImageStackHistogram()

    # - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
    # Slots relating to updating of the axes, etc
    def updateAxisLevels(self):
        # TODO: Decide what to do with minMax. Setting it here by directly manipulating the item seems wrong
        min_x, max_x = self.plottedIntensityRegionObj.getRegion()

        # Get all imagestacks
        all_image_stacks = self.returnIngredientByType('imagestack')
        if not all_image_stacks:
            return

        # Loop through all imagestacks and set their levels in each axis
        for img_stack in all_image_stacks:
            object_name = img_stack.objectName

            if object_name != self.selectedStackName():  # TODO: LAYERS
                continue

            for thisAxis in self.axes2D:
                img = find_pyqt_graph_object_name_in_plot_widget(thisAxis.view, object_name)
                img.setLevels([min_x, max_x])  # Sets levels immediately
                img_stack.minMax = [min_x, max_x]  # ensures levels stay set during all plot updates that follow

    def mouseMoved(self, evt):
        """
        Update the UI as the mouse interacts with one of the axes
        """
        if not self.stacksInTreeList():
            return

        axis_id = self.sender().axisID

        pos = evt[0]
        self.removeCrossHairs()
        if not(QtGui.QApplication.keyboardModifiers() == QtCore.Qt.ControlModifier):
            self.axes2D[axis_id].view.getViewBox().controlDrag = False

        if self.axes2D[axis_id].view.sceneBoundingRect().contains(pos):
            if self.showCrossHairs:
                self.axes2D[axis_id].view.addItem(self.crossHairVLine, ignoreBounds=True)
                self.axes2D[axis_id].view.addItem(self.crossHairHLine, ignoreBounds=True)

            self.mouseX, self.mouseY = self.axes2D[axis_id].getMousePositionInCurrentView(pos)
            # Record the current axis in which the mouse is in and the position of the mouse in the stack
            self.inAxis = axis_id
            voxel_position = [self.axes2D[axis_id].currentSlice, self.mouseX, self.mouseY]
            if axis_id == 1:
                voxel_position = [voxel_position[1], voxel_position[0], voxel_position[2]]
            elif axis_id == 2:
                voxel_position = [voxel_position[2], voxel_position[1], voxel_position[0]]

            self.mousePositionInStack = voxel_position

            if QtGui.QApplication.keyboardModifiers() == QtCore.Qt.ControlModifier and self.axes2D[axis_id].view.getViewBox().controlDrag:
                self.axes2D[axis_id].updateDisplayedSlices_2D(self.ingredientList, (self.mouseX, self.mouseY))
            self.updateMainWindowOnMouseMove(self.axes2D[axis_id])


