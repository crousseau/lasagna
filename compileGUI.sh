#!/usr/bin/env bash
pyuic5 ./designerFiles/lasagna_mainWindow.ui > ./lasagna/lasagna_mainWindow.py
pyrcc5 ./designerFiles/mainWindow.qrc >  ./lasagna/mainWindow_rc.py
pyuic5 ./designerFiles/alert.ui > ./lasagna/alert_UI.py
