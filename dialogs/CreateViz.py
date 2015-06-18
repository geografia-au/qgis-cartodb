"""
/***************************************************************************
CartoDB Plugin
A QGIS plugin

----------------------------------------------------------------------------
begin                : 2014-09-08
copyright            : (C) 2015 by Michael Salgado, Kudos Ltda.
email                : michaelsalgado@gkudos.com, info@gkudos.com
 ***************************************************************************/

/***************************************************************************
 *                                                                         *
 *   This program is free software; you can redistribute it and/or modify  *
 *   it under the terms of the GNU General Public License as published by  *
 *   the Free Software Foundation; either version 2 of the License, or     *
 *   (at your option) any later version.                                   *
 *                                                                         *
 ***************************************************************************/
"""
from PyQt4.QtCore import Qt, QFile, QFileInfo, pyqtSlot, qDebug
from PyQt4.QtGui import QApplication, QAbstractItemView, QDialog, QListWidgetItem, QLabel, QPixmap, QPushButton, QSizePolicy
from PyQt4.QtGui import QClipboard

from qgis.core import QGis, QgsMapLayerRegistry, QgsMapLayer
from qgis.gui import QgsMessageBar

import QgisCartoDB.CartoDBPlugin
from QgisCartoDB.cartodb import CartoDBApi
from QgisCartoDB.dialogs.Basic import CartoDBPluginUserDialog
from QgisCartoDB.ui.CreateViz import Ui_CreateViz
from QgisCartoDB.widgets import CartoDBLayersListWidget, CartoDBLayerListItem

from string import Template

import os
import webbrowser


class CartoDBPluginCreateViz(CartoDBPluginUserDialog):
    def __init__(self, toolbar, parent=None):
        CartoDBPluginUserDialog.__init__(self, toolbar, parent)
        self.toolbar = toolbar

        self.ui = Ui_CreateViz()
        self.ui.setupUi(self)

        self.ui.bar = QgsMessageBar()
        self.ui.bar.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.ui.verticalLayout.insertWidget(0, self.ui.bar)

        self.ui.availableList = CartoDBLayersListWidget(self, 'availableList')
        self.ui.availableList.setAcceptDrops(True)
        self.ui.availableList.viewport().setAcceptDrops(True)
        self.ui.availableList.setDragEnabled(True)
        self.ui.availableList.setDropIndicatorShown(True)
        self.ui.availableList.setDragDropMode(QAbstractItemView.DragDrop)
        self.ui.availableList.setDefaultDropAction(Qt.MoveAction)
        self.ui.availableList.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.ui.availableLayout.addWidget(self.ui.availableList)

        self.ui.mapList = CartoDBLayersListWidget(self, 'mapList')
        self.ui.mapList.setAcceptDrops(True)
        self.ui.mapList.viewport().setAcceptDrops(True)
        self.ui.mapList.setDragEnabled(True)
        self.ui.mapList.setDropIndicatorShown(True)
        self.ui.mapList.setDragDropMode(QAbstractItemView.DragDrop)
        self.ui.mapList.setDefaultDropAction(Qt.MoveAction)
        self.ui.mapList.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.ui.mapLayout.addWidget(self.ui.mapList)

        self.ui.mapNameTX.textChanged.connect(self.validateButtons)
        self.ui.mapList.itemSelectionChanged.connect(self.validateButtons)
        self.ui.cancelBT.clicked.connect(self.reject)
        self.ui.saveBT.clicked.connect(self.createViz)

        layers = QgsMapLayerRegistry.instance().mapLayers()

        self.ui.availableList.clear()
        for id, ly in layers.iteritems():
            if ly.type() == QgsMapLayer.VectorLayer:
                item = QListWidgetItem(self.ui.availableList)
                widget = CartoDBLayerListItem(ly.name(), ly, self.getSize(ly), ly.dataProvider().featureCount())
                item.setSizeHint(widget.sizeHint())
                self.ui.availableList.setItemWidget(item, widget)

    def getSize(self, layer):
        filePath = layer.dataProvider().dataSourceUri()
        if filePath.find('|') != -1:
            filePath = filePath[0:filePath.find('|')]

        file = QFile(filePath)
        fileInfo = QFileInfo(file)

        dirName = fileInfo.dir().absolutePath()
        fileName = fileInfo.completeBaseName()

        size = 0
        if layer.storageType() == 'ESRI Shapefile':
            for suffix in ['.shp', '.dbf', '.prj', '.shx']:
                file = QFile(os.path.join(dirName, fileName + suffix))
                fileInfo = QFileInfo(file)
                size = size + fileInfo.size()
        elif layer.storageType() in ['GPX', 'GeoJSON', 'LIBKML']:
            size = size + fileInfo.size()

        return size

    def createViz(self):
        self.ui.bar.clearWidgets()
        self.ui.bar.pushMessage("Info", "Creating Map", level=QgsMessageBar.INFO)

        item = self.ui.mapList.item(0)
        widget = self.ui.mapList.itemWidget(item)
        layer = widget.layer

        cartoDBApi = CartoDBApi(self.currentUser, self.currentApiKey, self.currentMultiuser)
        cartoDBApi.fetchContent.connect(self.cbCreateViz)
        cartoDBApi.createVizFromTable(layer.name(), self.ui.mapNameTX.text())

    def cbCreateViz(self, data):
        self.currentViz = data

        cartoDBApi = CartoDBApi(self.currentUser, self.currentApiKey, self.currentMultiuser)
        cartoDBApi.fetchContent.connect(self.cbGetLayers)
        cartoDBApi.getLayersMap(data['map_id'])

    def cbGetLayers(self, data):
        item = self.ui.mapList.item(0)
        widget = self.ui.mapList.itemWidget(item)
        layer = widget.layer
        cartoCSS = self.convert2cartoCSS(layer)
        cartoDBApi = CartoDBApi(self.currentUser, self.currentApiKey, self.currentMultiuser)
        layer1 = data['layers'][1]
        layer1['options']['tile_style'] = cartoCSS
        cartoDBApi.fetchContent.connect(self.showMessage)
        cartoDBApi.updateLayerInMap(self.currentViz['map_id'], layer1)

        for i in range(1, self.ui.mapList.count()):
            item = self.ui.mapList.item(i)
            widget = self.ui.mapList.itemWidget(item)
            layer = widget.layer
            qDebug('Agregando: ' + layer.name())
            cartoCSS = self.convert2cartoCSS(layer)
            # cartoDBApi.fetchContent.connect(self.cbCreateViz)
            cartoDBApi.addLayerToMap(self.currentViz['map_id'], layer.name(), cartoCSS)

    def showMessage(self, data):
        url = '{}/viz/{}/public_map'.format(self.currentUserData['base_url'], self.currentViz['id'])

        def openVis():
            qDebug('URL Viz: ' + url)
            webbrowser.open(url)

        def copyURL():
            QApplication.clipboard().setText(url)

        self.ui.bar.clearWidgets()
        widget = self.ui.bar.createMessage('Map Created', '{} created'.format(self.currentViz['name']))
        button = QPushButton(widget)
        button.setText("Copy Link")
        button.pressed.connect(copyURL)
        widget.layout().addWidget(button)

        button = QPushButton(widget)
        button.setText("Open")
        button.pressed.connect(openVis)
        widget.layout().addWidget(button)
        self.ui.bar.pushWidget(widget, QgsMessageBar.INFO)

    def convert2cartoCSS(self, layer):
        renderer = layer.rendererV2()
        cartoCSS = ''
        # CSS for single symbols
        if renderer.type() == 'singleSymbol':
            symbol = renderer.symbol()
            cartoCSS = self.simplePolygon(layer, symbol, '#' + layer.name())
        # CSS for categorized symbols
        elif renderer.type() == 'categorizedSymbol':
            # qDebug('Categorized: ' + renderer.classAttribute())
            for cat in renderer.categories():
                symbol = cat.symbol()
                qDebug("%s: %s type: %s" % (str(cat.value()), cat.label(), str(cat.value().isdecimal())))
                if cat.value() is not None and cat.value() != '':
                    value = cat.value() if cat.value().isdecimal() else ('"' + cat.value() + '"')
                    cartoCSS = cartoCSS + \
                        self.simplePolygon(layer, symbol, '#' + layer.name() + '[' + renderer.classAttribute() + '=' + str(value) + ']')
                else:
                    cartoCSS = self.simplePolygon(layer, symbol, '#' + layer.name()) + cartoCSS
        # CSS for graduated symbols
        elif renderer.type() == 'graduatedSymbol':
            # qDebug('Graduated')
            def upperValue(ran):
                return ran.upperValue()

            ranges = sorted(renderer.ranges(), key=upperValue, reverse=True)
            for ran in ranges:
                symbol = ran.symbol()
                qDebug("%f - %f: %s" % (
                    ran.lowerValue(),
                    ran.upperValue(),
                    ran.label()
                ))
                cartoCSS = cartoCSS + \
                    self.simplePolygon(layer, symbol, '#' + layer.name() + '[' + renderer.classAttribute() + '<=' + str(ran.upperValue()) + ']')

        # qDebug('CartoCSS: ' + cartoCSS)
        return cartoCSS

    def simplePolygon(self, layer, symbol, styleName):
        cartoCSS = ''
        layerOpacity = str((100 - layer.layerTransparency())/100)
        if symbol.symbolLayerCount() > 0:
            lyr = symbol.symbolLayer(0)

            qDebug('Map layer type: ' + str(layer.geometryType()))
            qDebug("Symbol Type: %s" % (lyr.layerType()))
            filein = None
            if layer.geometryType() == QGis.Point:
                d = {
                    'layername': styleName,
                    'fillColor': lyr.fillColor().name(),
                    'width': lyr.size(),
                    'opacity': layerOpacity,
                    'borderColor': lyr.outlineColor().name(),
                    'borderWidth': lyr.outlineWidth()
                }
                filein = open(QgisCartoDB.CartoDBPlugin.PLUGIN_DIR + '/templates/simplepoint.less')
            elif layer.geometryType() == QGis.Line:
                d = {
                    'layername': styleName,
                    'lineColor': lyr.color().name(),
                    'lineWidth': lyr.width(),
                    'opacity': layerOpacity
                }
                filein = open(QgisCartoDB.CartoDBPlugin.PLUGIN_DIR + '/templates/simpleline.less')
            elif layer.geometryType() == QGis.Polygon:
                d = {
                    'layername': styleName,
                    'fillColor': lyr.fillColor().name(),
                    'opacity': layerOpacity,
                    'borderColor': lyr.outlineColor().name(),
                    'borderWidth': lyr.borderWidth()
                }
                filein = open(QgisCartoDB.CartoDBPlugin.PLUGIN_DIR + '/templates/simplepolygon.less')

            cartoCSS = Template(filein.read())
            cartoCSS = cartoCSS.substitute(d)
        return cartoCSS

    def validateButtons(self):
        enabled = self.ui.mapNameTX.text() != '' and self.ui.mapList.count() > 0

        self.ui.saveBT.setEnabled(enabled)
